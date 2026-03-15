/*
 * OpenClaw Robotic Arm Control Firmware
 * Arduino Uno - Controls robotic arm based on serial coordinates
 * 
 * Receives: "PICK,x,y" where x,y are object coordinates relative to arm base
 * Controls: 6-DOF robotic arm with specific pin configuration
 * Features: Ultrasonic sensor for object distance confirmation
 */

#include <Servo.h>

// Servo objects
Servo clawServo;           // Claw open/close
Servo wristUpDownServo;    // Wrist up/down movement
Servo wristSideServo;      // Wrist side to side movement
Servo forearmSecondServo;  // Second forearm joint
Servo forearmBottomServo;  // Bottom forearm joint
Servo baseServo;           // Base rotation

// Pin assignments (matching your configuration)
const int CLAW_PIN = 2;
const int WRIST_UP_DOWN_PIN = 3;
const int WRIST_SIDE_PIN = 4;
const int FOREARM_SECOND_PIN = 5;
const int FOREARM_BOTTOM_PIN = 6;
const int BASE_PIN = 7;

// Ultrasonic sensor pins
const int ULTRASONIC_TRIGGER_PIN = 9;
const int ULTRASONIC_ECHO_PIN = 10;

// Arm dimensions (in cm) - adjust based on your arm
const float FOREARM_LENGTH_1 = 12.0;  // Bottom forearm segment
const float FOREARM_LENGTH_2 = 10.0;  // Second forearm segment
const float BASE_HEIGHT = 8.0;        // Base to first joint height

// Ultrasonic sensor parameters
const float SOUND_SPEED = 0.034;       // Speed of sound in cm/microsecond
const int ULTRASONIC_TIMEOUT = 30000;  // Timeout for ultrasonic reading (microseconds)
const float OBJECT_DETECTION_THRESHOLD = 15.0; // Maximum distance to consider object detected (cm)

// Servo positions structure
struct ArmPosition {
  int claw;
  int wristUpDown;
  int wristSide;
  int forearmSecond;
  int forearmBottom;
  int base;
};

// Current and target positions
ArmPosition currentPos = {0, 90, 90, 90, 90, 90}; // Start position
ArmPosition homePos = {0, 90, 90, 90, 90, 90};    // Home position

// Serial communication
String inputString = "";
boolean stringComplete = false;

// Movement parameters
const int MOVE_DELAY = 15;        // Delay between servo steps (ms)
const int CLAW_OPEN = 0;          // Claw open position
const int CLAW_CLOSED = 120;      // Claw closed position

