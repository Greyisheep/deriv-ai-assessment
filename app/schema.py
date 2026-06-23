"""Data contracts.

Two schemas, deliberately separate:

* `Extraction` / `RawItem` — the *untrusted* shape the model returns. Lenient and
  fully nullable; it carries `*_raw` sidecars for the three interpretation-heavy
  fields (currency, lead time, expiry) so deterministic code can own the
  conversion instead of the model.
* `FinalQuote` / `FinalItem` — the *strict* normalized output we promise
  downstream. Building one of these is itself the final schema check: if
  normalization produced a bad value (e.g. a non-int quantity), construction
  fails and we catch it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

# --- Untrusted model output (raw sidecars) ----------------------------------


class RawItem(BaseModel):
    sku: str | None = None
    description: str | None = None
    # Numbers stay loose here; range/int checks happen in validate + normalize.
    # Money is Decimal, never float — extractor parses with parse_float=Decimal so
    # a price never passes through a binary float.
    quantity: float | None = None
    unit_price: Decimal | None = None
    lead_time_raw: str | None = None


class Extraction(BaseModel):
    supplier_name: str | None = None
    currency_raw: str | None = None
    items: list[RawItem] = Field(default_factory=list)
    quote_expiry_raw: str | None = None
    shipping_included: bool | None = None
    notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    needs_review: bool | None = None  # advisory only; code decides the real value


# --- Strict normalized output (what we write to disk) -----------------------


class FinalItem(BaseModel):
    sku: str | None = None
    description: str
    quantity: int
    unit_price: Decimal  # exact money; kept as Decimal in code
    lead_time_days: int | None = None

    @field_serializer("unit_price", when_used="json")
    def _price_as_number(self, value: Decimal) -> float:
        # JSON has no Decimal type; emit a number (per the task schema) rather
        # than a string. Storage/comparison upstream stays exact Decimal.
        return float(value)


class FinalQuote(BaseModel):
    supplier_name: str | None = None
    currency: str | None = None
    items: list[FinalItem] = Field(default_factory=list)
    quote_expiry: str | None = None  # "YYYY-MM-DD" or None
    shipping_included: bool = False
    notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    needs_review: bool = True


class ReviewEntry(BaseModel):
    quote_id: str
    needs_review: bool
    validation_errors: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


# Required top-level keys we insist the model returns. Checked explicitly (before
# pydantic) so a missing key becomes a precise validation_error, not a silent
# default.
REQUIRED_TOP_LEVEL_KEYS = (
    "supplier_name",
    "currency_raw",
    "items",
    "quote_expiry_raw",
    "shipping_included",
    "notes",
    "assumptions",
    "needs_review",
)

# JSON schema pinned into the system prompt (llm.structured_call). Hand-written
# rather than derived from pydantic so the model sees a clean, intent-revealing
# shape with the raw sidecars spelled out.
EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": ["string", "null"]},
        "currency_raw": {
            "type": ["string", "null"],
            "description": "Exact currency text seen, e.g. 'USD', '$', 'EUR'. Do not convert.",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": ["string", "null"]},
                    "description": {"type": "string"},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "lead_time_raw": {
                        "type": ["string", "null"],
                        "description": "Exact lead-time text, e.g. '14 days', 'around 3 weeks'. Do not convert.",
                    },
                },
                "required": ["description", "quantity", "unit_price"],
            },
        },
        "quote_expiry_raw": {
            "type": ["string", "null"],
            "description": "Exact expiry text, e.g. '2026-08-15', 'next Friday'. Do not resolve relative dates.",
        },
        "shipping_included": {"type": ["boolean", "null"]},
        "notes": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "needs_review": {"type": "boolean"},
    },
    "required": list(REQUIRED_TOP_LEVEL_KEYS),
}
