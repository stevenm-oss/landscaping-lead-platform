"""Texts through Twilio and email through Resend. Both are skipped (and logged) until configured."""
import logging
import os
import re

import requests

log = logging.getLogger("notify")


def e164(phone):
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        return "+1" + d
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    return None


def sms(to, body):
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    sender = os.environ.get("TWILIO_FROM")
    service = os.environ.get("TWILIO_MESSAGING_SERVICE_SID")
    num = e164(to)
    if not num:
        return "skipped, bad number"
    if not (sid and token and (sender or service)):
        log.info("SMS (not sent, Twilio not set up) to %s: %s", num, body)
        return "skipped, Twilio not set up"
    data = {"To": num, "Body": body}
    if service:
        data["MessagingServiceSid"] = service
    else:
        data["From"] = sender
    try:
        r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                          data=data, auth=(sid, token), timeout=8)
        return "sent" if r.ok else f"failed ({r.status_code})"
    except requests.RequestException as e:
        return f"failed ({e.__class__.__name__})"


def email(to, subject, text):
    key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("EMAIL_FROM")
    if not to:
        return "skipped, no address"
    if not (key and sender):
        log.info("Email (not sent, Resend not set up) to %s: %s", to, subject)
        return "skipped, email not set up"
    try:
        r = requests.post("https://api.resend.com/emails",
                          json={"from": sender, "to": [to], "subject": subject, "text": text},
                          headers={"Authorization": f"Bearer {key}"}, timeout=8)
        return "sent" if r.ok else f"failed ({r.status_code})"
    except requests.RequestException as e:
        return f"failed ({e.__class__.__name__})"
