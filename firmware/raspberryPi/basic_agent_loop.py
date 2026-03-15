#!/usr/bin/env python3
"""Basic Raspberry Pi voice agent loop for find-and-pick tasks.

Flow:
1) Listen to mic and stream audio to faster-whisper websocket server.
2) Wait for wake phrase, then capture command text.
3) Parse intent and map user description -> current vision label using an LLM.
4) Request path planning via vision API (/plan), then poll robot/path endpoints.
5) When arrived near final waypoint, run pickup process (or dry-run stub).
"""

import argparse
import asyncio
import glob
import json
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
import sounddevice as sd
import websockets


class State(Enum):
    IDLE = "idle"
    ACTIVE = "active"


@dataclass
class AgentConfig:
    whisper_url: str
    vision_api_base: str
    wake_phrase: str
    sample_rate: int = 16000
    chunk_duration: float = 0.5
    silence_timeout: float = 2.0
    wake_timeout: float = 10.0
    poll_interval: float = 0.35
    arrival_threshold_cm: float = 12.0
    waypoint_tolerance_cm: float = 8.0
    heading_tolerance_deg: float = 12.0
    path_timeout_sec: float = 90.0
    llm_api_url: str = "https://api.openai.com/v1/chat/completions"
    llm_model: str = "gpt-4o-mini"
    llm_api_key_env: str = "OPENAI_API_KEY"
    dry_run_pickup: bool = True
    serial_port: str = "/dev/ttyUSB0"
    camera_index: int = 0
    drive_serial_port: str = "auto"
    drive_serial_baud: int = 9600
    drive_forward_step_cm: float = 10.0
    drive_turn_min_abs_deg: float = 10.0
    drive_turn_units_per_deg: float = 5.0
    drive_command_cooldown_sec: float = 0.15


def load_config(path: str) -> AgentConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return AgentConfig(
        whisper_url=raw["stt"]["whisper_server"],
        vision_api_base=raw["vision"]["api_base"].rstrip("/"),
        wake_phrase=raw.get("wake", {}).get("phrase", "hey claw").lower(),
        sample_rate=int(raw.get("audio", {}).get("sample_rate", 16000)),
        chunk_duration=float(raw.get("audio", {}).get("chunk_duration", 0.5)),
        silence_timeout=float(raw.get("timing", {}).get("silence_timeout", 2.0)),
        wake_timeout=float(raw.get("timing", {}).get("wake_timeout", 10.0)),
        poll_interval=float(raw.get("timing", {}).get("poll_interval", 0.35)),
        arrival_threshold_cm=float(raw.get("nav", {}).get("arrival_threshold_cm", 12.0)),
        waypoint_tolerance_cm=float(raw.get("nav", {}).get("waypoint_tolerance_cm", 8.0)),
        heading_tolerance_deg=float(raw.get("nav", {}).get("heading_tolerance_deg", 12.0)),
        path_timeout_sec=float(raw.get("nav", {}).get("path_timeout_sec", 90.0)),
        llm_api_url=raw.get("llm", {}).get("api_url", "https://api.openai.com/v1/chat/completions"),
        llm_model=raw.get("llm", {}).get("model", "gpt-4o-mini"),
        llm_api_key_env=raw.get("llm", {}).get("api_key_env", "OPENAI_API_KEY"),
        dry_run_pickup=bool(raw.get("pickup", {}).get("dry_run", True)),
        serial_port=raw.get("pickup", {}).get("serial_port", "/dev/ttyUSB0"),
        camera_index=int(raw.get("pickup", {}).get("camera_index", 0)),
        drive_serial_port=raw.get("drive", {}).get("serial_port", "auto"),
        drive_serial_baud=int(raw.get("drive", {}).get("baud", 9600)),
        drive_forward_step_cm=float(raw.get("drive", {}).get("forward_step_cm", 10.0)),
        drive_turn_min_abs_deg=float(raw.get("drive", {}).get("turn_min_abs_deg", 10.0)),
        drive_turn_units_per_deg=float(raw.get("drive", {}).get("turn_units_per_deg", 5.0)),
        drive_command_cooldown_sec=float(raw.get("drive", {}).get("command_cooldown_sec", 0.15)),
    )


