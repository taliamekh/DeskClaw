"""
Raw serial test for new protocol.
Run: python tests/serial_test.py
"""
import serial
import time

PORT = "/dev/ttyACM0"
print(f"Opening {PORT}...")
ser = serial.Serial(PORT, 9600, timeout=5)
time.sleep(2)

startup = ser.read(ser.in_waiting or 1)
print(f"Startup: {startup.decode().strip()}")

commands = ["d2000", "s", "l500", "s", "r500", "s"]
for cmd in commands:
    print(f"\nSending: {cmd}")
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.1)
    # Read all responses until timeout
    while True:
        line = ser.readline().decode().strip()
        if not line:
            break
        print(f"  Response: {line}")
    time.sleep(1)

ser.close()
print("\nDone.")
