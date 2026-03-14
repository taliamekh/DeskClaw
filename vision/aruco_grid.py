import cv2
import numpy as np
import os


CORNER_IDS = {
    0: "top_left",
    1: "top_right",
    2: "bottom_right",
    3: "bottom_left",
}

ROBOT_MARKER_ID = 4

DRAW_ORDER = [0, 1, 2, 3]

COLOR_PERIMETER = (0, 255, 0)
COLOR_CORNER = (0, 200, 255)
COLOR_LABEL = (255, 255, 255)
COLOR_STATUS_OK = (0, 255, 100)
COLOR_STATUS_NO = (0, 80, 255)
COLOR_ROBOT = (255, 100, 0)


aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
aruco_params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

MARKER_SIZE_M = 0.0508  # 2 inches


def _load_calibration():
    search_paths = [
        os.path.join(os.path.dirname(__file__), "..", "ArUco_vision", "camera_calibration.npz"),
        os.path.join(os.path.dirname(__file__), "camera_calibration.npz"),
    ]
    for path in search_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            cal = np.load(abs_path)
            return cal["camera_matrix"], cal["dist_coeffs"], abs_path
    return None, None, None


CAMERA_MATRIX, DIST_COEFFS, CALIBRATION_PATH = _load_calibration()

half = MARKER_SIZE_M / 2
OBJ_POINTS = np.array(
    [
        [-half, half, 0],
        [half, half, 0],
        [half, -half, 0],
        [-half, -half, 0],
    ],
    dtype=np.float32,
)


def _marker_center(corners_2d):
    center = corners_2d[0].mean(axis=0)
    return int(center[0]), int(center[1])


def _estimate_pose(corners_2d):
    if CAMERA_MATRIX is None or DIST_COEFFS is None:
        return None, None
    success, rvec, tvec = cv2.solvePnP(OBJ_POINTS, corners_2d[0], CAMERA_MATRIX, DIST_COEFFS)
    if not success:
        return None, None
    return rvec, tvec


def _rvec_to_heading_deg(rvec):
    """Convert marker rotation vector to yaw heading in degrees."""
    rotation_matrix, _ = cv2.Rodrigues(rvec)
    return float(np.degrees(np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])))


def _robot_position_cm_from_origin(robot_tvec, origin_rvec, origin_tvec):
    """Transform robot camera-space translation into origin-marker local XY in centimeters."""
    origin_rotation, _ = cv2.Rodrigues(origin_rvec)
    relative = robot_tvec.flatten() - origin_tvec.flatten()
    world_pos_m = origin_rotation.T @ relative
    return float(world_pos_m[0] * 100.0), float(world_pos_m[1] * 100.0)


def _build_world_homography(detected_corners):
    if CAMERA_MATRIX is None or DIST_COEFFS is None:
        return None, "missing_calibration"

    marker_poses = {}
    for marker_id in DRAW_ORDER:
        rvec, tvec = _estimate_pose(detected_corners[marker_id]["corners"])
        if rvec is None:
            return None, "pose_failed"
        marker_poses[marker_id] = (rvec, tvec)

    origin_rvec, origin_tvec = marker_poses[0]
    R_origin, _ = cv2.Rodrigues(origin_rvec)

    src_points = []
    dst_points_cm = []
    for marker_id in DRAW_ORDER:
        src_points.append(detected_corners[marker_id]["center"])

        _, marker_tvec = marker_poses[marker_id]
        relative = marker_tvec.flatten() - origin_tvec.flatten()
        world_pos_m = R_origin.T @ relative
        dst_points_cm.append([world_pos_m[0] * 100.0, world_pos_m[1] * 100.0])

    src = np.array(src_points, dtype=np.float32)
    dst = np.array(dst_points_cm, dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst), "calibrated_pose"


