import cv2
import threading
import time
import subprocess
import os

# Global variables for audio
audio_level = 0
audio_active = True
mic_available = False

def check_microphone():
    """Check if microphone is available using arecord"""
    try:
        # Test if arecord (ALSA) is available
        result = subprocess.run(['arecord', '--list-devices'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def audio_test_alsa():
    """Test microphone using ALSA arecord (Raspberry Pi friendly)"""
    global audio_level, audio_active, mic_available
    
    if not check_microphone():
        print("No microphone detected via ALSA")
        mic_available = False
        return
    
    mic_available = True
    print("Microphone detected - using ALSA")
    
    try:
        while audio_active:
            try:
                # Use arecord to capture a short audio sample
                cmd = ['arecord', '-D', 'plughw:1,0', '-d', '0.1', '-f', 'S16_LE', '-r', '44100', '-c', '1', '-t', 'raw']
                
                # Try different device indices if default doesn't work
                for device in ['plughw:1,0', 'plughw:0,0', 'default']:
                    try:
                        cmd[2] = device
                        result = subprocess.run(cmd, capture_output=True, timeout=1)
                        if result.returncode == 0:
                            # Calculate simple audio level from raw data length
                            data_length = len(result.stdout)
                            # Normalize to 0-100 scale (rough approximation)
                            audio_level = min(int(data_length / 100), 100)
                            break
                    except:
                        continue
                else:
                    audio_level = 0
                    
            except Exception as e:
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
        print("PyAudio not available, falling back to ALSA")
        audio_test_alsa()
    except Exception as e:
        print(f"PyAudio initialization failed: {e}")
        print("Falling back to ALSA method")
        audio_test_alsa()

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
    
    print("OpenClaw Camera & Microphone Test")
    print("Controls:")
    print("- ESC: Exit")
    print("- 'm': Toggle microphone test")
    print("- 's': Take screenshot")
    print("- 'i': Show system info")
    print("=" * 40)
    
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
        
        # Add frame counter
        cv2.putText(frame, f"Frame: {frame_count}", (20, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Add microphone level meter if enabled
        if mic_enabled:
            draw_audio_meter(frame, audio_level, mic_available)
        
        # Add status text
        if mic_available:
            status_text = "Mic: ON" if mic_enabled else "Mic: OFF"
            color = (0, 255, 0) if mic_enabled else (0, 0, 255)
        else:
            status_text = "Mic: N/A"
            color = (0, 0, 255)
            
        cv2.putText(frame, status_text, (20, frame.shape[0] - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Display frame
        cv2.imshow("OpenClaw Camera & Mic Test", frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        
        if key == 27:  # ESC key
            break
        elif key == ord('m'):  # Toggle microphone
            mic_enabled = not mic_enabled
            print(f"Microphone display {'enabled' if mic_enabled else 'disabled'}")
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