import os
import sys

IS_WINDOWS = sys.platform == "win32"

# eventlet must monkey-patch before *anything* that uses sockets/ssl is imported.
# On Windows we keep threading mode for simplicity.
if not IS_WINDOWS:
    try:
        import eventlet  # type: ignore

        eventlet.monkey_patch()
        _ASYNC_MODE = "eventlet"
    except ImportError:
        _ASYNC_MODE = "threading"
else:
    _ASYNC_MODE = "threading"

import json
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit
from twilio.twiml.messaging_response import MessagingResponse

if IS_WINDOWS:
    import win32print

app = Flask(__name__)
socketio = SocketIO(app, async_mode=_ASYNC_MODE, cors_allowed_origins="*")

PRINTER_NAME = os.environ.get("PRINTER_NAME", "POS-80")
PRINTER_DEVICE = os.environ.get("PRINTER_DEVICE", "/dev/usb/lp0")
PRINTER_USB_VENDOR = os.environ.get("PRINTER_USB_VENDOR", "").strip()
PRINTER_USB_PRODUCT = os.environ.get("PRINTER_USB_PRODUCT", "").strip()
printing_enabled = True

# ── Instagram polling config ─────────────────────────────────────────────
IG_USER_ID = os.environ.get("IG_USER_ID", "").strip()
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
IG_POLL_INTERVAL = int(os.environ.get("IG_POLL_INTERVAL", "300"))
IG_GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v21.0")
STATE_FILE = Path(__file__).with_name("ig_state.json")


# ── systemd notify (no external deps) ────────────────────────────────────
def sd_notify(state: str) -> None:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(addr)
            sock.sendall(state.encode())
        finally:
            sock.close()
    except OSError:
        pass


# ── Printer drivers ──────────────────────────────────────────────────────
def _raw_print_windows(job_name: str, payload: bytes) -> None:
    hprinter = win32print.OpenPrinter(PRINTER_NAME)
    try:
        win32print.StartDocPrinter(hprinter, 1, (job_name, None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, payload)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


def _raw_print_linux(job_name: str, payload: bytes) -> None:
    if PRINTER_USB_VENDOR and PRINTER_USB_PRODUCT:
        from escpos.printer import Usb

        p = Usb(int(PRINTER_USB_VENDOR, 16), int(PRINTER_USB_PRODUCT, 16))
        try:
            p._raw(payload)
        finally:
            p.close()
        return

    with open(PRINTER_DEVICE, "wb") as f:
        f.write(payload)


def _raw_print(job_name: str, payload: bytes) -> None:
    if IS_WINDOWS:
        _raw_print_windows(job_name, payload)
    else:
        _raw_print_linux(job_name, payload)


def print_sms(from_number, body):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "\n",
        "NEW MESSAGE\n",
        "-" * 32 + "\n",
        f"From: {from_number}\n",
        f"Time: {timestamp}\n",
        "-" * 32 + "\n",
        f"\n{body}\n",
        "\n\n\n\n\n\n",
    ]
    cut = b"\x1d\x56\x41\x05"
    _raw_print("SMS", "".join(lines).encode("utf-8") + cut)


def print_follower_update(username: str, count: int, delta: int) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    arrow = "+" if delta > 0 else ""
    label = "NEW FOLLOWER" if delta > 0 else "UNFOLLOW"
    lines = [
        "\n",
        f"{label}\n",
        "-" * 32 + "\n",
        f"@{username}\n",
        f"Time: {timestamp}\n",
        "-" * 32 + "\n",
        "\n",
        f"  Followers: {count:,}\n",
        f"  Change:    {arrow}{delta}\n",
        "\n\n\n\n\n\n",
    ]
    cut = b"\x1d\x56\x41\x05"
    _raw_print("IG-Followers", "".join(lines).encode("utf-8") + cut)


# ── State helpers (atomic write so a mid-write power cut can't corrupt) ──
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


# ── Instagram poller ─────────────────────────────────────────────────────
def fetch_ig_snapshot() -> dict | None:
    url = f"https://graph.facebook.com/{IG_GRAPH_VERSION}/{IG_USER_ID}"
    params = {
        "fields": "username,followers_count",
        "access_token": IG_ACCESS_TOKEN,
    }
    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code != 200:
        print(f"[IG] API error {resp.status_code}: {resp.text}", flush=True)
        return None
    return resp.json()


