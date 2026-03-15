"""
Raw lgpio motor test — bypasses RPi.GPIO shim entirely.
Tests each pin individually, then runs forward for 3 seconds.

Run: sudo python tests/raw_lgpio_test.py
(may need sudo for GPIO access on Pi 5)
"""
import lgpio
import time

IN1 = 27  # left motor
IN2 = 17  # left motor
IN3 = 23  # right motor
IN4 = 24  # right motor
PINS = [IN1, IN2, IN3, IN4]
NAMES = {IN1: "IN1(27)", IN2: "IN2(17)", IN3: "IN3(23)", IN4: "IN4(24)"}

print("Opening gpiochip0...")
h = lgpio.gpiochip_open(0)
print(f"Handle: {h}")

# Claim all pins as output, start LOW
for pin in PINS:
    lgpio.gpio_claim_output(h, pin, 0)
    print(f"  Claimed {NAMES[pin]} as output, set LOW")

print()

# Test each pin individually for 2 seconds
for pin in PINS:
    print(f"Setting {NAMES[pin]} HIGH for 2s...")
    lgpio.gpio_write(h, pin, 1)
    time.sleep(2)
    lgpio.gpio_write(h, pin, 0)
    print(f"  {NAMES[pin]} back to LOW")
    time.sleep(0.5)

print()
print("Now testing FORWARD (IN2+IN4 HIGH) for 3s...")
lgpio.gpio_write(h, IN2, 1)
lgpio.gpio_write(h, IN4, 1)
time.sleep(3)

# Stop
for pin in PINS:
    lgpio.gpio_write(h, pin, 0)
print("Stopped.")

lgpio.gpiochip_close(h)
print("Done. Chip closed.")
