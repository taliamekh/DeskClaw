"""
OpenClaw Rover Drive Module
Controls rover motors via L298N H-bridge on Raspberry Pi GPIO.
No pathfinding — only exposes movement primitives to be called externally.

Pin mapping (ENA/ENB jumpered on L298N):
  IN1 - GPIO 27 (left motor)
  IN2 - GPIO 17 (left motor)
  IN3 - GPIO 23 (right motor)
  IN4 - GPIO 24 (right motor)

Direction note (based on observed hardware behavior):
  _set_motors maps: IN1=left_fwd, IN2=left_bwd, IN3=right_fwd, IN4=right_bwd
  But the actual motor wiring is reversed, so movement methods
  swap True/False to match real-world directions.
"""

import RPi.GPIO as GPIO
import time

# Pin definitions — CONFIRMED CORRECT, do not change
IN1 = 27
IN2 = 17
IN3 = 23
IN4 = 24

DEFAULT_SPEED = 60


def _force_pins_low():
    """Use lgpio directly to force all motor pins LOW.
    Works around rpi-lgpio cleanup bug where pins stay stuck HIGH."""
    try:
        import lgpio
        h = lgpio.gpiochip_open(0)
        for pin in [IN1, IN2, IN3, IN4]:
            lgpio.gpio_claim_output(h, pin, 0)
            lgpio.gpio_write(h, pin, 0)
        lgpio.gpiochip_close(h)
    except Exception:
        pass  # Fall through to normal GPIO setup


class RoverDrive:
    def __init__(self, speed=DEFAULT_SPEED):
        self.speed = speed
        self._setup()

    def _setup(self):
        _force_pins_low()
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in [IN1, IN2, IN3, IN4]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def _set_motors(self, left_fwd, left_bwd, right_fwd, right_bwd, speed=None):
        GPIO.output(IN1, GPIO.HIGH if left_fwd else GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH if left_bwd else GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH if right_fwd else GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH if right_bwd else GPIO.LOW)

    # --- Movement primitives ---

    def forward(self, duration=None, speed=None):
        """Move forward. If duration given, stops after that many seconds."""
        self._set_motors(False, True, False, True, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def backward(self, duration=None, speed=None):
        """Move backward."""
        self._set_motors(True, False, True, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_left(self, duration=None, speed=None):
        """Turn left in place (right motor forward, left motor back)."""
        self._set_motors(True, False, False, True, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_right(self, duration=None, speed=None):
        """Turn right in place (left motor forward, right motor back)."""
        self._set_motors(False, True, True, False, speed)
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_left(self, duration=None, speed=None):
        """Gentle left arc (right motor only)."""
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        if duration:
            time.sleep(duration)
            self.stop()

    def arc_right(self, duration=None, speed=None):
        """Gentle right arc (left motor only)."""
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
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
        pass

    def cleanup(self):
        self.stop()
        _force_pins_low()
        GPIO.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
