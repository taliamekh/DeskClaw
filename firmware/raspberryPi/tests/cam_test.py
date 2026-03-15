import cv2
import threading
import time
import subprocess
import re
import platform

# Detect operating system
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

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

def audio_test_pyaudio():
    """Test microphone using PyAudio with cross-platform support"""
    global audio_level, audio_active, mic_available
    
    try:
        import pyaudio
        import numpy as np
        
        print("\n=== PYAUDIO INITIALIZATION ===")
        
        # Initialize PyAudio
        p = pyaudio.PyAudio()
        
        # List available audio devices
        print("Available audio devices:")
        device_count = p.get_device_count()
        input_devices = []
        
        for i in range(device_count):
            try:
                device_info = p.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    input_devices.append((i, device_info))
                    print(f"  Device {i}: {device_info['name']} (channels: {device_info['maxInputChannels']})")
            except Exception as e:
                print(f"  Device {i}: Error - {e}")
        
        if not input_devices:
            print("No input devices found!")
            p.terminate()
            if IS_LINUX:
                audio_test_alsa()
            else:
                print("No audio fallback available on Windows")
                mic_available = False
            return
        
        # Try to find the best input device
        selected_device = None
        
        # Prefer USB audio devices or devices with "microphone" in name
        for device_id, device_info in input_devices:
            device_name = device_info['name'].lower()
            if 'usb' in device_name or 'microphone' in device_name or 'audio' in device_name:
                selected_device = device_id
                print(f"Selected audio device: {device_info['name']}")
                break
        
        # Fall back to default input device
        if selected_device is None:
            try:
                default_device = p.get_default_input_device_info()
                selected_device = default_device['index']
                print(f"Using default input device: {default_device['name']}")
            except Exception:
                # Use first available input device
                selected_device = input_devices[0][0]
                print(f"Using first available device: {input_devices[0][1]['name']}")
        
        # Get device info for selected device
        device_info = p.get_device_info_by_index(selected_device)
        
        # Try different sample rates (Windows can be picky)
        sample_rates = [44100, 48000, 22050, 16000, 8000]
        stream = None
        
        for rate in sample_rates:
            try:
                print(f"Trying sample rate: {rate} Hz")
                stream = p.open(format=pyaudio.paInt16,
                               channels=1,
                               rate=rate,
                               input=True,
                               input_device_index=selected_device,
                               frames_per_buffer=1024)
                
                print(f"✓ Successfully opened stream at {rate} Hz")
                break
                
            except Exception as e:
                print(f"✗ Failed at {rate} Hz: {e}")
                if stream:
                    stream.close()
                    stream = None
        
        if stream is None:
            print("Failed to open audio stream with any sample rate")
            p.terminate()
            mic_available = False
            return
        
        mic_available = True
        print("✓ Microphone initialized successfully with PyAudio")
        print("=== PYAUDIO INITIALIZATION COMPLETE ===\n")
        
        # Main audio monitoring loop
        while audio_active:
            try:
                # Read audio data
                data = stream.read(1024, exception_on_overflow=False)
                
                # Convert to numpy array
                audio_data = np.frombuffer(data, dtype=np.int16)
                
                # Calculate RMS (Root Mean Square) for audio level
                rms = np.sqrt(np.mean(audio_data**2))
                
                # Normalize to 0-100 scale (adjusted for better sensitivity)
                audio_level = min(int(rms / 50), 100)
                
            except Exception as e:
                print(f"Audio read error: {e}")
                audio_level = 0
            
            time.sleep(0.05)  # 50ms update rate
        
        # Cleanup
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("PyAudio cleaned up")
        
    except ImportError:
        print("PyAudio not available")
        if IS_LINUX:
            print("Trying ALSA fallback...")
            audio_test_alsa()
        else:
            print("No audio fallback available on Windows")
            mic_available = False
    except Exception as e:
        print(f"PyAudio initialization failed: {e}")
        if IS_LINUX:
            print("Falling back to ALSA method")
            audio_test_alsa()
        else:
            print("No audio fallback available on Windows")
            mic_available = False

