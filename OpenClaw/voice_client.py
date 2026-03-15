#!/usr/bin/env python3
"""
OpenClaw Voice Client  (Raspberry Pi)

Captures audio from the mic and streams it to a remote whisper_server over
WebSocket.  Transcription text comes back from the server.  The client handles
wake-phrase detection, command buffering, gateway communication, TTS via
ElevenLabs (streamed directly into mpg123), and playback through the JBL Go 3.

No Whisper model runs on the Pi — all ASR happens on the Mac.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR.parent / ".env")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.WARNING,
)
logger = logging.getLogger("voice_client")
logger.setLevel(logging.DEBUG)

# ── Audio ────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.5  # send half-second chunks for lower latency

# ── Timing ───────────────────────────────────────────────────────────────
SILENCE_TIMEOUT = 2.0
WAKE_TIMEOUT = 10.0

# ── Wake phrases ─────────────────────────────────────────────────────────
WAKE_PHRASES = [
    "hey claw", "hey claude", "hey clawed", "hey clog", "hey clo",
    "hey law", "hey claws", "a claw", "hey clock", "hey claw.",
]
ROLLING_BUFFER_SIZE = 4


# ── State machine ────────────────────────────────────────────────────────
class State(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"


# ── Config ───────────────────────────────────────────────────────────────
def load_config():
    with open(SCRIPT_DIR / "openclaw.json") as f:
        return json.load(f)


# ── Wake-phrase helpers ──────────────────────────────────────────────────
def contains_wake_phrase(text):
    lower = text.lower().strip()
    return any(p in lower for p in WAKE_PHRASES)


def strip_wake_phrase(text):
    lower = text.lower()
    for phrase in WAKE_PHRASES:
        idx = lower.find(phrase)
        if idx != -1:
            return text[idx + len(phrase):].strip()
    return text.strip()


def check_rolling_buffer(rolling_buffer):
    for i in range(len(rolling_buffer)):
        combined = " ".join(rolling_buffer[i:]).lower().strip()
        for phrase in WAKE_PHRASES:
            if phrase in combined:
                after = combined.split(phrase, 1)[1].strip()
                return True, after
    return False, ""


# ── Streaming TTS ────────────────────────────────────────────────────────
def stream_speak(text, config):
    """Stream ElevenLabs TTS audio directly into mpg123 via stdin pipe."""
    tts = config["tts"]
    api_key = os.getenv("ELEVENLABS_API_KEY", tts.get("api_key", ""))
    voice_id = tts.get("voice_id", "nPczCjzI2devNBz1zQrb")
    model_id = tts.get("model", "eleven_flash_v2_5")
    max_len = tts.get("max_speak_length", 500)
    output_format = tts.get("output_format", "mp3_22050_32")

    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"

    url = (f"https://api.elevenlabs.io/v1/text-to-speech/"
           f"{voice_id}/stream?output_format={output_format}")
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    logger.info("TTS stream request: %d chars", len(text))
    t0 = time.time()
    resp = requests.post(url, json=payload, headers=headers,
                         stream=True, timeout=(10, 60))
    resp.raise_for_status()

    player = subprocess.Popen(["mpg123", "--quiet", "-"], stdin=subprocess.PIPE)
    first_byte = True
    try:
        for chunk in resp.iter_content(chunk_size=4096):
            if first_byte:
                logger.info("TTS first audio byte: %.2fs", time.time() - t0)
                first_byte = False
            player.stdin.write(chunk)
    finally:
        player.stdin.close()
        player.wait()


# ── Gateway communication ────────────────────────────────────────────────
IDENTITY_FILE = SCRIPT_DIR / "device_identity.json"
DEFAULT_SCOPES = [
    "operator.read", "operator.write", "operator.admin",
    "operator.approvals", "operator.pairing",
]


def _get_device_identity():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    import hashlib
    import base64

    if IDENTITY_FILE.exists():
        return json.loads(IDENTITY_FILE.read_text())

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    identity = {
        "id": hashlib.sha256(pub_raw).hexdigest(),
        "publicKey": base64.urlsafe_b64encode(pub_raw).decode().rstrip("="),
        "privateKey": private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
    }
    IDENTITY_FILE.write_text(json.dumps(identity, indent=2))
    return identity


def _sign_challenge(identity, nonce, ts, token=""):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    import base64

    parts = [
        "v2", identity["id"], "cli", "cli", "operator",
        ",".join(DEFAULT_SCOPES), str(ts), token, nonce,
    ]
    payload = "|".join(parts).encode()

    private_key = serialization.load_pem_private_key(
        identity["privateKey"].encode(), password=None, backend=default_backend(),
    )
    signature = private_key.sign(payload)

    return {
        "id": identity["id"],
        "publicKey": identity["publicKey"],
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
        "signedAt": ts,
        "nonce": nonce,
    }


async def send_to_gateway(text, host="127.0.0.1", port=18789):
    import websockets
    import uuid

    uri = f"ws://{host}:{port}"
    logger.info("Sending to gateway: %s", text)

    identity = _get_device_identity()
    token = os.getenv("OPENCLAW_TOKEN", "")

    response_parts = []
    try:
        async with websockets.connect(uri, ping_interval=None, open_timeout=10) as ws:
            frame = await asyncio.wait_for(ws.recv(), timeout=10)
            challenge = json.loads(frame)
            if challenge.get("event") != "connect.challenge":
                logger.error("Expected connect.challenge, got: %s", challenge)
                return ""

            nonce = challenge["payload"]["nonce"]
            ts = challenge["payload"]["ts"]
            signed_device = _sign_challenge(identity, nonce, ts, token)

            connect_req = {
                "type": "req",
                "id": str(uuid.uuid4()),
                "method": "connect",
                "params": {
                    "minProtocol": 3, "maxProtocol": 3,
                    "client": {"id": "cli", "version": "1.0.0",
                               "platform": "linux", "mode": "cli"},
                    "role": "operator",
                    "scopes": DEFAULT_SCOPES,
                    "auth": {"token": token},
                    "device": signed_device,
                    "locale": "en-US",
                    "userAgent": "deskclaw-voice/1.0.0",
                    "caps": ["agent-events", "tool-events"],
                },
            }
            await ws.send(json.dumps(connect_req))

            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            resp_data = json.loads(resp)
            if not resp_data.get("ok"):
                error = resp_data.get("error", {})
                logger.error("Gateway connect failed: %s - %s",
                             error.get("code"), error.get("message"))
                return ""

            logger.info("Connected to gateway")

            session_key = "agent:main:voice-client"
            chat_id = str(uuid.uuid4())
            await ws.send(json.dumps({
                "type": "req", "id": chat_id, "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": text,
                    "idempotencyKey": f"voice-{chat_id}",
                },
            }))

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                except asyncio.TimeoutError:
                    logger.warning("Gateway response timed out")
                    break

                data = json.loads(raw)
                if data.get("event") in ("agent", "chat"):
                    evt = data.get("payload", {})
                    stream = evt.get("stream")
                    evt_data = evt.get("data", {})

                    if stream == "assistant":
                        delta = evt_data.get("delta", "")
                        if delta:
                            response_parts.append(delta)
                    elif stream == "lifecycle" and evt_data.get("phase") in ("end", "error"):
                        break

    except Exception as e:
        logger.error("Gateway connection failed: %s", e)

    return "".join(response_parts)


# ── Main loop ────────────────────────────────────────────────────────────
async def main():
    config = load_config()
    gw_cfg = config.get("gateway", {})
    gw_host = gw_cfg.get("host", "127.0.0.1")
    gw_port = gw_cfg.get("port", 18789)
    wake_word = config.get("voice", {}).get("wake", {}).get("wake_word", "hey claw")

    if wake_word.lower() not in WAKE_PHRASES:
        WAKE_PHRASES.append(wake_word.lower())

    whisper_url = config.get("stt", {}).get("whisper_server", "ws://localhost:8765")
    logger.info("Connecting to whisper server at %s …", whisper_url)

    import websockets

    state = State.IDLE
    command_buffer: list[str] = []
    rolling_buffer: list[str] = []
    last_text_time = 0.0
    wake_time = 0.0

    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)

    async with websockets.connect(whisper_url, ping_interval=20,
                                  ping_timeout=60, max_size=2**22) as whisper_ws:
        logger.info("Connected to whisper server")
        print(f"\n  Listening for '{wake_word}'… (Ctrl+C to quit)\n")

        transcript_queue: asyncio.Queue[str] = asyncio.Queue()

        async def recv_transcripts():
            """Read transcription results from the whisper server."""
            try:
                async for raw in whisper_ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "transcript":
                        await transcript_queue.put(msg["text"])
            except websockets.ConnectionClosed:
                logger.warning("Whisper server disconnected")

        async def audio_and_logic():
            nonlocal state, last_text_time, wake_time

            loop = asyncio.get_event_loop()

            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="float32", blocksize=chunk_samples) as mic:
                while True:
                    # Read audio from mic in a thread so we don't block the loop
                    audio_chunk, overflowed = await loop.run_in_executor(
                        None, mic.read, chunk_samples,
                    )
                    if overflowed:
                        logger.warning("Audio buffer overflow")

                    audio_data = audio_chunk[:, 0].astype(np.float32)

                    if state != State.PROCESSING:
                        await whisper_ws.send(audio_data.tobytes())

                    # Drain all available transcripts
                    text = None
                    while not transcript_queue.empty():
                        text = transcript_queue.get_nowait()

                    if text is None:
                        # No new transcript this iteration
                        if state == State.ACTIVE:
                            has_words = len(command_buffer) > 0
                            if has_words and (time.time() - last_text_time) > SILENCE_TIMEOUT:
                                await _process_command(
                                    command_buffer, config, gw_host, gw_port, whisper_ws,
                                )
                                command_buffer.clear()
                                rolling_buffer.clear()
                                state = State.IDLE
                                print(f"\n  Listening for '{wake_word}'…\n")
                            elif not has_words and (time.time() - wake_time) > WAKE_TIMEOUT:
                                logger.warning("No speech after wake phrase")
                                print(f"\n  No command heard. Listening for '{wake_word}'…\n")
                                rolling_buffer.clear()
                                await whisper_ws.send(json.dumps({"type": "reset"}))
                                state = State.IDLE
                        continue

                    logger.debug("Whisper: '%s'  [state=%s]", text, state.value)

                    if state == State.IDLE:
                        rolling_buffer.append(text)
                        if len(rolling_buffer) > ROLLING_BUFFER_SIZE:
                            rolling_buffer.pop(0)

                        found, remainder = check_rolling_buffer(rolling_buffer)
                        if not found:
                            found = contains_wake_phrase(text)
                            if found:
                                remainder = strip_wake_phrase(text)

                        if found:
                            logger.info("Wake phrase detected!")
                            print("  Wake phrase detected! Listening for command…")
                            state = State.ACTIVE
                            command_buffer.clear()
                            rolling_buffer.clear()
                            wake_time = time.time()
                            last_text_time = wake_time
                            if remainder:
                                command_buffer.append(remainder)
                                last_text_time = time.time()
                            await whisper_ws.send(json.dumps({"type": "reset"}))

                    elif state == State.ACTIVE:
                        command_buffer.append(text)
                        last_text_time = time.time()

        recv_task = asyncio.create_task(recv_transcripts())
        try:
            await audio_and_logic()
        finally:
            recv_task.cancel()


async def _process_command(command_buffer, config, gw_host, gw_port, whisper_ws):
    command_text = " ".join(command_buffer).strip()
    if not command_text:
        return

    logger.info("Command: '%s'", command_text)
    print(f"  You: {command_text}")

    response = await send_to_gateway(command_text, gw_host, gw_port)

    if response:
        logger.info("Response: %s", response[:200])
        print(f"  Claw: {response}")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, stream_speak, response, config)
        except Exception as e:
            logger.error("TTS/playback failed: %s", e)
    else:
        logger.warning("Empty response from gateway")

    await whisper_ws.send(json.dumps({"type": "reset"}))


if __name__ == "__main__":
    print("=" * 50)
    print("  OpenClaw Voice Client  (Pi → Mac Whisper)")
    print("  Mic: Nulea C905 webcam")
    print("  Speaker: JBL Go 3 (Bluetooth)")
    print("=" * 50)
    print()
    print("  Prerequisites:")
    print("    1. whisper_server.py running on Mac")
    print("    2. OpenClaw gateway running: openclaw gateway")
    print("    3. JBL Go 3 paired and connected via Bluetooth")
    print("    4. Webcam mic set as default audio source")
    print("    5. .env file with ELEVENLABS_API_KEY")
    print()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Shutting down voice client.")
