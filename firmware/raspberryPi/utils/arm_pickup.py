"""
OpenClaw Arm Serial Interface
Talks to Arduino over serial. Only sends commands, reads responses.
No webcam, no pickup logic — just the serial bridge.
"""

import serial
import time

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 9600


class ArmController:
    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        self.ser = None
        self.port = port
        self.baud = baud

    def connect(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=2)
        time.sleep(2)
        while self.ser.in_waiting:
            self.ser.readline()

    def disconnect(self):
        if self.ser:
            self.ser.close()

    def send(self, command):
        self.ser.write(f"{command}\n".encode())
        time.sleep(0.1)
        resp = ""
        while self.ser.in_waiting:
            resp += self.ser.readline().decode().strip() + "\n"
        return resp.strip()

    def home(self):
        return self.send("HOME")

    def open_claw(self):
        return self.send("OPEN")

    def close_claw(self):
        resp = self.send("CLOSE")
        return resp, self._parse_dist(resp)

    def get_distance(self):
        return self._parse_dist(self.send("DISTANCE"))

    def pick(self, x, y):
        return self.send(f"PICK,{x},{y}")

    def manual(self, servo, angle):
        return self.send(f"MANUAL,{servo},{angle}")

    def status(self):
        return self.send("STATUS")

    def _parse_dist(self, response):
        for line in response.split("\n"):
            if "DIST:" in line:
                try:
                    return float(line.split("DIST:")[-1])
                except ValueError:
                    pass
        return -1
