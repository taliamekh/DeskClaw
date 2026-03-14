import cv2
import numpy as np

# ─────────────────────────────────────────────
# CONFIG — edit these to match your setup
# ─────────────────────────────────────────────

# Which marker ID is at which corner
# Place your printed markers so these IDs match the physical corners
CORNER_IDS = {
    0: "top_left",
    1: "top_right",
    2: "bottom_right",
    3: "bottom_left",
}

# Physical size of your printed markers in meters (4 inches = ~0.1016m)
MARKER_SIZE = 0.1016

# Camera index (0 = default webcam)
CAMERA_INDEX = 0

# Your camera intrinsics — replace with your calibrated values if you have them
# These are rough defaults for a typical 720p webcam
CAMERA_MATRIX = np.array([
    [800,   0, 640],
    [  0, 800, 360],
    [  0,   0,   1]
], dtype=np.float32)
DIST_COEFFS = np.zeros((4, 1), dtype=np.float32)

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

# Perimeter draw order: TL → TR → BR → BL → TL
DRAW_ORDER = [0, 1, 2, 3]  # corner IDs in order

# Colors (BGR)
COLOR_PERIMETER = (0, 255, 0)       # green perimeter lines
COLOR_CORNER    = (0, 200, 255)     # orange corner dots
COLOR_LABEL     = (255, 255, 255)   # white labels
COLOR_AXIS      = None              # drawn by drawFrameAxes
COLOR_STATUS_OK = (0, 255, 100)
COLOR_STATUS_NO = (0, 80, 255)


def get_marker_center(corners_2d):
    """Return the 2D image center of a detected marker."""
    return tuple(corners_2d[0].mean(axis=0).astype(int))


def estimate_marker_pose(corners_2d):
    """Return rvec, tvec for a single marker."""
    success, rvec, tvec = cv2.solvePnP(
        obj_points, corners_2d[0], CAMERA_MATRIX, DIST_COEFFS
    )
    return (rvec, tvec) if success else (None, None)


def project_point(world_pt, rvec, tvec):
    """Project a 3D world point to 2D image coords using a marker's pose."""
    pts, _ = cv2.projectPoints(
        np.array([[world_pt]], dtype=np.float32),
        rvec, tvec, CAMERA_MATRIX, DIST_COEFFS
    )
    return tuple(pts[0][0].astype(int))


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print("ArUco Perimeter Tracker running — press Q to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera read failed")
        break

    corners_list, ids, _ = detector.detectMarkers(frame)

    # Build a dict of id → (corners_2d, rvec, tvec, center_px)
    detected = {}
    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            if marker_id in CORNER_IDS:
                rvec, tvec = estimate_marker_pose(corners_list[i])
                if rvec is not None:
                    center = get_marker_center(corners_list[i])
                    detected[marker_id] = {
                        "corners": corners_list[i],
                        "rvec": rvec,
                        "tvec": tvec,
                        "center": center,
                    }

    # ── Draw each detected corner marker ──
    for mid, data in detected.items():
        cv2.aruco.drawDetectedMarkers(frame, [data["corners"]], np.array([[mid]]))
        cv2.drawFrameAxes(frame, CAMERA_MATRIX, DIST_COEFFS,
                          data["rvec"], data["tvec"], MARKER_SIZE * 0.5)

        label = f'ID{mid}: {CORNER_IDS[mid]}'
        cx, cy = data["center"]
        cv2.putText(frame, label, (cx - 40, cy - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_LABEL, 2)

    # ── Draw perimeter if all 4 corners visible ──
    all_visible = all(mid in detected for mid in CORNER_IDS)

    if all_visible:
        centers = [detected[mid]["center"] for mid in DRAW_ORDER]

        # Draw filled semi-transparent perimeter polygon
        overlay = frame.copy()
        pts = np.array(centers, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 255, 0))
        frame = cv2.addWeighted(overlay, 0.08, frame, 0.92, 0)

        # Draw perimeter outline
        for i in range(len(centers)):
            pt1 = centers[i]
            pt2 = centers[(i + 1) % len(centers)]
            cv2.line(frame, pt1, pt2, COLOR_PERIMETER, 2)

        # Draw corner dots
        for center in centers:
            cv2.circle(frame, center, 6, COLOR_CORNER, -1)

        # Draw coordinate origin marker at corner ID 0 (top_left)
        origin = detected[0]["center"]
        cv2.circle(frame, origin, 10, (0, 0, 255), 2)
        cv2.putText(frame, "ORIGIN (0,0)", (origin[0] + 12, origin[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        status_text = "Perimeter locked"
        status_color = COLOR_STATUS_OK
    else:
        missing = [f"ID{mid}" for mid in CORNER_IDS if mid not in detected]
        status_text = f"Missing: {', '.join(missing)}"
        status_color = COLOR_STATUS_NO

    # ── HUD ──
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(frame, status_text, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
    cv2.putText(frame, f"Visible corners: {len(detected)}/4", (w - 220, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_LABEL, 1)

    cv2.imshow("ArUco Perimeter", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()