void setup() {
  Serial.begin(9600);
  
  // Attach servos to pins
  clawServo.attach(CLAW_PIN);
  wristUpDownServo.attach(WRIST_UP_DOWN_PIN);
  wristSideServo.attach(WRIST_SIDE_PIN);
  forearmSecondServo.attach(FOREARM_SECOND_PIN);
  forearmBottomServo.attach(FOREARM_BOTTOM_PIN);
  baseServo.attach(BASE_PIN);
  
  // Setup ultrasonic sensor pins
  pinMode(ULTRASONIC_TRIGGER_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  
  // Move to home position
  moveToPosition(homePos);
  
  Serial.println("OpenClaw Arm Control Ready");
  Serial.println("Ultrasonic sensor initialized on pins 9 (trigger) and 10 (echo)");
}

void loop() {
  // Check for serial input
  if (stringComplete) {
    processCommand(inputString);
    inputString = "";
    stringComplete = false;
  }
}

void processCommand(String command) {
  command.trim();
  command.toUpperCase();
  
  if (command.startsWith("PICK,")) {
    // Parse coordinates: PICK,x,y
    int firstComma = command.indexOf(',');
    int secondComma = command.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
      float x = command.substring(firstComma + 1, secondComma).toFloat();
      float y = command.substring(secondComma + 1).toFloat();
      
      Serial.print("Picking object at: (");
      Serial.print(x);
      Serial.print(", ");
      Serial.print(y);
      Serial.println(")");
      
      pickupObject(x, y);
    } else {
      Serial.println("ERROR: Invalid PICK command format");
    }
  }
  else if (command.startsWith("MANUAL,")) {
    // Parse manual control: MANUAL,servo,angle
    int firstComma = command.indexOf(',');
    int secondComma = command.indexOf(',', firstComma + 1);
    
    if (firstComma > 0 && secondComma > 0) {
      String servoName = command.substring(firstComma + 1, secondComma);
      int angle = command.substring(secondComma + 1).toInt();
      
      manualControl(servoName, angle);
    } else {
      Serial.println("ERROR: Invalid MANUAL command format");
      Serial.println("Use: MANUAL,servo,angle");
      Serial.println("Servos: CLAW, WRIST_UD, WRIST_SIDE, FOREARM2, FOREARM1, BASE");
    }
  }
  else if (command == "HOME") {
    Serial.println("Returning to home position");
    moveToPosition(homePos);
  }
  else if (command == "STATUS") {
    printStatus();
  }
  else if (command == "DISTANCE") {
    float distance = getUltrasonicDistance();
    Serial.print("DIST:");
    Serial.println(distance);
  }
  else if (command == "SCAN") {
    performUltrasonicScan();
  }
  else if (command == "OPEN") {
    currentPos.claw = CLAW_OPEN;
    clawServo.write(CLAW_OPEN);
    Serial.println("OK:OPEN");
  }
  else if (command == "CLOSE") {
    currentPos.claw = CLAW_CLOSED;
    clawServo.write(CLAW_CLOSED);
    delay(500);
    float d = getUltrasonicDistance();
    Serial.print("OK:CLOSE,DIST:");
    Serial.println(d);
  }
  else if (command.startsWith("MOVE,")) {
    // MOVE,base,forearmBottom,forearmSecond,wristUD,wristSide
    int c1 = command.indexOf(',');
    int c2 = command.indexOf(',', c1+1);
    int c3 = command.indexOf(',', c2+1);
    int c4 = command.indexOf(',', c3+1);
    int c5 = command.indexOf(',', c4+1);
    if (c5 > 0) {
      ArmPosition target;
      target.base = command.substring(c1+1, c2).toInt();
      target.forearmBottom = command.substring(c2+1, c3).toInt();
      target.forearmSecond = command.substring(c3+1, c4).toInt();
      target.wristUpDown = command.substring(c4+1, c5).toInt();
      target.wristSide = command.substring(c5+1).toInt();
      target.claw = currentPos.claw;
      moveToPosition(target);
      float d = getUltrasonicDistance();
      Serial.print("OK:MOVE,DIST:");
      Serial.println(d);
    } else {
      Serial.println("ERROR:MOVE format: MOVE,base,fb,fs,wud,ws");
    }
  }
  else {
    Serial.println("ERROR: Unknown command");
    Serial.println("Available commands:");
    Serial.println("PICK,x,y | HOME | STATUS | DISTANCE | SCAN | OPEN | CLOSE | MOVE,b,fb,fs,wud,ws | MANUAL,servo,angle");
  }
}

void pickupObject(float targetX, float targetY) {
  // Step 1: Calculate arm position using inverse kinematics
  ArmPosition pickPos = calculateInverseKinematics(targetX, targetY, 2.0); // 2cm above ground
  
  if (pickPos.base == -1) {
    Serial.println("ERROR: Target position unreachable");
    return;
  }
  
  // Step 2: Open claw
  Serial.println("Opening claw...");
  currentPos.claw = CLAW_OPEN;
  moveToPosition(currentPos);
  delay(500);
  
  // Step 3: Move to position above object
  Serial.println("Moving to pickup position...");
  ArmPosition abovePos = pickPos;
  abovePos.wristUpDown += 15; // Slightly higher approach
  moveToPosition(abovePos);
  delay(500);
  
  // Step 4: Confirm object presence with ultrasonic sensor
  Serial.println("Confirming object presence...");
  float distance = getUltrasonicDistance();
  Serial.print("Object distance: ");
  Serial.print(distance);
  Serial.println(" cm");
  
  if (distance > OBJECT_DETECTION_THRESHOLD) {
    Serial.println("WARNING: No object detected within range!");
    Serial.println("Continuing with pickup sequence...");
  } else {
    Serial.println("Object confirmed - proceeding with pickup");
  }
  
  // Step 5: Lower to object
  Serial.println("Lowering to object...");
  moveToPosition(pickPos);
  delay(500);
  
  // Step 6: Final distance check before closing claw
  distance = getUltrasonicDistance();
  Serial.print("Final distance check: ");
  Serial.print(distance);
  Serial.println(" cm");
  
  // Step 7: Close claw
  Serial.println("Closing claw...");
  currentPos.claw = CLAW_CLOSED;
  moveToPosition(currentPos);
  delay(1000);
  
  // Step 8: Verify object pickup
  distance = getUltrasonicDistance();
  if (distance < 3.0) {
    Serial.println("Object successfully grasped!");
  } else {
    Serial.println("WARNING: Object may not be properly grasped");
  }
  
  // Step 9: Lift object
  Serial.println("Lifting object...");
  currentPos.wristUpDown -= 20;
  currentPos.forearmSecond -= 10;
  moveToPosition(currentPos);
  delay(500);
  
  // Step 10: Return to home position
  Serial.println("Returning to home with object...");
  moveToPosition(homePos);
  
  Serial.println("Pickup sequence complete!");
}

