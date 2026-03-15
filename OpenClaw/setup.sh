#!/bin/bash
set -euo pipefail

# OpenClaw Raspberry Pi Setup
# Hardware: Nulea C905 webcam mic (USB) + JBL Go 3 (Bluetooth speaker)

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
step "1/7  Updating system packages"
# ---------------------------------------------------------------------------
sudo apt-get update -y
sudo apt-get upgrade -y

# ---------------------------------------------------------------------------
step "2/7  Installing system audio & build dependencies"
# ---------------------------------------------------------------------------
sudo apt-get install -y \
    pulseaudio \
    pulseaudio-module-bluetooth \
    bluez \
    bluez-tools \
    alsa-utils \
    mpg123 \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    libportaudio2 \
    libsndfile1

# Ensure PulseAudio Bluetooth module loads on start
PULSE_DEFAULT="/etc/pulse/default.pa"
if [ -f "$PULSE_DEFAULT" ]; then
    if ! grep -q "module-bluetooth-discover" "$PULSE_DEFAULT"; then
        echo "load-module module-bluetooth-discover" | sudo tee -a "$PULSE_DEFAULT" > /dev/null
        info "Added module-bluetooth-discover to PulseAudio config"
    else
        info "module-bluetooth-discover already present in PulseAudio config"
    fi
fi

sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# ---------------------------------------------------------------------------
step "3/7  Installing Node.js 22 (for OpenClaw gateway)"
# ---------------------------------------------------------------------------
if command -v node &> /dev/null && [[ "$(node --version)" == v2[2-9]* || "$(node --version)" == v[3-9]* ]]; then
    info "Node.js $(node --version) already installed"
else
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
    info "Node.js $(node --version) installed"
fi

# ---------------------------------------------------------------------------
step "4/7  Installing OpenClaw"
# ---------------------------------------------------------------------------
if command -v openclaw &> /dev/null; then
    info "OpenClaw already installed: $(openclaw --version)"
else
    sudo npm install -g openclaw
    info "OpenClaw $(openclaw --version) installed"
fi

# ---------------------------------------------------------------------------
step "5/7  Setting up Python environment & whisper_streaming"
# ---------------------------------------------------------------------------

# Clone whisper_streaming if not present
if [ ! -d "$SCRIPT_DIR/whisper_streaming" ]; then
    git clone https://github.com/ufal/whisper_streaming.git "$SCRIPT_DIR/whisper_streaming"
    info "Cloned whisper_streaming"
else
    info "whisper_streaming already present"
fi

# Create Python virtual environment
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    python3 -m venv "$SCRIPT_DIR/venv"
    info "Created Python virtual environment"
fi

source "$SCRIPT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"
# whisper_streaming needs librosa and soundfile
pip install librosa soundfile
info "Python dependencies installed"

# ---------------------------------------------------------------------------
step "6/7  Pairing JBL Go 3 Bluetooth speaker"
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Bluetooth Pairing Instructions:${NC}"
echo "  1. Turn on your JBL Go 3"
echo "  2. Hold the Bluetooth button until the LED blinks (pairing mode)"
echo "  3. This script will scan for it and attempt to pair automatically"
echo ""
read -rp "Press Enter when the JBL Go 3 is in pairing mode..."

info "Scanning for Bluetooth devices (15 seconds)..."
sudo bluetoothctl -- power on
sudo bluetoothctl -- agent on
sudo bluetoothctl -- default-agent

JBL_MAC=""
SCAN_OUTPUT=$(timeout 15 sudo bluetoothctl -- scan on 2>&1 &)
sleep 15
sudo bluetoothctl -- scan off 2>/dev/null || true

JBL_MAC=$(bluetoothctl -- devices | grep -i "JBL" | head -1 | awk '{print $2}')

if [ -z "$JBL_MAC" ]; then
    warn "Could not auto-detect JBL Go 3."
    echo "Available devices:"
    bluetoothctl -- devices
    echo ""
    read -rp "Enter the MAC address of your JBL Go 3 (XX:XX:XX:XX:XX:XX): " JBL_MAC
fi

if [ -n "$JBL_MAC" ]; then
    info "Pairing with JBL Go 3 at $JBL_MAC..."
    bluetoothctl -- pair "$JBL_MAC" || warn "Pairing may have already been done"
    bluetoothctl -- trust "$JBL_MAC"
    bluetoothctl -- connect "$JBL_MAC"
    info "JBL Go 3 connected"
else
    warn "Skipping Bluetooth pairing. Pair manually later with bluetoothctl."
fi

# ---------------------------------------------------------------------------
step "7/7  Configuring audio devices"
# ---------------------------------------------------------------------------

sleep 3

info "Detecting Nulea C905 webcam microphone..."
WEBCAM_SOURCE=$(pactl list sources short 2>/dev/null | grep -i -E "usb|nulea|c905" | head -1 | awk '{print $2}')

if [ -z "$WEBCAM_SOURCE" ]; then
    WEBCAM_SOURCE=$(pactl list sources short 2>/dev/null | grep -v "monitor" | grep -i "input" | head -1 | awk '{print $2}')
fi

if [ -n "$WEBCAM_SOURCE" ]; then
    pactl set-default-source "$WEBCAM_SOURCE"
    info "Default audio source set to: $WEBCAM_SOURCE"
else
    warn "Could not auto-detect webcam mic. Available sources:"
    pactl list sources short
    echo ""
    echo "Set manually with: pactl set-default-source <source_name>"
fi

info "Detecting JBL Go 3 Bluetooth speaker..."
BT_SINK=$(pactl list sinks short 2>/dev/null | grep -i -E "bluez|jbl" | head -1 | awk '{print $2}')

if [ -n "$BT_SINK" ]; then
    pactl set-default-sink "$BT_SINK"
    info "Default audio sink set to: $BT_SINK"
else
    warn "Could not auto-detect JBL Go 3 sink. It may need a moment after connecting."
    echo "Available sinks:"
    pactl list sinks short
    echo ""
    echo "Set manually with: pactl set-default-sink <sink_name>"
fi

# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Run OpenClaw onboarding (first time only):"
echo "       openclaw onboard"
echo ""
echo "  2. Copy voice config:"
echo "       cp $SCRIPT_DIR/openclaw.json ~/.openclaw/openclaw.json"
echo "       cp $SCRIPT_DIR/SOUL.md ~/.openclaw/SOUL.md"
echo "       cp $SCRIPT_DIR/USER.md ~/.openclaw/USER.md"
echo ""
echo "  3. Start the OpenClaw gateway:"
echo "       openclaw gateway"
echo ""
echo "  4. In a second terminal, start the voice client:"
echo "       cd $SCRIPT_DIR"
echo "       source venv/bin/activate"
echo "       python voice_client.py"
echo ""
echo "  5. Say 'Hey Claw' and start talking!"
echo ""
echo "Verification commands:"
echo "  Test mic:     arecord -d 5 -f cd test.wav && aplay test.wav"
echo "  Test speaker: mpg123 /path/to/any.mp3"
echo "  List sources: pactl list sources short"
echo "  List sinks:   pactl list sinks short"
if [ -n "${JBL_MAC:-}" ]; then
    echo "  BT status:    bluetoothctl -- info $JBL_MAC"
fi
echo ""
