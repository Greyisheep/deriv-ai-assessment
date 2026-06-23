"""LLM_EXTRACTION — the only stage that touches the model.

The adapter interface is deliberately deep: it speaks the *domain*
(`extract(quote_text)` / `repair(...)`), and each adapter hides its own
mechanics — the real one builds prompts and calls Gemini, the mock runs a
heuristic reader. Neither knows anything about JSON parsing or validation; this
module owns that, plus the repair-once / safe-default policy.

The extractor never raises on bad *model output* (it repairs, then degrades). A
transport/auth error may propagate; the pipeline catches it per quote.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import llm

from .mock_llm import heuristic_json
from .prompts import repair_prompt, system_prompt, user_prompt
from .schema import EXTRACTION_JSON_SCHEMA, Extraction
from .validate import validate_extraction


class LLMAdapter(Protocol):
    provider: str
    model: str

    def extract(self, quote_text: str) -> str:
        """Return the model's raw JSON text for one quote."""

    def repair(self, quote_text: str, bad_output: str, error: str) -> str:
        """Return corrected raw JSON text after a failed first attempt."""


class RealAdapter:
    provider = "gemini"

    def __init__(self) -> None:
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    def extract(self, quote_text: str) -> str:
        return llm.structured_text(system_prompt(), user_prompt(quote_text), EXTRACTION_JSON_SCHEMA)

    def repair(self, quote_text: str, bad_output: str, error: str) -> str:
        prompt = repair_prompt(quote_text, bad_output, error)
        return llm.structured_text(system_prompt(), prompt, EXTRACTION_JSON_SCHEMA)


class MockAdapter:
    provider = "mock"
    model = "heuristic-v1"

    def extract(self, quote_text: str) -> str:
        return heuristic_json(quote_text)

    def repair(self, quote_text: str, bad_output: str, error: str) -> str:
        return heuristic_json(quote_text)  # best effort; the heuristic is deterministic


def select_adapter(mode: str = "auto") -> LLMAdapter:
    """mode: 'auto' (mock unless GEMINI_API_KEY is set), 'mock', or 'real'."""
    if mode == "mock":
        return MockAdapter()
    if mode == "real":
        return RealAdapter()
    return RealAdapter() if os.environ.get("GEMINI_API_KEY") else MockAdapter()


@dataclass
class ExtractResult:
    raw_text: str
    extraction: Extraction | None
    validation_errors: list[str]
    status: str  # success | parse_error | validation_failed


def _parse_and_validate(raw: str) -> tuple[Extraction | None, list[str], bool]:
    """Returns (extraction, errors, parseable). parse_float=Decimal keeps money
    exact — a price never becomes a binary float."""
    try:
        parsed = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError:
        return None, ["model output was not valid JSON"], False
    extraction, errors = validate_extraction(parsed)
    return extraction, errors, True


def extract_quote(adapter: LLMAdapter, quote_text: str) -> ExtractResult:
    raw = adapter.extract(quote_text)
    extraction, errors, parseable = _parse_and_validate(raw)
    if extraction is not None and not errors:
        return ExtractResult(raw, extraction, [], "success")

    # Repair once: show the model what broke and ask for corrected JSON.
    summary = "; ".join(errors) if errors else "unparseable JSON"
    raw = adapter.repair(quote_text, raw, summary)
    extraction, errors, parseable = _parse_and_validate(raw)
    if extraction is not None and not errors:
        return ExtractResult(raw, extraction, [], "success")

    status = "validation_failed" if parseable else "parse_error"
    return ExtractResult(raw, None, errors, status)
