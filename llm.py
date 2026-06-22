"""Minimal, reusable Gemini helper. Loads the key from .env and makes a
structured (JSON) call or a plain text call. Task-agnostic: define the schema and
prompts at the call site once you know the task. Always validate the returned
dict at the call site; never trust raw model output."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    # Lazy so importing this module never fails just because the key is unset.
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set (put it in .env)")
        _client = genai.Client(api_key=key)
    return _client


def structured_call(system: str, user: str, schema: dict, model: str | None = None) -> dict:
    """Return JSON matching `schema` (a JSON-Schema-style dict). The schema is
    pinned into the system instruction and JSON mode is forced, so output parses.
    Returns the raw dict; validate it (pydantic or hand-rolled) at the call site."""
    system_full = (
        f"{system}\n\nReturn ONLY a JSON object matching this schema:\n"
        f"{json.dumps(schema)}"
    )
    resp = _get_client().models.generate_content(
        model=model or _MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            system_instruction=system_full,
        ),
    )
    return json.loads(resp.text)


def text_call(system: str, user: str, model: str | None = None) -> str:
    """Plain text completion for when you do not need structure."""
    resp = _get_client().models.generate_content(
        model=model or _MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return resp.text
