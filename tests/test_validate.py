"""Deterministic validation of untrusted model output."""

from decimal import Decimal

from app.validate import validate_extraction


def _good() -> dict:
    return {
        "supplier_name": "Acme",
        "currency_raw": "USD",
        "items": [
            {"sku": None, "description": "Widget", "quantity": 5,
             "unit_price": 1.5, "lead_time_raw": "7 days"}
        ],
        "quote_expiry_raw": None,
        "shipping_included": True,
        "notes": [],
        "assumptions": [],
        "needs_review": False,
    }


def test_valid_passes_clean():
    extraction, errors = validate_extraction(_good())
    assert errors == []
    assert extraction is not None and extraction.supplier_name == "Acme"


def test_money_is_exact_decimal_not_float():
    # 2.2 is not representable in binary float; the value must stay exact.
    data = _good()
    data["items"][0]["unit_price"] = Decimal("2.2")
    extraction, errors = validate_extraction(data)
    assert errors == []
    price = extraction.items[0].unit_price
    assert isinstance(price, Decimal)
    assert price == Decimal("2.2")


def test_none_is_parse_error():
    extraction, errors = validate_extraction(None)
    assert extraction is None
    assert any("not valid JSON" in e for e in errors)


def test_missing_top_level_key():
    bad = _good()
    del bad["currency_raw"]
    _, errors = validate_extraction(bad)
    assert any("missing required key: currency_raw" in e for e in errors)


def test_empty_items_flagged():
    bad = _good()
    bad["items"] = []
    _, errors = validate_extraction(bad)
    assert any("items is empty" in e for e in errors)


def test_non_positive_quantity_and_negative_price():
    bad = _good()
    bad["items"][0]["quantity"] = 0
    bad["items"][0]["unit_price"] = -1
    _, errors = validate_extraction(bad)
    assert any("quantity must be a positive integer" in e for e in errors)
    assert any("unit_price must be non-negative" in e for e in errors)
