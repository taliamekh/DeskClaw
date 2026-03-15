"""
Motor Test — runs each motor direction for 2 seconds on startup.
Tests: forward, backward, left turn, right turn.
If nothing moves, check wiring and power supply.
"""

import RPi.GPIO as GPIO
import time

# Pin definitions — must match rover_drive.py
ENA = 17
IN1 = 22
IN2 = 27
IN3 = 23
IN4 = 24
ENB = 25

SPEED = 70  # Duty cycle 0-100
DURATION = 2  # Seconds per test

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [ENA, IN1, IN2, IN3, IN4, ENB]:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    pwm_a = GPIO.PWM(ENA, 1000)
    pwm_b = GPIO.PWM(ENB, 1000)
    pwm_a.start(SPEED)
    pwm_b.start(SPEED)
    return pwm_a, pwm_b

def stop_all():
    for pin in [IN1, IN2, IN3, IN4]:
        GPIO.output(pin, GPIO.LOW)

def test(name, in1, in2, in3, in4):
    print(f"{name}...", end=" ", flush=True)
    GPIO.output(IN1, in1)
    GPIO.output(IN2, in2)
    GPIO.output(IN3, in3)
    GPIO.output(IN4, in4)
    time.sleep(DURATION)
    stop_all()
    print("done")
    time.sleep(0.5)

print("=== MOTOR TEST ===")
print(f"Speed: {SPEED}%  Duration: {DURATION}s per test\n")

try:
    pwm_a, pwm_b = setup()

    test("FORWARD",     GPIO.HIGH, GPIO.LOW,  GPIO.HIGH, GPIO.LOW)
    test("BACKWARD",    GPIO.LOW,  GPIO.HIGH, GPIO.LOW,  GPIO.HIGH)
    test("TURN LEFT",   GPIO.LOW,  GPIO.HIGH, GPIO.HIGH, GPIO.LOW)
    test("TURN RIGHT",  GPIO.HIGH, GPIO.LOW,  GPIO.LOW,  GPIO.HIGH)

    # Test individual motors
    print("\nLeft motor only (forward)...", end=" ", flush=True)
    GPIO.output(IN1, GPIO.HIGH)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.LOW)
    GPIO.output(IN4, GPIO.LOW)
    time.sleep(DURATION)
    stop_all()
    print("done")

    print("Right motor only (forward)...", end=" ", flush=True)
    GPIO.output(IN1, GPIO.LOW)
    GPIO.output(IN2, GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH)
    GPIO.output(IN4, GPIO.LOW)
    time.sleep(DURATION)
    stop_all()
    print("done")

    print("\n=== TEST COMPLETE ===")

except KeyboardInterrupt:
    print("\nInterrupted")
finally:
    stop_all()
    try:
        pwm_a.stop()
        pwm_b.stop()
    except Exception:
        pass
    GPIO.cleanup()
