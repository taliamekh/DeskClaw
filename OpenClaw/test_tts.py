#!/usr/bin/env python3
"""Quick test for ElevenLabs TTS API — verifies key, model, and voice work."""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR.parent / ".env")

API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOICE_ID = "nPczCjzI2devNBz1zQrb"  # Brian
MODEL_ID = "eleven_flash_v2_5"
TEXT = "Hello, I am Claw. The voice system is working."

if not API_KEY:
    print("ELEVENLABS_API_KEY not found in .env")
    exit(1)

print(f"Key:   {API_KEY[:6]}...{API_KEY[-4:]}")
print(f"Voice: {VOICE_ID}")
print(f"Model: {MODEL_ID}")
print(f"Text:  {TEXT}")
print()

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
payload = {
    "text": TEXT,
    "model_id": MODEL_ID,
    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
}

start = time.time()
print("Sending request...")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=(10, 60))
    elapsed = time.time() - start
    print(f"Status: {resp.status_code} ({elapsed:.1f}s)")

    if resp.status_code == 200:
        out = SCRIPT_DIR / "output" / "test_tts.mp3"
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(resp.content)
        print(f"Saved:  {out} ({len(resp.content)} bytes)")
        print("\nPlay it with:  mpg123 output/test_tts.mp3")
    else:
        print(f"Error:  {resp.text}")
except requests.exceptions.ConnectTimeout:
    print(f"Connection timed out after {time.time() - start:.1f}s (can't reach ElevenLabs)")
except requests.exceptions.ReadTimeout:
    print(f"Read timed out after {time.time() - start:.1f}s (connected but response too slow)")
except Exception as e:
    print(f"Failed: {e}")
