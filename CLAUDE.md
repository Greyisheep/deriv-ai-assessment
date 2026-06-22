# Working Rules — AI Engineer Assessment

## Mission
Ship the smallest correct LLM-powered solution that shows engineering AROUND
the model, not a happy-path demo.

## Non-negotiables
1. Structured output only (tool/JSON + schema validation). Never parse free text.
2. Fail safe: on malformed/empty/refused output, repair once, then return a safe
   default. Never crash on the model.
3. At least 3 labeled eval cases + a runner that scores them.
4. Validation and error handling beat extra features.
5. Never commit secrets. Key from env only (.env is gitignored).
6. Determinism via explicit system-instruction rules (Gemini 3.x discourages
   temperature/top_p); model behind a swappable interface (llm.py).

## Workflow
1. Restate problem + MVP in PLAN.md, state assumptions.
2. One pseudo-issue at a time; run after each change.
3. Mock the model in unit tests.
4. Stop polishing once shippable; document gaps in README.

## Style
Simple names, no clever abstractions, comments only for intent/tradeoffs,
keep code human-reviewable.

## Available helper
`llm.py` exposes `structured_call(system, user, schema)` and `text_call(...)`.
Reuse it; do not rebuild the client.