class ArduinoDriveBridge:
    """Sends movement commands to Arduino over serial.

    Protocol:
    - d<number>: forward duration ticks, where each tick is 100 ms
    - l<number> or r<number>: turn left/right units (1..1000)
    """

    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self._serial = None

    def _candidate_ports(self) -> List[str]:
        configured = (self.port or "").strip()
        if configured and configured.lower() != "auto":
            return [configured]

        candidates: List[str] = []

        # Common USB serial names on Linux/Raspberry Pi.
        candidates.extend(sorted(glob.glob("/dev/ttyACM*")))
        candidates.extend(sorted(glob.glob("/dev/ttyUSB*")))

        # Optional pyserial discovery (works on Linux/macOS/Windows).
        try:
            from serial.tools import list_ports  # type: ignore[import-not-found]

            discovered = [p.device for p in list_ports.comports() if p.device]
            for dev in discovered:
                if dev not in candidates:
                    candidates.append(dev)
        except Exception:
            pass

        # Windows-style fallback names.
        for i in range(1, 21):
            com = f"COM{i}"
            if com not in candidates:
                candidates.append(com)

        return candidates

    def connect(self) -> None:
        try:
            import serial  # type: ignore[import-not-found]  # Lazy import for environments without pyserial.

            for candidate in self._candidate_ports():
                try:
                    self._serial = serial.Serial(candidate, self.baud, timeout=1)
                    self.port = candidate
                    time.sleep(2)
                    print(f"Drive serial connected: {candidate} @ {self.baud}")
                    return
                except Exception:
                    self._serial = None

            print("[warn] drive serial unavailable: no candidate port opened")
        except Exception as exc:
            self._serial = None
            print(f"[warn] drive serial unavailable: {exc}")

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def send_command(self, command: str) -> bool:
        if self._serial is None:
            return False
        try:
            self._serial.write(f"{command.strip()}\n".encode("utf-8"))
            return True
        except Exception as exc:
            print(f"[warn] drive serial write failed: {exc}")
            return False


