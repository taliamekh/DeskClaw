"""
OpenClaw Rover Drive Module
Controls rover motors via L298N H-bridge on Raspberry Pi GPIO.
No pathfinding — only exposes movement primitives to be called externally.

Pin mapping:
  ENA - Pin 17 (PWM speed, left motor)
  IN1 - Pin 22
  IN2 - Pin 27
  IN3 - Pin 23
  IN4 - Pin 24
  ENB - Pin 25 (PWM speed, right motor)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
ENA = 17
IN1 = 22
IN2 = 27
IN3 = 23
IN4 = 24
ENB = 25

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

        self._pwm_a = GPIO.PWM(ENA, PWM_FREQ)
        self._pwm_b = GPIO.PWM(ENB, PWM_FREQ)
        self._pwm_a.start(0)
        self._pwm_b.start(0)

    def _set_motors(self, left_fwd, left_bwd, right_fwd, right_bwd, speed=None):
        spd = speed if speed is not None else self.speed
        GPIO.output(IN1, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH if left_bwd else GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH if right_fwd else GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH if right_bwd else GPIO.LOW)
        self._pwm_a.ChangeDutyCycle(spd)
        self._pwm_b.ChangeDutyCycle(spd)

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
        """Gentle left arc (right motor faster than left)."""
        spd = speed if speed is not None else self.speed
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        self._pwm_a.ChangeDutyCycle(max(spd - 30, 10))  # Left slower
        self._pwm_b.ChangeDutyCycle(spd)                 # Right full
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_right(self, duration=None, speed=None):
        """Gentle right arc (left motor faster than right)."""
        spd = speed if speed is not None else self.speed
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        self._pwm_a.ChangeDutyCycle(spd)                 # Left full
        self._pwm_b.ChangeDutyCycle(max(spd - 30, 10))  # Right slower
        if duration:
            time.sleep(duration)
            self.stop()

    def stop(self):
        """Stop all motors."""
        self._set_motors(False, False, False, False, 0)

    def set_speed(self, speed):
        """Set default speed (0-100)."""
        self.speed = max(0, min(100, speed))

    def cleanup(self):
        """Release GPIO resources."""
        self.stop()
        self._pwm_a.stop()
        self._pwm_b.stop()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
