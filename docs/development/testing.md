# Testing

```bash
./dev test              # everything
./dev test backend      # ruff, mypy, pytest with coverage
./dev test frontend     # eslint, tsc, vitest, production build
./dev test scripts      # bash helper tests
```

## Backend

pytest with coverage, threshold 80 percent. `tests/conftest.py` builds the app with a temporary
data directory and fixture mode on, so no test ever reaches the Model API. Tests are named after
the behaviour they pin down (`test_missing_key_fails_fast_in_live_mode`).

Model API behaviour is tested against `httpx.MockTransport`: the handler plays the server, a
recording `sleep` captures the backoff delays, and the ledger is inspected after each call. Async
tests use the `anyio` marker on the asyncio backend.

## Frontend

vitest for pure modules under `src/lib/`. Component tests come with the first real pages.

## Scripts

`scripts/tests/run.sh` loads every `test_*.sh`, runs each `test_*` function and counts
`assert_eq`, `assert_true` and `assert_false`. CI runs it on Linux and macOS.

## Fixture mode and recorded fixtures

`OPL_FAKE_API=1` makes the Model API client serve recorded responses from
`backend/tests/fixtures/api/<endpoint>/`. A file named after the request digest matches one exact
request; a file named after the operation (`extract.json`) answers every request for that
operation. Recording is `OPL_RECORD_FIXTURES=1` with a real key: each response is written next to
its request summary, with inline images replaced by a digest. Details in
[Model API client](../models/model-api-client.md).