class VisionApiClient:
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Dict[str, Any]:
        response = requests.get(f"{self.base_url}{path}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_objects(self) -> Dict[str, Any]:
        return self._get("/objects")

    def get_robot(self) -> Dict[str, Any]:
        return self._get("/robot")

    def get_path(self) -> Dict[str, Any]:
        return self._get("/path")

    def queue_plan(self, target_name: str) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/plan",
            json={"target_name": target_name},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def queue_plan_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/plan",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def clear_plan(self) -> Dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/plan",
            json={"clear": True},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def parse_intent(command_text: str) -> Dict[str, Any]:
    text = command_text.strip().lower()
    action = None
    bring_back = any(p in text for p in ["bring it", "bring back", "bring it back", "return with it"])

    if any(k in text for k in ["pick up", "pickup", "grab", "get me"]):
        action = "pickup"
    elif any(k in text for k in ["move to", "go to", "navigate to", "drive to"]):
        action = "move"
    elif any(k in text for k in ["find", "locate", "where is"]):
        action = "find"

    target = text
    patterns = [
        r"(?:pick up|pickup|grab|get me|find|locate|where is)\s+(?:the\s+)?(.+)",
        r"(?:can you|please)\s+(?:pick up|find|grab)\s+(?:the\s+)?(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            target = match.group(1).strip()
            break

    target = re.sub(r"\b(for me|please|right now)\b", "", target).strip()

    corner = None
    for token in ["top left", "top right", "bottom right", "bottom left"]:
        if token in text:
            corner = token.replace(" ", "_")
            break

    coord_match = re.search(r"x\s*[:=]?\s*(-?\d+(?:\.\d+)?)\D+y\s*[:=]?\s*(-?\d+(?:\.\d+)?)", text)
    if coord_match:
        coord = {
            "x": float(coord_match.group(1)),
            "y": float(coord_match.group(2)),
        }
    else:
        coord = None

    return {
        "action": action,
        "target_description": target if target else None,
        "bring_back": bring_back,
        "corner": corner,
        "coordinate": coord,
        "raw": command_text,
    }


class LabelResolver:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg

    def resolve(self, user_description: str, labels: List[str]) -> Optional[str]:
        if not labels:
            return None

        llm_choice = self._resolve_with_llm(user_description, labels)
        if llm_choice in labels:
            return llm_choice

        return self._fallback_match(user_description, labels)

    def resolve_move_target(self, user_description: str) -> Optional[Dict[str, Any]]:
        # Fast path for explicit corner words.
        for token in ["top_left", "top_right", "bottom_right", "bottom_left"]:
            if token.replace("_", " ") in user_description.lower() or token in user_description.lower():
                return {"goal_type": "corner", "corner": token, "target_name": token}

        # Fast path for explicit x,y mention.
        match = re.search(r"x\s*[:=]?\s*(-?\d+(?:\.\d+)?)\D+y\s*[:=]?\s*(-?\d+(?:\.\d+)?)", user_description.lower())
        if match:
            return {
                "goal_type": "point",
                "mode": "cm",
                "target_name": "point_target",
                "target_point": {
                    "x": float(match.group(1)),
                    "y": float(match.group(2)),
                },
            }

        llm_result = self._resolve_move_with_llm(user_description)
        if llm_result is not None:
            return llm_result
        return None

    def _resolve_move_with_llm(self, user_description: str) -> Optional[Dict[str, Any]]:
        api_key = os.getenv(self.cfg.llm_api_key_env, "").strip()
        if not api_key:
            return None

        system_prompt = (
            "Extract a navigation goal from the user request. "
            "Return strict JSON only, either: "
            '{"goal_type":"corner","corner":"top_left|top_right|bottom_right|bottom_left"} '
            "or "
            "{\"goal_type\":\"point\",\"mode\":\"cm\",\"x\":number,\"y\":number}."
        )
        payload = {
            "model": self.cfg.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User request: {user_description}"},
            ],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(self.cfg.llm_api_url, headers=headers, json=payload, timeout=12)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = self._extract_json(content)
            goal_type = str(parsed.get("goal_type", "")).lower()
            if goal_type == "corner":
                corner = str(parsed.get("corner", "")).strip().lower()
                if corner in {"top_left", "top_right", "bottom_right", "bottom_left"}:
                    return {"goal_type": "corner", "corner": corner, "target_name": corner}
                return None

            if goal_type == "point":
                return {
                    "goal_type": "point",
                    "mode": "cm",
                    "target_name": "point_target",
                    "target_point": {
                        "x": float(parsed.get("x")),
                        "y": float(parsed.get("y")),
                    },
                }
        except Exception:
            return None

        return None

    def _resolve_with_llm(self, user_description: str, labels: List[str]) -> Optional[str]:
        api_key = os.getenv(self.cfg.llm_api_key_env, "").strip()
        if not api_key:
            return None

        system_prompt = (
            "You map user intent descriptions to one label from live vision detections. "
            "The user is trying to find/pick an object. Return only strict JSON: "
            '{"label":"<one label or null>","reason":"short"}. '
            "label must be exactly one of the provided labels or null."
        )
        user_prompt = (
            f"User request: {user_description}\n"
            f"Available labels: {labels}\n"
            "Choose the best matching label."
        )

        payload = {
            "model": self.cfg.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(self.cfg.llm_api_url, headers=headers, json=payload, timeout=12)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = self._extract_json(content)
            label = parsed.get("label")
            return label if isinstance(label, str) else None
        except Exception:
            return None

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _fallback_match(user_description: str, labels: List[str]) -> Optional[str]:
        lowered = user_description.lower()
        for label in labels:
            if label.lower() in lowered:
                return label

        target_tokens = set(re.findall(r"[a-z0-9]+", lowered))
        if not target_tokens:
            return labels[0]

        best_label = None
        best_score = -1
        for label in labels:
            label_tokens = set(re.findall(r"[a-z0-9]+", label.lower()))
            score = len(target_tokens & label_tokens)
            if score > best_score:
                best_score = score
                best_label = label

        return best_label or labels[0]


class PickupRunner:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg

    def run(self, label: str, target_obj: Dict[str, Any], robot: Dict[str, Any]) -> Dict[str, Any]:
        if self.cfg.dry_run_pickup:
            return {
                "success": True,
                "message": f"DRY RUN pickup for {label}",
                "target": target_obj,
                "robot": robot,
            }

        from pickup_controller import pickup

        target_cm = target_obj.get("position_cm") or {}
        robot_cm = (robot or {}).get("pose_position_cm") or (robot or {}).get("position_cm") or {}
        heading = float((robot or {}).get("heading_deg") or 0.0)

        return pickup(
            target_x=float(target_cm.get("x", 0.0)),
            target_y=float(target_cm.get("y", 0.0)),
            rover_x=float(robot_cm.get("x", 0.0)),
            rover_y=float(robot_cm.get("y", 0.0)),
            heading=heading,
            serial_port=self.cfg.serial_port,
            camera_index=self.cfg.camera_index,
        )


class VoicePickupAgent:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self._validate_serial_ports()
        self.vision = VisionApiClient(cfg.vision_api_base)
        self.resolver = LabelResolver(cfg)
        self.pickup = PickupRunner(cfg)
        self.drive = ArduinoDriveBridge(cfg.drive_serial_port, cfg.drive_serial_baud)
        self._last_drive_cmd_ts = 0.0

    def _validate_serial_ports(self) -> None:
        """Fail fast if drive and arm are pointed to the same explicit serial device."""
        drive_port = (self.cfg.drive_serial_port or "").strip()
        arm_port = (self.cfg.serial_port or "").strip()
        if not drive_port or not arm_port:
            return

        if drive_port.lower() != "auto" and os.path.realpath(drive_port) == os.path.realpath(arm_port):
            raise ValueError(
                f"Drive and arm serial ports resolve to the same device ({drive_port}). "
                "Use separate aliases such as /dev/uno_drive and /dev/uno_arm."
            )

    @staticmethod
    def _contains_wake_phrase(text: str, wake_phrase: str) -> bool:
        return wake_phrase in text.lower().strip()

    @staticmethod
    def _strip_wake_phrase(text: str, wake_phrase: str) -> str:
        lower = text.lower()
        idx = lower.find(wake_phrase)
        if idx == -1:
            return text.strip()
        return text[idx + len(wake_phrase) :].strip()

    async def run(self):
        self.drive.connect()
        state = State.IDLE
        wake_time = 0.0
        last_text_time = 0.0
        command_buffer: List[str] = []

        chunk_samples = int(self.cfg.sample_rate * self.cfg.chunk_duration)
        transcript_queue: asyncio.Queue[str] = asyncio.Queue()

        print(f"Listening for wake phrase '{self.cfg.wake_phrase}'...")
        print(f"Whisper websocket: {self.cfg.whisper_url}")
        print(f"Vision API: {self.cfg.vision_api_base}")

        async with websockets.connect(self.cfg.whisper_url, ping_interval=20, ping_timeout=60, max_size=2**22) as ws:
            async def recv_transcripts():
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "transcript":
                        await transcript_queue.put(str(msg.get("text", "")))

            async def audio_and_logic():
                nonlocal state, wake_time, last_text_time
                loop = asyncio.get_event_loop()
                with sd.InputStream(
                    samplerate=self.cfg.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=chunk_samples,
                ) as mic:
                    while True:
                        chunk, overflowed = await loop.run_in_executor(None, mic.read, chunk_samples)
                        if overflowed:
                            print("[warn] audio overflow")

                        audio = chunk[:, 0].astype(np.float32)
                        await ws.send(audio.tobytes())

                        text = None
                        while not transcript_queue.empty():
                            text = transcript_queue.get_nowait()

                        if text is None:
                            if state == State.ACTIVE:
                                has_words = len(command_buffer) > 0
                                if has_words and (time.time() - last_text_time) > self.cfg.silence_timeout:
                                    await self.handle_command(" ".join(command_buffer).strip())
                                    command_buffer.clear()
                                    state = State.IDLE
                                    await ws.send(json.dumps({"type": "reset"}))
                                    print(f"Listening for wake phrase '{self.cfg.wake_phrase}'...")
                                elif (not has_words) and (time.time() - wake_time) > self.cfg.wake_timeout:
                                    command_buffer.clear()
                                    state = State.IDLE
                                    await ws.send(json.dumps({"type": "reset"}))
                            continue

                        if state == State.IDLE:
                            if self._contains_wake_phrase(text, self.cfg.wake_phrase):
                                state = State.ACTIVE
                                wake_time = time.time()
                                last_text_time = wake_time
                                remainder = self._strip_wake_phrase(text, self.cfg.wake_phrase)
                                command_buffer = [remainder] if remainder else []
                                await ws.send(json.dumps({"type": "reset"}))
                                print("Wake phrase detected. Listening for command...")
                        else:
                            command_buffer.append(text)
                            last_text_time = time.time()

            recv_task = asyncio.create_task(recv_transcripts())
            try:
                await audio_and_logic()
            finally:
                recv_task.cancel()
                self.drive.close()

    async def handle_command(self, command_text: str):
        if not command_text:
            return

        print(f"You said: {command_text}")
        intent = parse_intent(command_text)
        action = intent.get("action") or "pickup"
        target_description = intent.get("target_description")
        bring_back = bool(intent.get("bring_back"))

        plan_request = None
        selected_label = None

        if action == "move":
            if intent.get("coordinate") is not None:
                point = intent["coordinate"]
                plan_request = {
                    "goal_type": "point",
                    "mode": "cm",
                    "target_name": "point_target",
                    "target_point": {"x": float(point["x"]), "y": float(point["y"])},
                }
            elif intent.get("corner"):
                corner = str(intent["corner"])
                plan_request = {
                    "goal_type": "corner",
                    "corner": corner,
                    "target_name": corner,
                }
            elif target_description:
                plan_request = self.resolver.resolve_move_target(str(target_description))

            if plan_request is None:
                print("Could not resolve move target. Try 'move to x 20 y -10' or 'move to top left corner'.")
                return

            print(f"Selected move target: {plan_request}")
            try:
                self.vision.queue_plan_request(plan_request)
            except Exception as exc:
                print(f"Failed to queue move plan: {exc}")
                return

        else:
            if not target_description:
                print("Could not parse a target description from command.")
                return

            try:
                objects_data = self.vision.get_objects()
            except Exception as exc:
                print(f"Vision API unavailable: {exc}")
                return

            labels = objects_data.get("labels", [])
            if not labels:
                print("No visible labels from vision right now.")
                return

            selected_label = self.resolver.resolve(str(target_description), labels)
            if not selected_label:
                print("No matching label found for intent.")
                return

            print(f"Selected label: {selected_label}")
            try:
                self.vision.queue_plan(selected_label)
            except Exception as exc:
                print(f"Failed to queue plan: {exc}")
                return

        arrived, path_snapshot = await self.follow_planned_path(selected_label)
        if not arrived:
            print("Did not reach target waypoint before timeout.")
            return

        if action == "move":
            print("Move command complete.")
            return

        latest_objects = self.vision.get_objects().get("objects", [])
        target_obj = self._best_object_by_label(latest_objects, selected_label or "")
        robot = self.vision.get_robot().get("robot")
        if not target_obj:
            print("Target object no longer visible at pickup stage.")
            return

        pickup_result = self.pickup.run(selected_label or "target", target_obj, robot or {})
        print(f"Pickup result: {pickup_result}")

        if bring_back and pickup_result.get("success") and path_snapshot is not None:
            print("Bring-back requested: returning along reverse path...")
            returned = await self.follow_reverse_path(path_snapshot)
            if not returned:
                print("Return traversal timed out before completion.")

    # =====================
    # INTEGRATED MOTION LOOP
    # =====================
    # This is where the agent consumes planned waypoints and executes them.
    # Replace _cmd_turn_toward_heading and _cmd_drive_forward with your actual
    # rover motor calls (serial, GPIO, CAN, etc.).
    async def follow_planned_path(self, target_label: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        deadline = time.time() + self.cfg.path_timeout_sec
        waypoint_index = 0
        last_path = None

        while time.time() < deadline:
            try:
                path_resp = self.vision.get_path()
                robot_resp = self.vision.get_robot()
            except Exception:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            path = path_resp.get("path", {})
            robot = robot_resp.get("robot") or {}
            last_path = path

            if not path.get("active"):
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            path_target = str(path.get("target_name", ""))
            if target_label and path_target and path_target != target_label:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            waypoints = path.get("waypoints") or []
            headings = path.get("waypoint_headings") or []
            mode = path.get("mode", "")
            if not waypoints:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            if waypoint_index >= len(waypoints):
                waypoint_index = len(waypoints) - 1

            end_x, end_y = waypoints[-1]
            robot_point = self._robot_point_for_mode(robot, mode)
            if robot_point is None:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            # Move along path one waypoint at a time.
            wp_x, wp_y = waypoints[waypoint_index]
            dist_to_wp = float(np.hypot(wp_x - robot_point[0], wp_y - robot_point[1]))
            wp_tol = self.cfg.waypoint_tolerance_cm if mode == "cm" else 0.05

            if dist_to_wp <= wp_tol:
                if waypoint_index < len(waypoints) - 1:
                    waypoint_index += 1
                    await asyncio.sleep(self.cfg.poll_interval)
                    continue

            desired_heading = self._desired_heading_for_waypoint(
                headings=headings,
                waypoints=waypoints,
                waypoint_index=waypoint_index,
                robot_point=robot_point,
            )
            robot_heading = self._robot_heading_deg(robot)
            heading_error = self._normalize_angle(desired_heading - robot_heading)

            if abs(heading_error) > self.cfg.heading_tolerance_deg:
                self._cmd_turn_toward_heading(heading_error)
            else:
                self._cmd_drive_forward(dist_to_wp, mode)

            dist = float(np.hypot(end_x - robot_point[0], end_y - robot_point[1]))
            if mode == "cm" and dist <= self.cfg.arrival_threshold_cm:
                print(f"Arrival reached (distance {dist:.2f} cm)")
                return True, path
            if mode == "grid" and dist <= 0.08:
                print(f"Arrival reached (normalized distance {dist:.3f})")
                return True, path

            await asyncio.sleep(self.cfg.poll_interval)

        return False, last_path

    async def follow_reverse_path(self, path_snapshot: Dict[str, Any]) -> bool:
        waypoints = path_snapshot.get("waypoints") or []
        mode = str(path_snapshot.get("mode", "cm"))
        if not waypoints:
            return False

        reverse_waypoints = list(reversed(waypoints))
        reverse_headings = []
        for i in range(len(reverse_waypoints) - 1):
            x1, y1 = reverse_waypoints[i]
            x2, y2 = reverse_waypoints[i + 1]
            reverse_headings.append(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))))
        if reverse_headings:
            reverse_headings.append(reverse_headings[-1])
        else:
            reverse_headings.append(0.0)

        deadline = time.time() + self.cfg.path_timeout_sec
        waypoint_index = 0

        while time.time() < deadline:
            try:
                robot_resp = self.vision.get_robot()
            except Exception:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            robot = robot_resp.get("robot") or {}
            robot_point = self._robot_point_for_mode(robot, mode)
            if robot_point is None:
                await asyncio.sleep(self.cfg.poll_interval)
                continue

            if waypoint_index >= len(reverse_waypoints):
                waypoint_index = len(reverse_waypoints) - 1

            wp_x, wp_y = reverse_waypoints[waypoint_index]
            dist_to_wp = float(np.hypot(wp_x - robot_point[0], wp_y - robot_point[1]))
            wp_tol = self.cfg.waypoint_tolerance_cm if mode == "cm" else 0.05

            if dist_to_wp <= wp_tol:
                if waypoint_index < len(reverse_waypoints) - 1:
                    waypoint_index += 1
                    await asyncio.sleep(self.cfg.poll_interval)
                    continue

                print("Return path complete.")
                return True

            desired_heading = self._desired_heading_for_waypoint(
                headings=reverse_headings,
                waypoints=reverse_waypoints,
                waypoint_index=waypoint_index,
                robot_point=robot_point,
            )
            robot_heading = self._robot_heading_deg(robot)
            heading_error = self._normalize_angle(desired_heading - robot_heading)

            if abs(heading_error) > self.cfg.heading_tolerance_deg:
                self._cmd_turn_toward_heading(heading_error)
            else:
                self._cmd_drive_forward(dist_to_wp, mode)

            await asyncio.sleep(self.cfg.poll_interval)

        return False

    def _cmd_turn_toward_heading(self, heading_error_deg: float):
        """Send turn command as l/r followed by 1..1000 units."""
        now = time.time()
        if (now - self._last_drive_cmd_ts) < self.cfg.drive_command_cooldown_sec:
            return

        angle = int(round(self._normalize_angle(heading_error_deg)))
        if abs(angle) < int(max(self.cfg.drive_turn_min_abs_deg, 10.0)):
            return

        angle = max(-180, min(180, angle))
        units = int(round(abs(angle) * max(self.cfg.drive_turn_units_per_deg, 0.1)))
        units = max(1, min(1000, units))

        direction = "l" if angle > 0 else "r"
        command = f"{direction}{units}"

        sent = self.drive.send_command(command)
        print(f"[DRIVE] turn cmd {command} (angle={angle} deg) {'(serial)' if sent else '(no serial)'}")
        self._last_drive_cmd_ts = now

    def _cmd_drive_forward(self, distance_to_waypoint: float, mode: str):
        """Convert waypoint distance to d<ticks>, where each tick is 100 ms forward."""
        now = time.time()
        if (now - self._last_drive_cmd_ts) < self.cfg.drive_command_cooldown_sec:
            return

        distance_cm = float(distance_to_waypoint) if mode == "cm" else float(distance_to_waypoint) * 100.0
        if distance_cm <= 0.0:
            return

        step = max(self.cfg.drive_forward_step_cm, 1.0)
        ticks = int(np.ceil(distance_cm / step))
        ticks = max(1, ticks)
        command = f"d{ticks}"

        sent = self.drive.send_command(command)
        print(f"[DRIVE] forward cmd {command} for {distance_cm:.1f}cm {'(serial)' if sent else '(no serial)'}")
        self._last_drive_cmd_ts = now

    @staticmethod
    def _normalize_angle(angle_deg: float) -> float:
        while angle_deg > 180.0:
            angle_deg -= 360.0
        while angle_deg < -180.0:
            angle_deg += 360.0
        return angle_deg

    @staticmethod
    def _robot_heading_deg(robot: Dict[str, Any]) -> float:
        value = robot.get("heading_deg")
        if value is None:
            return 0.0
        return float(value)

    @staticmethod
    def _desired_heading_for_waypoint(
        headings: List[float],
        waypoints: List[List[float]],
        waypoint_index: int,
        robot_point: Tuple[float, float],
    ) -> float:
        if waypoint_index < len(headings):
            return float(headings[waypoint_index])

        wp_x, wp_y = waypoints[waypoint_index]
        dx = float(wp_x) - float(robot_point[0])
        dy = float(wp_y) - float(robot_point[1])
        return float(np.degrees(np.arctan2(dy, dx)))

    @staticmethod
    def _robot_point_for_mode(robot: Dict[str, Any], mode: str) -> Optional[Tuple[float, float]]:
        if mode == "cm":
            pose = robot.get("pose_position_cm") or robot.get("position_cm")
            if pose:
                return float(pose.get("x", 0.0)), float(pose.get("y", 0.0))
        if mode == "grid":
            pose = robot.get("grid_position")
            if pose:
                return float(pose.get("x", 0.0)), float(pose.get("y", 0.0))
        return None

    @staticmethod
    def _best_object_by_label(objects: List[Dict[str, Any]], label: str) -> Optional[Dict[str, Any]]:
        matching = [obj for obj in objects if str(obj.get("label", "")) == label]
        if not matching:
            return None
        return max(matching, key=lambda obj: float(obj.get("confidence", 0.0)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Basic Pi voice -> plan -> pickup loop")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "pi_agent_config.json"),
        help="Path to agent config JSON",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    agent = VoicePickupAgent(cfg)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("Shutting down agent loop.")


if __name__ == "__main__":
    main()

