/*
 * OpenClaw Robotic Arm Control Firmware
 * Arduino Uno - Controls robotic arm based on serial coordinates
 * 
 * Receives: "PICK,x,y" where x,y are object coordinates relative to arm base
 * Controls: 6-DOF robotic arm with specific pin configuration
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

// Arm dimensions (in cm) - adjust based on your arm
const float FOREARM_LENGTH_1 = 12.0;  // Bottom forearm segment
const float FOREARM_LENGTH_2 = 10.0;  // Second forearm segment
const float BASE_HEIGHT = 8.0;        // Base to first joint height

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
  
  // Move to home position
  moveToPosition(homePos);

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
  else {
    Serial.println("ERROR: Unknown command");
    Serial.println("Available commands:");
    Serial.println("PICK,x,y | HOME | STATUS | MANUAL,servo,angle");
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
  
  // Step 4: Lower to object
  Serial.println("Lowering to object...");
  moveToPosition(pickPos);
  delay(500);
  
  // Step 5: Close claw
  Serial.println("Closing claw...");
  currentPos.claw = CLAW_CLOSED;
  moveToPosition(currentPos);
  delay(1000);
  
  // Step 6: Lift object
  Serial.println("Lifting object...");
  currentPos.wristUpDown -= 20;
  currentPos.forearmSecond -= 10;
  moveToPosition(currentPos);
  delay(500);
  
  // Step 7: Return to home position
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
  Serial.println("==================");
}