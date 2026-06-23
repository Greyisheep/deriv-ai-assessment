"""Normalization is the heart of the deterministic layer — test the conversions."""

from app.normalize import normalize_currency, normalize_expiry, normalize_lead_time


def test_currency_explicit_iso_wins():
    assert normalize_currency("USD") == ("USD", "ok")
    assert normalize_currency("Currency USD") == ("USD", "ok")
    assert normalize_currency("2.2 AED each") == ("AED", "ok")


def test_currency_unambiguous_symbol_maps():
    assert normalize_currency("€73/unit") == ("EUR", "ok")


def test_currency_dollar_is_ambiguous():
    assert normalize_currency("$18.50") == (None, "ambiguous")


def test_currency_missing_and_unrecognized():
    assert normalize_currency("") == (None, "missing")
    assert normalize_currency(None) == (None, "missing")
    assert normalize_currency("zzz") == (None, "unrecognized")


def test_lead_time_weeks_to_days():
    assert normalize_lead_time("3 weeks") == (21, None, False)
    assert normalize_lead_time("14 days") == (14, None, False)


def test_lead_time_approx_adds_assumption():
    days, assumption, unresolved = normalize_lead_time("around 3 weeks")
    assert days == 21
    assert assumption and "21 days" in assumption
    assert unresolved is False


def test_lead_time_months_and_garbage_unresolved():
    assert normalize_lead_time("2 months") == (None, None, True)
    assert normalize_lead_time("soon") == (None, None, True)
    assert normalize_lead_time(None) == (None, None, False)


def test_expiry_iso_passes():
    assert normalize_expiry("valid until 2026-08-15") == ("2026-08-15", None, "ok")


def test_expiry_relative_flagged():
    iso, assumption, flag = normalize_expiry("next Friday")
    assert iso is None
    assert flag == "relative"
    assert assumption and "not resolved" in assumption


def test_expiry_invalid_date():
    assert normalize_expiry("2026-13-40") == (None, None, "invalid")


def test_expiry_absent():
    assert normalize_expiry(None) == (None, None, "absent")
