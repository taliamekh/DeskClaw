"""
OpenClaw Rover Drive Module
Controls rover motors via Arduino over USB serial (UART 9600).

Protocol: "<cmd><ms>\\n"
  d<ms> = drive forward for <ms> milliseconds
  b<ms> = drive backward for <ms> milliseconds
  l<ms> = turn left for <ms> milliseconds
  r<ms> = turn right for <ms> milliseconds
  s     = stop immediately
"""

import serial
import time
import glob


def _find_arduino(preferred="/dev/uno_drive"):
    """Auto-detect Arduino serial port."""
    for port in [preferred] + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"):
        try:
            s = serial.Serial(port, 9600, timeout=1)
            s.close()
            return port
        except (serial.SerialException, OSError):
            continue
    return None


class RoverDrive:
    def __init__(self, port=None):
        self.port = port or _find_arduino()
        if not self.port:
            raise RuntimeError("No Arduino found. Check USB connection.")
        self.ser = serial.Serial(self.port, 9600, timeout=2)
        time.sleep(2)  # wait for Arduino reset
        self.ser.read(self.ser.in_waiting or 1)

    def send(self, cmd):
        """Send command string, return Arduino response."""
        self.ser.write(f"{cmd}\n".encode())
        # Wait for OK:DONE (motor runs on Arduino side)
        responses = []
        while True:
            line = self.ser.readline().decode().strip()
            if not line:
                break
            responses.append(line)
            if line == "OK:DONE" or line.startswith("ERR"):
                break
        return responses

    # --- Movement primitives ---

    def forward(self, ms=1000):
        """Drive forward for ms milliseconds."""
        return self.send(f"d{ms}")

    def backward(self, ms=1000):
        """Drive backward for ms milliseconds."""
        return self.send(f"b{ms}")

    def turn_left(self, ms=500):
        """Turn left for ms milliseconds."""
        return self.send(f"l{ms}")

    def turn_right(self, ms=500):
        """Turn right for ms milliseconds."""
        return self.send(f"r{ms}")

    def stop(self):
        """Stop immediately."""
        self.ser.write(b"s\n")
        return self.ser.readline().decode().strip()

    def cleanup(self):
        self.stop()
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
