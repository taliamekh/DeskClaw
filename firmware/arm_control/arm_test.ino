/*
 * OpenClaw Arm Test — Ultrasonic Auto-Grab
 * Claw stays open. When ultrasonic detects object within range, closes claw and lifts.
 * Uses same pin config as arm_control.ino.
 */

#include <Servo.h>

// Servos
Servo claw, wristUD, forearmSecond, forearmBottom;

// Pins
const int CLAW_PIN = 2;
const int WRIST_UD_PIN = 3;
const int FOREARM2_PIN = 5;
const int FOREARM1_PIN = 6;
const int TRIG_PIN = 9;
const int ECHO_PIN = 10;

// Positions
const int CLAW_OPEN = 0;
const int CLAW_CLOSED = 120;
const int GRAB_THRESHOLD_CM = 8;  // Close claw when object is this close

// State
bool holding = false;

void setup() {
  Serial.begin(9600);

  claw.attach(CLAW_PIN);
  wristUD.attach(WRIST_UD_PIN);
  forearmSecond.attach(FOREARM2_PIN);
  forearmBottom.attach(FOREARM1_PIN);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Start in ready position: arm lowered, claw open
  claw.write(CLAW_OPEN);
  wristUD.write(110);       // Angled down toward ground
  forearmSecond.write(90);
  forearmBottom.write(70);   // Reaching forward

  Serial.println("=== ARM GRAB TEST ===");
  Serial.println("Place an object near the claw.");
  Serial.print("Grab threshold: ");
  Serial.print(GRAB_THRESHOLD_CM);
  Serial.println(" cm");
  holding = false;
}

void loop() {
  float dist = readDistance();

  if (dist > 0) {
    Serial.print("Distance: ");
    Serial.print(dist);
    Serial.println(" cm");
  }

  if (!holding && dist > 0 && dist <= GRAB_THRESHOLD_CM) {
    grab();
  }

  // Press any key in serial monitor to release and reset
  if (Serial.available()) {
    Serial.read();
    release();
  }

  delay(200);
}

float readDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long dur = pulseIn(ECHO_PIN, HIGH, 30000);
  if (dur == 0) return -1;
  return (dur * 0.034) / 2.0;
}

void smoothMove(Servo &s, int from, int to, int delayMs) {
  int step = (to > from) ? 1 : -1;
  for (int pos = from; pos != to; pos += step) {
    s.write(pos);
    delay(delayMs);
  }
  s.write(to);
}

void grab() {
  Serial.println(">> Object detected! Grabbing...");

  // Close claw
  smoothMove(claw, CLAW_OPEN, CLAW_CLOSED, 10);
  delay(500);

  // Verify grab with ultrasonic
  float d = readDistance();
  Serial.print("Post-grab distance: ");
  Serial.print(d);
  Serial.println(" cm");

  if (d > 0 && d < 3.0) {
    Serial.println(">> Object grasped!");
  } else {
    Serial.println(">> Grab uncertain, lifting anyway");
  }

  // Lift: raise wrist and pull forearm back
  smoothMove(wristUD, 110, 60, 15);
  smoothMove(forearmBottom, 70, 90, 15);

  holding = true;
  Serial.println(">> Holding. Send any character to release.");
}

void release() {
  Serial.println(">> Releasing...");

  // Lower back down
  smoothMove(forearmBottom, 90, 70, 15);
  smoothMove(wristUD, 60, 110, 15);

  // Open claw
  smoothMove(claw, CLAW_CLOSED, CLAW_OPEN, 10);

  holding = false;
  Serial.println(">> Ready for next object.");
}
