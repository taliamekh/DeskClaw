import cv2
from yolo_detection import detect_objects
from gemini_interpretation import interpret_scene
import threading
import time

# Global variables for threading
latest_interpretation = ""
interpretation_lock = threading.Lock()

def gemini_worker(frame, detections):
    """Background thread for Gemini interpretation to avoid blocking"""
    global latest_interpretation
    try:
        interpretation = interpret_scene(frame, detections)
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
    """Draw bounding boxes on the frame"""
    for i, detection in enumerate(detections):
        x1, y1, x2, y2 = map(int, detection["bbox"])
        confidence = detection["confidence"]
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw object number and confidence
        label_text = f"Object {i+1}: {confidence:.2f}"
        label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        
        # Background rectangle for text
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0], y1), (0, 255, 0), -1)
        
        # Text
        cv2.putText(frame, label_text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    
    return frame

cap = cv2.VideoCapture(0)
frame_count = 0
gemini_thread = None
current_detections = []
current_frame = None

print("OpenClaw Vision System Started")
print("Press 'w' to get Gemini analysis (make sure camera window is focused)")
print("Press 'q' to quit")
print("=" * 50)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to capture frame")
        break

    # Get detections
    detections = detect_objects(frame)
    current_detections = detections  # Store current detections for 'w' key
    current_frame = frame.copy()     # Store current frame for 'w' key
    
    # Draw bounding boxes on frame
    frame_with_boxes = draw_detections(frame.copy(), detections)

    frame_count += 1

    # Show frame with bounding boxes
    cv2.imshow("OpenClaw Vision Feed", frame_with_boxes)

    key = cv2.waitKey(1) & 0xFF
    
    # Check for key presses
    if key == ord("q"):
        break
    elif key == ord("w"):
        print(f"\n--- Frame {frame_count} Analysis (Manual Request) ---")
        if current_detections:
            # Only start new thread if previous one is done
            if gemini_thread is None or not gemini_thread.is_alive():
                print("Processing image with Gemini...")
                gemini_thread = threading.Thread(target=gemini_worker, args=(current_frame, current_detections))
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
            print("No objects detected to analyze")

cap.release()
cv2.destroyAllWindows()
print("OpenClaw Vision System Stopped")