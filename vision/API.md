# Vision API

`vision/main.py` now exposes a lightweight HTTP API for OpenClaw scripts.

## Endpoints

- `GET /objects` (also `/api/objects`)
  - Returns current in-grid detections and unique labels.
- `GET /robot` (also `/api/robot`)
  - Returns current robot pose/heading data from ArUco tracking.
- `GET /path` (also `/api/path`)
  - Returns current planned waypoint path and heading sequence.
- `POST /plan` (also `/api/plan`)
  - Queue or clear path planning requests.
  - Body: `{"target_name": "bottle"}` to plan.
  - Body: `{"clear": true}` to clear.

## Defaults

- Host: `0.0.0.0`
- Port: `8787`

Override with environment variables:

- `VISION_API_HOST`
- `VISION_API_PORT`

## Quick Check

Run vision:

```bash
python main.py
```

Then in another terminal:

```bash
python test_api_endpoints.py
```

