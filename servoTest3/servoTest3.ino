#include <Servo.h>

Servo servo1;
Servo servo2;
Servo servo3;

int servoNum;
int angle;

void setup() {
  Serial.begin(9600);

  servo1.attach(2);
  servo2.attach(3);
  servo3.attach(6);

  Serial.println("Ready: type '<servo#> <angle>'");
  Serial.println("Example: 1 90");
}

void loop() {

  if (Serial.available()) {

    servoNum = Serial.parseInt();
    angle = Serial.parseInt();

    angle = constrain(angle, 0, 180);

    if (servoNum == 1) {
      servo1.write(angle);
      Serial.print("Servo 1 -> ");
      Serial.println(angle);
    }

    else if (servoNum == 2) {
      servo2.write(angle);
      Serial.print("Servo 2 -> ");
      Serial.println(angle);
    }

    else if (servoNum == 3) {
      servo3.write(angle);
      Serial.print("Servo 3 -> ");
      Serial.println(angle);
    }

    else {
      Serial.println("Invalid servo number");
    }

    while (Serial.available()) Serial.read(); // clear buffer
  }
}