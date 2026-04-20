# Raspberry Pi Deployment

Target hardware: **Raspberry Pi 3 Model B** running **Raspberry Pi OS 64-bit**.
The Pi auto-starts three systemd services on boot:

| Service                      | What it does                                                            |
| ---------------------------- | ----------------------------------------------------------------------- |
| `sms-printer.service`        | The Flask app (`app.py`) — receives Twilio SMS and prints them.         |
| `sms-printer-ngrok.service`  | Starts the ngrok HTTPS tunnel pointing at port 5000.                    |
| `sms-printer-webhook.service` | Waits for ngrok, then updates the Twilio SMS webhook to the new URL.   |

## 1. Prepare the SD card

Flash **Raspberry Pi OS (64-bit)** using Raspberry Pi Imager. In the imager
settings, preconfigure:
- hostname (e.g. `smsprinter`)
- username + password
- Wi-Fi SSID / password
- enable SSH

Boot the Pi and SSH in.

## 2. Clone the project

```bash
sudo apt-get update
sudo apt-get install -y git
git clone <this repo> ~/sms-printer
cd ~/sms-printer
```

## 3. Configure credentials

```bash
cp .env.example .env
nano .env
```

Fill in:
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- `NGROK_AUTHTOKEN` — get one at https://dashboard.ngrok.com
- (optional) `IG_USER_ID`, `IG_ACCESS_TOKEN` for the Instagram poller

## 4. Identify the printer

Plug the thermal printer into a USB port and run:

```bash
lsusb
```

You should see a line like `ID 0416:5011 ...`. There are two ways to use it:

**Option A — character device (simplest).** Leave `PRINTER_USB_VENDOR` /
`PRINTER_USB_PRODUCT` blank in `.env`. The app writes raw ESC/POS to
`PRINTER_DEVICE` (default `/dev/usb/lp0`). This works on most POS-80 clones out
of the box.

**Option B — USB vendor/product ids.** Put the hex values from `lsusb` into
`PRINTER_USB_VENDOR` and `PRINTER_USB_PRODUCT` in `.env`. The app talks to the
printer via `python-escpos` + `pyusb` directly. Use this if `/dev/usb/lp0`
doesn't appear (some printers need it).

If your printer's vendor id is not in
[`deploy/99-escpos-printer.rules`](99-escpos-printer.rules), add a line for it
and re-run `sudo udevadm control --reload-rules && sudo udevadm trigger`.

## 5. Run the installer

```bash
sudo bash deploy/install.sh
```

This script:
- installs apt packages (`python3-venv`, `libusb-1.0-0`, `usbutils`, …)
- creates a Python virtualenv at `~/sms-printer/venv`
- downloads the ARM64 ngrok binary to `/usr/local/bin/ngrok`
- registers your `NGROK_AUTHTOKEN`
- adds your user to the `lp` group so it can talk to the USB printer
- installs the udev rules and three systemd units, and enables them on boot

Reboot to verify auto-start:

```bash
sudo reboot
```

After the Pi comes back up, visit `http://<pi-hostname>.local:5000` on your
LAN to see the dashboard, and send a test SMS to your Twilio number.

## 6. Day-to-day operations

```bash
# Tail the app logs
journalctl -u sms-printer.service -f

# Check that all three services are up
systemctl status sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service

# Restart after changing .env
sudo systemctl restart sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service

# Remove everything (keeps the code + venv)
sudo bash deploy/uninstall.sh
```

## Troubleshooting

- **`/dev/usb/lp0` missing** → switch to Option B (vendor/product ids), or
  `sudo modprobe usblp`. If the kernel is refusing to bind it because ESC/POS
  tools grabbed it, removing `usblp` is expected when using pyusb directly.
- **`permission denied` on the printer** → confirm your user is in the `lp`
  group (`groups`) and that the udev rule matches `lsusb` output. Re-login
  after `usermod -aG lp`.
- **Twilio webhook 502s after a reboot** → `sms-printer-webhook.service`
  re-registers the ngrok URL on each boot, but ngrok free URLs change every
  restart. Check `systemctl status sms-printer-webhook.service` to confirm it
  ran successfully. A paid ngrok plan with a reserved domain avoids this.
- **Instagram poller silent** → `IG_USER_ID` / `IG_ACCESS_TOKEN` not set.
  Check `journalctl -u sms-printer.service | grep IG`.
