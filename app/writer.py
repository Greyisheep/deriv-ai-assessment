"""RESULTS_WRITTEN — persist artifacts. Pure I/O, no business logic.

Layout:
  <out_dir>/<id>.json        final normalized result
  <out_dir>/<id>_raw.json    raw model output (verbatim)
  <base>/review_summary.json  one entry per quote
  <base>/llm_calls.jsonl      one line per extraction call
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schema import FinalQuote


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_result(out_dir: Path, quote_id: str, final: FinalQuote) -> Path:
    # model_dump_json runs the field serializers, so unit_price (Decimal) is
    # written as a JSON number, not a string.
    path = out_dir / f"{quote_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(final.model_dump_json(indent=2) + "\n")
    return path


def write_raw(out_dir: Path, quote_id: str, raw_text: str) -> Path:
    """Write the model's raw output verbatim. Falls back to wrapping non-JSON
    text so the file is always present for debugging."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{quote_id}_raw.json"
    try:
        # Re-dump if it parses, for readability; otherwise keep the exact bytes.
        path.write_text(json.dumps(json.loads(raw_text), indent=2, ensure_ascii=False) + "\n")
    except (json.JSONDecodeError, TypeError):
        path.write_text(raw_text if isinstance(raw_text, str) else json.dumps({"raw": raw_text}))
    return path


def write_review_summary(base: Path, entries: list[dict]) -> Path:
    path = base / "review_summary.json"
    _write_json(path, entries)
    return path


def log_call(
    base: Path,
    *,
    quote_id: str,
    provider: str,
    model: str,
    input_artifact: str,
    output_artifact: str,
    status: str,
) -> None:
    record = {
        "quote_id": quote_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "input_artifact": input_artifact,
        "output_artifact": output_artifact,
        "status": status,
    }
    path = base / "llm_calls.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
