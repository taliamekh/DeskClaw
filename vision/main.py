import cv2
from yolo_detector import detect_objects
from gemini_interpreter import interpret_scene

cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()
    if not ret:
        break

    detections = detect_objects(frame)

    if detections:
        frame_count = 0

    frame_count += 1
    if frame_count % 30 == 0:
        interpretation = interpret_scene(detections)
        print(interpretation)

    cv2.imshow("Camera Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()