ArmPosition calculateInverseKinematics(float x, float y, float z) {
  ArmPosition pos;
  
  // Calculate base rotation angle
  float baseAngle = atan2(y, x) * 180.0 / PI;
  baseAngle += 90; // Adjust for servo orientation
  
  // Constrain base angle
  if (baseAngle < 0) baseAngle += 180;
  if (baseAngle > 180) baseAngle = 180;
  
  // Calculate horizontal distance from base
  float horizontalDist = sqrt(x*x + y*y);
  
  // Calculate vertical distance (accounting for base height)
  float verticalDist = z - BASE_HEIGHT;
  
  // Calculate total distance to target
  float totalDist = sqrt(horizontalDist*horizontalDist + verticalDist*verticalDist);
  
  // Check if target is reachable
  if (totalDist > (FOREARM_LENGTH_1 + FOREARM_LENGTH_2)) {
    pos.base = -1; // Error flag
    return pos;
  }
  
  // Calculate forearm angles using law of cosines
  float forearmBottomAngle = acos((FOREARM_LENGTH_1*FOREARM_LENGTH_1 + totalDist*totalDist - FOREARM_LENGTH_2*FOREARM_LENGTH_2) / 
                                 (2 * FOREARM_LENGTH_1 * totalDist));
  float groundAngle = atan2(verticalDist, horizontalDist);
  forearmBottomAngle = (groundAngle + forearmBottomAngle) * 180.0 / PI;
  
  float forearmSecondAngle = acos((FOREARM_LENGTH_1*FOREARM_LENGTH_1 + FOREARM_LENGTH_2*FOREARM_LENGTH_2 - totalDist*totalDist) / 
                                 (2 * FOREARM_LENGTH_1 * FOREARM_LENGTH_2));
  forearmSecondAngle = 180 - (forearmSecondAngle * 180.0 / PI);
  
  // Adjust angles for servo orientation
  forearmBottomAngle = 180 - forearmBottomAngle;
  
  // Constrain angles to servo limits
  pos.base = constrain(baseAngle, 0, 180);
  pos.forearmBottom = constrain(forearmBottomAngle, 0, 180);
  pos.forearmSecond = constrain(forearmSecondAngle, 0, 180);
  pos.wristUpDown = 90; // Keep wrist level initially
  pos.wristSide = 90;   // Keep wrist centered
  pos.claw = currentPos.claw; // Maintain current claw state
  
  return pos;
}

void manualControl(String servoName, int angle) {
  angle = constrain(angle, 0, 180);
  
  if (servoName == "CLAW") {
    currentPos.claw = angle;
    clawServo.write(angle);
    Serial.print("Claw set to: ");
  }
  else if (servoName == "WRIST_UD") {
    currentPos.wristUpDown = angle;
    wristUpDownServo.write(angle);
    Serial.print("Wrist Up/Down set to: ");
  }
  else if (servoName == "WRIST_SIDE") {
    currentPos.wristSide = angle;
    wristSideServo.write(angle);
    Serial.print("Wrist Side set to: ");
  }
  else if (servoName == "FOREARM2") {
    currentPos.forearmSecond = angle;
    forearmSecondServo.write(angle);
    Serial.print("Forearm Second set to: ");
  }
  else if (servoName == "FOREARM1") {
    currentPos.forearmBottom = angle;
    forearmBottomServo.write(angle);
    Serial.print("Forearm Bottom set to: ");
  }
  else if (servoName == "BASE") {
    currentPos.base = angle;
    baseServo.write(angle);
    Serial.print("Base set to: ");
  }
  else {
    Serial.println("ERROR: Unknown servo name");
    Serial.println("Valid servos: CLAW, WRIST_UD, WRIST_SIDE, FOREARM2, FOREARM1, BASE");
    return;
  }
  
  Serial.println(angle);
}

