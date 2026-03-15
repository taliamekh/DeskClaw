"""
WASD Motor Control — max speed
w=forward  s=backward  a=left  d=right  space=stop  q=quit
"""

import RPi.GPIO as GPIO
import sys
import tty
import termios
import select

ENA, IN1, IN2 = 13, 22, 27
IN3, IN4, ENB = 23, 24, 12

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in [ENA, IN1, IN2, IN3, IN4, ENB]:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    GPIO.output(ENA, GPIO.HIGH)
    GPIO.output(ENB, GPIO.HIGH)

def motors(a, b, c, d):
    GPIO.output(IN1, GPIO.HIGH if a else GPIO.LOW)
    GPIO.output(IN2, GPIO.HIGH if b else GPIO.LOW)
    GPIO.output(IN3, GPIO.HIGH if c else GPIO.LOW)
    GPIO.output(IN4, GPIO.HIGH if d else GPIO.LOW)

def stop():
    motors(0, 0, 0, 0)

def get_key(timeout=0.05):
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        return sys.stdin.read(1) if ready else None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# IN1 IN2 IN3 IN4
KEYS = {
    'w': (1, 0, 1, 0, "FORWARD"),
    's': (0, 1, 0, 1, "BACKWARD"),
    'a': (0, 1, 1, 0, "LEFT"),
    'd': (1, 0, 0, 1, "RIGHT"),
}

setup()
print("WASD motor control — max speed")
print("w=forward  s=backward  a=left  d=right  space=stop  q=quit\n")

last = None
try:
    while True:
        key = get_key()
        if key == 'q':
            break
        elif key == ' ':
            stop(); last = None; print("STOP      ", end='\r')
        elif key in KEYS:
            a, b, c, d, name = KEYS[key]
            motors(a, b, c, d)
            if key != last:
                print(f"{name}    ", end='\r')
            last = key
        elif key is None and last is not None:
            stop(); last = None; print("STOP      ", end='\r')
except KeyboardInterrupt:
    pass
finally:
    stop()
    GPIO.cleanup()
    print("\nDone.")
