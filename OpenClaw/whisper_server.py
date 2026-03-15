#!/usr/bin/env python3
"""
Whisper ASR Server
Runs on a fast machine (Mac/desktop). Accepts raw 16 kHz float32 audio over
WebSocket, feeds it through faster-whisper via OnlineASRProcessor, and sends
transcription results back to the client.

Protocol
--------
Client -> Server:
    binary frame : raw float32 samples (16 kHz mono)
    text   frame : JSON  {"type": "reset"}  — reinitialise the ASR buffer

Server -> Client:
    text   frame : JSON  {"type": "transcript", "text": "..."}

Usage:
    python whisper_server.py [--host 0.0.0.0] [--port 8765] [--model tiny.en]
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR / "whisper_streaming"))

from whisper_online import FasterWhisperASR, OnlineASRProcessor

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("whisper_server")

SAMPLE_RATE = 16000

HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you for watching",
    "bye", "goodbye", "bye now",
    "thanks for listening", "subscribe", "see you next time",
    "you", "thank you.", "thanks.", "bye.", "the end",
    "thanks for watching!", "please subscribe", "power supply",
    "oh", "now",
}


def build_asr(model: str):
    logger.info("Loading model '%s' …", model)
    if os.path.isdir(model):
        asr = FasterWhisperASR(lan="en", model_dir=model)
    else:
        asr = FasterWhisperASR(lan="en", modelsize=model)
    logger.info("Model ready.")
    return asr


async def handle_client(ws, asr):
    import websockets

    addr = ws.remote_address
    logger.info("Client connected: %s", addr)

    online = OnlineASRProcessor(asr, buffer_trimming=("segment", 15))

    try:
        async for message in ws:
            if isinstance(message, bytes):
                audio = np.frombuffer(message, dtype=np.float32)
                online.insert_audio_chunk(audio)

                beg, end, text = online.process_iter()
                if text:
                    cleaned = text.strip()
                    if cleaned.lower().rstrip(".!") in HALLUCINATIONS:
                        logger.debug("Filtered hallucination: '%s'", cleaned)
                        continue
                    logger.info("Transcript: '%s'", cleaned)
                    await ws.send(json.dumps({
                        "type": "transcript",
                        "text": text,
                    }))

            elif isinstance(message, str):
                try:
                    msg = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "reset":
                    logger.info("ASR reset requested")
                    online.init()

    except websockets.ConnectionClosed:
        pass
    finally:
        logger.info("Client disconnected: %s", addr)


async def main(host: str, port: int, model: str):
    import websockets

    asr = build_asr(model)

    async with websockets.serve(
        lambda ws: handle_client(ws, asr),
        host,
        port,
        max_size=2**22,  # ~4 MB — plenty for audio chunks
    ):
        logger.info("Whisper server listening on ws://%s:%d", host, port)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Whisper ASR WebSocket server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default="tiny.en",
                        help="Model name (e.g. tiny.en) or path to local model dir")
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port, args.model))
