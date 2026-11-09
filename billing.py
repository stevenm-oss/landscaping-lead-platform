"""Stripe invoicing through the REST API. Each run emails every contractor a Stripe invoice with a pay link."""
import os

import requests

API = "https://api.stripe.com/v1"


class StripeError(Exception):
    pass


def enabled():
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def _post(path, data):
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise StripeError("Stripe isn’t set up yet. Add STRIPE_SECRET_KEY on Render.")
    try:
        r = requests.post(API + path, data=data, auth=(key, ""), timeout=20)
    except requests.RequestException as e:
        raise StripeError(f"Couldn’t reach Stripe ({e.__class__.__name__}).")
    body = r.json() if r.content else {}
    if not r.ok:
        raise StripeError(body.get("error", {}).get("message", f"Stripe error {r.status_code}"))
    return body


def create_customer(name, email, contractor_id):
    return _post("/customers", {"name": name, "email": email, "metadata[contractor_id]": contractor_id})["id"]


def send_invoice(customer_id, items):
    """items: list of (amount_in_cents, description). Returns the finalized invoice."""
    for cents, desc in items:
        _post("/invoiceitems", {"customer": customer_id, "amount": cents, "currency": "usd", "description": desc[:500]})
    inv = _post("/invoices", {"customer": customer_id, "collection_method": "send_invoice", "days_until_due": 7,
                              "pending_invoice_items_behavior": "include", "auto_advance": "false"})
    inv = _post(f"/invoices/{inv['id']}/finalize", {})
    _post(f"/invoices/{inv['id']}/send", {})
    return inv
