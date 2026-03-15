"""
Rover drive test — forward, left, right, then stop.
Run from firmware/raspberryPi/: python tests/rover_test.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rover_drive import RoverDrive

rover = RoverDrive()
try:
    print("Forward 2s...")
    rover.forward(duration=2)
    print("Left 1s...")
    rover.turn_left(duration=1)
    print("Right 1s...")
    rover.turn_right(duration=1)
    print("Done.")
finally:
    rover.cleanup()
