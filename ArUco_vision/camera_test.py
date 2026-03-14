import cv2

CAMERA_INDEX = 1  # change this to 1, 2 etc for different cameras

cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print(f"Could not open camera at index {CAMERA_INDEX}")
    exit()

print(f"Showing camera {CAMERA_INDEX} — press Q to quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to read frame")
        break

    cv2.imshow(f"Camera {CAMERA_INDEX}", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()