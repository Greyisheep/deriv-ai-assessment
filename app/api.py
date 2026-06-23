"""FastAPI layer — a thin wrapper over pipeline.py. No business logic here.

    uvicorn app.api:app --reload

Mode follows env LLM_MODE (auto|mock|real); 'auto' uses the mock unless
GEMINI_API_KEY is set, so the server runs key-free out of the box.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.extractor import select_adapter
from app.loader import InputError
from app.pipeline import run_from_file, run_quotes

app = FastAPI(title="Supplier Quote Extraction")


def _mode() -> str:
    return os.environ.get("LLM_MODE", "auto")


class QuoteIn(BaseModel):
    id: str
    text: str


class ExtractIn(BaseModel):
    quotes: list[QuoteIn]


class RunIn(BaseModel):
    input_path: str = "quotes.json"


def _read_finals(out_dir: Path, ids: list[str]) -> list[dict]:
    return [json.loads((out_dir / f"{i}.json").read_text()) for i in ids]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": select_adapter(_mode()).provider}


@app.post("/run")
def run(body: RunIn | None = None) -> dict:
    """Batch path: read quotes from disk, run, write artifacts, return summary."""
    path = (body or RunIn()).input_path
    try:
        summary = run_from_file(path, mode=_mode())
    except InputError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"review_summary": summary}


@app.post("/extract")
def extract(body: ExtractIn) -> dict:
    """Service path: extract quotes supplied in the request body."""
    quotes = [q.model_dump() for q in body.quotes]
    summary = run_quotes(quotes, mode=_mode(), source="api")
    results = _read_finals(Path("outputs"), [q["id"] for q in quotes])
    return {"results": results, "review_summary": summary}
