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

Build and reuse is tested with a recorded two-step tool loop (`propose-1`, `propose-2`): the
templates load and are checked (a repeated key, no blocking requirement, a file named
otherwise refused); the tools show only what a build may use; the proposal built on an item
nobody has is dropped and an allocation of the wrong kind is dropped and said; nothing usable
refused before any call; selection commits and reserves, a second build wanting the same item
is a conflict until it takes it, abandoning releases, advancing in order and not before every blocking requirement is filled;
a requirement filled by hand with an item of the right kind, and the wrong kind, a gone item,
a filled requirement and a project that is over refused; a missing requirement becomes a search
under the budget left and the item bought from it marks the search found; the build pack
written from what stands (the items' accepted values in, a serial number, a location and a note
out, the search with its top price, the budget line, the tools, the steps with progress, the
limits), refused before selection, stale once an item on it or the budget changed and the next
writing the next version; progress on a selected project and an unknown step refused; the
outcome recorded only while building, a failed test keeping it building and a working one
marking it done with the items still reserved, the dates real and past, blank text refused; the
share text redacted and refused until shared; the routes with the Markdown file and its
headers; the loop replayed statelessly through a
mock server (the brief, the output items and one result per call, two ledger entries) and a
loop that never answers refused; the routes and their refusals.

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

Deciding is tested against a recorded answer (`uses`): the templates a laptop fills and a
charger does not, the brief without a serial number, a location or the notes, the model's text
trimmed and capped, the uses kept per item and made stale by an edit, the view with its
guidance, searches, committed projects and last decision, the same choice again as an event
without a new version, a choice from an older version refused with 409, and the demo visitor
refused on every route.

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
so the browser sees exactly what a user sees and no credit is spent; `PICTURE_ENABLED` is on for
the run, so the item dialog draws its picture from the recorded stub. The runner shares the
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

## The live check

```bash
./dev live-check                         # one real call per operation, at most $0.25
./dev live-check --ops segment,extract   # a few of them
./dev live-check --ops price --max-usd 1.02  # the price call on its own
./dev live-check --ops picture           # Muse Image, only when named
OPL_FAKE_API=1 ./dev live-check          # the dry run on the recordings: the default set, $0
./dev live-check --against local         # over HTTP against the stack on this machine
./dev live-check --against hosted        # over HTTP against API_URL
```

Everything above runs on recorded answers. The live check is the one command that calls the
Model API for real, on purpose: each operation the product makes (`segment`, `transcribe`,
`extract`, `listing-text`, `draft`, `uses`, `propose`, `price`, and `picture` when named) once,
through the service its route calls, on one item made from the demo set, with a line per
operation: the model that answered, PASS or FAIL, milliseconds, input, output and reasoning
tokens, the cost, and the exception's one-line message on failure. A live run spends real
credit: `price`, with its web search, is the dearest at ten to sixteen cents, `propose` and its
tool loop a cent or more, `segment` a quarter of a cent. Each operation has a ceiling (its
output budget and reasoning headroom, an input allowance, its searches, times the client's
attempts); before the first call the run names every operation whose ceiling alone is above
`--max-usd` (at the default 0.25, `propose` and `price`) and skips it, then stops before one
whose ceiling would take the run past `--max-usd`, and refuses to start when the spend ledger
has less headroom than that. It never records fixtures. With `--against` the proof runs over
HTTP against a running backend: behind a gate, an extract without the code is answered from the
recordings and a write is refused, then a session with `LIVECHECK_ACCESS_CODE` reads the live
models and signs out. The access code is used in that mode only; it and the key come from the
environment (the shell or `.env`), never an argument, and `./dev` passes them on by name
without reading either value.

The check lives in `livecheck/` at the repository root. It runs in a development backend
container, where `docker-compose.yml` mounts the folder read-only, or on this machine in the
backend's virtualenv with `NATIVE=1`; it is in no image and never deployed.
`backend/tests/test_livecheck.py` pins that: the Modal app does not name it and adds the three
known directories only, both images build from their own directories and copy nothing from
outside them, the production overlay mounts nothing but the data volume, nothing in the app
imports it. It also runs the dry run as a subprocess with a placeholder key and asserts the key
never appears in the output, refuses record mode, checks the redaction, the ceilings and the
live ledger rule, and drives the HTTP proof against a gated app on recordings.
`scripts/tests/test_livecheck.sh` scans every file under `livecheck/` and the `live-check`
lines of `./dev` for anything that reads like a credential, runs gitleaks over the folder when
it is installed, fails unless the folder holds only tracked `.py` and `.md` files, and runs
`./dev live-check` against a stand-in `docker` to show that it reads `OPL_FAKE_API` strictly,
refuses to record, and traces no secret under `-d`. The `livecheck` lines in both
`.dockerignore` files are belt and braces beside the build contexts. `livecheck/README.md` has
the price table.

## Fixture mode and recorded fixtures

The Android app has unit tests on the JVM (`./dev android test`): the client's requests as
they go on the wire (the access call and the bearer token it keeps, the photo and the
recording as multipart, the item with the whole reading, the error text read off a 422), the
multipart framing, the WAV header and sizes, and the settings' URL. The smoke run
(`./dev android smoke`) installs the debug APK on the connected phone or a headless emulator
(`ANDROID_AVD`), launches the app, confirms its activity is on screen and keeps a screenshot;
`scripts/tests/test_android.sh` checks that script with stand-ins for gradlew and adb.

Enhancement is tested on synthetic images: a stretched, sharpened copy keeps the size and
stays a JPEG; printed text scores far above its blurred copy and a flat patch; a reading of a
flat photo carries the blur warning and the `enhanced` flag, and none of either with
`EXTRACT_ENHANCE=0` and the threshold at zero.

Pairing is tested in isolation (a session only when gated, verified by the gate; the origin
kept as given and anything but a scheme, a host and a port refused; the SVG and the terminal
block) and through the routes (open without a gate, 401 behind one until a session, the
phone's token working as a bearer header); the command line's answers. The Android setup
script is tested with stand-ins for java, curl, sdkmanager and the package manager: what
`--check` reports and that it runs nothing, an old JDK sent to the package manager, the
packages installed after the licences, a download refused on its checksum.

Captures are tested on bundles made in the test (a synthetic photo, a WAV, the head of an MP4):
a bundle kept as sent with the photos re-encoded on arrival and read into an item with the
transcript and the line, processed once only, deleted with its files while the item stays; a
capture without photos still an item; every refusal (an empty bundle, five photos, a bad photo,
a clip of the wrong kind, an audio file that is not a WAV, a clip beyond the limit); a failed reading
recorded with the media kept; the label found first through a mock server; the multipart
route, the media routes and their 404s; and the paths in the OpenAPI document.

The demo set (`demo/set.yaml`, `python -m app.demo`) is tested on a set written into a temporary
directory: the set checked (repeated keys, a search needing an item that is not there, a search
without an item or a profile, five photos refused, an empty file allowed); the scrub (metadata
gone, the long side shrunk, a PNG as a JPEG, a WAV copied, other files left out with a note, the
raw directory untouched); a load in fixture mode (items, the reading's values accepted, an
owner value beside them, a voice note kept, drafts, guidance, searches with candidates from a
file and from text, the proposals, the counts and the skipped line); record mode through a mock
server writing one fixture keyed by the request digest; the reset removing only the inventory
file; the command line's answers; and the committed set naming only files under `demo/` with
every written listing labelled as demo data.

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