def detect_grid(frame):
    corners_list, ids, _ = detector.detectMarkers(frame)
    detected_corners = {}
    robot_marker = None

    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            if marker_id in CORNER_IDS:
                detected_corners[marker_id] = {
                    "corners": corners_list[i],
                    "center": _marker_center(corners_list[i]),
                }
            elif marker_id == ROBOT_MARKER_ID:
                robot_marker = {
                    "id": ROBOT_MARKER_ID,
                    "corners": corners_list[i],
                    "center": _marker_center(corners_list[i]),
                }

    if robot_marker is not None:
        robot_rvec, robot_tvec = _estimate_pose(robot_marker["corners"])
        if robot_rvec is not None:
            robot_marker["rvec"] = robot_rvec
            robot_marker["tvec"] = robot_tvec
            robot_marker["heading_deg"] = _rvec_to_heading_deg(robot_rvec)

    locked = all(marker_id in detected_corners for marker_id in CORNER_IDS)
    polygon = None
    homography = None
    world_homography_cm = None
    metric_source = "unavailable"

    if locked:
        centers = [detected_corners[marker_id]["center"] for marker_id in DRAW_ORDER]
        polygon = np.array(centers, dtype=np.float32)
        dst = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)
        homography = cv2.getPerspectiveTransform(polygon, dst)
        world_homography_cm, metric_source = _build_world_homography(detected_corners)

        if robot_marker is not None:
            robot_center = robot_marker["center"]
            robot_marker["inside_grid"] = point_in_grid(robot_center, polygon)
            if robot_marker["inside_grid"]:
                grid_x, grid_y = pixel_to_grid(robot_center, homography)
                robot_marker["grid_position"] = {"x": grid_x, "y": grid_y}
                if world_homography_cm is not None:
                    world_x_cm, world_y_cm = pixel_to_grid(robot_center, world_homography_cm)
                    robot_marker["position_cm"] = {"x": world_x_cm, "y": world_y_cm}

            # Prefer pose-derived robot position from marker ID0 frame when available.
            if "tvec" in robot_marker:
                origin_rvec, origin_tvec = _estimate_pose(detected_corners[0]["corners"])
                if origin_rvec is not None:
                    px_cm, py_cm = _robot_position_cm_from_origin(
                        robot_marker["tvec"],
                        origin_rvec,
                        origin_tvec,
                    )
                    robot_marker["pose_position_cm"] = {"x": px_cm, "y": py_cm}
    elif robot_marker is not None:
        robot_marker["inside_grid"] = False

    return {
        "detected_corners": detected_corners,
        "locked": locked,
        "polygon": polygon,
        "homography": homography,
        "world_homography_cm": world_homography_cm,
        "metric_source": metric_source,
        "calibration_path": CALIBRATION_PATH,
        "robot": robot_marker,
    }


def point_in_grid(point_xy, polygon):
    if polygon is None:
        return False
    contour = np.asarray(polygon, dtype=np.float32).reshape((-1, 1, 2))
    point = (float(point_xy[0]), float(point_xy[1]))
    return cv2.pointPolygonTest(contour, point, False) >= 0


