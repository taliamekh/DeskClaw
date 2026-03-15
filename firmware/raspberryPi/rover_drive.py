"""
OpenClaw Rover Drive Module
Controls rover motors via L298N H-bridge on Raspberry Pi GPIO.
No pathfinding — only exposes movement primitives to be called externally.

Pin mapping:
  ENA - Pin 13 (left motor enable)
  IN1 - Pin 22
  IN2 - Pin 27
  IN3 - Pin 23
  IN4 - Pin 24
  ENB - Pin 12 (right motor enable)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
ENA = 13
IN1 = 22
IN2 = 27
IN3 = 23
IN4 = 24
ENB = 12

# Default speed (0-100)
DEFAULT_SPEED = 60
PWM_FREQ = 1000


class RoverDrive:
    def __init__(self, speed=DEFAULT_SPEED):
        self.speed = speed
        self._pwm_a = None
        self._pwm_b = None
        self._setup()

    def _setup(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in [ENA, IN1, IN2, IN3, IN4, ENB]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        # Enable both motors with direct HIGH (PWM not needed)
        GPIO.output(ENA, GPIO.HIGH)
        GPIO.output(ENB, GPIO.HIGH)

    def _set_motors(self, left_fwd, left_bwd, right_fwd, right_bwd, speed=None):
        GPIO.output(IN1, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH if left_bwd else GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH if right_fwd else GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH if right_bwd else GPIO.LOW)

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
        """Gentle left arc (right motor only)."""
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_right(self, duration=None, speed=None):
        """Gentle right arc (left motor only)."""
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.LOW)
        if duration:
            time.sleep(duration)
            self.stop()

    def stop(self):
        """Stop all motors."""
        for pin in [IN1, IN2, IN3, IN4]:
            GPIO.output(pin, GPIO.LOW)

    def set_speed(self, speed):
        """No-op — speed control removed (direct GPIO mode)."""
        pass

    def cleanup(self):
        """Release GPIO resources."""
        self.stop()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
