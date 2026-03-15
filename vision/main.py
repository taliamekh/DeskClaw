import queue
import threading
import time

import cv2
import numpy as np

from aruco_grid import COLOR_STATUS_NO, detect_grid, draw_grid_overlay, filter_detections_in_grid
from gemini_interpretation import interpret_scene
from path_planning import (
    adjust_endpoints_for_standoff,
    compute_waypoint_headings,
    plan_path_astar,
    select_target_detection,
    simplify_waypoints,
)
from yolo_detection import detect_objects

# Global variables for threading
latest_interpretation = ""
interpretation_lock = threading.Lock()
command_queue = queue.Queue()

OBSTACLE_PADDING_CM = 10.0
TARGET_STANDOFF_CM = 10.0
ROBOT_START_STANDOFF_CM = 10.0
WAYPOINT_MIN_SPACING_CM = 8.0


def default_path_state():
    return {
        "active": False,
        "target_name": "",
        "mode": "",
        "waypoints": [],
        "waypoint_headings": [],
        "status": "No cached path",
    }


def load_path_state():
    # Runtime-only cache: path exists only while this process is running.
    return default_path_state()


def command_input_worker(cmd_queue):
    """Read target-name commands from stdin without blocking the video loop."""
    while True:
        try:
            raw = input("Target object name (or 'clear path'): ").strip()
        except EOFError:
            break
        if raw:
            cmd_queue.put(raw)


def transform_points(points, homography):
    src = np.array(points, dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(src, homography)
    return transformed.reshape(-1, 2)


def detect_objects_in_grid_roi(frame, polygon):
    """Run YOLO only inside the ArUco polygon ROI and map boxes back to full-frame coords."""
    if polygon is None:
        return []

    contour = polygon.astype("int32")
    x, y, w, h = cv2.boundingRect(contour)
    if w <= 0 or h <= 0:
        return []

    roi = frame[y : y + h, x : x + w]
    if roi.size == 0:
        return []

    # Keep only pixels inside the detected field polygon so YOLO ignores outside clutter.
    local_polygon = contour - [x, y]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [local_polygon], 255)
    roi_masked = cv2.bitwise_and(roi, roi, mask=mask)

    roi_detections = detect_objects(roi_masked)

    remapped = []
    for detection in roi_detections:
        x1, y1, x2, y2 = detection["bbox"]
        remapped.append(
            {
                **detection,
                "bbox": [x1 + x, y1 + y, x2 + x, y2 + y],
            }
        )

    return remapped


def build_detection_crops(frame, detections, padding=10):
    """Create cropped images for each accepted detection."""
    h, w = frame.shape[:2]
    crops = []

    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        left = max(0, int(x1) - padding)
        top = max(0, int(y1) - padding)
        right = min(w, int(x2) + padding)
        bottom = min(h, int(y2) + padding)

        if right <= left or bottom <= top:
            continue

        crop = frame[top:bottom, left:right].copy()
        if crop.size == 0:
            continue

        crops.append(
            {
                "image": crop,
                "bbox": detection["bbox"],
                "confidence": detection["confidence"],
                "label": detection.get("label", "object"),
                "grid_position": detection.get("grid_position"),
                "position_cm": detection.get("position_cm"),
            }
        )

    return crops


def _marker_polygons_from_grid(grid_state):
    """Collect ArUco marker polygons (corner markers + robot marker) from grid state."""
    polygons = []

    for marker_data in grid_state.get("detected_corners", {}).values():
        corners = np.asarray(marker_data["corners"][0], dtype=np.float32)
        polygons.append(corners)

    robot = grid_state.get("robot")
    if robot is not None and "corners" in robot:
        polygons.append(np.asarray(robot["corners"][0], dtype=np.float32))

    return polygons


def remove_aruco_marker_detections(detections, grid_state):
    """Drop detections whose centers fall inside any detected ArUco marker polygon."""
    marker_polygons = _marker_polygons_from_grid(grid_state)
    if not marker_polygons:
        return detections

    filtered = []
    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        center = detection.get("center", (int((x1 + x2) / 2), int((y1 + y2) / 2)))
        center_pt = (float(center[0]), float(center[1]))

        is_marker = False
        for polygon in marker_polygons:
            contour = polygon.reshape((-1, 1, 2))
            if cv2.pointPolygonTest(contour, center_pt, False) >= 0:
                is_marker = True
                break

        if not is_marker:
            filtered.append(detection)

    return filtered


