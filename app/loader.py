"""LOAD_INPUT — read and shape-check the quotes file from disk.

Deterministic. We fail loudly on a malformed *input file* (that's an operator
error, not model output), but tolerate individual records missing an id/text by
reporting them rather than crashing the whole batch.
"""

from __future__ import annotations

import json
from pathlib import Path


class InputError(Exception):
    """The input file itself is unusable (missing, not JSON, not a list)."""


def load_quotes(path: str | Path) -> list[dict]:
    """Return a list of {"id": str, "text": str} records.

    Raises InputError for a broken file. Records missing id/text are skipped with
    a generated id so one bad row can't sink the batch.
    """
    p = Path(path)
    if not p.exists():
        raise InputError(f"input file not found: {p}")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise InputError(f"input file is not valid JSON: {e}") from e

    if not isinstance(data, list):
        raise InputError("input must be a JSON array of quote objects")

    quotes: list[dict] = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            continue
        qid = str(row.get("id") or f"row-{i}")
        text = row.get("text")
        quotes.append({"id": qid, "text": text if isinstance(text, str) else ""})
    return quotes
