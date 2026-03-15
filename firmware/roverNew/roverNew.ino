/*
 * OpenClaw Rover Motor Control
 * Arduino — receives commands from Pi over USB serial (UART 9600).
 *
 * Protocol: "<cmd><ms>\n"
 *   d<ms> = drive forward for <ms> milliseconds
 *   b<ms> = drive backward for <ms> milliseconds
 *   l<ms> = turn left for <ms> milliseconds
 *   r<ms> = turn right for <ms> milliseconds
 *   s     = stop immediately
 *
 * Example: "d2000\n" = drive forward 2 seconds
 *
 * L298N wiring:
 *   IN1/IN2 → left motor   (pins 4, 5)
 *   IN3/IN4 → right motor  (pins 6, 7)
 *   ENA/ENB → PWM speed    (pins 9, 10)
 */

const int IN1 = 4;
const int IN2 = 5;
const int IN3 = 6;
const int IN4 = 7;
const int ENA = 9;
const int ENB = 10;

const int SPEED = 40;

void setup() {
  Serial.begin(9600);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  stopMotors();
  Serial.println("ROVER_READY");
}

void driveForward() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  analogWrite(ENA, SPEED);
  analogWrite(ENB, SPEED);
}

void driveBackward() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  analogWrite(ENA, SPEED);
  analogWrite(ENB, SPEED);
}

void turnLeft() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  analogWrite(ENA, SPEED);
  analogWrite(ENB, SPEED);
}

void turnRight() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  analogWrite(ENA, SPEED);
  analogWrite(ENB, SPEED);
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() == 0) return;

    char cmd = input.charAt(0);
    int ms = input.substring(1).toInt();

    if (cmd == 's') {
      stopMotors();
      Serial.println("OK:STOP");
      return;
    }

    if (ms <= 0) {
      Serial.println("ERR:BAD_MS");
      return;
    }

    switch (cmd) {
      case 'd': driveForward();  break;
      case 'b': driveBackward(); break;
      case 'l': turnLeft();      break;
      case 'r': turnRight();     break;
      default:
        Serial.println("ERR:BAD_CMD");
        return;
    }

    Serial.print("OK:");
    Serial.print(cmd);
    Serial.print(":");
    Serial.println(ms);

    delay(ms);
    stopMotors();
    Serial.println("OK:DONE");
  }
}
