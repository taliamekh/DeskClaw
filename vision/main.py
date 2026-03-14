import cv2
from yolo_detection import detect_objects
from gemini_interpretation import interpret_scene
from aruco_grid import detect_grid, draw_grid_overlay, filter_detections_in_grid, COLOR_STATUS_NO
import threading
import time

# Global variables for threading
latest_interpretation = ""
interpretation_lock = threading.Lock()

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
                "grid_position": detection.get("grid_position"),
                "position_cm": detection.get("position_cm"),
            }
        )

    return crops


def gemini_worker(crop_payloads):
    """Background thread for Gemini interpretation to avoid blocking"""
    global latest_interpretation
    try:
        interpretation = interpret_scene(crop_payloads)
        with interpretation_lock:
            latest_interpretation = interpretation
    except Exception as e:
        with interpretation_lock:
            latest_interpretation = f"Interpretation error: {str(e)}"

def print_latest_interpretation():
    """Print the latest interpretation when ready"""
    with interpretation_lock:
        if latest_interpretation:
            print(latest_interpretation)
            print("=" * 50)
        else:
            print("No interpretation available yet...")
            print("=" * 50)

def draw_detections(frame, detections):
    """Draw accepted (in-grid) object detections on the frame."""
    for i, detection in enumerate(detections):
        x1, y1, x2, y2 = map(int, detection["bbox"])
        confidence = detection["confidence"]
        center_x, center_y = detection["center"]
        grid_x = detection["grid_position"]["x"]
        grid_y = detection["grid_position"]["y"]
        position_cm = detection.get("position_cm")
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw object number, confidence, and normalized grid coordinates.
        if position_cm:
            label_text = (
                f"Object {i+1}: {confidence:.2f} "
                f"cm=({position_cm['x']:.1f}, {position_cm['y']:.1f})"
            )
        else:
            label_text = f"Object {i+1}: {confidence:.2f} grid=({grid_x:.2f}, {grid_y:.2f})"
        label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        
        # Background rectangle for text
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0], y1), (0, 255, 0), -1)
        
        # Text
        cv2.putText(frame, label_text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

        # Center point of the accepted detection.
        cv2.circle(frame, (center_x, center_y), 4, (255, 255, 0), -1)
    
    return frame

cap = cv2.VideoCapture(2)
frame_count = 0
gemini_thread = None
current_detections = []
current_crop_payloads = []

print("OpenClaw Vision System Started")
print("Press 'w' to get Gemini analysis (make sure camera window is focused)")
print("Press 'q' to quit")
print("=" * 50)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to capture frame")
        break

    # Build ArUco grid state and gate detections to only objects inside the grid.
    grid_state = detect_grid(frame)
    detections = detect_objects(frame)
    if grid_state["locked"]:
        detections = filter_detections_in_grid(
            detections,
            grid_state["polygon"],
            grid_state["homography"],
            grid_state["world_homography_cm"],
        )
    else:
        detections = []

    current_detections = detections  # Store current detections for 'w' key
    current_crop_payloads = build_detection_crops(frame, detections)
    
    # Draw ArUco grid first, then accepted detections.
    status_text, status_color = draw_grid_overlay(frame, grid_state)
    frame_with_boxes = draw_detections(frame.copy(), detections)

    h, w = frame_with_boxes.shape[:2]
    cv2.rectangle(frame_with_boxes, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(frame_with_boxes, status_text, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
    metric_suffix = "cm" if grid_state.get("world_homography_cm") is not None else "norm"
    detect_status = f"In-grid objects: {len(detections)} ({metric_suffix})"
    detect_color = (0, 255, 0) if detections else COLOR_STATUS_NO
    cv2.putText(frame_with_boxes, detect_status, (w - 300, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, detect_color, 2)

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
    cv2.putText(frame_with_boxes, robot_status, (10, h - 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, robot_color, 2)

    frame_count += 1

    # Show frame with bounding boxes
    cv2.imshow("OpenClaw Vision Feed", frame_with_boxes)

    key = cv2.waitKey(1) & 0xFF
    
    # Check for key presses
    if key == ord("q"):
        break
    elif key == ord("w"):
        print(f"\n--- Frame {frame_count} Analysis (Manual Request) ---")
        if current_crop_payloads:
            # Only start new thread if previous one is done
            if gemini_thread is None or not gemini_thread.is_alive():
                print("Processing image with Gemini...")
                gemini_thread = threading.Thread(target=gemini_worker, args=(current_crop_payloads,))
                gemini_thread.daemon = True
                gemini_thread.start()
                
                # Wait for the thread to complete and print result
                def wait_and_print():
                    gemini_thread.join(timeout=10)  # Wait up to 10 seconds
                    time.sleep(0.5)  # Small buffer
                    print_latest_interpretation()
                
                threading.Thread(target=wait_and_print, daemon=True).start()
            else:
                print("Analysis in progress, please wait...")
        else:
            print("No in-grid object crops detected to analyze")

cap.release()
cv2.destroyAllWindows()
print("OpenClaw Vision System Stopped")