def bbox_iou(box_a, box_b):
    """Compute IoU between two [x1, y1, x2, y2] boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area

    if union <= 0.0:
        return 0.0
    return inter_area / union


def suppress_overlapping_detections(detections, iou_threshold=0.55):
    """Class-agnostic NMS: keep highest-confidence detection among overlapping boxes."""
    if not detections:
        return detections

    sorted_detections = sorted(detections, key=lambda d: float(d.get("confidence", 0.0)), reverse=True)
    kept = []

    for candidate in sorted_detections:
        candidate_box = candidate["bbox"]
        overlaps_existing = any(
            bbox_iou(candidate_box, existing["bbox"]) >= iou_threshold for existing in kept
        )
        if not overlaps_existing:
            kept.append(candidate)

    return kept


def get_planning_mode_and_homography(grid_state):
    if grid_state.get("world_homography_cm") is not None:
        return "cm", grid_state["world_homography_cm"]
    if grid_state.get("homography") is not None:
        return "grid", grid_state["homography"]
    return None, None


def get_planning_bounds(grid_state, coord_homography):
    polygon = grid_state.get("polygon")
    if polygon is None or coord_homography is None:
        return None

    corners = transform_points(polygon, coord_homography)
    min_x = float(np.min(corners[:, 0]))
    min_y = float(np.min(corners[:, 1]))
    max_x = float(np.max(corners[:, 0]))
    max_y = float(np.max(corners[:, 1]))
    return min_x, min_y, max_x, max_y


def get_robot_point_for_mode(robot, mode):
    if robot is None:
        return None

    if mode == "cm":
        if robot.get("pose_position_cm"):
            return (
                float(robot["pose_position_cm"]["x"]),
                float(robot["pose_position_cm"]["y"]),
            )
        if robot.get("position_cm"):
            return (
                float(robot["position_cm"]["x"]),
                float(robot["position_cm"]["y"]),
            )

    if mode == "grid" and robot.get("grid_position"):
        return (
            float(robot["grid_position"]["x"]),
            float(robot["grid_position"]["y"]),
        )

    return None


def get_detection_point_for_mode(detection, mode):
    if mode == "cm" and detection.get("position_cm"):
        return (
            float(detection["position_cm"]["x"]),
            float(detection["position_cm"]["y"]),
        )

    if mode == "grid" and detection.get("grid_position"):
        return (
            float(detection["grid_position"]["x"]),
            float(detection["grid_position"]["y"]),
        )

    return None


def build_obstacles(detections, target_detection, mode, coord_homography):
    obstacles = []
    inflate = OBSTACLE_PADDING_CM if mode == "cm" else 0.10

    for detection in detections:
        if detection is target_detection:
            continue

        center = get_detection_point_for_mode(detection, mode)
        if center is None:
            continue

        x1, y1, x2, y2 = detection["bbox"]
        diag_coord = transform_points([(x1, y1), (x2, y2)], coord_homography)
        width = abs(float(diag_coord[1][0] - diag_coord[0][0]))
        height = abs(float(diag_coord[1][1] - diag_coord[0][1]))
        radius = max(width, height) * 0.5 + inflate

        obstacles.append({"center": center, "radius": radius})

    return obstacles


def detection_radius_in_mode(detection, mode, coord_homography):
    x1, y1, x2, y2 = detection["bbox"]
    diag_coord = transform_points([(x1, y1), (x2, y2)], coord_homography)
    width = abs(float(diag_coord[1][0] - diag_coord[0][0]))
    height = abs(float(diag_coord[1][1] - diag_coord[0][1]))
    return max(width, height) * 0.5


def draw_stored_path(frame, path_state, grid_state):
    if not path_state.get("active") or not path_state.get("waypoints"):
        return

    if not grid_state.get("locked"):
        cv2.putText(
            frame,
            "Cached path waiting for grid lock",
            (10, 56),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 200, 255),
            2,
        )
        return

    if path_state.get("mode") == "cm":
        pixel_to_coord = grid_state.get("world_homography_cm")
    else:
        pixel_to_coord = grid_state.get("homography")

    if pixel_to_coord is None:
        return

    inv = np.linalg.inv(pixel_to_coord)
    points = transform_points(path_state["waypoints"], inv)
    points_int = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
    headings = path_state.get("waypoint_headings", [])

    if len(points_int) >= 2:
        cv2.polylines(frame, [points_int], False, (255, 0, 255), 2)

    for idx, p in enumerate(points_int):
        point = np.asarray(p).reshape(-1)
        px, py = int(point[0]), int(point[1])
        cv2.circle(frame, (px, py), 4, (255, 0, 255), -1)

        if idx < len(headings):
            angle = np.radians(float(headings[idx]))
            ax = int(px + 18 * np.cos(angle))
            ay = int(py + 18 * np.sin(angle))
            cv2.arrowedLine(frame, (px, py), (ax, ay), (255, 0, 255), 1, tipLength=0.35)

        if idx == len(points_int) - 1:
            cv2.putText(
                frame,
                "TARGET",
                (px + 8, py - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 0, 255),
                2,
            )


def gemini_worker(crop_payloads):
    """Background thread for Gemini interpretation to avoid blocking."""
    global latest_interpretation
    try:
        interpretation = interpret_scene(crop_payloads)
        with interpretation_lock:
            latest_interpretation = interpretation
    except Exception as e:
        with interpretation_lock:
            latest_interpretation = f"Interpretation error: {str(e)}"


def print_latest_interpretation():
    """Print the latest interpretation when ready."""
    with interpretation_lock:
        if latest_interpretation:
            print(latest_interpretation)
            print("=" * 50)
        else:
            print("No interpretation available yet...")
            print("=" * 50)


def draw_detections(frame, detections):
    """Draw accepted (in-grid) object detections on the frame."""
    for detection in detections:
        x1, y1, x2, y2 = map(int, detection["bbox"])
        confidence = detection["confidence"]
        label = detection.get("label", "object")
        center_x, center_y = detection["center"]
        grid_x = detection["grid_position"]["x"]
        grid_y = detection["grid_position"]["y"]
        position_cm = detection.get("position_cm")

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        if position_cm:
            label_text = (
                f"{label} {confidence:.2f} "
                f"cm=({position_cm['x']:.1f}, {position_cm['y']:.1f})"
            )
        else:
            label_text = f"{label} {confidence:.2f} grid=({grid_x:.2f}, {grid_y:.2f})"

        label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(
            frame,
            (x1, y1 - label_size[1] - 10),
            (x1 + label_size[0], y1),
            (0, 255, 0),
            -1,
        )
        cv2.putText(
            frame,
            label_text,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            2,
        )

        cv2.circle(frame, (center_x, center_y), 4, (255, 255, 0), -1)

    return frame


cap = cv2.VideoCapture(2)
frame_count = 0
gemini_thread = None
current_detections = []
current_crop_payloads = []
path_state = load_path_state()
requested_target_name = ""

command_thread = threading.Thread(target=command_input_worker, args=(command_queue,), daemon=True)
command_thread.start()

print("OpenClaw Vision System Started")
print("Press 'w' to get Gemini analysis (make sure camera window is focused)")
print("Type an object name in terminal (example: bottle) to plan a waypoint path")
print("Type 'clear path' to remove current-session path")
print("Press 'q' to quit")
print("=" * 50)

while True:
    while not command_queue.empty():
        cmd = command_queue.get().strip().lower()
        if cmd in {"clear", "clear path", "reset path"}:
            path_state = default_path_state()
            requested_target_name = ""
            print("Cleared current-session path.")
        else:
            requested_target_name = cmd
            path_state["status"] = f"Planning path to '{cmd}' when grid is ready"
            print(f"Queued target request: {cmd}")

    ret, frame = cap.read()
    if not ret:
        print("Failed to capture frame")
        break

    grid_state = detect_grid(frame)

    if grid_state["locked"]:
        detections = detect_objects_in_grid_roi(frame, grid_state["polygon"])
        detections = filter_detections_in_grid(
            detections,
            grid_state["polygon"],
            grid_state["homography"],
            grid_state["world_homography_cm"],
        )
        detections = remove_aruco_marker_detections(detections, grid_state)
        detections = suppress_overlapping_detections(detections)

        robot = grid_state.get("robot")
        mode, coord_homography = get_planning_mode_and_homography(grid_state)
        if requested_target_name and mode and coord_homography is not None:
            target_detection = select_target_detection(detections, requested_target_name)
            if target_detection is not None:
                robot_point = get_robot_point_for_mode(robot, mode)
                target_point = get_detection_point_for_mode(target_detection, mode)
                bounds = get_planning_bounds(grid_state, coord_homography)

                if robot_point and target_point and bounds:
                    obstacles = build_obstacles(detections, target_detection, mode, coord_homography)
                    resolution = 3.0 if mode == "cm" else 0.04

                    # Plan from slightly ahead of robot and stop before target object's box.
                    start_offset = ROBOT_START_STANDOFF_CM if mode == "cm" else 0.10
                    target_stop_offset = detection_radius_in_mode(target_detection, mode, coord_homography)
                    target_stop_offset += TARGET_STANDOFF_CM if mode == "cm" else 0.10
                    planning_start, planning_goal = adjust_endpoints_for_standoff(
                        robot_point,
                        target_point,
                        bounds,
                        start_offset=start_offset,
                        goal_offset=target_stop_offset,
                    )

                    raw_waypoints = plan_path_astar(
                        planning_start,
                        planning_goal,
                        obstacles,
                        bounds,
                        resolution=resolution,
                    )
                    min_spacing = WAYPOINT_MIN_SPACING_CM if mode == "cm" else 0.08
                    waypoints = simplify_waypoints(raw_waypoints, min_spacing=min_spacing)

                    if waypoints:
                        waypoint_headings = compute_waypoint_headings(
                            waypoints,
                            fallback_heading=float(robot.get("heading_deg", 0.0)) if robot else 0.0,
                        )

                        # Force final pose to face the true target center, not just the previous segment.
                        if waypoint_headings and target_point is not None:
                            end_x, end_y = waypoints[-1]
                            to_target_x = float(target_point[0]) - float(end_x)
                            to_target_y = float(target_point[1]) - float(end_y)
                            if abs(to_target_x) > 1e-6 or abs(to_target_y) > 1e-6:
                                waypoint_headings[-1] = float(
                                    np.degrees(np.arctan2(to_target_y, to_target_x))
                                )

                        path_state = {
                            "active": True,
                            "target_name": requested_target_name,
                            "mode": mode,
                            "waypoints": [[float(x), float(y)] for x, y in waypoints],
                            "waypoint_headings": [float(h) for h in waypoint_headings],
                            "status": (
                                f"Path ready to {target_detection.get('label', requested_target_name)} "
                                f"({len(waypoints)} waypoints)"
                            ),
                        }
                        print(path_state["status"])
                        requested_target_name = ""
                    else:
                        path_state["status"] = (
                            f"Could not find collision-free path to '{requested_target_name}'"
                        )
                else:
                    path_state["status"] = "Need robot pose and target coordinates to plan"
            else:
                path_state["status"] = f"Target '{requested_target_name}' not visible in grid"
    else:
        detections = []
        if path_state.get("active"):
            path_state["status"] = "Grid offline; cached path will redraw when lock returns"

    current_detections = detections
    current_crop_payloads = build_detection_crops(frame, detections)

    status_text, status_color = draw_grid_overlay(frame, grid_state)
    frame_with_boxes = draw_detections(frame.copy(), detections)
    draw_stored_path(frame_with_boxes, path_state, grid_state)

    h, w = frame_with_boxes.shape[:2]
    cv2.rectangle(frame_with_boxes, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(
        frame_with_boxes,
        status_text,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        status_color,
        2,
    )

    metric_suffix = "cm" if grid_state.get("world_homography_cm") is not None else "norm"
    detect_status = f"In-grid objects: {len(detections)} ({metric_suffix})"
    detect_color = (0, 255, 0) if detections else COLOR_STATUS_NO
    cv2.putText(
        frame_with_boxes,
        detect_status,
        (w - 320, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        detect_color,
        2,
    )

    path_text = f"Path: {path_state.get('status', 'idle')}"
    cv2.putText(
        frame_with_boxes,
        path_text,
        (10, 76),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 255),
        2,
    )

    robot = grid_state.get("robot")
    if robot is None:
        robot_status = "Robot ID4: not detected"
        robot_color = COLOR_STATUS_NO
    elif robot.get("inside_grid"):
        if robot.get("pose_position_cm"):
            px = robot["pose_position_cm"]["x"]
            py = robot["pose_position_cm"]["y"]
            heading = robot.get("heading_deg")
            if heading is not None:
                robot_status = f"Robot ID4: x={px:.1f}cm y={py:.1f}cm h={heading:.1f}deg"
            else:
                robot_status = f"Robot ID4: x={px:.1f}cm y={py:.1f}cm"
        else:
            robot_status = "Robot ID4: detected (in grid)"
        robot_color = (255, 100, 0)
    else:
        heading = robot.get("heading_deg")
        if heading is not None:
            robot_status = f"Robot ID4: outside grid h={heading:.1f}deg"
        else:
            robot_status = "Robot ID4: detected (outside grid)"
        robot_color = (255, 100, 0)

    cv2.putText(
        frame_with_boxes,
        robot_status,
        (10, h - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        robot_color,
        2,
    )

    frame_count += 1
    cv2.imshow("OpenClaw Vision Feed", frame_with_boxes)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break
    elif key == ord("w"):
        print(f"\n--- Frame {frame_count} Analysis (Manual Request) ---")
        if current_crop_payloads:
            if gemini_thread is None or not gemini_thread.is_alive():
                print("Processing image with Gemini...")
                gemini_thread = threading.Thread(target=gemini_worker, args=(current_crop_payloads,))
                gemini_thread.daemon = True
                gemini_thread.start()

                def wait_and_print():
                    gemini_thread.join(timeout=10)
                    time.sleep(0.5)
                    print_latest_interpretation()

                threading.Thread(target=wait_and_print, daemon=True).start()
            else:
                print("Analysis in progress, please wait...")
        else:
            print("No in-grid object crops detected to analyze")

cap.release()
cv2.destroyAllWindows()
print("OpenClaw Vision System Stopped")

