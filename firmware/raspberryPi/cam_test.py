import cv2
import threading
import time
import subprocess
import os
import re

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

def get_audio_devices():
    """Get list of audio input devices"""
    try:
        result = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Parse device information
            devices = []
            lines = result.stdout.split('\n')
            for line in lines:
                if 'card' in line and 'device' in line:
                    # Extract card and device numbers
                    match = re.search(r'card (\d+):.*device (\d+):', line)
                    if match:
                        card = match.group(1)
                        device = match.group(2)
                        devices.append(f"plughw:{card},{device}")
            return devices
    except:
        pass
    return ['default', 'plughw:1,0', 'plughw:0,0']

def test_audio_device(device):
    """Test if an audio device works"""
    try:
        cmd = ['arecord', '-D', device, '-d', '0.1', '-f', 'S16_LE', '-r', '44100', '-c', '1', '-t', 'raw']
        result = subprocess.run(cmd, capture_output=True, timeout=2)
        return result.returncode == 0 and len(result.stdout) > 0
    except:
        return False

def audio_test_alsa():
    """Test microphone using ALSA arecord with better device detection"""
    global audio_level, audio_active, mic_available
    
    print("Detecting audio devices...")
    devices = get_audio_devices()
    working_device = None
    
    # Test each device to find a working one
    for device in devices:
        print(f"Testing audio device: {device}")
        if test_audio_device(device):
            working_device = device
            print(f"Found working audio device: {device}")
            break
    
    if not working_device:
        print("No working audio device found")
        mic_available = False
        return
    
    mic_available = True
    print(f"Using audio device: {working_device}")
    
    try:
        while audio_active:
            try:
                # Use arecord to capture a short audio sample
                cmd = ['arecord', '-D', working_device, '-d', '0.1', '-f', 'S16_LE', '-r', '44100', '-c', '1', '-t', 'raw']
                result = subprocess.run(cmd, capture_output=True, timeout=1)
                
                if result.returncode == 0 and len(result.stdout) > 0:
                    # Calculate audio level from raw data
                    data = result.stdout
                    if len(data) > 0:
                        # Convert bytes to integers and calculate RMS-like value
                        samples = [abs(int.from_bytes(data[i:i+2], 'little', signed=True)) for i in range(0, len(data)-1, 2)]
                        if samples:
                            avg_amplitude = sum(samples) / len(samples)
                            # Normalize to 0-100 scale
                            audio_level = min(int(avg_amplitude / 300), 100)  # Adjust divisor as needed
                        else:
                            audio_level = 0
                    else:
                        audio_level = 0
                else:
                    audio_level = 0
                    
            except Exception as e:
                print(f"Audio read error: {e}")
                audio_level = 0
            
            time.sleep(0.1)  # Update every 100ms
            
    except Exception as e:
        print(f"Audio monitoring error: {e}")
        mic_available = False

def audio_test_pyaudio():
    """Test microphone using PyAudio (if available)"""
    global audio_level, audio_active, mic_available
    
    try:
        import pyaudio
        import numpy as np
        
        # Audio configuration
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        # Initialize PyAudio
        p = pyaudio.PyAudio()
        
        # Open audio stream
        stream = p.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       input=True,
                       frames_per_buffer=CHUNK)
        
        mic_available = True
        print("Microphone initialized with PyAudio")
        
        while audio_active:
            try:
                # Read audio data
                data = stream.read(CHUNK, exception_on_overflow=False)
                
                # Convert to numpy array
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Calculate RMS (Root Mean Square) for audio level
                rms = np.sqrt(np.mean(audio_data**2))
                
                # Normalize to 0-100 scale
                audio_level = min(int(rms / 100), 100)
                
            except Exception as e:
                audio_level = 0
            
            time.sleep(0.01)
        
        # Cleanup
        stream.stop_stream()
        stream.close()
        p.terminate()
        
    except ImportError:
        print("PyAudio not available, using ALSA")
        audio_test_alsa()
    except Exception as e:
        print(f"PyAudio initialization failed: {e}")
        print("Using ALSA method")
        audio_test_alsa()

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
    print("Controls:")
    print("- ESC: Exit")
    print("- 'm': Toggle microphone test")
    print("- 'd': Toggle object detection")
    print("- 's': Take screenshot")
    print("- 'i': Show system info")
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
    audio_thread = threading.Thread(target=audio_test_pyaudio, daemon=True)
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
            except:
                print("Could not list audio devices")
            print("==================\n")
    
    # Cleanup
    audio_active = False
    cap.release()
    cv2.destroyAllWindows()
    print("Test completed")

if __name__ == "__main__":
    main()