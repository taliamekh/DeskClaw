import cv2
import threading
import time

# Global variables for audio
audio_level = 0
audio_active = True
mic_available = False

# YOLO detection (simple version without ultralytics dependency)
def detect_objects_simple(frame):
    """Simple object detection using OpenCV's built-in methods"""
    # Convert to grayscale for contour detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Edge detection
    edges = cv2.Canny(blurred, 50, 150)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    detections = []
    for contour in contours:
        # Filter small contours
        area = cv2.contourArea(contour)
        if area > 1000:  # Minimum area threshold
            x, y, w, h = cv2.boundingRect(contour)
            # Filter by aspect ratio and size
            if w > 30 and h > 30 and w < 400 and h < 400:
                detections.append({
                    'bbox': [x, y, x+w, y+h],
                    'confidence': min(area / 10000, 1.0),  # Rough confidence based on area
                    'label': 'object'
                })
    
    return detections

def audio_monitor():
    global audio_level, audio_active, mic_available

    import pyaudio
    import numpy as np

    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100

    try:
        p = pyaudio.PyAudio()

        # Find USB microphone automatically
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                print(f"Input device {i}: {info['name']}")
                if "USB" in info["name"] or "Camera" in info["name"] or "Audio" in info["name"]:
                    device_index = i

        # fallback to default input
        if device_index is None:
            device_index = p.get_default_input_device_info()["index"]

        print(f"Using audio device index: {device_index}")

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )

        mic_available = True
        print("Microphone initialized")

        while audio_active:
            data = stream.read(CHUNK, exception_on_overflow=False)

            samples = np.frombuffer(data, dtype=np.int16)

            # compute RMS volume
            rms = np.sqrt(np.mean(samples.astype(np.float32)**2))

            # normalize to 0–100
            audio_level = min(int(rms / 200), 100)

            time.sleep(0.03)

        stream.stop_stream()
        stream.close()
        p.terminate()

    except Exception as e:
        print("Microphone error:", e)
        mic_available = False

def draw_detections(frame, detections):
    """Draw bounding boxes on detected objects"""
    for detection in detections:
        x1, y1, x2, y2 = map(int, detection['bbox'])
        confidence = detection['confidence']
        label = detection['label']
        
        # Draw bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw label with confidence
        label_text = f"{label}: {confidence:.2f}"
        label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        
        # Background rectangle for text
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                     (x1 + label_size[0], y1), (0, 255, 0), -1)
        
        # Text
        cv2.putText(frame, label_text, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    
    return frame

def draw_audio_meter(frame, level, available):
    """Draw audio level meter on the frame"""
    # Meter dimensions
    meter_x = 20
    meter_y = 50
    meter_width = 200
    meter_height = 20
    
    if not available:
        # Draw "No Mic" indicator
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_width, meter_y + meter_height), (50, 50, 50), -1)
        cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_width, meter_y + meter_height), (0, 0, 255), 2)
        cv2.putText(frame, "No Microphone Detected", (meter_x, meter_y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return
    
    # Background rectangle
    cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_width, meter_y + meter_height), (50, 50, 50), -1)
    
    # Audio level bar
    level_width = int((level / 100.0) * meter_width)
    color = (0, 255, 0) if level < 70 else (0, 255, 255) if level < 90 else (0, 0, 255)
    cv2.rectangle(frame, (meter_x, meter_y), (meter_x + level_width, meter_y + meter_height), color, -1)
    
    # Border
    cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_width, meter_y + meter_height), (255, 255, 255), 2)
    
    # Text
    cv2.putText(frame, f"Mic Level: {level}%", (meter_x, meter_y - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def main():
    global audio_active, mic_available
    
    print("OpenClaw Camera & Microphone Test with Object Detection")
    print("=" * 50)
    
    # Test imports
    print("Testing dependencies...")
    try:
        import pyaudio
        print("✓ PyAudio available")
    except ImportError:
        print("✗ PyAudio not available - will use ALSA fallback")
    
    try:
        import numpy as np
        print("✓ NumPy available")
    except ImportError:
        print("✗ NumPy not available - audio processing may be limited")
    
    print("✓ OpenCV available")
    print("=" * 50)
    
    print("Controls:")
    print("- ESC: Exit")
    print("- 'm': Toggle microphone test")
    print("- 'd': Toggle object detection")
    print("- 's': Take screenshot")
    print("- 'i': Show system info")
    print("- 't': Manual microphone test (detailed)")
    print("=" * 50)
    
    # Initialize camera
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open camera")
        return
    
    # Set camera properties
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    print("Camera initialized successfully")
    
    # Start audio test in separate thread
    mic_enabled = True
    detection_enabled = True
    audio_thread = threading.Thread(target=audio_monitor, daemon=True)
    audio_thread.start()
    
    frame_count = 0
    screenshot_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture frame")
            break
        
        frame_count += 1
        
        # Object detection
        detections = []
        if detection_enabled:
            detections = detect_objects_simple(frame)
            frame = draw_detections(frame, detections)
        
        # Add frame counter and detection count
        cv2.putText(frame, f"Frame: {frame_count} | Objects: {len(detections)}", (20, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add microphone level meter if enabled
        if mic_enabled:
            draw_audio_meter(frame, audio_level, mic_available)
        
        # Add status text
        status_y = frame.shape[0] - 40
        if mic_available:
            status_text = "Mic: ON" if mic_enabled else "Mic: OFF"
            color = (0, 255, 0) if mic_enabled else (0, 0, 255)
        else:
            status_text = "Mic: N/A"
            color = (0, 0, 255)
            
        cv2.putText(frame, status_text, (20, status_y), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Detection status
        det_text = "Detection: ON" if detection_enabled else "Detection: OFF"
        det_color = (0, 255, 0) if detection_enabled else (0, 0, 255)
        cv2.putText(frame, det_text, (20, frame.shape[0] - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, det_color, 2)
        
        # Display frame
        cv2.imshow("OpenClaw Camera & Mic Test", frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        
        if key == 27:  # ESC key
            break
        elif key == ord('m'):  # Toggle microphone
            mic_enabled = not mic_enabled
            print(f"Microphone display {'enabled' if mic_enabled else 'disabled'}")
        elif key == ord('d'):  # Toggle detection
            detection_enabled = not detection_enabled
            print(f"Object detection {'enabled' if detection_enabled else 'disabled'}")
        elif key == ord('s'):  # Screenshot
            screenshot_count += 1
            filename = f"screenshot_{screenshot_count:03d}.jpg"
            cv2.imwrite(filename, frame)
            print(f"Screenshot saved: {filename}")
        elif key == ord('i'):  # System info
            print("\n=== SYSTEM INFO ===")
            print(f"OpenCV version: {cv2.__version__}")
            print(f"Camera resolution: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            print(f"Camera FPS: {cap.get(cv2.CAP_PROP_FPS)}")
            print(f"Microphone available: {mic_available}")
            print(f"Current audio level: {audio_level}%")
            
            # Check audio devices
            try:
                result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
                if result.returncode == 0:
                    print("Audio devices:")
                    print(result.stdout)
            except Exception:
                print("Could not list audio devices")
            print("==================\n")
    
    # Cleanup
    audio_active = False
    cap.release()
    cv2.destroyAllWindows()
    print("Test completed")

if __name__ == "__main__":
    main()