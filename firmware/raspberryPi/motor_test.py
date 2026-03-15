"""
Motor Direction Test — forward, backward, left, right.
Uses direct GPIO (no PWM) since that's confirmed working.
"""

import RPi.GPIO as GPIO
import time

ENA = 13
IN1 = 22
IN2 = 27
IN3 = 23
IN4 = 24
ENB = 12

DURATION = 2

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for pin in [ENA, IN1, IN2, IN3, IN4, ENB]:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

# Enable both motors (direct HIGH, no PWM)
GPIO.output(ENA, GPIO.HIGH)
GPIO.output(ENB, GPIO.HIGH)

def stop():
    for pin in [IN1, IN2, IN3, IN4]:
        GPIO.output(pin, GPIO.LOW)

def run(name, in1, in2, in3, in4):
    print(f"{name}...", flush=True)
    GPIO.output(IN1, GPIO.HIGH if in1 else GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH if in2 else GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH if in3 else GPIO.LOW)
    GPIO.output(IN4, GPIO.HIGH if in4 else GPIO.LOW)
    time.sleep(DURATION)
    stop()
    time.sleep(0.5)

print("=== DIRECTION TEST ===\n")

try:
    run("FORWARD",    True,  False, True,  False)
    run("BACKWARD",   False, True,  False, True)
    run("TURN LEFT",  False, True,  True,  False)
    run("TURN RIGHT", True,  False, False, True)
    print("All done!")

except KeyboardInterrupt:
    print("\nStopped")
finally:
    stop()
    GPIO.cleanup()
