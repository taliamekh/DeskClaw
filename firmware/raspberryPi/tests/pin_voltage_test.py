"""
Pin voltage hold test — sets IN1 HIGH and holds it for 30 seconds.
While this runs, measure voltage on GPIO 27 with a multimeter.
Should read ~3.3V if the pin is actually outputting.

Run: sudo python tests/pin_voltage_test.py
"""
import lgpio
import time

PIN = 27  # IN1

print(f"Opening gpiochip0 and setting GPIO {PIN} HIGH for 30 seconds...")
print("Measure voltage on this pin NOW with a multimeter.")
print("Expected: ~3.3V if working, 0V if broken.\n")

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, PIN, 0)

lgpio.gpio_write(h, PIN, 1)
print(f"GPIO {PIN} is HIGH. Measure now...")

for i in range(30, 0, -1):
    print(f"  {i}s remaining...", end='\r')
    time.sleep(1)

lgpio.gpio_write(h, PIN, 0)
lgpio.gpiochip_close(h)
print("\nGPIO set LOW. Chip closed.")
