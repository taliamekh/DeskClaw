# Basic Pi Voice Agent Loop

This is a lightweight standalone loop (not OpenClaw gateway) that runs on Raspberry Pi:

1. Streams mic audio to faster-whisper websocket server.
2. Waits for wake phrase.
3. Parses command intent (find/pickup).
4. Maps user description to current vision label using an LLM API.
5. Requests path planning from vision API (`POST /plan`).
6. Polls robot/path state until arrival.
7. Runs pickup flow (`pickup_controller`) or dry-run stub.
8. If user asked to "bring it back", follows reverse path after pickup.

## Where the movement loop is

In `basic_agent_loop.py`:

- `VoicePickupAgent.follow_planned_path(...)`
  - This is the integrated waypoint-following loop.
  - It reads `/path` + `/robot`, advances waypoint index, and decides turn/forward steps.
- `VoicePickupAgent._cmd_turn_toward_heading(...)`
- `VoicePickupAgent._cmd_drive_forward(...)`

Those two methods are intentionally boilerplate placeholders right now.
Put your real motor/servo drive calls there.

## Arduino drive serial protocol

`basic_agent_loop.py` now supports direct serial movement commands:

- `d<number>` => forward motion duration in 100 ms ticks
- `l<number>` / `r<number>` => left/right turn units, clamped to `1..1000`

Config fields in `pi_agent_config.json`:

- `drive.serial_port`
- `drive.baud`
- `drive.forward_step_cm`
- `drive.turn_min_abs_deg`
- `drive.turn_units_per_deg`
- `drive.command_cooldown_sec`

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
  - `{"goal_type": "corner", "corner": "top_left", "target_name": "top_left"}`
  - `{"goal_type": "point", "mode": "cm", "target_name": "point_target", "target_point": {"x": 20, "y": -10}}`
  - `{"clear": true}`

## Example voice commands

- "hey claw pick up the bottle"
- "hey claw pick up the bottle and bring it back"
- "hey claw move to top left corner"
- "hey claw move to x 20 y -10"

