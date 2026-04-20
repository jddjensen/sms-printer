# Raspberry Pi Deployment

Target hardware: **Raspberry Pi 3 Model B** running **Raspberry Pi OS 64-bit**.
Three systemd services start automatically at boot:

| Service                       | What it does                                                                      |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `sms-printer.service`         | The Flask app — receives Twilio SMS and prints them. Eventlet WSGI, systemd watchdog, auto-restarts on any hang or crash. |
| `sms-printer-ngrok.service`   | Starts the ngrok HTTPS tunnel pointing at port 5000. Respects `NGROK_DOMAIN` / `NGROK_REGION`. |
| `sms-printer-webhook.service` | Waits for ngrok, then updates the Twilio SMS webhook to the new URL.              |

## What makes the Pi install stable

- **Production WSGI.** SocketIO runs under `eventlet`, not Flask's dev server.
- **Systemd watchdog.** The app sends `WATCHDOG=1` to systemd only if
  `GET /healthz` returns `200` from inside the process. If the Flask loop
  wedges, systemd kills and restarts it within ~60 seconds.
- **Aggressive auto-restart.** `Restart=always`, `RestartSec=3`,
  `StartLimitBurst=20` on a 10 minute window — survives transient Wi-Fi or
  USB blips.
- **Atomic state writes.** `ig_state.json` is written via `tmp + rename` so a
  mid-write power cut cannot corrupt it.
- **Capped journald.** Logs are bounded (200 MB max, 30 day retention) so they
  cannot fill the SD card.
- **SD-card-friendly sysctl.** `vm.swappiness=10`, faster writeback — less wear,
  less data lost on a hard power cut.
- **`Requires=` chain.** ngrok requires the app; the webhook service requires
  ngrok. Fix the root cause, everything downstream follows.

## 1. Prepare the SD card

Flash **Raspberry Pi OS (64-bit)** with Raspberry Pi Imager. In imager
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
- (optional) `NGROK_DOMAIN` — a reserved domain (paid ngrok plan). **With a
  reserved domain the Twilio webhook never has to be rewritten, so the
  webhook service becomes a no-op after the first boot.**
- (optional) `IG_USER_ID`, `IG_ACCESS_TOKEN` for the Instagram poller

## 4. Identify the printer

Plug the thermal printer in and run `lsusb`. You should see something like
`ID 0416:5011 ...`.

- **Easy path:** leave `PRINTER_USB_VENDOR` / `PRINTER_USB_PRODUCT` blank. The
  app writes raw ESC/POS to `PRINTER_DEVICE` (default `/dev/usb/lp0`).
- **pyusb path:** set `PRINTER_USB_VENDOR` and `PRINTER_USB_PRODUCT` from
  `lsusb`. Use this if `/dev/usb/lp0` doesn't show up.

If your printer's vendor id is not already in
[`99-escpos-printer.rules`](99-escpos-printer.rules), add a line and rerun
`sudo udevadm control --reload-rules && sudo udevadm trigger`.

## 5. Run the installer

```bash
sudo bash deploy/install.sh
```

Then reboot:

```bash
sudo reboot
```

Visit `http://<pi-hostname>.local:5000` from any device on the LAN to see the
dashboard, and send a test SMS to your Twilio number.

## 6. Day-to-day operations

```bash
# Tail the app logs
journalctl -u sms-printer.service -f

# Check everything is up
systemctl status sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service

# Health probe (what systemd itself uses as the watchdog signal)
curl http://localhost:5000/healthz

# Restart after changing .env
sudo systemctl restart sms-printer.service sms-printer-ngrok.service sms-printer-webhook.service

# Remove everything (keeps the code + venv)
sudo bash deploy/uninstall.sh
```

## Troubleshooting

- **Service keeps restarting** → `journalctl -u sms-printer.service -n 200`.
  The watchdog only fires if `/healthz` fails — check what's unhealthy.
- **`/dev/usb/lp0` missing** → switch to pyusb path (vendor + product ids), or
  `sudo modprobe usblp`. Some printers need one or the other; try both.
- **`permission denied` on the printer** → confirm your user is in the `lp`
  group (`groups`) and re-login after `usermod -aG lp`. The udev rule must
  match `lsusb` output.
- **Twilio webhook 502s after reboot** → without a reserved domain, ngrok
  gives a new URL every boot. `sms-printer-webhook.service` waits up to
  ~3 minutes for ngrok then updates Twilio. Check
  `systemctl status sms-printer-webhook.service`. Setting `NGROK_DOMAIN`
  eliminates this entire class of problem.
- **Instagram poller silent** → `journalctl -u sms-printer.service | grep IG`
  will tell you whether the tokens are set.
