#!/usr/bin/env python3
"""
OpenClaw Voice Client
Listens via webcam mic using whisper_streaming, detects "Hey Claw" wake phrase,
sends commands to the OpenClaw gateway, converts responses to speech via ElevenLabs,
and plays audio through the JBL Go 3 Bluetooth speaker.
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

# Add whisper_streaming to path
SCRIPT_DIR = Path(__file__).parent.resolve()
WHISPER_STREAMING_DIR = SCRIPT_DIR / "whisper_streaming"
sys.path.insert(0, str(WHISPER_STREAMING_DIR))

from whisper_online import OpenaiApiASR, OnlineASRProcessor

load_dotenv(SCRIPT_DIR.parent / ".env")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.WARNING,
)
logger = logging.getLogger("voice_client")
logger.setLevel(logging.DEBUG)

SAMPLE_RATE = 16000
CHUNK_DURATION = 1.0  # seconds per audio chunk fed to whisper
SILENCE_TIMEOUT = 3.0  # seconds of no new text before command is considered complete
WAKE_TIMEOUT = 10.0  # max seconds to wait for first word after wake phrase
WAKE_PHRASES = [
    "hey claw", "hey claude", "hey clawed", "hey clog", "hey clo",
    "hey law", "hey claws", "a claw", "hey clock", "hey claw.",
]
ROLLING_BUFFER_SIZE = 4

WHISPER_HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching",
    "bye", "goodbye", "bye now",
    "thanks for listening", "subscribe", "see you next time",
    "you", "thank you.", "thanks.", "bye.", "the end",
    "thanks for watching!", "please subscribe", "power supply",
    "oh", "now",
}

OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


class State(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"


def load_config():
    config_path = SCRIPT_DIR / "openclaw.json"
    with open(config_path) as f:
        return json.load(f)


def contains_wake_phrase(text):
    lower = text.lower().strip()
    return any(phrase in lower for phrase in WAKE_PHRASES)


def strip_wake_phrase(text):
    lower = text.lower()
    for phrase in WAKE_PHRASES:
        idx = lower.find(phrase)
        if idx != -1:
            return text[idx + len(phrase):].strip()
    return text.strip()


def check_rolling_buffer(rolling_buffer):
    """Check if the concatenation of recent texts contains a wake phrase."""
    for i in range(len(rolling_buffer)):
        combined = " ".join(rolling_buffer[i:]).lower().strip()
        for phrase in WAKE_PHRASES:
            if phrase in combined:
                after = combined.split(phrase, 1)[1].strip()
                return True, after
    return False, ""


def text_to_speech(text, config):
    """Convert text to MP3 via ElevenLabs API. Returns path to the MP3 file."""
    tts_config = config["tts"]
    api_key = os.getenv("ELEVENLABS_API_KEY", tts_config.get("api_key", ""))
    voice_id = tts_config.get("voice_id", "nPczCjzI2devNBz1zQrb")
    model_id = tts_config.get("model", "eleven_multilingual_v2")

    max_len = tts_config.get("max_speak_length", 500)
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
        logger.info("Truncated TTS text to %d chars", len(text))

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    logger.info("TTS request: %d chars, voice=%s, model=%s", len(text), voice_id, model_id)
    resp = requests.post(url, json=payload, headers=headers, timeout=(10, 60))
    resp.raise_for_status()

    filename = OUTPUT_DIR / f"response_{int(time.time())}.mp3"
    filename.write_bytes(resp.content)
    logger.info("TTS saved to %s (%d bytes)", filename, len(resp.content))
    return filename


def play_mp3(filepath):
    """Play an MP3 file through mpg123 (routes to default PulseAudio sink / JBL Go 3)."""
    try:
        subprocess.run(["mpg123", "--quiet", str(filepath)], check=True)
    except FileNotFoundError:
        logger.error("mpg123 not found. Install with: sudo apt-get install mpg123")
    except subprocess.CalledProcessError as e:
        logger.error("mpg123 playback failed: %s", e)


IDENTITY_FILE = SCRIPT_DIR / "device_identity.json"
DEFAULT_SCOPES = [
    "operator.read", "operator.write", "operator.admin",
    "operator.approvals", "operator.pairing",
]


def _get_device_identity():
    """Load or generate an Ed25519 device identity for gateway auth."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    import hashlib
    import base64

    if IDENTITY_FILE.exists():
        return json.loads(IDENTITY_FILE.read_text())

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
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
    logger.info("Generated new device identity: %s", IDENTITY_FILE)
    return identity


