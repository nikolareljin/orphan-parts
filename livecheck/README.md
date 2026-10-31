# The live check

One real call per Model API operation the product makes, through the product's own services,
with the demo set's inputs, and a line per operation saying what answered and what it cost.
It proves the wiring to Meta's Model API end to end before a demo, after a key change, or when
a model id moves. It is a command on this machine and nothing else: never built into an image,
never deployed, never a route.

```bash
./dev live-check                          # the default set, at most $0.25
./dev live-check --ops segment,extract    # a few operations
./dev live-check --ops picture            # the priciest, only when named
./dev live-check --max-usd 0.05           # a tighter ceiling for the run
OPL_FAKE_API=1 ./dev live-check           # the dry run on recordings: every op, $0
./dev live-check --against local          # over HTTP against the stack on this machine
./dev live-check --against hosted         # over HTTP against API_URL (the hosted demo)
```

## What it spends

A live run spends real credit from the key's account. Each operation is one call (the propose
loop up to four), priced as the client's own table prices it (`backend/app/model_api/pricing.py`,
the published standard rates). What one usually costs, and the ceiling the guard holds it to:

| op             | what it calls                                              | model                   | about         | ceiling   |
|----------------|------------------------------------------------------------|-------------------------|---------------|-----------|
| `segment`      | `Segmenter.segment`, one concept (`label`)                 | `sam-3.1`               | $0.0025       | $0.0025   |
| `transcribe`   | `ModelApiClient.transcribe`, the demo note or a tone       | `muse-voice-transcribe` | under $0.0001 | by length |
| `extract`      | `Extractor.extract`, one label photo                       | `muse-spark`            | $0.003-0.008  | $0.0271   |
| `listing-text` | `Finder.read_text`, a written listing from `demo/listings` | `muse-spark`            | $0.002-0.006  | $0.0246   |
| `draft`        | `Lister.draft`, a sell listing for the item                | `muse-spark`            | $0.002-0.006  | $0.0241   |
| `uses`         | `Decider.uses`, what the item is good for                  | `muse-spark`            | $0.002-0.006  | $0.0241   |
| `propose`      | `Planner.propose`, the tool loop, one project asked        | `muse-spark`            | $0.01-0.03    | $0.1118   |
| `price`        | `Valuer.guide`, with web search: the dearest of the set    | `muse-spark` + search   | $0.01-0.03    | $0.0350   |
| `picture`      | `Pictures.draw`, only with `--ops picture`                 | `muse-image`            | $0.01         | $0.01     |

The default set (everything but `picture`) usually comes to a few cents. The ceiling of an
operation is what the client puts on the wire for the service's `MAX_OUTPUT_TOKENS` (the answer
budget plus the reasoning headroom for effort `low`, 4,096 tokens, under `MODEL_MAX_OUTPUT_TOKENS`
when set) at the output rate, plus an allowance for the input, times the steps a loop may take,
plus the searches or the media it is allowed. It bounds the worst call, not the usual one: tokens
are billed as used. The guard stops before an operation whose ceiling would take the run past
`--max-usd` less what the run has spent so far, and what a call then cost is read off the ledger. The run refuses
to start when the backend's spend ledger (`SPEND_CAP_USD` less what is spent) has less headroom
than `--max-usd`. The ledger is the backend's own file, so the run counts against the cap like
any other call; a running backend reads the file at its next start.

Exit code 0 only when every selected operation passed; 1 when one failed or was skipped; 2
when the run was refused. Without `--keep-going` the run stops at the first failure.

## Two modes

**api** (the default) runs inside the backend image (`compose run ... backend python -m livecheck`)
with `livecheck/` mounted read-only, and calls each operation through the service the route
calls, on one item made from the demo set's `adapter` entry in a temporary inventory. The
inputs are the set's own: the item's photo and note when they are under `demo/photos` and
`demo/notes` (the owner's, written by `./dev demo-scrub`, not committed), else a label drawn
and a one-second tone made at run time; the listing text is `demo/listings/L1.txt`. Each line
shows the op, the model that answered, PASS or FAIL, milliseconds, input, output and reasoning
tokens, the cost, and on failure the exception's one-line message (never a request body).

**`--against local|hosted|URL`** runs the proof over HTTP against a running backend, as a browser
or the phone would. `local` is the stack on this machine (the backend service by name from
inside the compose network, `localhost:8000` with `NATIVE=1`); `hosted` is `API_URL` from the
shell or `.env`. Behind a gate it shows what the gate is for: an extract without the code is
answered from the recordings (`from_fixture` true) and a write (`POST /api/items`) is refused
with 403, so no code means no spend; then it signs in with the code, reads the same photo on
the live models (`from_fixture` false), confirms `GET /api/access` says `live`, and signs out
(`DELETE /api/access`). On a host without a gate every caller is the owner, and only the live
reading is checked.

## The dry run

`OPL_FAKE_API=1` puts the same run on the recorded answers under `backend/tests/fixtures/api/`:
every operation runs, every line is PASS, the total is $0 and nothing leaves this machine. That
is how the tests and CI exercise it (`backend/tests/test_livecheck.py` runs it as a subprocess
with a placeholder key and asserts the key never appears in the output).

## Credentials

The check reads two names from the environment and nowhere else:

- `MODEL_API_KEY`, the Model API key, as the backend reads it (from the shell, or from the
  git-ignored `.env` that Compose hands the backend container).
- `LIVECHECK_ACCESS_CODE`, the access code for `--against`, from the shell or `.env`,
  read by name by `./dev` and passed on through the environment; never an argument.

Neither is written to a file, logged or printed: the run says `MODEL_API_KEY: set (N chars)`
or `missing`, and the same for the code, and every line of output goes through a filter that
replaces either value should anything try to print it. `scripts/tests/test_livecheck.sh` scans
every file under `livecheck/` and the `live-check` lines of `./dev` for anything that reads like
a key, a token, a bearer header, a long hex or base64 run, an email address or an environment
file, and fails on a hit.

## Why it is never deployed

The Modal image takes `backend/app`, `backend/tests/fixtures` and `demo` and nothing else
(`deploy/modal_app.py`); the backend and web images take only their own directories, and both
`.dockerignore` files name `livecheck` besides; nothing under `backend/app` imports from here.
`backend/tests/test_livecheck.py` pins all three. The folder reaches a container only as the
read-only mount `./dev live-check` adds to the development stack.
