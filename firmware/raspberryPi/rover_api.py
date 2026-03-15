"""
OpenClaw Rover API
FastAPI server exposing rover movement as POST endpoints.
Run on the Pi: uvicorn rover_api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from rover_drive import RoverDrive

rover: RoverDrive = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global rover
    rover = RoverDrive()
    print("Rover GPIO initialized")
    yield
    rover.cleanup()
    print("Rover GPIO cleaned up")

app = FastAPI(title="OpenClaw Rover", lifespan=lifespan)


class ForwardRequest(BaseModel):
    duration: float = Field(..., gt=0, le=5.0, description="Seconds to drive forward")


class TurnRequest(BaseModel):
    direction: str = Field(..., pattern="^(left|right)$", description="Turn direction: left or right")
    duration: float = Field(..., gt=0, le=3.0, description="Seconds to turn")


@app.post("/forward")
def drive_forward(req: ForwardRequest):
    rover.forward(duration=req.duration)
    return {"action": "forward", "duration": req.duration}


@app.post("/turn")
def turn(req: TurnRequest):
    if req.direction == "left":
        rover.turn_left(duration=req.duration)
    else:
        rover.turn_right(duration=req.duration)
    return {"action": f"turn_{req.direction}", "duration": req.duration}


@app.post("/stop")
def stop():
    rover.stop()
    return {"action": "stop"}
