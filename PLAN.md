# PLAN — Supplier Quote Extraction Service

## Problem (restated)
Extract normalized pricing JSON from messy free-form supplier quote text using an
LLM, but treat model output as untrusted. Deterministic code validates,
normalizes, and decides review status. Ship the smallest correct version that
shows the engineering *around* the model.

## The one idea the whole design serves
Draw a hard line between **what the model may decide** and **what code must own**.
The model touches exactly one stage (extraction). Everything after it is
deterministic and unit-testable. Making that boundary visible IS the deliverable.

## Decisions locked with reviewer
1. **Normalization = raw sidecar, code owns it.** Model returns the target field
   *plus* the raw span it read for the three interpretation-heavy fields
   (lead time, currency, expiry). Deterministic code derives the final value.
2. **Relative dates: flag & null.** `quote_expiry=null` + assumption + review.
   We do NOT guess which "next Friday" the supplier meant.
3. **Interface: CLI primary, then FastAPI.** Build & green the CLI first
   (`python main.py --input quotes.json`); add FastAPI as a thin layer over the
   same `pipeline.py` once the core works. Both call identical pipeline code.
4. **No-key adapter: heuristic mock.** A small rule/regex extractor that works on
   equivalent inputs, not canned answers for the samples.

## Smaller calls I made (flag if you disagree)
- **needs_review is code-authoritative.** Model self-flags as advisory input only;
  code computes the final decision from deterministic rules.
- **`validation_errors` vs `review_reasons` are separate lists.** Errors =
  shape/type/parse failures. Reasons = business rules. Both can trip review.
- **Unknown `shipping_included` → `false` + assumption + review.** Schema demands a
  bool; we default conservatively and flag rather than invent "included".
- **Mode auto-detect:** `real` if `GEMINI_API_KEY` present, else `mock`. Override
  with `LLM_MODE=mock|real`. Keeps clean-checkout runs working with zero config.
- **Raw artifact fidelity:** on a successful parse we save the re-serialized dict
  as `_raw.json` (same JSON content, not byte-exact model text). Keeps us reusing
  `llm.py` untouched. Noted as a tradeoff in README.
- **Deps:** add `fastapi`, `uvicorn`, `httpx` (TestClient). No date library —
  stdlib `date.fromisoformat` is enough since we don't resolve relative dates.

## Data contracts

### Extraction schema (what the model returns — raw sidecars)
```jsonc
{
  "supplier_name": "string | null",
  "currency_raw":  "string | null",      // "USD", "$", "EUR 73/unit"
  "items": [{
    "sku": "string | null",
    "description": "string",
    "quantity": "number | null",
    "unit_price": "number | null",
    "lead_time_raw": "string | null"      // "14 days", "around 3 weeks"
  }],
  "quote_expiry_raw": "string | null",    // "2026-08-15", "next Friday"
  "shipping_included": "boolean | null",
  "notes": ["string"],
  "assumptions": ["string"],
  "needs_review": "boolean"               // advisory only
}
```

### Final schema (output, per spec)
```jsonc
{
  "supplier_name": "string", "currency": "string|null",
  "items": [{ "sku": "string|null", "description": "string",
              "quantity": int, "unit_price": number, "lead_time_days": int|null }],
  "quote_expiry": "YYYY-MM-DD|null", "shipping_included": bool,
  "notes": ["string"], "assumptions": ["string"], "needs_review": bool
}
```

## Pipeline = one module per stage
```
LOAD_INPUT  -> loader.py     (code) read+shape-check quotes.json
LLM_EXTRACT -> extractor.py  (model) one call/quote, repair once, save raw, log
VALIDATE    -> validate.py   (code) pydantic: keys/types/ranges
NORMALIZE   -> normalize.py  (code) weeks->days, symbol->ISO, trim/case, date check
REVIEW      -> review.py     (code) deterministic needs_review rules
WRITE       -> writer.py     (code) outputs/*, review_summary.json, llm_calls.jsonl
orchestrate -> pipeline.py (interface-agnostic core)
entrypoints -> main.py (CLI, primary) + app/main.py (FastAPI, thin layer)
model seam  -> extractor adapters: RealAdapter (reuses llm.py) | MockAdapter
```

