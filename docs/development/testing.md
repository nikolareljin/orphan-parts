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

The inventory is tested at the service level against a temporary SQLite file (provenance,
review, versions, components, soft delete, schema version) and through the routes, including a
reading saved from the recorded extraction answer.

Assessment is tested at three levels: each rule kind in isolation (missing values, normalised
text, uncertainty that straddles the tolerance), the ladder from a list of checks, and the
service against inventory items, including a value that came from a stored measurement with
its uncertainty; the route covers both sides as items and as values, the profile's rules
endpoint and every error status.

Measurement is tested on synthetic photos with known geometry (`tests/measure_images.py`): a
ruler bar of 400 px for 100 mm and an opening of 140 px, sharp and blurred; the geometry
module against a known projective transform; every refusal reason; the routes including a
capture stored on an item and the proposed value it leaves.

Two conftest fixtures matter here: `recorded_client` serves the fixtures committed under
`tests/fixtures/api/`, and `client` serves an empty fixture directory, which is how the "no
recorded answer" path is tested.

## Frontend

vitest for the pure modules under `src/lib/`: the API client against a stubbed `fetch`, the
formatting helpers. The components are covered end to end in the browser.

## End to end

```bash
./dev e2e                 # the whole flow in a real browser
E2E_KEEP=1 ./dev e2e      # leave the stack up afterwards
E2E_VIDEO=on ./dev e2e    # record every test, not only failures
```

Playwright runs in its official image against the dev stack with the backend in fixture mode,
so the browser sees exactly what a user sees and no credit is spent. The runner shares the
frontend container's network and runs as the host user; results, traces and videos land under
`e2e/test-results/`. Specs live in `e2e/tests/` and address the page by role and label, the way
a user does. CI runs the same command in its `e2e` job.

The command starts the backend in fixture mode, recreating it if it was running with a key, and
stops the whole stack afterwards unless `E2E_KEEP=1`; the next `./dev up` brings it back in the
mode set by `.env`. The Playwright image tag in `docker-compose.yml` and the `@playwright/test`
version in `e2e/package.json` must match, or the browsers in the image are the wrong build.

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

The committed `responses/extract.json` is the answer for a laptop power adapter label, and
`responses/segment-<concept>.json` the answers for the item, the label and the connector of one
photo (the mask payloads are small synthetic shapes in the real wire encoding); together they
make the tests, CI and the offline demo work with no key and no network.
