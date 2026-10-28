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

Feature tests come in three layers. The pure parts (image preparation, normalisers) are tested
directly. The service is tested twice: against the recorded fixture, and against a mock server
that captures the request body, so the prompt, the schema and the image parts are pinned. The
route is tested through the app with multipart uploads, including every error status.

Two conftest fixtures matter here: `recorded_client` serves the fixtures committed under
`tests/fixtures/api/`, and `client` serves an empty fixture directory, which is how the "no
recorded answer" path is tested.

## Frontend

vitest for pure modules under `src/lib/`. Component tests come with the first real pages.

## Scripts

`scripts/tests/run.sh` loads every `test_*.sh`, runs each `test_*` function and counts
`assert_eq`, `assert_true` and `assert_false`.

## Fixture mode and recorded fixtures

`OPL_FAKE_API=1` makes the Model API client serve recorded responses from
`backend/tests/fixtures/api/<endpoint>/`. A file named after the request digest matches one exact
request; a file named after the operation (`extract.json`) answers every request for that
operation. Recording is `OPL_RECORD_FIXTURES=1` with a real key: each response is written next to
its request summary, with inline images replaced by a digest. Details in
[Model API client](../models/model-api-client.md).

The committed `responses/extract.json` is the answer for a laptop power adapter label; it makes
the tests, CI and the offline demo work with no key and no network.
