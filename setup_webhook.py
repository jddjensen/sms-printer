import os
import sys
import time
import requests
from twilio.rest import Client

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

NGROK_API = os.environ.get("NGROK_API", "http://localhost:4040/api/tunnels")
RETRIES = int(os.environ.get("WEBHOOK_SETUP_RETRIES", "60"))
SLEEP_SECS = float(os.environ.get("WEBHOOK_SETUP_SLEEP", "3"))


def get_ngrok_url(retries=RETRIES, sleep_secs=SLEEP_SECS):
    for i in range(retries):
        try:
            resp = requests.get(NGROK_API, timeout=5)
            tunnels = resp.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
        except Exception as e:
            last_err = e
        else:
            last_err = "no https tunnel yet"
        print(f"Waiting for ngrok... ({i+1}/{retries}) [{last_err}]", flush=True)
        time.sleep(sleep_secs)
    return None


def set_twilio_webhook(webhook_url, retries=5):
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    last_err = None
    for i in range(retries):
        try:
            numbers = client.incoming_phone_numbers.list(phone_number=PHONE_NUMBER)
            if not numbers:
                print(f"ERROR: Phone number {PHONE_NUMBER} not found in your Twilio account.")
                sys.exit(1)
            numbers[0].update(sms_url=webhook_url, sms_method="POST")
            print(f"Twilio webhook set to: {webhook_url}")
            return
        except Exception as e:
            last_err = e
            print(f"Twilio update failed ({i+1}/{retries}): {e}", flush=True)
            time.sleep(5)
    print(f"ERROR: Could not update Twilio after {retries} tries: {last_err}")
    sys.exit(1)


if __name__ == "__main__":
    if not all([ACCOUNT_SID, AUTH_TOKEN, PHONE_NUMBER]):
        print("ERROR: Missing Twilio credentials (check .env)")
        sys.exit(1)

    print("Fetching ngrok public URL...", flush=True)
    ngrok_url = get_ngrok_url()
    if not ngrok_url:
        print("ERROR: Could not reach ngrok. Is it running?")
        sys.exit(1)

    webhook_url = ngrok_url + "/sms"
    print(f"ngrok URL: {ngrok_url}", flush=True)
    set_twilio_webhook(webhook_url)
