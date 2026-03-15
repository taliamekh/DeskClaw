/*
 * OpenClaw Rover Motor Control
 * Arduino — receives steering commands from Pi over USB serial (UART).
 *
 * Protocol: Pi sends an integer as ASCII text terminated by newline.
 *   -10 to +10  → straight drive (negative=backward, positive=forward,
 *                  magnitude maps to speed, 0=stop)
 *   -11 to -180 → left turn  (magnitude = turn sharpness)
 *   +11 to +180 → right turn (magnitude = turn sharpness)
 *
 * L298N pin mapping:
 *   IN1/IN2 → left motor   (pins 4, 5)
 *   IN3/IN4 → right motor  (pins 6, 7)
 *   ENA/ENB → PWM speed    (pins 9, 10)
 */

// Motor pins
const int IN1 = 4;
const int IN2 = 5;
const int IN3 = 6;
const int IN4 = 7;
const int ENA = 9;
const int ENB = 10;

const int MIN_PWM = 80;   // minimum PWM to overcome motor friction
const int MAX_PWM = 255;

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

// --- low-level helpers ---

void setLeft(int pwm, bool fwd) {
  digitalWrite(IN1, fwd ? HIGH : LOW);
  digitalWrite(IN2, fwd ? LOW  : HIGH);
  analogWrite(ENA, pwm);
}

void setRight(int pwm, bool fwd) {
  digitalWrite(IN3, fwd ? HIGH : LOW);
  digitalWrite(IN4, fwd ? LOW  : HIGH);
  analogWrite(ENB, pwm);
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}

// --- command handling ---

void handleCommand(int val) {
  // Stop
  if (val == 0) {
    stopMotors();
    Serial.println("OK:STOP");
    return;
  }

  // Straight: -10..+10
  if (val >= -10 && val <= 10) {
    bool fwd = val > 0;
    int speed = map(abs(val), 1, 10, MIN_PWM, MAX_PWM);
    setLeft(speed, fwd);
    setRight(speed, fwd);
    Serial.print("OK:STRAIGHT:");
    Serial.println(val);
    return;
  }

  // Turn: magnitude 11..180
  int mag = abs(val);
  if (mag > 180) mag = 180;

  int speed = map(mag, 11, 180, MIN_PWM, MAX_PWM);

  if (val < 0) {
    // Left turn: left motor backward, right motor forward
    setLeft(speed, false);
    setRight(speed, true);
    Serial.print("OK:LEFT:");
    Serial.println(mag);
  } else {
    // Right turn: left motor forward, right motor backward
    setLeft(speed, true);
    setRight(speed, false);
    Serial.print("OK:RIGHT:");
    Serial.println(mag);
  }
}

void loop() {
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input.length() > 0) {
      int val = input.toInt();
      handleCommand(val);
    }
  }
}
