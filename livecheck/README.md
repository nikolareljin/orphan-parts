# The live check

One real call per Model API operation the product makes, through the product's own services,
with the demo set's inputs, and a line per operation saying what answered and what it cost.
It proves the wiring to Meta's Model API end to end before a demo, after a key change, or when
a model id moves. It is a command on this machine and nothing else: never built into an image,
never deployed, never a route.

```bash
./dev live-check                          # the default set, at most $0.25 (says what it skips)
./dev live-check --ops price --max-usd 0.44  # the price call on its own
./dev live-check --ops segment,extract    # a few operations
./dev live-check --ops picture            # the priciest, only when named
./dev live-check --max-usd 0.05           # a tighter ceiling for the run
OPL_FAKE_API=1 ./dev live-check           # the dry run on recordings: the default set, $0
./dev live-check --against local          # over HTTP against the stack on this machine
./dev live-check --against hosted         # over HTTP against API_URL (the hosted demo)
```

## What it spends

A live run spends real credit from the key's account. Each operation is one call (the propose
loop up to four), priced as the client's own table prices it (`backend/app/model_api/pricing.py`,
the published standard rates). What one usually costs, and the ceiling the guard holds it to:

| op             | what it calls                                              | model                   | about         | ceiling   |
|----------------|------------------------------------------------------------|-------------------------|---------------|-----------|
| `segment`      | `Segmenter.segment`, one concept (`label`)                 | `sam-3.1`               | $0.0025       | $0.0100   |
| `transcribe`   | `VoiceNotes.note`, the demo note or a tone                 | `muse-voice-transcribe` | under $0.0001 | by length |
| `extract`      | `Extractor.extract`, one label photo                       | `muse-spark`            | $0.003-0.008  | $0.1082   |
| `listing-text` | `Finder.read_text`, a written listing from `demo/listings` | `muse-spark`            | $0.002-0.006  | $0.0982   |
| `draft`        | `Lister.draft`, a sell listing for the item                | `muse-spark`            | $0.002-0.006  | $0.0965   |
| `uses`         | `Decider.uses`, what the item is good for                  | `muse-spark`            | $0.002-0.006  | $0.0965   |
| `propose`      | `Planner.propose`, the tool loop, one project asked        | `muse-spark`            | $0.01-0.03    | $0.5073   |
| `price`        | `Valuer.guide`, with web search: the dearest of the set    | `muse-spark` + search   | $0.04-0.07    | $0.4399   |
| `picture`      | `Pictures.draw`, only with `--ops picture`                 | `muse-image`            | $0.01         | $0.0400   |

The ceilings are at the default settings (`MODEL_API_MAX_ATTEMPTS=4`, effort `low`, no
`MODEL_MAX_OUTPUT_TOKENS`, `PRICE_MAX_SEARCHES=4`); the run works them out from the settings it
has. Every operation of the default set (everything but `picture`) usually comes to about $0.08
to $0.15 together, most of it the price call, which reads tens of thousands of tokens of search
results; a run at the default `--max-usd` skips `propose` and `price` (below) and spends a few
cents.

The ceiling of an operation is what the client puts on the wire for the service's
`MAX_OUTPUT_TOKENS` (the answer budget plus the reasoning headroom for the effort the service
asks for: `EXTRACT_REASONING_EFFORT` for extract, `low`, 4,096 tokens, for the rest; under
`MODEL_MAX_OUTPUT_TOKENS` when set) at the output rate, plus an input allowance (the most a live
call of that kind has read, times 1.5; for the price call 15,000 tokens a search on top of the
brief, 63,000 at four searches, from live calls that read up to 100,000 over 12 unbounded
searches), times the steps a loop may take, plus the searches (`PRICE_MAX_SEARCHES`) or the
media it is allowed, and all of it times `MODEL_API_MAX_ATTEMPTS`, since the client retries a
failed request and a timed-out one may still be billed. It bounds the worst call, not the usual
one: tokens are billed as used.

The guard works in two steps. Before the first call the run prints the sum of the ceilings and,
when that is above `--max-usd`, names every operation whose ceiling alone is above it: those
are skipped (at the default 0.25, `propose` and `price`), each with the `--ops <op> --max-usd N`
that runs it on its own. Then, as it goes, it stops before an operation whose ceiling would take
the run past `--max-usd` less what the run has spent so far, and what a call cost is read off the
ledger. The run refuses to start when the backend's spend ledger (`SPEND_CAP_USD` less what is
spent) has less headroom than `--max-usd`. The ledger is the backend's own file, so the run
counts against the cap like any other call; a running backend reads the file at its next start.

```bash
./dev live-check --ops price --max-usd 0.44    # the price call on its own, with its search
./dev live-check --ops propose --max-usd 0.51  # the propose loop on its own
```

Exit code 0 when every operation run passed (one skipped before the run, named in that first
line, does not count against it); 1 when one failed or was skipped on the way; 2 when the run
was refused. Without `--keep-going` the run stops at the first failure. A live PASS also needs a
call on the ledger that the API answered (`fixture` false) for that operation: an answer from a
recording or the client's cache is a FAIL in live mode.