def pixel_to_grid(point_xy, homography):
    src = np.array([[[float(point_xy[0]), float(point_xy[1])]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(src, homography)
    gx, gy = transformed[0, 0]
    return float(gx), float(gy)


def filter_detections_in_grid(detections, polygon, homography, world_homography_cm=None):
    accepted = []
    if polygon is None or homography is None:
        return accepted

    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        center = (int((x1 + x2) / 2), int((y1 + y2) / 2))

        if point_in_grid(center, polygon):
            grid_x, grid_y = pixel_to_grid(center, homography)
            accepted_detection = {
                **detection,
                "center": center,
                "grid_position": {
                    "x": grid_x,
                    "y": grid_y,
                },
            }
            if world_homography_cm is not None:
                world_x_cm, world_y_cm = pixel_to_grid(center, world_homography_cm)
                accepted_detection["position_cm"] = {
                    "x": world_x_cm,
                    "y": world_y_cm,
                }
            accepted.append(accepted_detection)

    return accepted


def draw_grid_overlay(frame, grid_state):
    detected_corners = grid_state["detected_corners"]
    locked = grid_state["locked"]

    for marker_id, data in detected_corners.items():
        cv2.aruco.drawDetectedMarkers(frame, [data["corners"]], np.array([[marker_id]]))
        cx, cy = data["center"]
        cv2.putText(
            frame,
            f"ID{marker_id}: {CORNER_IDS[marker_id]}",
            (cx - 40, cy - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            COLOR_LABEL,
            2,
        )

    if locked:
        centers = [detected_corners[marker_id]["center"] for marker_id in DRAW_ORDER]

        overlay = frame.copy()
        cv2.fillPoly(overlay, [np.array(centers, dtype=np.int32)], (0, 255, 0))
        frame[:] = cv2.addWeighted(overlay, 0.08, frame, 0.92, 0)

        for i in range(len(centers)):
            cv2.line(frame, centers[i], centers[(i + 1) % len(centers)], COLOR_PERIMETER, 2)
        for center in centers:
            cv2.circle(frame, center, 6, COLOR_CORNER, -1)

        origin = detected_corners[0]["center"]
        cv2.circle(frame, origin, 10, (0, 0, 255), 2)
        cv2.putText(
            frame,
            "GRID ORIGIN (0,0)",
            (origin[0] + 12, origin[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            2,
        )

        metric_source = grid_state.get("metric_source", "unavailable")
        if metric_source == "calibrated_pose":
            status_text = "Grid locked (cm calibrated)"
        else:
            status_text = "Grid locked (cm unavailable)"
        status_color = COLOR_STATUS_OK
    else:
        missing = [f"ID{marker_id}" for marker_id in CORNER_IDS if marker_id not in detected_corners]
        status_text = f"Missing corners: {', '.join(missing)}"
        status_color = COLOR_STATUS_NO

    robot = grid_state.get("robot")
    if robot is not None:
        cv2.aruco.drawDetectedMarkers(frame, [robot["corners"]], np.array([[ROBOT_MARKER_ID]]))
        rx, ry = robot["center"]
        cv2.circle(frame, (rx, ry), 8, COLOR_ROBOT, -1)

        if CAMERA_MATRIX is not None and DIST_COEFFS is not None and "rvec" in robot:
            cv2.drawFrameAxes(
                frame,
                CAMERA_MATRIX,
                DIST_COEFFS,
                robot["rvec"],
                robot["tvec"],
                MARKER_SIZE_M * 0.5,
            )

        if "heading_deg" in robot:
            arrow_len = 50
            angle = np.radians(robot["heading_deg"])
            ax = int(rx + arrow_len * np.cos(angle))
            ay = int(ry + arrow_len * np.sin(angle))
            cv2.arrowedLine(frame, (rx, ry), (ax, ay), COLOR_ROBOT, 2, tipLength=0.3)

        robot_text = "Robot ID4"
        if robot.get("inside_grid") and "pose_position_cm" in robot:
            px = robot["pose_position_cm"]["x"]
            py = robot["pose_position_cm"]["y"]
            robot_text += f" ({px:.1f}cm, {py:.1f}cm)"
        elif robot.get("inside_grid") and "position_cm" in robot:
            px = robot["position_cm"]["x"]
            py = robot["position_cm"]["y"]
            robot_text += f" ({px:.1f}cm, {py:.1f}cm)"
        elif robot.get("inside_grid") and "grid_position" in robot:
            gx = robot["grid_position"]["x"]
            gy = robot["grid_position"]["y"]
            robot_text += f" ({gx:.2f}, {gy:.2f})"
        else:
            robot_text += " (outside grid)"

        if "heading_deg" in robot:
            robot_text += f" h={robot['heading_deg']:.1f}deg"

        cv2.putText(
            frame,
            robot_text,
            (rx + 12, ry - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            COLOR_ROBOT,
            2,
        )

    return status_text, status_color
