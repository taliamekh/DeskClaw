"""
Rover drive test — sends encoded commands to Arduino over serial.
Run from firmware/raspberryPi/: python tests/rover_test.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rover_drive import RoverDrive

with RoverDrive() as rover:
    print("Forward (speed 5) 2s...")
    rover.forward(duration=2, speed=5)

    print("Backward (speed 3) 1s...")
    rover.backward(duration=1, speed=3)

    print("Left turn (45°) 1s...")
    rover.turn_left(duration=1, angle=45)

    print("Right turn (90°) 1s...")
    rover.turn_right(duration=1, angle=90)

    print("Raw send: full speed forward (10)...")
    resp = rover.send(10)
    print(f"  Arduino: {resp}")
    import time
    time.sleep(2)

    print("Stop.")
    rover.stop()
    print("Done.")
