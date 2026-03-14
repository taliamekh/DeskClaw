#!/bin/bash
# play_response.sh -- Play TTS MP3 output through the default audio sink (JBL Go 3)
#
# Usage:
#   ./play_response.sh <path_to_mp3>
#   ./play_response.sh output/response.mp3
#
# OpenClaw's TTS generates MP3 files. On a headless Pi (no browser for WebChat),
# this script bridges the gap by playing each file via mpg123 through PulseAudio,
# which routes to the paired Bluetooth speaker.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <mp3_file>" >&2
    exit 1
fi

MP3_FILE="$1"

if [ ! -f "$MP3_FILE" ]; then
    echo "Error: File not found: $MP3_FILE" >&2
    exit 1
fi

if ! command -v mpg123 &> /dev/null; then
    echo "Error: mpg123 is not installed. Run: sudo apt-get install mpg123" >&2
    exit 1
fi

# Verify a Bluetooth sink is available; warn but don't block playback
BT_SINK=$(pactl list sinks short 2>/dev/null | grep -i "bluez" | head -1 | awk '{print $2}')
if [ -z "$BT_SINK" ]; then
    echo "Warning: No Bluetooth audio sink detected. Playing through default output." >&2
else
    pactl set-default-sink "$BT_SINK" 2>/dev/null || true
fi

mpg123 --quiet "$MP3_FILE"
