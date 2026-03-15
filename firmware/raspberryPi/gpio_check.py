"""
GPIO Diagnostic — checks if Pi pins are actually outputting HIGH.
Run this and use a multimeter on the pins to verify voltage.
"""

import RPi.GPIO as GPIO
import time

PINS = {"ENA": 17, "IN1": 22, "IN2": 27, "IN3": 23, "IN4": 24, "ENB": 25}

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for name, pin in PINS.items():
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

print("=== GPIO DIAGNOSTIC ===")
print("Setting each pin HIGH for 3 seconds.")
print("Measure voltage on each pin with a multimeter (should read ~3.3V)\n")

try:
    for name, pin in PINS.items():
        print(f"Pin {pin} ({name}) → HIGH", flush=True)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(3)
        GPIO.output(pin, GPIO.LOW)
        print(f"Pin {pin} ({name}) → LOW\n")

    # Now set IN1+ENA HIGH together (should spin left motor)
    print("IN1 + ENA HIGH together (left motor should spin)...")
    GPIO.output(PINS["IN1"], GPIO.HIGH)
    GPIO.output(PINS["ENA"], GPIO.HIGH)
    time.sleep(3)
    GPIO.output(PINS["IN1"], GPIO.LOW)
    GPIO.output(PINS["ENA"], GPIO.LOW)

    # IN3+ENB HIGH together (should spin right motor)
    print("IN3 + ENB HIGH together (right motor should spin)...")
    GPIO.output(PINS["IN3"], GPIO.HIGH)
    GPIO.output(PINS["ENB"], GPIO.HIGH)
    time.sleep(3)
    GPIO.output(PINS["IN3"], GPIO.LOW)
    GPIO.output(PINS["ENB"], GPIO.LOW)

    print("\nDone. If no movement, check:")
    print("1. L298N has its own 12V power supply connected")
    print("2. L298N GND is shared with Pi GND")
    print("3. ENA/ENB jumpers are removed (if using PWM)")
    print("4. Motor wires are connected to OUT1/OUT2 and OUT3/OUT4")

except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
