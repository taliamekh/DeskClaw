from ultralytics import YOLO

# Initialize model with optimizations
model = YOLO("yolo11m.pt")
model.overrides['verbose'] = False  # Reduce console output

def detect_objects(frame):
    """Detect objects in frame using YOLO11 - returns bounding boxes only"""
    # Run inference with lower confidence threshold to detect more objects
    results = model(frame, verbose=False, conf=0.25)  # Lowered from 0.5 to 0.25
    
    detections = []
    
    # Check if any detections exist
    if results[0].boxes is not None:
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf)
            
            detections.append({
                "bbox": [x1, y1, x2, y2],
                "confidence": conf
            })
    
    return detections