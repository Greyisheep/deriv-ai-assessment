"""REVIEW_DECISION — the one place that decides needs_review.

Deterministic. Consumes normalized fields + normalization flags + validation
errors and returns (needs_review, review_reasons). The model's own needs_review
flag is NOT consulted here; code owns this decision.
"""

from __future__ import annotations


def decide(fields: dict, flags: dict, validation_errors: list[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if validation_errors:
        reasons.append("model output failed validation")

    if not fields.get("supplier_name"):
        reasons.append("supplier name missing")

    currency_flag = flags.get("currency")
    if currency_flag == "missing":
        reasons.append("currency missing")
    elif currency_flag in ("ambiguous", "unrecognized"):
        reasons.append("currency ambiguous or unrecognized")

    items = fields.get("items") or []
    if not items:
        reasons.append("no line items")
    for i, item in enumerate(items):
        if not item.get("description"):
            reasons.append(f"item {i}: description missing")
        if not item.get("quantity") or item["quantity"] <= 0:
            reasons.append(f"item {i}: quantity missing or invalid")
        if item.get("unit_price") is None or item["unit_price"] < 0:
            reasons.append(f"item {i}: unit price missing or invalid")

    if flags.get("expiry") == "relative":
        reasons.append("quote expiry is relative and could not be resolved")
    elif flags.get("expiry") == "invalid":
        reasons.append("quote expiry is present but not a valid date")

    if flags.get("lead_time_unresolved"):
        reasons.append("a lead time was stated but could not be resolved")

    if flags.get("shipping") == "defaulted":
        reasons.append("shipping terms not stated; defaulted to not included")

    return bool(reasons), reasons
