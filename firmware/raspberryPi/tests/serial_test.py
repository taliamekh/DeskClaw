"""
Raw serial test — sends commands and prints Arduino responses.
Run: python tests/serial_test.py
"""
import serial
import time

PORT = "/dev/ttyACM0"
print(f"Opening {PORT}...")
ser = serial.Serial(PORT, 9600, timeout=2)
time.sleep(2)  # wait for Arduino reset

# Read startup message
startup = ser.read(ser.in_waiting or 1)
print(f"Startup: {startup.decode().strip()}")

commands = ["5", "0", "-45", "0", "10", "0"]
for cmd in commands:
    print(f"\nSending: {cmd}")
    ser.write(f"{cmd}\n".encode())
    time.sleep(0.5)
    resp = ser.readline().decode().strip()
    print(f"Response: '{resp}'")
    time.sleep(2)

ser.close()
print("\nDone.")