def _sign_challenge(identity, nonce, ts, token=""):
    """Sign the gateway connect challenge with the device's Ed25519 key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    import base64

    parts = [
        "v2", identity["id"], "cli", "cli", "operator",
        ",".join(DEFAULT_SCOPES), str(ts), token, nonce,
    ]
    payload = "|".join(parts).encode()

    private_key = serialization.load_pem_private_key(
        identity["privateKey"].encode(), password=None, backend=default_backend()
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
    """Send a chat message to the OpenClaw gateway via WebSocket and collect the response."""
    import websockets
    import uuid

    uri = f"ws://{host}:{port}"
    logger.info("Sending to OpenClaw gateway: %s", text)

    identity = _get_device_identity()
    token = os.getenv("OPENCLAW_TOKEN", "")

    response_parts = []
    try:
        async with websockets.connect(uri, ping_interval=None, open_timeout=10) as ws:
            # Step 1: Receive connect.challenge
            frame = await asyncio.wait_for(ws.recv(), timeout=10)
            challenge = json.loads(frame)

            if challenge.get("event") != "connect.challenge":
                logger.error("Expected connect.challenge, got: %s", challenge)
                return ""

            nonce = challenge["payload"]["nonce"]
            ts = challenge["payload"]["ts"]
            signed_device = _sign_challenge(identity, nonce, ts, token)

            # Step 2: Send connect request
            connect_req = {
                "type": "req",
                "id": str(uuid.uuid4()),
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {"id": "cli", "version": "1.0.0", "platform": "linux", "mode": "cli"},
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

            # Step 3: Wait for hello-ok
            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            resp_data = json.loads(resp)

            if not resp_data.get("ok"):
                error = resp_data.get("error", {})
                logger.error("Gateway connect failed: %s - %s",
                             error.get("code"), error.get("message"))
                return ""

            logger.info("Connected to gateway")

            # Step 4: Send chat message
            session_key = "agent:main:voice-client"
            chat_id = str(uuid.uuid4())

            await ws.send(json.dumps({
                "type": "req",
                "id": chat_id,
                "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": text,
                    "idempotencyKey": f"voice-{chat_id}",
                },
            }))

            # Step 5: Listen for response events
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


def main():
    config = load_config()
    gateway_config = config.get("gateway", {})
    gw_host = gateway_config.get("host", "127.0.0.1")
    gw_port = gateway_config.get("port", 18789)
    wake_word = config.get("voice", {}).get("wake", {}).get("wake_word", "hey claw")

    if wake_word.lower() not in WAKE_PHRASES:
        WAKE_PHRASES.append(wake_word.lower())

    logger.info("Initializing OpenAI Whisper API backend...")
    asr = OpenaiApiASR(lan="en", temperature=0)
    online = OnlineASRProcessor(asr, buffer_trimming=("segment", 15))

    state = State.IDLE
    command_buffer = []
    rolling_buffer = []
    last_text_time = 0.0
    wake_time = 0.0

    logger.info("Voice client ready. Say '%s' to activate.", wake_word)
    print(f"\n  Listening for '{wake_word}'... (Ctrl+C to quit)\n")

    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=chunk_samples) as stream:
            while True:
                audio_chunk, overflowed = stream.read(chunk_samples)
                if overflowed:
                    logger.warning("Audio buffer overflow")

                audio_data = audio_chunk[:, 0].astype(np.float32)

                if state == State.PROCESSING:
                    continue

                online.insert_audio_chunk(audio_data)
                beg, end, text = online.process_iter()

                if text:
                    logger.debug("Whisper: '%s' [state=%s]", text, state.value)

                if text and text.strip().lower().rstrip(".!") in WHISPER_HALLUCINATIONS:
                    logger.debug("Ignoring hallucination: '%s'", text)
                    text = ""

                if not text:
                    if state == State.ACTIVE:
                        has_words = len(command_buffer) > 0
                        timed_out = False
                        if has_words and (time.time() - last_text_time) > SILENCE_TIMEOUT:
                            timed_out = True
                        elif not has_words and (time.time() - wake_time) > WAKE_TIMEOUT:
                            logger.warning("No speech detected after wake phrase, returning to idle")
                            print(f"\n  No command heard. Listening for '{wake_word}'...\n")
                            rolling_buffer.clear()
                            online.init()
                            state = State.IDLE
                            continue
                        if not timed_out:
                            continue
                        command_text = " ".join(command_buffer).strip()
                        if command_text:
                            state = State.PROCESSING
                            logger.info("Command captured: '%s'", command_text)
                            print(f"  You: {command_text}")

                            response = asyncio.run(
                                send_to_gateway(command_text, gw_host, gw_port)
                            )

                            if response:
                                logger.info("Gateway response: %s", response[:200])
                                print(f"  Claw: {response}")

                                try:
                                    mp3_path = text_to_speech(response, config)
                                    play_mp3(mp3_path)
                                except Exception as e:
                                    logger.error("TTS/playback failed: %s", e)
                            else:
                                logger.warning("Empty response from gateway")

                            command_buffer.clear()
                            rolling_buffer.clear()
                            online.init()
                            state = State.IDLE
                            logger.info("Back to idle. Listening for '%s'...", wake_word)
                            print(f"\n  Listening for '{wake_word}'...\n")
                    continue

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
                        print("  Wake phrase detected! Listening for command...")
                        state = State.ACTIVE
                        command_buffer.clear()
                        rolling_buffer.clear()
                        wake_time = time.time()
                        last_text_time = wake_time
                        if remainder:
                            command_buffer.append(remainder)
                            last_text_time = time.time()
                        online.init()

                elif state == State.ACTIVE:
                    command_buffer.append(text)
                    last_text_time = time.time()

    except KeyboardInterrupt:
        print("\n  Shutting down voice client.")
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)


if __name__ == "__main__":
    print("=" * 50)
    print("  OpenClaw Voice Client")
    print("  Mic: Nulea C905 webcam")
    print("  Speaker: JBL Go 3 (Bluetooth)")
    print("=" * 50)
    print()
    print("  Prerequisites:")
    print("    1. OpenClaw gateway running: openclaw gateway")
    print("    2. JBL Go 3 paired and connected via Bluetooth")
    print("    3. Webcam mic set as default audio source")
    print("    4. .env file with OPENAI_API_KEY and ELEVENLABS_API_KEY")
    print()
    main()
