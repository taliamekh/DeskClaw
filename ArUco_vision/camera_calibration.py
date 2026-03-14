import cv2
import numpy as np
import os
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

# Checkerboard dimensions — number of INNER corners (not squares)
# e.g. a standard 8x6 checkerboard has 7x5 inner corners
CHECKERBOARD = (7, 5)

# Size of each square in meters (measure your printed checkerboard)
SQUARE_SIZE = 0.015  # 2.5cm default

# How many good captures to collect before calibrating
TARGET_CAPTURES = 20

# Minimum seconds between auto-captures (to avoid duplicates)
CAPTURE_INTERVAL = 1.5

# Camera index
CAMERA_INDEX = 0

# Where to save the calibration result
OUTPUT_FILE = "camera_calibration.npz"

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

# Prepare object points for the checkerboard
objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
objp *= SQUARE_SIZE

obj_points = []  # 3D world points
img_points = []  # 2D image points

criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

cap = cv2.VideoCapture(CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print("=" * 50)
print("  Camera Calibration Tool")
print("=" * 50)
print(f"  Target: {TARGET_CAPTURES} captures")
print(f"  Checkerboard: {CHECKERBOARD[0]}x{CHECKERBOARD[1]} inner corners")
print(f"  Square size: {SQUARE_SIZE*100:.1f}cm")
print()
print("  Hold a printed checkerboard in front of the camera.")
print("  Move it to different angles, distances and positions.")
print("  Captures are taken automatically when a board is detected.")
print()
print("  SPACE = force capture | R = reset | Q = quit & calibrate")
print("=" * 50)

last_capture_time = 0
captured = 0
frame_size = None

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera read failed")
        break

    if frame_size is None:
        frame_size = (frame.shape[1], frame.shape[0])

    display = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    found, corners = cv2.findChessboardCorners(
        gray, CHECKERBOARD,
        cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    )

    now = time.time()
    auto_captured = False

    if found:
        corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        cv2.drawChessboardCorners(display, CHECKERBOARD, corners_refined, found)

        # Auto capture if enough time has passed and we still need more
        if (now - last_capture_time > CAPTURE_INTERVAL) and (captured < TARGET_CAPTURES):
            obj_points.append(objp)
            img_points.append(corners_refined)
            captured += 1
            last_capture_time = now
            auto_captured = True
            print(f"  Captured {captured}/{TARGET_CAPTURES}")

        # Flash effect on capture
        if auto_captured:
            flash = display.copy()
            cv2.rectangle(flash, (0, 0), (frame_size[0], frame_size[1]), (255, 255, 255), -1)
            display = cv2.addWeighted(flash, 0.3, display, 0.7, 0)

        board_status = f"Board found! ({captured}/{TARGET_CAPTURES} captured)"
        board_color = (0, 255, 100)
    else:
        board_status = "No board detected — move checkerboard into view"
        board_color = (0, 80, 255)

    # ── Progress bar ──
    h, w = display.shape[:2]
    bar_width = int((captured / TARGET_CAPTURES) * (w - 20))
    cv2.rectangle(display, (10, h - 30), (w - 10, h - 10), (60, 60, 60), -1)
    cv2.rectangle(display, (10, h - 30), (10 + bar_width, h - 10), (0, 200, 100), -1)
    cv2.putText(display, f"{captured}/{TARGET_CAPTURES}", (w // 2 - 20, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # ── HUD ──
    cv2.rectangle(display, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(display, board_status, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, board_color, 2)

    # Tips for getting good coverage
    tips = []
    if captured < TARGET_CAPTURES:
        tips = [
            "Tips for good calibration:",
            "- Tilt the board left/right/up/down",
            "- Move it close, mid-range and far",
            "- Cover all corners of the frame",
            "- Avoid motion blur",
        ]
        for i, tip in enumerate(tips):
            cv2.putText(display, tip, (10, 60 + i * 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                        (200, 200, 200) if i > 0 else (255, 255, 100), 1)

    if captured >= TARGET_CAPTURES:
        cv2.putText(display, "Press Q to calibrate!", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    cv2.imshow("Camera Calibration", display)

    key = cv2.waitKey(1) & 0xFF

    # Force capture on SPACE
    if key == ord(' ') and found:
        obj_points.append(objp)
        img_points.append(corners_refined)
        captured += 1
        last_capture_time = now
        print(f"  Manual capture {captured}/{TARGET_CAPTURES}")

    # Reset
    elif key == ord('r'):
        obj_points.clear()
        img_points.clear()
        captured = 0
        print("  Reset — starting over")

    # Quit and calibrate
    elif key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# ─────────────────────────────────────────────
# CALIBRATE
# ─────────────────────────────────────────────

if captured < 6:
    print(f"\nNot enough captures ({captured}) — need at least 6. Exiting.")
    exit()

print(f"\nCalibrating with {captured} captures...")

ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
    obj_points, img_points, frame_size, None, None
)

# Compute reprojection error (lower = better, under 1.0 is good)
total_error = 0
for i in range(len(obj_points)):
    projected, _ = cv2.projectPoints(obj_points[i], rvecs[i], tvecs[i], camera_matrix, dist_coeffs)
    error = cv2.norm(img_points[i], projected, cv2.NORM_L2) / len(projected)
    total_error += error
reprojection_error = total_error / len(obj_points)

# Save results
np.savez(OUTPUT_FILE,
         camera_matrix=camera_matrix,
         dist_coeffs=dist_coeffs,
         reprojection_error=reprojection_error)

print("\n" + "=" * 50)
print("  Calibration complete!")
print("=" * 50)
print(f"  Reprojection error: {reprojection_error:.4f} px", end="  ")
if reprojection_error < 0.5:
    print("(Excellent)")
elif reprojection_error < 1.0:
    print("(Good)")
elif reprojection_error < 2.0:
    print("(Acceptable)")
else:
    print("(Poor — try again with more varied captures)")

print(f"\n  Camera matrix:")
print(f"    fx={camera_matrix[0,0]:.1f}  fy={camera_matrix[1,1]:.1f}")
print(f"    cx={camera_matrix[0,2]:.1f}  cy={camera_matrix[1,2]:.1f}")
print(f"\n  Saved to: {OUTPUT_FILE}")
print()
print("  To use in your perimeter script, replace CAMERA_MATRIX and")
print("  DIST_COEFFS with:")
print()
print("  import numpy as np")
print(f"  cal = np.load('{OUTPUT_FILE}')")
print("  CAMERA_MATRIX = cal['camera_matrix']")
print("  DIST_COEFFS   = cal['dist_coeffs']")
print("=" * 50)