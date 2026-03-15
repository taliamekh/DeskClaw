"""
OpenClaw Webcam Module
Onboard rover camera — detects objects and computes offsets.
No arm control, no serial. Just vision.
"""

import cv2
import numpy as np


class WebcamGuide:
    def __init__(self, camera_index=0, width=640, height=480):
        self.cap = None
        self.camera_index = camera_index
        self.w = width
        self.h = height
        self.cx = width // 2
        self.cy = height // 2

    def open(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.h)
        return True

    def close(self):
        if self.cap:
            self.cap.release()

    def grab_frame(self):
        if not self.cap:
            return None
        ret, frame = self.cap.read()
        return frame if ret else None

    def detect_object(self, frame):
        """Find largest contour. Returns {cx, cy, area, bbox} or None."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (7, 7), 0), 40, 120)
        edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best, best_area = None, 0
        for c in contours:
            area = cv2.contourArea(c)
            if area < 500:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if w > self.w * 0.8 or h > self.h * 0.8:
                continue
            if area > best_area:
                best_area = area
                best = {"cx": x + w // 2, "cy": y + h // 2, "area": area, "bbox": (x, y, w, h)}
        return best

    def guide_step(self):
        """Single guidance step. Returns {found, dx, dy, area, frame}."""
        frame = self.grab_frame()
        if frame is None:
            return {"found": False}

        det = self.detect_object(frame)
        if not det:
            return {"found": False, "frame": frame}

        return {
            "found": True,
            "dx": det["cx"] - self.cx,
            "dy": det["cy"] - self.cy,
            "area": det["area"],
            "frame": frame,
        }

    def confirm_pickup(self, ref_frame):
        """Compare current frame to reference. Returns True if object likely removed."""
        cur = self.grab_frame()
        if cur is None or ref_frame is None:
            return False
        diff = cv2.absdiff(
            cv2.cvtColor(ref_frame, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY),
        )
        _, thresh = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
        return np.count_nonzero(thresh) / thresh.size > 0.05
