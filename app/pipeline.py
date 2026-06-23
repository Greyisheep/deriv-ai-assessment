"""Orchestration — wire the stages. Interface-agnostic so the CLI and the API
call identical code.

    load -> extract -> validate -> normalize -> review -> write

Validation runs inside `extract` (it drives the repair decision); the remaining
stages run here. A quote that can't be extracted becomes a safe default with
needs_review=true — the pipeline never crashes on the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from . import review, writer
from .extractor import ExtractResult, extract_quote, select_adapter
from .loader import load_quotes
from .normalize import normalize
from .schema import FinalQuote, ReviewEntry


def _safe_default() -> FinalQuote:
    return FinalQuote(
        needs_review=True,
        assumptions=["automatic extraction failed; manual review required"],
    )


def process_quote(adapter, quote: dict, base: Path, out_dir: Path, source: str) -> dict:
    """Run one quote end to end, write its artifacts, and return its review entry."""
    quote_id = quote["id"]

    try:
        result = extract_quote(adapter, quote["text"])
    except Exception as e:  # transport/auth/etc. — degrade, don't crash
        result = ExtractResult(
            raw_text=json.dumps({"error": str(e)}),
            extraction=None,
            validation_errors=[f"extraction call failed: {e}"],
            status="parse_error",
        )

    raw_path = writer.write_raw(out_dir, quote_id, result.raw_text)

    if result.extraction is None:
        final = _safe_default()
        review_reasons = ["model output failed validation"]
        validation_errors = result.validation_errors
        needs_review = True
    else:
        fields, flags = normalize(result.extraction)
        needs_review, review_reasons = review.decide(fields, flags, [])
        fields["needs_review"] = needs_review
        validation_errors = []
        try:
            final = FinalQuote(**fields)  # final schema gate
        except ValidationError as e:
            validation_errors = [f"normalized output invalid: {e}"]
            final = _safe_default()
            review_reasons = ["normalized output failed final schema check"]
            needs_review = True

    writer.write_result(out_dir, quote_id, final)
    writer.log_call(
        base,
        quote_id=quote_id,
        provider=adapter.provider,
        model=adapter.model,
        input_artifact=f"{source}#{quote_id}",
        output_artifact=str(raw_path),
        status=result.status,
    )

    return ReviewEntry(
        quote_id=quote_id,
        needs_review=needs_review,
        validation_errors=validation_errors,
        review_reasons=review_reasons,
    ).model_dump()


def run_quotes(
    quotes: list[dict],
    *,
    mode: str = "auto",
    base: Path | str = ".",
    out_dir: Path | str | None = None,
    source: str = "input",
) -> list[dict]:
    """Process a list of {id, text} quotes; write artifacts + review_summary."""
    base = Path(base)
    out_dir = Path(out_dir) if out_dir else base / "outputs"
    adapter = select_adapter(mode)

    summary = [process_quote(adapter, q, base, out_dir, source) for q in quotes]
    writer.write_review_summary(base, summary)
    return summary


def run_from_file(
    path: str | Path,
    *,
    mode: str = "auto",
    base: Path | str = ".",
    out_dir: Path | str | None = None,
) -> list[dict]:
    quotes = load_quotes(path)
    return run_quotes(
        quotes, mode=mode, base=base, out_dir=out_dir, source=str(path)
    )
