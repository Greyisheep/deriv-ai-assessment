# Supplier Quote Extraction Service

Extracts structured pricing JSON from messy free-form supplier quote text using
an LLM, then **validates and normalizes the result in deterministic code**. The
model is treated as untrusted: every field it returns is checked, converted, and
review-gated by plain Python before it leaves the service.

## What this does
For each quote it runs one pipeline:

```
LOAD_INPUT -> LLM_EXTRACTION -> SCHEMA_VALIDATION -> NORMALIZATION -> REVIEW_DECISION -> RESULTS_WRITTEN
```

and writes, per quote, a normalized result, the raw model output, a review
summary, and a call log.

## Design — the one idea
**The model touches exactly one stage (extraction). Everything after it is
deterministic and unit-testable.** That boundary is literal in the layout: one
module per stage, all under [`app/`](app/).

| Stage | Module | Owner |
|---|---|---|
| Load input | [`app/loader.py`](app/loader.py) | code |
| LLM extraction (+ repair) | [`app/extractor.py`](app/extractor.py) | model |
| Schema validation | [`app/validate.py`](app/validate.py) | code |
| Normalization | [`app/normalize.py`](app/normalize.py) | code |
| Review decision | [`app/review.py`](app/review.py) | code |
| Write artifacts | [`app/writer.py`](app/writer.py) | code |
| Orchestration | [`app/pipeline.py`](app/pipeline.py) | code |
| CLI / API entrypoints | [`main.py`](main.py) / [`app/api.py`](app/api.py) | code |

### Raw sidecars: how code (not the model) owns normalization
The model is told to **copy the exact text** it saw for the three
interpretation-heavy fields into `*_raw` sidecars — `currency_raw` (`"$"`),
`lead_time_raw` (`"around 3 weeks"`), `quote_expiry_raw` (`"next Friday"`) — and
**never to convert them**. Deterministic code does the conversion:

- `"3 weeks"` → `21` lead-time days (weeks × 7; `"around"` adds an assumption).
- `"$"` alone → flagged **ambiguous** (could be USD/CAD/AUD…), so `currency=null`
  + review. An explicit ISO code (`"USD"`, `"EUR"`, `"AED"`) or unambiguous
  symbol (`€`, `£`) resolves cleanly.
- Relative expiry (`"next Friday"`) → `quote_expiry=null` + assumption + review.
  We deliberately do **not** guess which Friday.

This is why "normalize `3 weeks` → `21`" lives in code, not the prompt.

### Money is exact `Decimal`, never float
`unit_price` is a `Decimal` everywhere in code. Binary floats can't represent
values like `2.2` or `18.50` exactly, so they're wrong for money that's stored
and compared. The extractor parses model JSON with `json.loads(parse_float=Decimal)`,
so a price never passes through a float even transiently (`Decimal(2.2)` would
already be lossy — we get `Decimal("2.2")`). At the output boundary a Pydantic
field serializer emits it as a JSON *number* (per the task schema), not a string.

### Prompts live in `.txt`, not in code ([`app/prompts/`](app/prompts/))
`system.txt`, `user.txt`, and `repair.txt` hold the prompt text; `prompts.py` is a
thin typed loader. Prompts can be edited without touching code, and the code that
builds calls stays small.

### A deep model seam ([`app/extractor.py`](app/extractor.py))
The adapter interface speaks the domain — `extract(quote_text)` /
`repair(quote_text, bad_output, error)` — and each adapter hides its own
mechanics (the real one builds prompts + calls Gemini; the mock runs a heuristic
reader). Neither knows about JSON parsing or validation; the extractor owns that
plus the repair-once policy. Swapping models or going offline touches one small
class, nothing downstream.

### Two schemas, on purpose ([`app/schema.py`](app/schema.py))
- `Extraction` — the lenient, fully-nullable shape the model returns (with raw
  sidecars). Validated, never trusted.
- `FinalQuote` — the strict normalized output. Building one is itself the final
  schema gate: if normalization produced a bad value, construction fails and we
  fall back to a safe default.

### Review is code-authoritative
The prompt asks the model to self-flag `needs_review`, but that's advisory only.
[`app/review.py`](app/review.py) is the single owner of the decision and ignores
the model's flag (per the "no LLM for deterministic decisions" constraint).
`validation_errors` (shape/parse failures) and `review_reasons` (business rules)
are kept as separate lists.

### Fail-safe
On malformed/invalid model output the extractor **repairs once** (re-prompts with
the error), then returns a **safe default** (`needs_review=true`, empty items,
error recorded). The pipeline never crashes on the model; a transport/auth error
is caught per-quote and degraded the same way.

## Setup & run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

No API key is required to run or evaluate: with `GEMINI_API_KEY` unset the
pipeline auto-selects a **heuristic mock model** (a small regex reader) so a
clean checkout works end to end. To use the real model:
```bash
cp .env.example .env          # add your GEMINI_API_KEY
python check_key.py           # optional: verify connectivity
```

### CLI (primary)
```bash
python main.py --input quotes.json          # auto: real if key set, else mock
python main.py --input quotes.json --mock   # force the heuristic mock
python main.py --input quotes.json --real   # force Gemini
```

### API
```bash
uvicorn app.api:app --reload
curl -s -X POST localhost:8000/run                                  # batch from quotes.json
curl -s -X POST localhost:8000/extract \
  -H 'content-type: application/json' \
  -d '{"quotes":[{"id":"Q-9","text":"Acme: 10 bolts at $2 each. USD."}]}'
```
Mode is controlled by `LLM_MODE=auto|mock|real`.

## Output artifacts
- `outputs/{id}.json` — final normalized result
- `outputs/{id}_raw.json` — raw model output (verbatim)
- `review_summary.json` — `{quote_id, needs_review, validation_errors, review_reasons}` per quote
- `llm_calls.jsonl` — one log line per extraction call (provider, model, status, artifacts)

## Tests & evals
```bash
python -m pytest            # 29 unit/API tests
python evals/run_evals.py   # 4 labeled cases scored through the full pipeline (mock, no key)
```
Unit tests cover normalization, validation, the code-authoritative review rules,
and the repair-once / safe-default fail-safe (model mocked). Evals score
end-to-end behavior against labeled expectations in
[`evals/cases.json`](evals/cases.json).

## Assumptions
- Quote text is English and roughly sentence-shaped (matches the sample format).
- One logical line item per quote in the sample shapes; the schema supports many,
  and lead time is tracked per item.
- Unknown shipping terms default to `false` (not included) **and** flag for
  review — the schema requires a boolean and we won't invent "included".
- Months as a lead-time unit are treated as unresolved (length varies) rather
  than guessed.

## Tradeoffs / cut for time
- **Heuristic mock is best-effort**, not a real parser; it handles the common
  quote shapes and degrades to nulls → review on anything unusual. The real model
  handles arbitrary text.
- One repair attempt only; no exponential backoff or multi-provider retry.
- No persistence/DB, no auth, no concurrency/batching.
- Currency resolution uses a small ISO/symbol table, not a full currency library.

## What I'd do next
- Run evals in CI; add adversarial/malformed fixtures to the eval set.
- Real-model integration tests behind a key-gated marker.
- Structured logging + metrics on review rate and repair rate.
- Dockerfile for deploy; pin dependency versions.