## Normalization rules (deterministic)
- **currency_raw -> currency:** explicit ISO-4217 code in text wins; else map an
  unambiguous symbol; bare `$` (no ISO context) -> null + review (ambiguous).
- **lead_time_raw -> lead_time_days:** `n days`->n; `n weeks`->n*7; `~/around/about`
  -> keep value + assumption; months/unparseable -> null + review.
- **quote_expiry_raw -> quote_expiry:** valid ISO date -> pass; relative -> null +
  assumption + review; unparseable -> null + review.
- Trim whitespace; uppercase currency; collapse blank notes/assumptions.

## Review rules (any -> needs_review=true)
- supplier_name missing
- currency missing or ambiguous
- any item missing description / quantity / unit_price (or qty<=0, price<0)
- quote expiry relative/unresolved
- model JSON invalid or incomplete (validation_errors non-empty)
- shipping terms not stated (extra rule)

## Fail-safe (CLAUDE.md #2)
extract -> parse+validate -> on failure: ONE repair call (feed back the error) ->
still failing: safe-default record (empty items, needs_review=true,
validation_errors set), status `parse_error`/`validation_failed`. Never crash.

## Entrypoints
### CLI (primary)
- `python main.py --input quotes.json [--mock] [--out outputs]`
- Reads from disk, runs batch, writes all artifacts, prints review summary.
  This is the path the evaluator runs first.

### FastAPI (added after CLI is green — thin layer over pipeline.py)
- `GET  /health` -> `{status, mode}`
- `POST /run`     -> reads `quotes.json` from disk, runs batch, writes artifacts,
  returns `review_summary`.
- `POST /extract` -> body `{quotes:[{id,text}]}`; in-memory run + writes artifacts;
  returns `{results, review_summary}`. The "service another system calls" path.

## Artifacts
`outputs/{id}.json`, `outputs/{id}_raw.json`, `review_summary.json`,
`llm_calls.jsonl` (quote_id, ISO timestamp, provider, model, input_artifact,
output_artifact, status).

## Evals (>=3, key-free via mock)
`evals/cases.json` + `evals/run_evals.py`. Cases exercise each path:
A clean/no-review · B relative expiry->review · C bare `$`->review · D missing
unit_price->review · (E malformed->repair->safe default — covered in unit test).
Runner asserts currency/lead_time/needs_review per case, prints pass/fail score.

## Unit tests (2-4)
`test_normalize` (weeks->days, symbol map, `$` ambiguous, ISO date, relative->None),
`test_validate` (missing key, bad type, qty=0, neg price),
`test_review` (each trigger), `test_extractor` (repair-once + safe-default).

## Build order
1. `quotes.json` + `schema.py` + `prompts.py`
2. `loader` -> `extractor`(+adapters,repair) -> `validate` -> `normalize` -> `review` -> `writer`
3. `pipeline.py` wiring + `main.py` CLI  ->  **get CLI green end-to-end (mock)**
4. evals + unit tests, run everything
5. `app/main.py` FastAPI layer over the same pipeline + smoke test
6. README + prune

## Revisions after review
- **Money is `Decimal`, not float.** `unit_price` is Decimal throughout; extractor
  parses with `parse_float=Decimal` (exact even on the real-model number path);
  output serializes as a JSON number via a Pydantic field serializer.
- **Prompts externalized** to `app/prompts/*.txt`; `prompts.py` is a thin loader.
- **Deeper model seam.** Adapter interface is `extract()/repair()` (domain-level);
  JSON parsing + validation + repair policy live in the extractor. The mock no
  longer parses prompt strings.

## Out of scope (documented in README)
Auth, persistence/DB, batching/concurrency, retries beyond one repair, multi-
currency line items, true byte-fidelity raw capture, OpenAPI polish.
```