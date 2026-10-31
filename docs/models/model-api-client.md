# Model API client

Every call to a Meta model goes through `backend/app/model_api/`. It is a thin layer over
`httpx` against `https://api.meta.ai/v1`, with no third-party SDK, so the request that leaves the
process is exactly the one in the code.

## What it does

| Concern | Behaviour |
|---|---|
| Auth | `Authorization: Bearer $MODEL_API_KEY` from settings. The key never appears in logs, errors or `repr()`; error text that echoes it is redacted. |
| Timeouts | `MODEL_API_TIMEOUT_S` per request, 10 s to connect. |
| Retries | 429, 500 and 503 are retried up to `MODEL_API_MAX_ATTEMPTS` with exponential backoff and jitter (0.5 s, 1 s, 2 s...). A `Retry-After` header is honoured, capped at `MODEL_API_RETRY_AFTER_MAX_S`. 400, 401, 402, 403, 404 and 413 are never retried. Timeouts and connection errors count as retryable. |
| Spend cap | Before each live call the ledger must be under `SPEND_CAP_USD`, otherwise `SpendCapError` is raised and nothing is sent. |
| Cost ledger | Every call appends one line to `DATA_DIR/model_api_spend.jsonl` with tokens, price, attempts and the request ID; `GET /api/spend` and `/readyz` read the totals. |
| Output cap | `max_output_tokens` from a caller is the answer budget; the request carries it plus a reasoning headroom by effort (1,024 `minimal`, 4,096 `low`, 8,192 `medium`, 16,384 `high`, 32,768 `xhigh`; 4,096 with no effort), under `MODEL_MAX_OUTPUT_TOKENS` when set, since reasoning tokens count against the cap. A response that still stops at the cap raises with the operation, the tokens used and the reasoning share. |
| Structured output | `respond_structured(Model, ...)` sends the Pydantic model's JSON Schema as `text.format` with `strict: true` (every object closed, every property required) and validates the reply. |
| Fixture mode | `OPL_FAKE_API=1`: responses come from `backend/tests/fixtures/api/`, no network, zero cost. |
| Record mode | `OPL_RECORD_FIXTURES=1`: live calls, and every response is saved as a fixture. |
| Prompt caching | `prompt_cache_key` is sent on every call so repeated prefixes land on the same backend. |

## Calling it

```python
from app.model_api import image_part, text_part, user_message

result = await client.respond(
    model=settings.model_spark,
    input=[user_message(text_part("Read the label."), image_part(jpeg_bytes, "image/jpeg"))],
    effort="low",
    op="extract",
)
result.text        # concatenated output_text
result.usage       # input, cached, output and reasoning tokens
result.cost_usd    # priced from the published rates
```

For typed answers:

```python
class Label(BaseModel):
    part_number: str
    capacity_gb: int | None

answer = await client.respond_structured(Label, model=settings.model_spark, input=..., op="extract")
answer.parsed.part_number
```

With tools, the client runs the loop and answers each call through a handler you pass:

```python
answer = await client.respond_with_tools(
    ProposalSet, model=settings.model_spark, input=..., tools=TOOLS, handle=planner.tool, op="propose"
)
```

Every step resends the input, the output items so far and one `function_call_output` per
call (stateless replay); each step is its own ledger entry, `propose-1`, `propose-2` and so
on, and its own fixture.

`op` names the operation in the ledger and selects the fallback fixture (see below).

## Pricing

`pricing.py` holds the published standard-mode rates: Muse Wonder 4.00 / 20.00, Muse Spark
1.25 / 4.25 USD per million input / output tokens, with cached input at 0.20 and 0.15; SAM 3.1
per image and per video frame (50-frame minimum); Muse Image per generated image; Muse Voice
Transcribe per hour of audio; search grounding per query. A model the table does not know is
charged at the highest token rate, so the ledger over-counts rather than under-counts.

The response reports tokens, images and video frames. It does not report audio length or
search queries, so the caller passes the seconds (`respond(..., audio_seconds=len_s)` for a Muse
Voice Transcribe call) and the client counts the `web_search_call` items of a grounded answer
unless the caller passes `search_queries=n` itself. Negative values are rejected.

## Errors

| Exception | When |
|---|---|
| `ModelApiError` | HTTP error after the last attempt, or a non-retryable status. Carries `status`, `error_type`, `code`, `attempts`. |
| `IncompleteResponseError` | the response status is not `completed`, the model refused, or structured output did not validate |
| `SpendCapError` | the ledger is at the cap |
| `FixtureMissingError` | fixture mode and no recorded response matches |

## Fixtures

A fixture is one JSON file under `backend/tests/fixtures/api/<endpoint>/`:

- `<key>.json`: exact match. The key is a digest of the request body with inline images replaced
  by their own digest, so the same photo and prompt always find the same file and the file stays
  small. The body is keyed with the caller's answer budget as `max_output_tokens`, not the cap
  sent, so a recording outlives a change of headroom or ceiling.
- `<op>.json`: fallback for every request made for that operation. Tests use this form when the
  exact prompt does not matter.

Recording: set `OPL_RECORD_FIXTURES=1` and `MODEL_API_KEY`, run the flow once, commit the files.
Fixtures contain the model's reply and token counts, never the key.

## Checking a key

```bash
./dev check-api
```

Runs one `GET /models` with the key from `.env` and prints the mode, the models the account can
reach and the ledger totals. No tokens are spent.

```bash
./dev live-check
```

Goes one step further and spends: one real call per operation the product makes, through its
own services, each line with the model that answered, the tokens and the cost from this price
table, held under `--max-usd` (default 0.25; an operation whose ceiling alone is above it is
named and skipped before the first call) and the ledger's headroom. `OPL_FAKE_API=1` runs the
same on the recordings for nothing. [Testing](../development/testing.md#the-live-check)
says what it covers; `livecheck/README.md` in the repository has the price per operation.
