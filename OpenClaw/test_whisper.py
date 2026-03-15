#!/usr/bin/env python3
"""Quick test to load faster-whisper tiny.en and transcribe a short clip."""

import time
import numpy as np

print("Importing faster_whisper...")
t0 = time.time()
from faster_whisper import WhisperModel
print(f"  Import: {time.time() - t0:.1f}s")

print("Loading tiny.en model (CPU, int8)...")
t0 = time.time()
model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
print(f"  Load:   {time.time() - t0:.1f}s")

print("Transcribing 3s of silence (warm-up)...")
t0 = time.time()
silence = np.zeros(16000 * 3, dtype=np.float32)
segments, info = model.transcribe(silence, language="en", beam_size=5)
list(segments)
print(f"  Infer:  {time.time() - t0:.1f}s")

print("\nAll good. faster-whisper is working.")
