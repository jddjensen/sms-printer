#!/usr/bin/env bash
# Install the SMS Printer stack on Raspberry Pi OS (64-bit).
# Run from the project root:  sudo bash deploy/install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This installer must be run with sudo." >&2
    exit 1
fi

# Resolve the invoking user and their project directory.
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo ">> Installing for user: $RUN_USER"
echo ">> Project directory:   $INSTALL_DIR"

# --- System packages ---------------------------------------------------------
echo ">> Installing apt packages"
apt-get update
apt-get install -y \
    python3 python3-venv python3-pip python3-dev \
    libusb-1.0-0 libjpeg-dev zlib1g-dev build-essential \
    curl unzip usbutils ca-certificates

# --- Python virtualenv -------------------------------------------------------
echo ">> Building Python virtualenv"
sudo -u "$RUN_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$RUN_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel
sudo -u "$RUN_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# --- ngrok (ARM64) -----------------------------------------------------------
if ! command -v ngrok >/dev/null 2>&1; then
    echo ">> Downloading ngrok (arm64)"
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/ngrok.tgz" \
        https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz
    tar -xzf "$tmp/ngrok.tgz" -C "$tmp"
    install -m 0755 "$tmp/ngrok" /usr/local/bin/ngrok
    rm -rf "$tmp"
else
    echo ">> ngrok already installed: $(command -v ngrok)"
fi

# --- ngrok authtoken + wrapper ------------------------------------------------
chmod +x "$INSTALL_DIR/deploy/ngrok-run.sh"

if [[ -f "$INSTALL_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    set -a; source "$INSTALL_DIR/.env"; set +a
    if [[ -n "${NGROK_AUTHTOKEN:-}" ]]; then
        echo ">> Configuring ngrok authtoken"
        sudo -u "$RUN_USER" ngrok config add-authtoken "$NGROK_AUTHTOKEN"
    else
        echo "!! NGROK_AUTHTOKEN not set in .env — add it and run 'ngrok config add-authtoken <token>' as $RUN_USER"
    fi
else
    echo "!! .env not found at $INSTALL_DIR/.env — copy .env.example and fill it in before starting the services"
fi

# --- Printer permissions -----------------------------------------------------
echo ">> Adding $RUN_USER to 'lp' group for USB printer access"
usermod -aG lp "$RUN_USER" || true

echo ">> Installing udev rules for USB thermal printers"
install -m 0644 "$INSTALL_DIR/deploy/99-escpos-printer.rules" /etc/udev/rules.d/99-escpos-printer.rules
udevadm control --reload-rules
udevadm trigger

# --- journald log caps (protect SD card) ------------------------------------
echo ">> Configuring journald log retention caps"
mkdir -p /etc/systemd/journald.conf.d
install -m 0644 "$INSTALL_DIR/deploy/journald-sms-printer.conf" \
    /etc/systemd/journald.conf.d/99-sms-printer.conf
systemctl restart systemd-journald

# --- sysctl tweaks for SD-card longevity ------------------------------------
echo ">> Applying sysctl tweaks"
install -m 0644 "$INSTALL_DIR/deploy/sysctl-sms-printer.conf" \
    /etc/sysctl.d/99-sms-printer.conf
sysctl --system >/dev/null || true

# --- Systemd units -----------------------------------------------------------
echo ">> Installing systemd units"
for unit in sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service; do
    sed -e "s|__USER__|$RUN_USER|g" \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$INSTALL_DIR/deploy/$unit" > "/etc/systemd/system/$unit"
done

systemctl daemon-reload
systemctl enable sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service

echo
echo "Install complete."
echo
echo "Next steps:"
echo "  1. Make sure $INSTALL_DIR/.env has your Twilio + ngrok credentials."
echo "  2. Plug in the thermal printer over USB. Verify with: lsusb"
echo "  3. Start everything now:"
echo "       sudo systemctl start sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service"
echo "  4. Tail logs with:"
echo "       journalctl -u sms-printer.service -f"
echo "  5. Reboot to confirm auto-start:  sudo reboot"
