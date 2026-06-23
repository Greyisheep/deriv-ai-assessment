"""The review decision is code-authoritative — test each trigger."""

from app.review import decide


def _clean_fields() -> dict:
    return {
        "supplier_name": "Acme",
        "currency": "USD",
        "items": [{"description": "Widget", "quantity": 5, "unit_price": 1.5}],
        "quote_expiry": "2026-08-15",
        "shipping_included": True,
    }


def _clean_flags() -> dict:
    return {"currency": "ok", "expiry": "ok", "lead_time_unresolved": False, "shipping": "stated"}


def test_clean_quote_no_review():
    needs_review, reasons = decide(_clean_fields(), _clean_flags(), [])
    assert needs_review is False
    assert reasons == []


def test_missing_supplier_triggers_review():
    fields = _clean_fields()
    fields["supplier_name"] = None
    needs_review, reasons = decide(fields, _clean_flags(), [])
    assert needs_review is True
    assert any("supplier name missing" in r for r in reasons)


def test_ambiguous_currency_triggers_review():
    flags = _clean_flags()
    flags["currency"] = "ambiguous"
    needs_review, reasons = decide(_clean_fields(), flags, [])
    assert needs_review is True
    assert any("currency ambiguous" in r for r in reasons)


def test_relative_expiry_triggers_review():
    flags = _clean_flags()
    flags["expiry"] = "relative"
    needs_review, reasons = decide(_clean_fields(), flags, [])
    assert needs_review is True
    assert any("expiry is relative" in r for r in reasons)


def test_validation_errors_force_review():
    needs_review, reasons = decide(_clean_fields(), _clean_flags(), ["some error"])
    assert needs_review is True
    assert any("failed validation" in r for r in reasons)
