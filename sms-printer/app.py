import os
import win32print
from flask import Flask, render_template, request
from flask_socketio import SocketIO
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')
PRINTER_NAME = "POS-80"


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
    raw_text = "".join(lines).encode("utf-8") + cut

    hprinter = win32print.OpenPrinter(PRINTER_NAME)
    try:
        win32print.StartDocPrinter(hprinter, 1, ("SMS", None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, raw_text)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/sms", methods=["POST"])
def sms_webhook():
    from_number = request.form.get("From", "Unknown")
    body = request.form.get("Body", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"SMS from {from_number}: {body}", flush=True)

    try:
        print_sms(from_number, body)
        print("Printed successfully.", flush=True)
        socketio.emit("new_message", {
            "from": from_number,
            "body": body,
            "time": timestamp,
            "status": "printed",
        })
    except Exception as e:
        print(f"Print error: {e}", flush=True)
        socketio.emit("new_message", {
            "from": from_number,
            "body": body,
            "time": timestamp,
            "status": "error",
        })

    return str(MessagingResponse())


if __name__ == "__main__":
    print("SMS Printer running on http://localhost:5000", flush=True)
    socketio.run(app, host="0.0.0.0", port=5000)
