"""CLI entrypoint (primary interface).

    python main.py --input quotes.json
    python main.py --input quotes.json --mock      # force heuristic mock
    python main.py --input quotes.json --out outputs

With no GEMINI_API_KEY set, the pipeline auto-selects the heuristic mock so a
clean checkout runs with zero config.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.loader import InputError
from app.pipeline import run_from_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract structured pricing from supplier quotes.")
    parser.add_argument("--input", default="quotes.json", help="path to quotes JSON file")
    parser.add_argument("--out", default="outputs", help="directory for per-quote artifacts")
    parser.add_argument("--mock", action="store_true", help="force the heuristic mock model")
    parser.add_argument("--real", action="store_true", help="force the real Gemini model")
    args = parser.parse_args(argv)

    if args.mock and args.real:
        parser.error("--mock and --real are mutually exclusive")
    mode = "mock" if args.mock else "real" if args.real else "auto"

    try:
        summary = run_from_file(args.input, mode=mode, out_dir=args.out)
    except InputError as e:
        print(f"input error: {e}", file=sys.stderr)
        return 2

    flagged = sum(1 for s in summary if s["needs_review"])
    print(json.dumps(summary, indent=2))
    print(
        f"\nProcessed {len(summary)} quote(s); {flagged} flagged for review. "
        f"Artifacts in '{args.out}/', review_summary.json + llm_calls.jsonl written.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
