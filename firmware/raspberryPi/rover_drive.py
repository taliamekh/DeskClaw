"""
OpenClaw Rover Drive Module
Controls rover motors via L298N H-bridge on Raspberry Pi GPIO.
No pathfinding — only exposes movement primitives to be called externally.

Pin mapping (ENA/ENB jumpered on L298N):
  IN1 - GPIO 17 (left motor)
  IN2 - GPIO 27 (left motor)
  IN3 - GPIO 23 (right motor)
  IN4 - GPIO 24 (right motor)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
IN1 = 27
IN2 = 17
IN3 = 24  # swapped to test
IN4 = 23  # swapped to test

DEFAULT_SPEED = 60


class RoverDrive:
    def __init__(self, speed=DEFAULT_SPEED):
        self.speed = speed
        self._setup()

    def _setup(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in [IN1, IN2, IN3, IN4]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def _set_motors(self, left_fwd, left_bwd, right_fwd, right_bwd, speed=None):
        # Actual wiring (verified by testing):
        # IN2 (GPIO 17) = OUT1/2 (left motor) forward
        # IN1 (GPIO 27) = OUT1/2 (left motor) backward
        # IN4 (GPIO 23) = OUT3/4 (right motor) forward
        # IN3 (GPIO 24) = OUT3/4 (right motor) backward
        GPIO.output(IN1, GPIO.HIGH if left_bwd else GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH if right_bwd else GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH if right_fwd else GPIO.LOW)

    # --- Movement primitives ---

    def forward(self, duration=None, speed=None):
        """Move forward. If duration given, stops after that many seconds."""
        self._set_motors(True, False, True, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def backward(self, duration=None, speed=None):
        """Move backward."""
        self._set_motors(False, True, False, True, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_left(self, duration=None, speed=None):
        """Turn left in place (right motor forward, left motor back)."""
        self._set_motors(False, True, True, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_right(self, duration=None, speed=None):
        """Turn right in place (left motor forward, right motor back)."""
        self._set_motors(True, False, False, True, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_left(self, duration=None, speed=None):
        """Gentle left arc (right motor forward only)."""
        self._set_motors(False, False, True, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_right(self, duration=None, speed=None):
        """Gentle right arc (left motor forward only)."""
        self._set_motors(True, False, False, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def stop(self):
        """Stop all motors."""
        for pin in [IN1, IN2, IN3, IN4]:
            GPIO.output(pin, GPIO.LOW)

    def set_speed(self, speed):
        pass

    def cleanup(self):
        self.stop()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
