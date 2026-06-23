"""SCHEMA_VALIDATION — deterministic checks on the untrusted model output.

Pure functions, no LLM. Returns a validated `Extraction` plus a list of
human-readable error strings. An empty error list means the shape is sound; it
does NOT mean the quote is review-free (that's `review.py`).
"""

from __future__ import annotations

from pydantic import ValidationError

from .schema import REQUIRED_TOP_LEVEL_KEYS, Extraction


def validate_extraction(parsed: dict | None) -> tuple[Extraction | None, list[str]]:
    """Validate raw model output. Returns (Extraction | None, errors).

    On unparseable input (`None`) or any structural problem we return a non-empty
    error list. The extractor uses this to decide whether to repair.
    """
    errors: list[str] = []

    if parsed is None:
        return None, ["model output was not valid JSON"]
    if not isinstance(parsed, dict):
        return None, ["model output was not a JSON object"]

    # Required top-level keys — checked explicitly so each is a precise error.
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in parsed:
            errors.append(f"missing required key: {key}")

    # Type/shape via pydantic. If this fails the output is unusable, bail early.
    try:
        extraction = Extraction.model_validate(parsed)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            errors.append(f"type error at {loc or '<root>'}: {err['msg']}")
        return None, errors

    # Range / content checks the schema alone can't express.
    if not extraction.items:
        errors.append("items is empty")
    for i, item in enumerate(extraction.items):
        where = f"items[{i}]"
        if not (item.description and item.description.strip()):
            errors.append(f"{where}: description missing")
        if item.quantity is None:
            errors.append(f"{where}: quantity missing")
        elif item.quantity <= 0 or item.quantity != int(item.quantity):
            errors.append(f"{where}: quantity must be a positive integer")
        if item.unit_price is None:
            errors.append(f"{where}: unit_price missing")
        elif item.unit_price < 0:
            errors.append(f"{where}: unit_price must be non-negative")

    return extraction, errors