def ig_poller():
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("[IG] IG_USER_ID / IG_ACCESS_TOKEN not set — poller disabled.", flush=True)
        return

    state = load_state()
    last_count = state.get("followers_count")
    print(f"[IG] Poller started (interval={IG_POLL_INTERVAL}s, last_count={last_count})", flush=True)

    while True:
        try:
            snap = fetch_ig_snapshot()
            if snap:
                username = snap.get("username", "unknown")
                count = snap.get("followers_count")
                if count is None:
                    print(f"[IG] No followers_count in response: {snap}", flush=True)
                elif last_count is None:
                    print(f"[IG] Baseline set: @{username} = {count}", flush=True)
                    last_count = count
                    save_state({"username": username, "followers_count": count})
                elif count != last_count:
                    delta = count - last_count
                    print(f"[IG] Change: {last_count} -> {count} ({delta:+d})", flush=True)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    status = "printed"
                    if printing_enabled:
                        try:
                            print_follower_update(username, count, delta)
                        except Exception as e:
                            print(f"[IG] Print error: {e}", flush=True)
                            status = "error"
                    else:
                        status = "skipped"
                    socketio.emit("new_message", {
                        "from": f"@{username}",
                        "body": f"Followers: {count:,}  ({delta:+d})",
                        "time": timestamp,
                        "status": status,
                    })
                    last_count = count
                    save_state({"username": username, "followers_count": count})
        except Exception as e:
            print(f"[IG] Poll error: {e}", flush=True)

        time.sleep(IG_POLL_INTERVAL)


# ── Socket / routes ──────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    emit("printing_state", {"enabled": printing_enabled})


@socketio.on("set_printing")
def on_set_printing(data):
    global printing_enabled
    printing_enabled = bool(data.get("enabled", True))
    socketio.emit("printing_state", {"enabled": printing_enabled})


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "printing_enabled": printing_enabled, "async_mode": _ASYNC_MODE})


@app.route("/shutdown", methods=["POST"])
def shutdown():
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


@app.route("/ig/check", methods=["POST"])
def ig_check_now():
    """Force an immediate IG poll (useful for testing)."""
    threading.Thread(target=_one_shot_check, daemon=True).start()
    return jsonify({"ok": True})


def _one_shot_check():
    snap = fetch_ig_snapshot()
    if not snap:
        return
    state = load_state()
    last_count = state.get("followers_count")
    count = snap.get("followers_count")
    username = snap.get("username", "unknown")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    socketio.emit("new_message", {
        "from": f"@{username}",
        "body": f"Manual check — Followers: {count:,}"
        + (f" (was {last_count:,})" if last_count is not None else ""),
        "time": timestamp,
        "status": "skipped",
    })


@app.route("/sms", methods=["POST"])
def sms_webhook():
    from_number = request.form.get("From", "Unknown")
    body = request.form.get("Body", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"SMS from {from_number}: {body}", flush=True)

    if not printing_enabled:
        socketio.emit("new_message", {
            "from": from_number, "body": body, "time": timestamp, "status": "skipped",
        })
        return str(MessagingResponse())

    status = "printed"
    try:
        print_sms(from_number, body)
    except Exception as e:
        print(f"Print error: {e}", flush=True)
        status = "error"

    socketio.emit("new_message", {
        "from": from_number, "body": body, "time": timestamp, "status": status,
    })
    return str(MessagingResponse())


# ── Watchdog: self-check + sd_notify WATCHDOG=1 every ~15s ───────────────
def _self_check() -> bool:
    try:
        r = requests.get("http://127.0.0.1:5000/healthz", timeout=5)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


def _watchdog_loop():
    time.sleep(5)
    sd_notify("READY=1")
    sd_notify("STATUS=SMS Printer online")
    while True:
        if _self_check():
            sd_notify("WATCHDOG=1")
        time.sleep(15)


if __name__ == "__main__":
    print(f"SMS/IG Printer running on http://0.0.0.0:5000 (async={_ASYNC_MODE})", flush=True)
    threading.Thread(target=ig_poller, daemon=True).start()
    threading.Thread(target=_watchdog_loop, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
