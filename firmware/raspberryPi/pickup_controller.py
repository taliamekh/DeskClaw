"""
OpenClaw Pickup Controller
Single orchestrator: rover + arm + webcam + ultrasonic.
Called externally with target coordinates.

Flow:
1. Receive pickup command with coordinates
2. Rover drives toward target
3. Arm moves toward target (IK on Arduino)
4. Webcam guides arm closer
5. Ultrasonic confirms object proximity
6. Claw grabs object
7. Webcam confirms pickup
"""

import math
import time
from rover_drive import RoverDrive
from arm_pickup import ArmController
from webcam import WebcamGuide

# Tuning
ROVER_SPEED = 50
APPROACH_CM = 20.0        # Stop rover this far from target
ULTRASONIC_GRAB_CM = 5.0  # Close enough to grab
ULTRASONIC_DETECT_CM = 15.0
GUIDE_MAX_ITER = 20
CENTER_TOL_PX = 30
PX_TO_SERVO = 0.05


class PickupController:
    def __init__(self, serial_port="/dev/ttyUSB0", camera_index=0):
        self.rover = RoverDrive(speed=ROVER_SPEED)
        self.arm = ArmController(port=serial_port)
        self.cam = WebcamGuide(camera_index=camera_index)

    def connect(self):
        self.arm.connect()
        if not self.cam.open():
            raise RuntimeError("Webcam failed to open")

    def shutdown(self):
        self.rover.cleanup()
        self.arm.home()
        self.arm.disconnect()
        self.cam.close()

    def execute(self, target_x, target_y, rover_x=0, rover_y=0, heading=0):
        """
        Full pickup sequence. All positions in cm, heading in degrees.
        Returns {success, message, verified}.
        """
        try:
            # 1-2: Drive rover close to target
            self._drive_to(target_x, target_y, rover_x, rover_y, heading)

            # 3: Arm rough positioning via Arduino IK
            self.arm.open_claw()
            self.arm.pick(target_x - rover_x, target_y - rover_y)

            # 4: Webcam fine guidance
            ref_frame = self._guide_arm()

            # 5: Ultrasonic confirmation
            dist = self.arm.get_distance()
            if dist < 0 or dist > ULTRASONIC_DETECT_CM:
                self.arm.home()
                return {"success": False, "message": f"No object detected ({dist:.1f} cm)"}

            # 6: Grab
            _, grab_dist = self.arm.close_claw()
            if grab_dist > ULTRASONIC_GRAB_CM:
                self.arm.open_claw()
                self.arm.home()
                return {"success": False, "message": "Grasp failed"}

            # 7: Verify with webcam
            self.arm.home()
            time.sleep(0.5)
            verified = self.cam.confirm_pickup(ref_frame) if ref_frame else False

            return {"success": True, "message": "Pickup complete", "verified": verified}

        except Exception as e:
            self.arm.home()
            self.rover.stop()
            return {"success": False, "message": str(e)}

    def _drive_to(self, tx, ty, rx, ry, heading):
        dx, dy = tx - rx, ty - ry
        dist = math.hypot(dx, dy)
        if dist <= APPROACH_CM:
            return

        # Turn toward target
        angle = math.degrees(math.atan2(dy, dx)) - heading
        while angle > 180: angle -= 360
        while angle < -180: angle += 360

        if abs(angle) > 10:
            turn_fn = self.rover.turn_left if angle > 0 else self.rover.turn_right
            turn_fn(duration=abs(angle) / 180.0)

        # Drive forward
        drive_time = max((dist - APPROACH_CM) / 15.0, 0.2)
        self.rover.forward(duration=drive_time)

    def _guide_arm(self):
        ref_frame = None
        for _ in range(GUIDE_MAX_ITER):
            g = self.cam.guide_step()
            if not g["found"]:
                continue

            ref_frame = g["frame"]
            if abs(g["dx"]) < CENTER_TOL_PX and abs(g["dy"]) < CENTER_TOL_PX:
                break

            self.arm.manual("BASE", 90 + int(g["dx"] * PX_TO_SERVO))
            if g["dy"] != 0:
                self.arm.manual("WRIST_UD", 90 - int(g["dy"] * PX_TO_SERVO))
            time.sleep(0.3)

        return ref_frame


# --- Public API ---

def pickup(target_x, target_y, rover_x=0, rover_y=0, heading=0,
           serial_port="/dev/ttyUSB0", camera_index=0):
    """Single-call pickup. Handles setup/teardown."""
    ctrl = PickupController(serial_port=serial_port, camera_index=camera_index)
    try:
        ctrl.connect()
        return ctrl.execute(target_x, target_y, rover_x, rover_y, heading)
    finally:
        ctrl.shutdown()
