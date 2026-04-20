#!/usr/bin/env bash
# Remove the SMS Printer systemd units. Does NOT delete the project directory,
# the venv, or ngrok.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This uninstaller must be run with sudo." >&2
    exit 1
fi

for unit in sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service; do
    systemctl disable --now "$unit" 2>/dev/null || true
    rm -f "/etc/systemd/system/$unit"
done

rm -f /etc/udev/rules.d/99-escpos-printer.rules
udevadm control --reload-rules || true
systemctl daemon-reload

echo "SMS Printer services removed."
