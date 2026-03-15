from ultralytics import YOLO

# Initialize model with optimizations
model = YOLO("yolo11n.pt")
model.overrides['verbose'] = False  # Reduce console output

def detect_objects(frame):
    """Detect objects in frame using YOLO11 and return box + class metadata."""
    # Run inference with lower confidence threshold to detect more objects
    results = model(frame, verbose=False, conf=0.05, imgsz=1280)  # Lowered from 0.5 to 0.25
    
    detections = []
    
    # Check if any detections exist
    if results[0].boxes is not None:
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf)
            class_id = int(box.cls)
            label = str(model.names.get(class_id, f"class_{class_id}"))
            
            detections.append({
                "bbox": [x1, y1, x2, y2],
                "confidence": conf,
                "class_id": class_id,
                "label": label,
            })
    
    return detections