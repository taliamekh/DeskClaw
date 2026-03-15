# DeskClaw

A voice-controlled robotic arm and rover system. Say "Hey Claw" to give commands — the system sees objects on a desk via overhead camera, plans paths around obstacles, drives the rover to the target, and picks it up with a claw arm.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  RASPBERRY PI                                                   │
│                                                                 │
│  ┌──────────────┐   WebSocket    ┌───────────────────┐          │
│  │  Microphone   │──────────────▶│  Whisper Server    │ (Mac)   │
│  │  (Nulea C905) │  audio stream │  (faster-whisper)  │         │
│  └──────────────┘               └────────┬──────────┘          │
│                                          │ transcript           │
│  ┌───────────────────────────────────────▼──────────────────┐  │
│  │  voice_client.py                                         │  │
│  │  • Wake phrase detection ("Hey Claw")                    │  │
│  │  • Command buffering with silence timeout                │  │
│  │  • LLM integration (Gemini 2.5 Flash)                    │  │
│  │  • TTS playback via ElevenLabs → mpg123                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────────┐    ┌───────────────────┐               │
│  │  Rover API (FastAPI)│    │  Arm Controller    │              │
│  │  /forward /turn     │    │  (Arduino serial)  │              │
│  │  /stop              │    │  PICK, HOME, OPEN  │              │
│  │  port 8000          │    │  CLOSE, SCAN       │              │
│  └────────────────────┘    └───────────────────┘               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MAC (DESKTOP)                                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Vision Pipeline (vision/main.py)                        │  │
│  │  • Overhead camera (index 2)                             │  │
│  │  • ArUco grid detection (IDs 0-3 corners, ID 4 robot)   │  │
│  │  • YOLO11 object detection                               │  │
│  │  • Gemini scene interpretation                           │  │
│  │  • A* path planning with waypoints                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Whisper Server (whisper_server.py)                      │  │
│  │  • WebSocket ASR server on port 8765                     │  │
│  │  • faster-whisper with streaming                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
DeskClaw/
├── OpenClaw/                        # Voice assistant
│   ├── voice_client.py              # Pi voice client (mic → whisper → LLM → TTS)
│   ├── whisper_server.py            # WebSocket ASR server (runs on Mac)
│   ├── SOUL.md                      # AI personality / system prompt
│   ├── USER.md                      # User context
│   ├── main.py                      # Config loader with env var resolution
│   ├── setup.sh                     # Raspberry Pi setup script
│   ├── play_response.sh             # Play audio via mpg123
│   ├── requirements.txt             # All Python dependencies
│   ├── requirements-client.txt      # Pi-only dependencies
│   ├── requirements-server.txt      # Whisper server dependencies
│   └── whisper_streaming/           # UFAL whisper_streaming (git submodule)
│
├── vision/                          # Computer vision (runs on Mac)
│   ├── main.py                      # Main loop: camera → ArUco → YOLO → path planning
│   ├── aruco_grid.py                # ArUco marker detection, grid homography, robot pose
│   ├── yolo_detection.py            # YOLO11n object detection
│   ├── path_planning.py             # A* path planner, waypoint simplification
│   └── gemini_interpretation.py     # Gemini crop-based scene descriptions
│
├── firmware/
│   ├── raspberryPi/                 # Robot hardware control (runs on Pi)
│   │   ├── rover_api.py             # FastAPI server: /forward, /turn, /stop
│   │   ├── rover_drive.py           # L298N motor driver via GPIO
│   │   ├── pickup_controller.py     # Full pickup orchestration
│   │   ├── arm_pickup.py            # Arduino serial interface
│   │   └── webcam.py                # On-board webcam for arm guidance
│   └── arm_control/
│       └── arm_control.ino          # Arduino firmware (servos, IK, ultrasonic)
│
├── ArUco_vision/                    # Camera calibration data
└── .env                             # API keys (not committed)
```

## Hardware

| Component | Model | Connection |
|---|---|---|
| Single-board computer | Raspberry Pi | — |
| Microphone | Nulea C905 webcam mic | USB |
| Speaker | JBL Go 3 | Bluetooth |
| Overhead camera | Webcam (index 2) | USB to Mac |
| Rover motors | L298N motor driver | GPIO |
| Claw arm | Servo-based, 5-DOF | Arduino via USB serial |
| ArUco markers | 4x4_50 dict, IDs 0-3 (grid), ID 4 (robot) | Printed, camera-visible |

## Frameworks & Libraries

| Purpose | Library |
|---|---|
| Rover HTTP API | FastAPI, Pydantic |
| Object detection | Ultralytics (YOLO11n) |
| Computer vision | OpenCV (ArUco, homography) |
| Scene interpretation | google-genai (Gemini 2.5 Flash) |
| Speech-to-text | faster-whisper |
| Text-to-speech | ElevenLabs REST API |
| Audio capture | sounddevice, NumPy |
| Networking | websockets, requests |
| Config | python-dotenv |
| Hardware (Pi) | RPi.GPIO, pyserial |

## Prerequisites

- **Raspberry Pi** with Raspberry Pi OS
- **Mac/Desktop** with Python 3.11+ and webcam
- **Arduino** with arm_control firmware flashed

### API Keys

Create a `.env` file in the project root:

```
ELEVENLABS_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

