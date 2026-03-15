"""
OpenClaw Rover Drive Module
Controls rover motors via Arduino over USB serial (UART).

Protocol — Pi sends an integer string terminated by newline:
  -10 to +10  : straight (neg=backward, pos=forward, 0=stop, magnitude=speed)
  -11 to -180 : left turn  (magnitude = sharpness)
  +11 to +180 : right turn (magnitude = sharpness)
"""

import serial
import time
import glob


def _find_arduino(preferred="/dev/uno_drive"):
    """Auto-detect Arduino serial port."""
    for port in [preferred] + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"):
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
        self.ser = serial.Serial(self.port, 9600, timeout=1)
        time.sleep(2)  # wait for Arduino reset
        self.ser.read(self.ser.in_waiting or 1)  # drain startup msg

    def send(self, value):
        """Send steering integer to Arduino. Returns Arduino response."""
        value = max(-180, min(180, int(value)))
        self.ser.write(f"{value}\n".encode())
        time.sleep(0.05)
        return self.ser.readline().decode().strip()

    # --- Movement primitives (same interface as before) ---

    def forward(self, duration=None, speed=5):
        """Move forward. speed: 1-10."""
        self.send(max(1, min(10, speed)))
        if duration:
            time.sleep(duration)
            self.stop()

    def backward(self, duration=None, speed=5):
        """Move backward. speed: 1-10."""
        self.send(-max(1, min(10, speed)))
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_left(self, duration=None, angle=45):
        """Turn left. angle: 11-180."""
        self.send(-max(11, min(180, angle)))
        if duration:
            time.sleep(duration)
            self.stop()

    def turn_right(self, duration=None, angle=45):
        """Turn right. angle: 11-180."""
        self.send(max(11, min(180, angle)))
        if duration:
            time.sleep(duration)
            self.stop()

    def stop(self):
        """Stop all motors."""
        self.send(0)

    def cleanup(self):
        self.stop()
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