def audio_test_alsa():
    """Test microphone using ALSA (Linux only)"""
    global audio_level, audio_active, mic_available
    
    if IS_WINDOWS:
        print("ALSA not available on Windows")
        mic_available = False
        return
    
    print("\n=== AUDIO DEBUGGING (ALSA) ===")
    
    # Check if ALSA tools are available
    try:
        subprocess.run(['which', 'arecord'], check=True, capture_output=True)
        print("✓ arecord command is available")
    except Exception:
        print("✗ arecord command not found")
        print("Install with: sudo apt-get install alsa-utils")
        mic_available = False
        return
    
    # Try to find working audio device
    devices_to_test = ['default', 'plughw:0,0', 'plughw:1,0', 'hw:0,0', 'hw:1,0']
    working_device = None
    
    for device in devices_to_test:
        try:
            cmd = ['arecord', '-D', device, '-d', '0.1', '-f', 'S16_LE', '-r', '44100', '-c', '1', '-t', 'raw']
            result = subprocess.run(cmd, capture_output=True, timeout=2)
            
            if result.returncode == 0 and len(result.stdout) > 0:
                working_device = device
                print(f"✓ Found working audio device: {device}")
                break
        except Exception:
            continue
    
    if not working_device:
        print("✗ No working audio device found")
        mic_available = False
        return
    
    mic_available = True
    print(f"✓ Using audio device: {working_device}")
    print("=== AUDIO DEBUGGING COMPLETE ===\n")
    
    # Audio monitoring loop
    try:
        while audio_active:
            try:
                cmd = ['arecord', '-D', working_device, '-d', '0.1', '-f', 'S16_LE', '-r', '44100', '-c', '1', '-t', 'raw']
                result = subprocess.run(cmd, capture_output=True, timeout=2)
                
                if result.returncode == 0 and len(result.stdout) > 0:
                    data = result.stdout
                    if len(data) > 0:
                        try:
                            samples = []
                            for i in range(0, len(data)-1, 2):
                                if i+1 < len(data):
                                    sample = int.from_bytes(data[i:i+2], 'little', signed=True)
                                    samples.append(abs(sample))
                            
                            if samples:
                                avg_amplitude = sum(samples) / len(samples)
                                audio_level = min(int(avg_amplitude / 300), 100)
                            else:
                                audio_level = 0
                        except Exception:
                            audio_level = 0
                    else:
                        audio_level = 0
                else:
                    audio_level = 0
                    
            except Exception:
                audio_level = 0
            
            time.sleep(0.1)
            
    except Exception as e:
        print(f"Audio monitoring error: {e}")
        mic_available = False

def manual_microphone_test():
    """Manual microphone test with cross-platform support"""
    print("\n=== MANUAL MICROPHONE TEST ===")
    
    # Step 1: Test PyAudio
    print("1. Testing PyAudio...")
    try:
        import pyaudio
        import numpy as np
        
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()
        
        print(f"PyAudio found {device_count} audio devices:")
        input_devices = []
        
        for i in range(device_count):
            try:
                device_info = p.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    input_devices.append((i, device_info))
                    print(f"  ✓ Device {i}: {device_info['name']}")
                    print(f"    Channels: {device_info['maxInputChannels']}, Rate: {device_info['defaultSampleRate']}")
            except Exception as e:
                print(f"  ✗ Device {i}: Error - {e}")
        
        if input_devices:
            print(f"\nTesting first input device...")
            device_id, device_info = input_devices[0]
            
            # Try different sample rates
            sample_rates = [44100, 48000, 22050, 16000]
            for rate in sample_rates:
                try:
                    print(f"Testing {rate} Hz...")
                    stream = p.open(format=pyaudio.paInt16,
                                   channels=1,
                                   rate=rate,
                                   input=True,
                                   input_device_index=device_id,
                                   frames_per_buffer=1024)
                    
                    # Test recording for 0.5 seconds
                    frames = []
                    for _ in range(int(rate / 1024 * 0.5)):
                        data = stream.read(1024)
                        frames.append(data)
                    
                    stream.stop_stream()
                    stream.close()
                    
                    # Analyze the audio
                    audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
                    rms = np.sqrt(np.mean(audio_data**2))
                    
                    print(f"✓ SUCCESS at {rate} Hz: RMS level: {rms:.2f}")
                    if rms > 50:
                        print("  Audio level detected - microphone is working!")
                    else:
                        print("  Low audio level - try speaking into microphone")
                    
                    p.terminate()
                    return device_id
                    
                except Exception as e:
                    print(f"✗ FAILED at {rate} Hz: {e}")
                    if 'stream' in locals():
                        stream.close()
        
        p.terminate()
        
    except ImportError:
        print("PyAudio not available")
    except Exception as e:
        print(f"PyAudio test failed: {e}")
    
    # Step 2: Platform-specific tests
    if IS_LINUX:
        print("\n2. Checking Linux audio devices...")
        try:
            result = subprocess.run(['arecord', '-l'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("ALSA devices:")
                print(result.stdout)
            else:
                print("No ALSA devices found")
        except Exception as e:
            print(f"Error checking ALSA: {e}")
    elif IS_WINDOWS:
        print("\n2. Windows audio system detected")
        print("Make sure your microphone is enabled in Windows Sound settings")
    
    print("\n=== MANUAL TEST COMPLETE ===")
    return None

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
    
    # Test imports and show platform info
    print(f"Platform: {platform.system()} {platform.release()}")
    print("Testing dependencies...")
    try:
        import pyaudio
        print("✓ PyAudio available")
    except ImportError:
        print("✗ PyAudio not available - install with: pip install pyaudio")
    
    try:
        import numpy as np
        print("✓ NumPy available")
    except ImportError:
        print("✗ NumPy not available")
    
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
            print(f"Platform: {platform.system()} {platform.release()}")
            print(f"OpenCV version: {cv2.__version__}")
            print(f"Camera resolution: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            print(f"Camera FPS: {cap.get(cv2.CAP_PROP_FPS)}")
            print(f"Microphone available: {mic_available}")
            print(f"Current audio level: {audio_level}%")
            print("==================\n")
        elif key == ord('t'):  # Manual microphone test
            print("Running detailed microphone test...")
            working_device = manual_microphone_test()
            if working_device:
                print(f"\n✓ Found working device: {working_device}")
                print("You can try restarting the application to use this device.")
            else:
                print("\n✗ No working microphone device found.")
                print("Check the troubleshooting steps above.")
    
    # Cleanup
    audio_active = False
    cap.release()
    cv2.destroyAllWindows()
    print("Test completed")

if __name__ == "__main__":
    main()