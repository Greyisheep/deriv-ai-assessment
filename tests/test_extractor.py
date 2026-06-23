"""Fail-safe behavior: repair once, then a safe default. Never trust the model."""

import json

from app.extractor import extract_quote


class FakeAdapter:
    """Returns scripted raw-text responses, one per call (extract then repair)."""

    provider = "fake"
    model = "fake"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def _next(self) -> str:
        r = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return r

    def extract(self, quote_text):
        return self._next()

    def repair(self, quote_text, bad_output, error):
        return self._next()


def _valid() -> dict:
    return {
        "supplier_name": "Acme",
        "currency_raw": "USD",
        "items": [{"sku": None, "description": "Widget", "quantity": 5,
                   "unit_price": 1.5, "lead_time_raw": None}],
        "quote_expiry_raw": None,
        "shipping_included": True,
        "notes": [],
        "assumptions": [],
        "needs_review": False,
    }


def test_first_call_succeeds_no_repair():
    adapter = FakeAdapter([json.dumps(_valid())])
    result = extract_quote(adapter, "irrelevant")
    assert result.status == "success"
    assert adapter.calls == 1
    assert result.extraction is not None


def test_repairs_after_malformed_json():
    adapter = FakeAdapter(["not json", json.dumps(_valid())])
    result = extract_quote(adapter, "irrelevant")
    assert result.status == "success"
    assert adapter.calls == 2  # repaired on the second call


def test_safe_default_after_two_failures():
    adapter = FakeAdapter(["not json", "still not json"])
    result = extract_quote(adapter, "irrelevant")
    assert result.status == "parse_error"
    assert result.extraction is None
    assert result.validation_errors  # carries the reason


def test_valid_json_bad_content_is_validation_failed():
    bad = _valid()
    bad["items"] = []  # valid JSON, invalid content
    adapter = FakeAdapter([json.dumps(bad)])
    result = extract_quote(adapter, "irrelevant")
    assert result.status == "validation_failed"
    assert result.extraction is None
