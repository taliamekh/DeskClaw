import cv2
import numpy as np
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

CORNER_IDS = {
    0: "top_left",
    1: "top_right",
    2: "bottom_right",
    3: "bottom_left",
}

ROBOT_MARKER_ID = 4  # ID of the marker on the robot

MARKER_SIZE = 0.0508  # 2 inches in meters
CAMERA_INDEX = 2

# Load calibration from file
cal = np.load(os.path.expanduser("camera_calibration.npz"))
CAMERA_MATRIX = cal['camera_matrix']
DIST_COEFFS   = cal['dist_coeffs']

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

aruco_dict   = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
aruco_params = cv2.aruco.DetectorParameters()
detector     = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

half = MARKER_SIZE / 2
obj_points = np.array([
    [-half,  half, 0],
    [ half,  half, 0],
    [ half, -half, 0],
    [-half, -half, 0],
], dtype=np.float32)

DRAW_ORDER = [0, 1, 2, 3]

COLOR_PERIMETER = (0, 255, 0)
COLOR_CORNER    = (0, 200, 255)
COLOR_LABEL     = (255, 255, 255)
COLOR_ROBOT     = (255, 100, 0)       # blue for robot
COLOR_STATUS_OK = (0, 255, 100)
COLOR_STATUS_NO = (0, 80, 255)


def get_marker_center(corners_2d):
    return tuple(corners_2d[0].mean(axis=0).astype(int))


def estimate_pose(corners_2d):
    success, rvec, tvec = cv2.solvePnP(
        obj_points, corners_2d[0], CAMERA_MATRIX, DIST_COEFFS
    )
    return (rvec, tvec) if success else (None, None)


def rvec_to_heading(rvec):
    """Convert rotation vector to a yaw angle in degrees (heading)."""
    R, _ = cv2.Rodrigues(rvec)
    # Extract yaw from rotation matrix (rotation around Z axis)
    yaw = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    return yaw


def get_robot_world_position(robot_rvec, robot_tvec, corner_poses):
    """
    Compute robot position in the desk coordinate system.
    Uses the average transform from corner markers to define world space.
    Origin = marker ID 0 (top_left).
    """
    if 0 not in corner_poses:
        return None, None

    # Use marker 0 as the world origin
    origin_rvec, origin_tvec = corner_poses[0]
    R_origin, _ = cv2.Rodrigues(origin_rvec)

    # Robot position in camera space
    robot_cam_pos = robot_tvec.flatten()

    # Origin marker position in camera space
    origin_cam_pos = origin_tvec.flatten()

    # Robot position relative to origin, in camera space
    relative = robot_cam_pos - origin_cam_pos

    # Transform into the origin marker's coordinate system
    world_pos = R_origin.T @ relative

    return world_pos[0], world_pos[1]  # x, y in meters


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

cap = cv2.VideoCapture(CAMERA_INDEX)
print("ArUco Perimeter + Robot Tracker — press Q to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera read failed")
        break

    corners_list, ids, _ = detector.detectMarkers(frame)

    detected_corners = {}
    robot = None

    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            rvec, tvec = estimate_pose(corners_list[i])
            if rvec is None:
                continue
            center = get_marker_center(corners_list[i])

            if marker_id in CORNER_IDS:
                detected_corners[marker_id] = {
                    "corners": corners_list[i],
                    "rvec": rvec, "tvec": tvec, "center": center,
                }
            elif marker_id == ROBOT_MARKER_ID:
                robot = {
                    "corners": corners_list[i],
                    "rvec": rvec, "tvec": tvec, "center": center,
                }

    # ── Draw corner markers ──
    for mid, data in detected_corners.items():
        cv2.aruco.drawDetectedMarkers(frame, [data["corners"]], np.array([[mid]]))
        cv2.drawFrameAxes(frame, CAMERA_MATRIX, DIST_COEFFS,
                          data["rvec"], data["tvec"], MARKER_SIZE * 0.5)
        cx, cy = data["center"]
        cv2.putText(frame, f'ID{mid}: {CORNER_IDS[mid]}', (cx - 40, cy - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_LABEL, 2)

    # ── Draw perimeter ──
    all_visible = all(mid in detected_corners for mid in CORNER_IDS)
    if all_visible:
        centers = [detected_corners[mid]["center"] for mid in DRAW_ORDER]

        overlay = frame.copy()
        cv2.fillPoly(overlay, [np.array(centers, dtype=np.int32)], (0, 255, 0))
        frame = cv2.addWeighted(overlay, 0.08, frame, 0.92, 0)

        for i in range(len(centers)):
            cv2.line(frame, centers[i], centers[(i + 1) % len(centers)], COLOR_PERIMETER, 2)
        for center in centers:
            cv2.circle(frame, center, 6, COLOR_CORNER, -1)

        origin = detected_corners[0]["center"]
        cv2.circle(frame, origin, 10, (0, 0, 255), 2)
        cv2.putText(frame, "ORIGIN (0,0)", (origin[0] + 12, origin[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

        status_text  = "Perimeter locked"
        status_color = COLOR_STATUS_OK
    else:
        missing = [f"ID{mid}" for mid in CORNER_IDS if mid not in detected_corners]
        status_text  = f"Missing corners: {', '.join(missing)}"
        status_color = COLOR_STATUS_NO

    # ── Draw robot marker ──
    corner_poses = {mid: (d["rvec"], d["tvec"]) for mid, d in detected_corners.items()}

    if robot is not None:
        cv2.aruco.drawDetectedMarkers(frame, [robot["corners"]], np.array([[ROBOT_MARKER_ID]]))
        cv2.drawFrameAxes(frame, CAMERA_MATRIX, DIST_COEFFS,
                          robot["rvec"], robot["tvec"], MARKER_SIZE * 0.5)

        cx, cy = robot["center"]
        heading = rvec_to_heading(robot["rvec"])

        # Draw robot dot
        cv2.circle(frame, (cx, cy), 10, COLOR_ROBOT, -1)

        # Draw heading arrow
        arrow_len = 50
        angle_rad = np.radians(heading)
        ax = int(cx + arrow_len * np.cos(angle_rad))
        ay = int(cy + arrow_len * np.sin(angle_rad))
        cv2.arrowedLine(frame, (cx, cy), (ax, ay), COLOR_ROBOT, 2, tipLength=0.3)

        # Get world position if perimeter is locked
        if all_visible:
            rx, ry = get_robot_world_position(robot["rvec"], robot["tvec"], corner_poses)
            if rx is not None:
                pos_text = f"Robot  x={rx*100:.1f}cm  y={ry*100:.1f}cm  heading={heading:.1f}deg"
            else:
                pos_text = f"Robot  heading={heading:.1f}deg  (lock perimeter for position)"
        else:
            pos_text = f"Robot  heading={heading:.1f}deg  (lock perimeter for position)"

        cv2.putText(frame, pos_text, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_ROBOT, 2)

    # ── HUD ──
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(frame, status_text, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
    robot_status = "Robot: visible" if robot else "Robot: not detected"
    robot_color  = COLOR_ROBOT if robot else COLOR_STATUS_NO
    cv2.putText(frame, robot_status, (w - 260, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, robot_color, 2)

    cv2.imshow("ArUco Perimeter + Robot", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()