void moveToPosition(ArmPosition targetPos) {
  // Smooth movement to target position
  while (currentPos.claw != targetPos.claw || 
         currentPos.wristUpDown != targetPos.wristUpDown ||
         currentPos.wristSide != targetPos.wristSide ||
         currentPos.forearmSecond != targetPos.forearmSecond ||
         currentPos.forearmBottom != targetPos.forearmBottom ||
         currentPos.base != targetPos.base) {
    
    // Move each servo one step closer to target
    if (currentPos.claw < targetPos.claw) currentPos.claw++;
    else if (currentPos.claw > targetPos.claw) currentPos.claw--;
    
    if (currentPos.wristUpDown < targetPos.wristUpDown) currentPos.wristUpDown++;
    else if (currentPos.wristUpDown > targetPos.wristUpDown) currentPos.wristUpDown--;
    
    if (currentPos.wristSide < targetPos.wristSide) currentPos.wristSide++;
    else if (currentPos.wristSide > targetPos.wristSide) currentPos.wristSide--;
    
    if (currentPos.forearmSecond < targetPos.forearmSecond) currentPos.forearmSecond++;
    else if (currentPos.forearmSecond > targetPos.forearmSecond) currentPos.forearmSecond--;
    
    if (currentPos.forearmBottom < targetPos.forearmBottom) currentPos.forearmBottom++;
    else if (currentPos.forearmBottom > targetPos.forearmBottom) currentPos.forearmBottom--;
    
    if (currentPos.base < targetPos.base) currentPos.base++;
    else if (currentPos.base > targetPos.base) currentPos.base--;
    
    // Update servo positions
    clawServo.write(currentPos.claw);
    wristUpDownServo.write(currentPos.wristUpDown);
    wristSideServo.write(currentPos.wristSide);
    forearmSecondServo.write(currentPos.forearmSecond);
    forearmBottomServo.write(currentPos.forearmBottom);
    baseServo.write(currentPos.base);
    
    delay(MOVE_DELAY);
  }
}

void printStatus() {
  Serial.println("=== ARM STATUS ===");
  Serial.print("Claw (Pin 2): "); Serial.println(currentPos.claw);
  Serial.print("Wrist Up/Down (Pin 3): "); Serial.println(currentPos.wristUpDown);
  Serial.print("Wrist Side (Pin 4): "); Serial.println(currentPos.wristSide);
  Serial.print("Forearm Second (Pin 5): "); Serial.println(currentPos.forearmSecond);
  Serial.print("Forearm Bottom (Pin 6): "); Serial.println(currentPos.forearmBottom);
  Serial.print("Base (Pin 7): "); Serial.println(currentPos.base);
  
  // Add ultrasonic sensor reading to status
  float distance = getUltrasonicDistance();
  Serial.print("Ultrasonic Distance: "); Serial.print(distance); Serial.println(" cm");
  Serial.println("==================");
}

// Ultrasonic sensor functions
float getUltrasonicDistance() {
  // Clear the trigger pin
  digitalWrite(ULTRASONIC_TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  
  // Send 10 microsecond pulse to trigger pin
  digitalWrite(ULTRASONIC_TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIGGER_PIN, LOW);
  
  // Read the echo pin and calculate distance
  long duration = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT);
  
  // Calculate distance in cm
  float distance = (duration * SOUND_SPEED) / 2;
  
  // Return -1 if timeout occurred (no echo received)
  if (duration == 0) {
    return -1;
  }
  
  return distance;
}

void performUltrasonicScan() {
  Serial.println("=== ULTRASONIC SCAN ===");
  Serial.println("Scanning for objects in different arm positions...");
  
  // Save current position
  ArmPosition originalPos = currentPos;
  
  // Scan positions: center, left, right
  int scanPositions[] = {60, 90, 120}; // Base angles
  String positionNames[] = {"LEFT", "CENTER", "RIGHT"};
  
  for (int i = 0; i < 3; i++) {
    Serial.print("Scanning ");
    Serial.print(positionNames[i]);
    Serial.print(" position (");
    Serial.print(scanPositions[i]);
    Serial.println(" degrees)...");
    
    // Move base to scan position
    ArmPosition scanPos = currentPos;
    scanPos.base = scanPositions[i];
    moveToPosition(scanPos);
    delay(500); // Allow movement to settle
    
    // Take multiple readings for accuracy
    float totalDistance = 0;
    int validReadings = 0;
    
    for (int j = 0; j < 5; j++) {
      float distance = getUltrasonicDistance();
      if (distance > 0 && distance < 200) { // Valid reading range
        totalDistance += distance;
        validReadings++;
      }
      delay(100);
    }
    
    if (validReadings > 0) {
      float avgDistance = totalDistance / validReadings;
      Serial.print("  Average distance: ");
      Serial.print(avgDistance);
      Serial.println(" cm");
      
      if (avgDistance <= OBJECT_DETECTION_THRESHOLD) {
        Serial.println("  *** OBJECT DETECTED ***");
      } else {
        Serial.println("  No object in range");
      }
    } else {
      Serial.println("  No valid readings");
    }
    
    Serial.println();
  }
  
  // Return to original position
  Serial.println("Returning to original position...");
  moveToPosition(originalPos);
  Serial.println("=== SCAN COMPLETE ===");
}

// Serial event handler for receiving commands
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    inputString += inChar;
    
    if (inChar == '\n') {
      stringComplete = true;
    }
  }
}