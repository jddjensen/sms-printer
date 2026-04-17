import os
import sys
import time
import requests
from twilio.rest import Client

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

def get_ngrok_url(retries=10):
    for i in range(retries):
        try:
            resp = requests.get("http://localhost:4040/api/tunnels")
            tunnels = resp.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t["public_url"]
        except Exception:
            pass
        print(f"Waiting for ngrok... ({i+1}/{retries})")
        time.sleep(2)
    return None

def set_twilio_webhook(webhook_url):
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    numbers = client.incoming_phone_numbers.list(phone_number=PHONE_NUMBER)
    if not numbers:
        print(f"ERROR: Phone number {PHONE_NUMBER} not found in your Twilio account.")
        sys.exit(1)
    numbers[0].update(sms_url=webhook_url, sms_method="POST")
    print(f"Twilio webhook set to: {webhook_url}")

if __name__ == "__main__":
    if not all([ACCOUNT_SID, AUTH_TOKEN, PHONE_NUMBER]):
        print("ERROR: Missing Twilio credentials in start.bat")
        sys.exit(1)

    print("Fetching ngrok public URL...")
    ngrok_url = get_ngrok_url()
    if not ngrok_url:
        print("ERROR: Could not reach ngrok. Is it running?")
        sys.exit(1)

    webhook_url = ngrok_url + "/sms"
    print(f"ngrok URL: {ngrok_url}")
    set_twilio_webhook(webhook_url)
