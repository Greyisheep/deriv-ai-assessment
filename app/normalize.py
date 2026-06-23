"""NORMALIZATION — deterministic conversion of raw sidecars into final values.

Pure functions, no LLM. Each helper returns the normalized value plus an optional
assumption string. Normalization reports *flags* (e.g. currency "ambiguous");
the review decision itself lives in `review.py`, so there's one owner of
needs_review.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .schema import Extraction

# Currency codes we recognize as explicit ISO-4217. Small, extend as needed.
KNOWN_CURRENCIES = {
    "USD", "EUR", "GBP", "AED", "JPY", "CNY", "INR", "CAD", "AUD",
    "CHF", "SGD", "HKD", "SEK", "NOK", "DKK", "NZD", "ZAR", "MXN", "BRL",
}

# Only unambiguous symbols. "$" is intentionally absent — it maps to many
# currencies, so a bare "$" is flagged for review rather than guessed.
UNAMBIGUOUS_SYMBOLS = {"€": "EUR", "£": "GBP", "₹": "INR"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEAD = re.compile(r"(\d+(?:\.\d+)?)\s*(day|week|month)s?", re.IGNORECASE)
_APPROX = re.compile(r"\b(around|about|approx|approximately|roughly|~)\b", re.IGNORECASE)
# Words that mark a relative (unresolvable) date.
_RELATIVE = re.compile(
    r"\b(next|this|tomorrow|today|week|month|day|friday|monday|tuesday|"
    r"wednesday|thursday|saturday|sunday|eom|end of)\b",
    re.IGNORECASE,
)


def normalize_currency(raw: str | None) -> tuple[str | None, str]:
    """Return (ISO code or None, flag). flag in {ok, missing, ambiguous, unrecognized}."""
    if not raw or not raw.strip():
        return None, "missing"
    text = raw.strip()
    # Explicit ISO code anywhere in the text wins.
    for token in re.findall(r"[A-Za-z]{3}", text):
        if token.upper() in KNOWN_CURRENCIES:
            return token.upper(), "ok"
    for sym, code in UNAMBIGUOUS_SYMBOLS.items():
        if sym in text:
            return code, "ok"
    if "$" in text:
        return None, "ambiguous"  # could be USD/CAD/AUD/...; refuse to guess
    return None, "unrecognized"


def normalize_lead_time(raw: str | None) -> tuple[int | None, str | None, bool]:
    """Return (days or None, assumption, unresolved). weeks*7, days as-is.

    Months are treated as unresolved (length varies) rather than guessed.
    `unresolved` is True when raw is present but couldn't be converted.
    """
    if not raw or not raw.strip():
        return None, None, False
    m = _LEAD.search(raw)
    if not m:
        return None, None, True
    value, unit = float(m.group(1)), m.group(2).lower()
    if unit == "day":
        days = int(round(value))
    elif unit == "week":
        days = int(round(value * 7))
    else:  # month — ambiguous length
        return None, None, True
    assumption = None
    if _APPROX.search(raw):
        assumption = f"lead time '{raw.strip()}' treated as exactly {days} days"
    return days, assumption, False


def normalize_expiry(raw: str | None) -> tuple[str | None, str | None, str]:
    """Return (ISO date or None, assumption, flag). flag in {ok, absent, relative, invalid}."""
    if not raw or not raw.strip():
        return None, None, "absent"
    text = raw.strip()
    # Pull an ISO-looking token out of phrases like "valid until 2026-08-15".
    token = next((t for t in re.findall(r"\d{4}-\d{2}-\d{2}", text)), None)
    if token:
        try:
            date.fromisoformat(token)
            return token, None, "ok"
        except ValueError:
            return None, None, "invalid"
    if _RELATIVE.search(text):
        return (
            None,
            f"quote expiry '{text}' is relative and was not resolved",
            "relative",
        )
    return None, None, "invalid"


def normalize(extraction: Extraction) -> tuple[dict, dict]:
    """Convert a validated Extraction into final fields + a flags dict.

    Returns (fields, flags). `fields` is ready to build a FinalQuote except for
    needs_review, which review.py sets. `flags` carries normalization outcomes
    review.py turns into review reasons.
    """
    assumptions = [a.strip() for a in extraction.assumptions if a and a.strip()]
    notes = [n.strip() for n in extraction.notes if n and n.strip()]

    currency, currency_flag = normalize_currency(extraction.currency_raw)

    expiry, expiry_assumption, expiry_flag = normalize_expiry(extraction.quote_expiry_raw)
    if expiry_assumption:
        assumptions.append(expiry_assumption)

    items = []
    lead_unresolved = False
    for item in extraction.items:
        days, lead_assumption, unresolved = normalize_lead_time(item.lead_time_raw)
        lead_unresolved = lead_unresolved or unresolved
        if lead_assumption:
            assumptions.append(lead_assumption)
        items.append(
            {
                "sku": (item.sku.strip() or None) if item.sku else None,
                "description": (item.description or "").strip(),
                "quantity": int(item.quantity) if item.quantity is not None else 0,
                "unit_price": item.unit_price if item.unit_price is not None else Decimal("0"),
                "lead_time_days": days,
            }
        )

    if extraction.shipping_included is None:
        shipping = False
        shipping_flag = "defaulted"
        assumptions.append("shipping terms not stated; defaulted to not included")
    else:
        shipping = extraction.shipping_included
        shipping_flag = "stated"

    supplier = extraction.supplier_name.strip() if extraction.supplier_name else None

    fields = {
        "supplier_name": supplier or None,
        "currency": currency,
        "items": items,
        "quote_expiry": expiry,
        "shipping_included": shipping,
        "notes": notes,
        "assumptions": assumptions,
    }
    flags = {
        "currency": currency_flag,
        "expiry": expiry_flag,
        "lead_time_unresolved": lead_unresolved,
        "shipping": shipping_flag,
    }
    return fields, flags