## Setup

### Raspberry Pi

```bash
cd OpenClaw
chmod +x setup.sh
./setup.sh
```

The setup script handles:
1. System package updates
2. Audio dependencies (PulseAudio, Bluetooth, ALSA, mpg123)
3. Python venv + dependencies
4. JBL Go 3 Bluetooth pairing
5. Audio device configuration (mic + speaker)

### Mac (Whisper Server + Vision)

```bash
python3 -m venv venv
source venv/bin/activate
pip install faster-whisper websockets numpy

# For vision pipeline
pip install opencv-python ultralytics google-genai python-dotenv Pillow
```

### Arduino

Flash `firmware/arm_control/arm_control.ino` to the Arduino via the Arduino IDE. Connect to the Pi via USB serial (`/dev/ttyUSB0`).

## Running

### 1. Start the Whisper Server (Mac)

```bash
cd OpenClaw
source venv/bin/activate
python whisper_server.py --host 0.0.0.0 --port 8765 --model tiny.en
```

### 2. Start the Vision Pipeline (Mac)

```bash
cd vision
source ../venv/bin/activate
python main.py
```

- Press `w` to trigger Gemini scene analysis
- Type an object name (e.g. `bottle`) to plan a path
- Type `clear path` to reset
- Press `q` to quit

### 3. Start the Rover API (Pi)

```bash
cd firmware/raspberryPi
uvicorn rover_api:app --host 0.0.0.0 --port 8000
```

### 4. Start the Voice Client (Pi)

```bash
cd OpenClaw
source venv/bin/activate
python voice_client.py
```

Say **"Hey Claw"** followed by your command.

## Configuration

Environment variables are loaded from `.env` in the project root. The voice client reads `SOUL.md` for the AI personality and `USER.md` for user context.

## Rover API

The FastAPI server runs on the Pi at port 8000.

| Endpoint | Method | Body | Description |
|---|---|---|---|
| `/forward` | POST | `{"duration": 1.5}` | Drive forward (0-5 seconds) |
| `/turn` | POST | `{"direction": "left", "duration": 0.5}` | Turn left or right (0-3 seconds) |
| `/stop` | POST | — | Stop all motors |

## Verification

```bash
# Test microphone (Pi)
arecord -d 5 -f cd test.wav && aplay test.wav

# Test speaker (Pi)
mpg123 /path/to/any.mp3

# List audio sources/sinks (Pi)
pactl list sources short
pactl list sinks short

# Test rover API (Pi)
curl -X POST http://localhost:8000/stop
```
