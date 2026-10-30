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

The demo gate is tested at the service level (the sliding allowance and when to come back, the
daily count, which calls spend, sessions signed, bound to the code and ending) and through the
app (nothing gated without a code; every page 401 with one and the open paths open; the right
code as a cookie and as a bearer token, a wrong one refused and limited; leaving; the hourly and
daily allowances on calls that spend; the operator's switch refusing only what spends; the
per-address limit with the open paths exempt; the forwarded address trusted only when told to;
the settings checked). Playwright runs behind the gate: one session from a global setup for
every test, and `access.spec.ts` starts without one.

Missing items are tested with a recorded listing reading (`listing-text`): the handoff link,
the ladder onto the states, the seller message; a search from an item or from values with its
refusals; a text candidate read, assessed and dated, with a rule key kept as read and an unknown
name dropped; typed values as the owner's word and a conflict rejected; a screenshot through the
extractor; a recheck after the need changed and a withdrawal; a candidate without its source
refused; the routes with multipart requests and every refusal.

Price guidance is tested against a recorded search-grounded answer (`price`): one search, four
results, five proposed comparables of which the unbacked one is dropped and said; the four
figures and their counts; a reported sale counted apart and one in another currency not; whole
against parts from the parts' own guidance; a live call through a mock server carrying the
`web_search` tool, the location and the include, with two searches billed; the routes and their
refusals. Search calls, results and citations are read off a response in isolation.

Listing drafts are tested against the recorded Muse Spark answers (`draft-sell`, `draft-give`):
facts resting on unconfirmed fields dropped, the disclosures appended, the free title, the
data steps, a stale draft after the item changes, and a working claim without a recorded test
flagged through a mock server. Voice notes: the WAV header read, a recorded transcript kept as
the owner's words, the live multipart request and its pricing by the seconds heard, the
limits before any call, and the route.

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
a user does. CI runs the same command in its `e2e` job. Expectations wait ten seconds rather
than the default five: six workers share one backend process, and while the segmentation test
decodes masks in pure Python every other read waits a second or two.

The command starts the backend in fixture mode, recreating it if it was running with a key, and
stops the whole stack afterwards unless `E2E_KEEP=1`; the next `./dev up` brings it back in the
mode set by `.env`. The Playwright image tag in `docker-compose.yml` and the `@playwright/test`
version in `e2e/package.json` must match, or the browsers in the image are the wrong build.

## Scripts

`scripts/tests/run.sh` loads every `test_*.sh`, runs each `test_*` function and counts
`assert_eq`, `assert_true` and `assert_false`. One file reads the backend Dockerfile and pins
the production command to one worker without reload; others run the release scripts against
throwaway repositories: the tag check (branch names, `VERSION`, manifests, changelog sections,
an existing tag), the release notes (the section, the pull requests since the last release, the
compare link, the images), the release itself (every refusal, a dry run, a tag created and
pushed to a bare origin), and the deploy (the one remote command, with a stand-in for `ssh`
that records it; what is not set up skipped or refused).

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
