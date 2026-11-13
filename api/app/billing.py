"""Bezahlung über Stripe Checkout.

Ablauf: Die Web-App fragt POST /billing/checkout an, die API legt bei Stripe eine Checkout-Sitzung an und
gibt deren Adresse zurück. Der Kunde bezahlt auf der Seite von Stripe (Kartendaten sehen wir nie).
Gutgeschrieben wird, sobald Stripe die Zahlung meldet: per Webhook (POST /billing/webhook) und zusätzlich,
wenn der Kunde zurückkommt (POST /billing/confirm). Beides läuft über fulfill(); die Tabelle payments
sorgt dafür, dass jede Zahlung genau einmal gutgeschrieben wird.

Bewusst ohne Stripe-Bibliothek: zwei REST-Aufrufe und die Signaturprüfung des Webhooks reichen.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import httpx

API = "https://api.stripe.com/v1"

# Pakete: Preis in Cent, Grundrisse. Muss zu den Preisen auf der Website passen (web/app/page.tsx).
PACKS: dict[str, dict] = {
    "einzel": {"credits": 1, "amount": 499, "name": "Planpause – 1 Grundriss"},
    "zehn": {"credits": 10, "amount": 4500, "name": "Planpause – 10 Grundrisse"},
}


class BillingError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def test_mode() -> bool:
    return os.environ.get("STRIPE_SECRET_KEY", "").startswith(("sk_test_", "rk_test_"))


def _http() -> httpx.Client:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise BillingError("Bezahlung ist noch nicht eingerichtet (STRIPE_SECRET_KEY fehlt).")
    return httpx.Client(base_url=API, auth=(key, ""), timeout=20)


def create_checkout(org: str, pack: str, email: str | None, site: str) -> dict:
    p = PACKS[pack]
    form = {
        "mode": "payment",
        "locale": "de",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "eur",
        "line_items[0][price_data][unit_amount]": str(p["amount"]),
        "line_items[0][price_data][product_data][name]": p["name"],
        "client_reference_id": org,
        "metadata[org]": org,
        "metadata[pack]": pack,
        "metadata[credits]": str(p["credits"]),
        "payment_intent_data[metadata][org]": org,
        "payment_intent_data[metadata][pack]": pack,
        "payment_intent_data[description]": p["name"],
        "success_url": f"{site}/projekte?kauf={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{site}/projekte?kauf=abbruch",
        "custom_text[submit][message]": (f"Das Guthaben ({p['credits']} Grundriss{'e' if p['credits'] > 1 else ''}) steht sofort nach der "
                                         f"Zahlung bereit. Es gelten unsere AGB: {site}/agb"),
    }
    if email:
        form["customer_email"] = email
    with _http() as c:
        r = c.post("/checkout/sessions", data=form)
    if r.status_code >= 400:
        raise BillingError(f"Stripe: {r.status_code} {r.text[:300]}")
    s = r.json()
    return {"id": s["id"], "url": s["url"]}


def get_session(sid: str) -> dict:
    with _http() as c:
        r = c.get(f"/checkout/sessions/{sid}")
    if r.status_code == 404:
        raise BillingError("Unbekannte Zahlung.")
    if r.status_code >= 400:
        raise BillingError(f"Stripe: {r.status_code} {r.text[:300]}")
    return r.json()


def verify_webhook(payload: bytes, header: str, secret: str, tolerance: int = 300, now: float | None = None) -> None:
    """Prüft die Signatur von Stripe (Header Stripe-Signature: t=…,v1=…). Wirft BillingError, wenn sie nicht passt."""
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError):
        raise BillingError("Signatur fehlt")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
        raise BillingError("Signatur ungültig")
    if abs((now or time.time()) - ts) > tolerance:
        raise BillingError("Signatur abgelaufen")


def paid_credits(session: dict) -> tuple[str, int] | None:
    """(Betrieb, Grundrisse) einer bezahlten Checkout-Sitzung; None, solange nicht bezahlt oder unbekanntes Paket."""
    if session.get("payment_status") != "paid":
        return None
    md = session.get("metadata") or {}
    pack = PACKS.get(md.get("pack", ""))
    org = md.get("org") or session.get("client_reference_id")
    if not pack or not org:
        return None
    if session.get("amount_total") is not None and session["amount_total"] < pack["amount"]:
        return None  # Betrag passt nicht zum Paket (z. B. Gutscheincode): nicht automatisch gutschreiben
    return org, pack["credits"]
