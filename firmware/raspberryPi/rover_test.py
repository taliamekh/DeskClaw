"""
OpenClaw Rover + Webcam Test
Webcam detects an object, rover drives toward it.
Object left of center → turn left. Right → turn right. Centered → drive forward.
Press Ctrl+C to stop.
"""

from webcam import WebcamGuide
from rover_drive import RoverDrive
import time

# Tuning
CENTER_TOL = 50       # Pixels from center to consider "centered"
CLOSE_AREA = 40000    # Object area threshold to stop (close enough)
DRIVE_SPEED = 45
TURN_SPEED = 40
STEP_SEC = 0.3        # Duration of each movement step


def run():
    cam = WebcamGuide(camera_index=0)
    rover = RoverDrive(speed=DRIVE_SPEED)

    if not cam.open():
        print("Failed to open webcam")
        return

    print("=== ROVER WEBCAM TEST ===")
    print(f"Center tolerance: {CENTER_TOL}px")
    print(f"Close enough area: {CLOSE_AREA}px")
    print("Ctrl+C to stop\n")

    try:
        while True:
            g = cam.guide_step()

            if not g["found"]:
                rover.stop()
                print("No object — stopped")
                time.sleep(0.3)
                continue

            dx, area = g["dx"], g["area"]
            print(f"dx={dx:+4d}  area={area:6d}", end="  ")

            # Close enough — stop
            if area >= CLOSE_AREA:
                rover.stop()
                print(">> CLOSE ENOUGH — stopped")
                time.sleep(0.5)
                continue

            # Steer toward object
            if dx < -CENTER_TOL:
                rover.turn_left(duration=STEP_SEC, speed=TURN_SPEED)
                print(">> turning left")
            elif dx > CENTER_TOL:
                rover.turn_right(duration=STEP_SEC, speed=TURN_SPEED)
                print(">> turning right")
            else:
                rover.forward(duration=STEP_SEC, speed=DRIVE_SPEED)
                print(">> driving forward")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        rover.cleanup()
        cam.close()
        print("Test complete.")


if __name__ == "__main__":
    run()
