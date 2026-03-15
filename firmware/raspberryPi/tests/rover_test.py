"""
Rover drive test — sends timed commands to Arduino.
Run from firmware/raspberryPi/: python tests/rover_test.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rover_drive import RoverDrive

with RoverDrive() as rover:
    print("Forward 2s...")
    print(rover.forward(ms=2000))

    print("Backward 1s...")
    print(rover.backward(ms=1000))

    print("Left 500ms...")
    print(rover.turn_left(ms=500))

    print("Right 500ms...")
    print(rover.turn_right(ms=500))

    print("Done.")
