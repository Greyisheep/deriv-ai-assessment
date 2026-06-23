"""Heuristic mock model — lets the pipeline run with no API key.

It is a small regex reader, NOT a real extractor: it handles the common quote
shapes and degrades to nulls (which the deterministic stages then flag for
review) on anything it doesn't recognize. It deliberately does NOT normalize —
it fills the *_raw sidecars exactly like the real model is told to, so the
deterministic stages do identical work in both modes.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

CURRENCY_CODES = r"USD|EUR|GBP|AED|JPY|CNY|INR|CAD|AUD|CHF|SGD|HKD|SEK|NOK|DKK|NZD|ZAR|MXN|BRL"


def _supplier(text: str) -> str | None:
    m = re.search(r"Supplier:\s*([^.]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"^([A-Z][\w&.\- ]+?)\s+(?:offers|quotation|quote|proposal|pricing)\b",
        text.strip(),
    )
    return m.group(1).strip() if m else None


def _currency_raw(text: str) -> str | None:
    m = re.search(rf"\b({CURRENCY_CODES})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"[€£$₹]", text)
    return m.group(0) if m else None


def _quantity(text: str) -> int | None:
    for pat in (r"qty\s*[:\-]?\s*(\d+)", r"(\d+)\s*units?\b", r"\b(\d+)\s+[A-Za-z]"):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _unit_price(text: str) -> Decimal | None:
    # Decimal straight from the matched digits — no float ever touches money.
    for pat in (
        rf"(?:\$|€|£|₹|{CURRENCY_CODES})\s*(\d+(?:\.\d+)?)",
        rf"(\d+(?:\.\d+)?)\s*(?:\$|€|£|₹|{CURRENCY_CODES})",
        r"(\d+(?:\.\d+)?)\s*/\s*unit",
        r"(?:at|@)\s*\$?\s*(\d+(?:\.\d+)?)",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return Decimal(m.group(1))
    return None


def _description(text: str) -> str | None:
    for pat in (
        r"units?\s+of\s+(.+?)\s+(?:at|@)\b",
        r":\s*(.+?)\s*-\s*qty",
        r"\d+\s+(.+?)\s+(?:at\b|@)",
        r"qty\s*\d+\s*-?\s*(.+?)(?:\s*-|\.|$)",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _lead_time_raw(text: str) -> str | None:
    for pat in (
        r"lead time\s*[:\-]?\s*([^.,;]+)",
        r"delivery\s*[:\-]?\s*([^.,;]+)",
        r"(\d+\s*(?:days?|weeks?|months?))",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _sku(text: str) -> str | None:
    if re.search(r"\bno sku\b", text, re.IGNORECASE):
        return None
    m = re.search(r"SKU\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m and re.search(r"[\d\-]", m.group(1)):  # looks like a code, not a word
        return m.group(1).strip()
    return None


def _expiry_raw(text: str) -> str | None:
    for pat in (
        r"valid until\s*([^.]+)",
        r"expires?\s*(?:on\s*)?([^.]+)",
        r"(\d{4}-\d{2}-\d{2})",
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _shipping(text: str) -> bool | None:
    if re.search(r"(shipping|freight)\s+included", text, re.IGNORECASE):
        return True
    if re.search(r"(shipping|freight)\s+(extra|not included|excluded)", text, re.IGNORECASE):
        return False
    return None


def _notes(text: str) -> list[str]:
    notes = []
    if re.search(r"\burgent\b", text, re.IGNORECASE):
        notes.append("urgent order")
    if re.search(r"\bno sku\b", text, re.IGNORECASE):
        notes.append("no SKU provided")
    return notes


def heuristic_extract(text: str) -> dict:
    desc = _description(text)
    qty = _quantity(text)
    price = _unit_price(text)
    currency = _currency_raw(text)
    supplier = _supplier(text)
    advisory_review = not all([supplier, currency, desc, qty, price])
    return {
        "supplier_name": supplier,
        "currency_raw": currency,
        "items": [
            {
                "sku": _sku(text),
                "description": desc or "",
                "quantity": qty,
                "unit_price": price,
                "lead_time_raw": _lead_time_raw(text),
            }
        ],
        "quote_expiry_raw": _expiry_raw(text),
        "shipping_included": _shipping(text),
        "notes": _notes(text),
        "assumptions": [],
        "needs_review": advisory_review,
    }


def heuristic_json(text: str) -> str:
    # default=str renders the Decimal price as a JSON string; the extractor
    # coerces it back to an exact Decimal. Keeps money float-free end to end.
    return json.dumps(heuristic_extract(text), default=str)