The check never records fixtures: `OPL_RECORD_FIXTURES` set to anything but off is refused, by
`./dev` and again by the check itself, and the run line sets it to 0.

## Two modes

**api** (the default) runs inside the backend image (`compose run ... backend python -m livecheck`)
with `livecheck/` mounted read-only, or on this machine in the backend's virtualenv with
`NATIVE=1`, and calls each operation through the service the route
calls, on one item made from the demo set's `adapter` entry, else its first item with a photo,
in a temporary inventory (named there whatever `INVENTORY_DB_FILE` says, so an absolute path
never reaches the real one). The inputs are the set's own: the item's photo and note when they
are under `demo/photos` and `demo/notes` (the owner's, written by `./dev demo-scrub`), else a
label drawn and a one-second tone made at run time; the listing text is `demo/listings/L1.txt`. Each line
shows the op, the model that answered, PASS or FAIL, milliseconds, input, output and reasoning
tokens, the cost, and on failure the exception's one-line message (never a request body).

**`--against local|hosted|URL`** runs the proof over HTTP against a running backend, as a browser
or the phone would. `local` is the stack on this machine (the backend service by name from
inside the compose network, `localhost:8000` with `NATIVE=1`); `hosted` is `API_URL` from the
shell or `.env`. Behind a gate it shows what the gate is for: without the code a sample photo
of the demo set (the first `GET /api/samples` lists) is read from its recording
(`from_fixture` true), a photo sent as a file is refused with 403 and a write
(`POST /api/items`) is refused with 403, so no code means no spend; then it signs in with the
code, reads the photo on the live models (`from_fixture` false), confirms `GET /api/access` says `live`, and signs out
(`DELETE /api/access`). Should the write go through (a broken gate), the probe item it made is
deleted again and the step still fails. On a host without a gate every caller is the owner, and
only the live reading is checked. The URL must be https, but for `localhost`, `127.0.0.1` and
`backend` (the compose service), since the session token travels in a header.

## The dry run

`OPL_FAKE_API=1` (or `true`, `yes`, `on`, in any case) puts the same run on the recorded answers
under `backend/tests/fixtures/api/`: every operation of the default set runs (`picture` too when
named), every line is PASS, the total is $0 and nothing leaves this machine. `./dev` reads the
setting strictly: `0`, `false`, `no`, `off` or empty is a live run, anything else is refused.
That is how the tests and CI exercise it (`backend/tests/test_livecheck.py` runs it as a subprocess
with a placeholder key and asserts the key never appears in the output).

## Credentials

The check reads two names from the environment and nowhere else:

- `MODEL_API_KEY`, the Model API key, as the backend reads it (from the shell, or from the
  git-ignored `.env` that Compose hands the backend container); used in the api mode.
- `LIVECHECK_ACCESS_CODE`, the access code, used only with `--against`: from the shell or
  `.env`, by the same two routes; never an argument.

`./dev` never reads either value: it reads `.env` with tracing off, checks only that the key is
there, and passes a name on (`-e MODEL_API_KEY`, `-e LIVECHECK_ACCESS_CODE`) only when the shell
sets it, so `./dev -d live-check` traces no value. Neither is written to a file, logged or
printed: the run says `MODEL_API_KEY: set (N chars)` or `missing`, and the same for the code,
and every line of output goes through a filter that replaces either value, and the key the
settings read, should anything try to print it; an error message is filtered before it is cut
short, and a last line without a line break goes out filtered at exit, a SIGTERM included.
`scripts/tests/test_livecheck.sh` scans every file under `livecheck/` and the `live-check`
lines of `./dev` for a key or code assigned a literal value, an environment read with a default
or a fallback literal, a long quoted literal, an Authorization header with a value, a key
prefix, a cloud key id, a JWT, a long hex or base64 run or an email address, runs gitleaks over
the folder (installed in CI, where a missing gitleaks fails the test), and fails unless every
file in the folder is a tracked `.py` or `.md` file. `backend/tests/test_livecheck.py` reads
every file's syntax tree for an environment read with a default that is not empty and for a
literal of 4 or more characters beside a name holding code, key, token, secret, password or
bearer.

## Why it is never deployed

The Modal image takes `backend/app`, `backend/tests/fixtures` and `demo` and nothing else
(`deploy/modal_app.py`, which does not name `livecheck` at all); the backend and web images are
built from `./backend` and `./frontend` and their Dockerfiles copy nothing from outside them;
nothing under `backend/app` imports from here. `backend/tests/test_livecheck.py` pins each of
those. Both `.dockerignore` files name `livecheck` as well, belt and braces: the build contexts
are what keep it out. The folder reaches a container only through the read-only bind mount in
`docker-compose.yml`, so every development backend container has it at `/opt/livecheck`; the
production overlay replaces the backend's volumes with its data volume alone, and the
production images and the hosted deploy never hold it.
