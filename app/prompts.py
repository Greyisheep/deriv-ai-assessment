"""Loads the LLM prompt templates from app/prompts/*.txt and fills them in.

Prompt *text* lives in plain .txt files so it can be edited without touching
code; this module is just the typed seam. Determinism comes from the explicit
rules in system.txt (Gemini 3.x discourages temperature/top_p), not sampling
params.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def _template(name: str) -> str:
    return (_DIR / name).read_text()


def system_prompt() -> str:
    return _template("system.txt")


def user_prompt(quote_text: str) -> str:
    return _template("user.txt").format(quote_text=quote_text)


def repair_prompt(quote_text: str, bad_output: str, error: str) -> str:
    return _template("repair.txt").format(
        quote_text=quote_text, bad_output=bad_output, error=error
    )
