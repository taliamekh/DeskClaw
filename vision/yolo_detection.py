from ultralytics import YOLO

model = YOLO("yolo11n.pt")

def detect_objects(frame):

    results = model(frame)

    detections = []

    for box in results[0].boxes:

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        label = results[0].names[int(box.cls)]
        conf = float(box.conf)

        detections.append({
            "label": label,
            "bbox": [x1, y1, x2, y2],
            "confidence": conf
        })

    return detections