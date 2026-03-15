#include <Servo.h>

Servo base;
Servo forearmbot;
Servo forearmtop;
Servo wristrot;
Servo wristnod;
Servo claw;

int servoNum;
int angle;

void setup() {
  Serial.begin(9600);
  base.attach(7);
  forearmbot.attach(6);
  forearmtop.attach(5);
  wristrot.attach(4);
  claw.attach(3);
  wristnod.attach(2);
  Serial.println("Ready: type '<servo#> <angle>'");
  Serial.println("base=7, forearmbot=6, forearmtop=5, wristrot=4, wristnod=3, claw=2");

  // Set forearm top to 0 first
  forearmtop.write(0);
  Serial.println("Forearm top -> 0");
  delay(1000);

 //turn to user
  wristrot.write(180);
  Serial.println("rot");
  delay(500);

  // Nod sequence
  wristnod.write(120);
  Serial.println("Nod up");
  delay(500);

  wristnod.write(0);
  Serial.println("Nod back");
  delay(500);

  Serial.println("Sequence done - serial control active");
}

void loop() {
  if (Serial.available()) {
    servoNum = Serial.parseInt();
    angle = Serial.parseInt();
    angle = constrain(angle, 0, 180);

    if (servoNum == 7) {
      base.write(angle);
      Serial.print("Base -> ");
      Serial.println(angle);
    }
    else if (servoNum == 6) {
      forearmbot.write(angle);
      Serial.print("Forearm bottom -> ");
      Serial.println(angle);
    }
    else if (servoNum == 5) {
      forearmtop.write(angle);
      Serial.print("Forearm top -> ");
      Serial.println(angle);
    }
    else if (servoNum == 4) {
      wristrot.write(angle);
      Serial.print("Wrist Rotation -> ");
      Serial.println(angle);
    }
    else if (servoNum == 3) {
      wristnod.write(angle);
      Serial.print("Wrist up-down -> ");
      Serial.println(angle);
    }
    else if (servoNum == 2) {
      claw.write(angle);
      Serial.print("Claw -> ");
      Serial.println(angle);
    }
    else {
      Serial.println("Invalid servo number");
    }
    while (Serial.available()) Serial.read();
  }
}