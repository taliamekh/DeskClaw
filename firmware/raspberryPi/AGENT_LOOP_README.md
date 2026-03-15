# Basic Pi Voice Agent Loop

This is a lightweight standalone loop (not OpenClaw gateway) that runs on Raspberry Pi:

1. Streams mic audio to faster-whisper websocket server.
2. Waits for wake phrase.
3. Parses command intent (find/pickup).
4. Maps user description to current vision label using an LLM API.
5. Requests path planning from vision API (`POST /plan`).
6. Polls robot/path state until arrival.
7. Runs pickup flow (`pickup_controller`) or dry-run stub.

## Files

- `basic_agent_loop.py` - main loop
- `pi_agent_config.json` - runtime config
- `tests/test_basic_agent_loop.py` - small local tests

## Prerequisites

- Whisper server running (see `OpenClaw/whisper_server.py`) on your fast machine.
- Vision loop running (`vision/main.py`) with API enabled.
- Pi has mic configured as default input.
- LLM API key env var set (default: `OPENAI_API_KEY`).

## Configure

Edit `pi_agent_config.json`:

- `stt.whisper_server`
- `vision.api_base`
- wake phrase / timing / nav thresholds
- LLM endpoint/model/env key
- pickup dry-run / hardware settings

## Run

```bash
cd /Users/nathannguyen/Documents/coding/hackathon/DeskClaw/firmware/raspberryPi
python basic_agent_loop.py --config pi_agent_config.json
```

## Test Harness

```bash
cd /Users/nathannguyen/Documents/coding/hackathon/DeskClaw/firmware/raspberryPi
python -m unittest tests.test_basic_agent_loop -v
```

## Vision API endpoints used

- `GET /objects`
- `GET /robot`
- `GET /path`
- `POST /plan` with either:
  - `{"target_name": "bottle"}`
  - `{"clear": true}`

