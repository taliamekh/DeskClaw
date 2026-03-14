#!/bin/bash
set -euo pipefail

# OpenClaw Raspberry Pi Setup
# Hardware: Nulea C905 webcam mic (USB) + JBL Go 3 (Bluetooth speaker)

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
step "1/6  Updating system packages"
# ---------------------------------------------------------------------------
sudo apt-get update -y
sudo apt-get upgrade -y

# ---------------------------------------------------------------------------
step "2/6  Installing system audio dependencies"
# ---------------------------------------------------------------------------
sudo apt-get install -y \
    pulseaudio \
    pulseaudio-module-bluetooth \
    bluez \
    bluez-tools \
    alsa-utils \
    mpg123 \
    curl

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

# Enable and start Bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# ---------------------------------------------------------------------------
step "3/6  Installing Node.js 22 via nvm"
# ---------------------------------------------------------------------------
export NVM_DIR="$HOME/.nvm"

if [ ! -d "$NVM_DIR" ]; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
fi

# Load nvm into current shell
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

if ! command -v nvm &> /dev/null; then
    error "nvm installation failed. Please restart your shell and re-run this script."
fi

nvm install 22
nvm use 22
nvm alias default 22
info "Node.js $(node --version) installed"

# ---------------------------------------------------------------------------
step "4/6  Installing OpenClaw"
# ---------------------------------------------------------------------------
npm install -g openclaw
info "OpenClaw $(openclaw --version) installed"

# ---------------------------------------------------------------------------
step "5/6  Pairing JBL Go 3 Bluetooth speaker"
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

# Scan and find JBL Go 3
JBL_MAC=""
SCAN_OUTPUT=$(timeout 15 sudo bluetoothctl -- scan on 2>&1 &)
sleep 15
sudo bluetoothctl -- scan off 2>/dev/null || true

# Look for JBL device in known devices
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
    warn "Skipping Bluetooth pairing. You can pair manually later with bluetoothctl."
fi

# ---------------------------------------------------------------------------
step "6/6  Configuring audio devices"
# ---------------------------------------------------------------------------

# Wait for PulseAudio to register devices
sleep 3

# --- Set Nulea C905 webcam mic as default source ---
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

# --- Set JBL Go 3 as default sink ---
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
echo "  1. Run the OpenClaw onboarding wizard:"
echo "       openclaw onboard"
echo ""
echo "  2. Copy your voice config into ~/.openclaw/openclaw.json"
echo "     (see OpenClaw/openclaw.json for the template)"
echo ""
echo "  3. Start OpenClaw:"
echo "       openclaw start"
echo ""
echo "Verification commands:"
echo "  Test mic:     arecord -d 5 -f cd test.wav && aplay test.wav"
echo "  Test speaker: mpg123 /path/to/any.mp3"
echo "  List sources: pactl list sources short"
echo "  List sinks:   pactl list sinks short"
echo "  BT status:    bluetoothctl -- info $JBL_MAC"
echo ""
