"""Eval runner — score labeled cases through the full pipeline (mock mode, no key).

    python evals/run_evals.py

Each case lists expected normalized fields; we run the pipeline, read the written
artifacts, and assert. Exits non-zero if any assertion fails.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Allow running as a script from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import run_quotes  # noqa: E402

CASES = json.loads((Path(__file__).parent / "cases.json").read_text())


def _actual(final: dict, key: str):
    # lead_time_days lives on the first item; everything else is top-level.
    if key == "lead_time_days":
        items = final.get("items") or [{}]
        return items[0].get("lead_time_days")
    return final.get(key)


def main() -> int:
    passed = failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        quotes = [{"id": c["id"], "text": c["text"]} for c in CASES]
        run_quotes(quotes, mode="mock", base=base, source="evals")

        for case in CASES:
            final = json.loads((base / "outputs" / f"{case['id']}.json").read_text())
            for key, expected in case["expect"].items():
                actual = _actual(final, key)
                ok = actual == expected
                passed += ok
                failed += not ok
                mark = "PASS" if ok else "FAIL"
                print(f"[{mark}] {case['id']}.{key}: expected {expected!r}, got {actual!r}")

    total = passed + failed
    print(f"\n{passed}/{total} assertions passed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
