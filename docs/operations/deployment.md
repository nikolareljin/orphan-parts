# Deployment

Production runs the same two images the release workflow publishes.

## Where it runs

The web app is static and is served by **Cloudflare Pages**; the backend, with its image work,
the inventory and the captures, runs on **Modal** as one container with a persistent volume; the
models are the Meta Model API. The web app calls the backend across origins and the backend keeps
the API key. This is the hosted demo; the sections after this one describe running the two
Docker images yourself on a host of your own, which stays supported.

### The backend on Modal

```bash
pipx install modal && modal setup          # once, a browser login
modal secret create orphan-parts \
  MODEL_API_KEY=... DEMO_ACCESS_CODE=... SPEND_CAP_USD=20 OPL_FAKE_API=1 \
  CORS_ORIGINS=https://orphan-parts.pages.dev DEMO_COOKIE_SECURE=1 DEMO_TRUST_PROXY=1
./dev deploy modal                         # modal deploy deploy/modal_app.py; prints the URL
curl -fsS https://<the url>/readyz
```

That is the by-hand path; the workflow under *From GitHub Actions* below does the same from
the repository's settings.

`deploy/modal_app.py` builds the image from `backend/pyproject.toml`, adds `backend/app`, the
recorded answers under `backend/tests/fixtures` (fixture mode on the host replays them) and
the demo set under `demo/`, mounts the volume `orphan-parts-data` at `/data` (the inventory
file, the captures, the spend ledger) and reads the secret. One container (`max_containers=1`: one writer for the database, one
counter for the demo gate), kept warm (`min_containers=1`; `OPL_MIN_CONTAINERS=0` at deploy
time lets it scale to zero, with a cold start of some seconds on the first request after an
idle quarter hour). A write is committed to the volume as soon as its request succeeds, and
what another container committed is read back before any write and within half a minute
otherwise. The database runs with `SQLITE_JOURNAL_MODE=DELETE` there: the write-ahead log
needs shared memory that a network filesystem cannot give. `DEMO_TRUST_PROXY=1` in the
secret makes the gate count visitors by the address Modal's proxy forwards, not by the
proxy's own. Without `MODEL_API_KEY` in the secret the service runs in fixture mode
(recorded answers, nothing spent); with a key that cannot work (401, 402, 403, or 404 on a
wrong URL at startup), the service runs in fixture mode too and `/readyz` reports `fixture
(key failed)` until a restart with a working key (`OPL_KEY_PROBE=0` turns that probe off);
the deploy step treats that answer as a failure, so the web app is never built against a
backend whose key is wrong. An API that is busy or down at startup (429, 5xx, a timeout)
changes nothing: every request retries on its own. Changing the secret takes a redeploy. `modal app logs orphan-parts` streams the log; `modal volume ls orphan-parts-data`
lists the data. The demo set goes into the host's inventory with
`modal run deploy/modal_app.py::load_demo` (the inventory reset first; `--no-reset` adds to
it), the same load as `./dev demo` on a machine of your own, in the mode the secret says;
record the set's fixtures and commit them before the deploy, or the load answers from the
operations' stubs and says so.

### The web app on Cloudflare Pages

A Pages project (`orphan-parts`, so the site is `https://orphan-parts.pages.dev`) that holds
the production build of `frontend/`, made with `VITE_API_URL` set to the Modal URL (no
trailing slash). The deploy workflow below builds and publishes it with `wrangler`; by hand it
is `npx wrangler@4 pages deploy frontend/dist --project-name orphan-parts --branch main` after
`VITE_API_URL=... npm run build`. The Pages origin is the backend's `CORS_ORIGINS`.

### From GitHub Actions

`deploy.yml` does the two deploys from the repository's own settings, so no key is typed on a
laptop and the secret on Modal is written from one place. It is inert until the repository
variable `HOSTED_DEPLOY` is `true`; then it runs on **Run workflow** (choose `both`, `backend`
or `web`) and after every release tag. Its two jobs call `scripts/deploy-hosted.sh`, which
also runs from a shell as `./dev deploy hosted [secret|backend|web|all]` with the same
settings in the environment and this machine's `modal` and `wrangler` logins:

1. **backend**: `secret` writes the Modal secret `orphan-parts` from the settings below, each
   value quoted so that a `$`, a space or a `#` in a code or a key is kept as it is (every
   field, replaced), then `backend` runs `modal deploy deploy/modal_app.py`, reads the URL off
   the output and waits for `/readyz` to answer `ok`;
2. **web**: builds the web app against that URL and publishes `frontend/dist` to the Pages
   project, creating the project when it does not exist yet.

The settings, under the repository's **Settings, Secrets and variables, Actions**. Names only
here; the values live there and in the operator's password manager.

| Secret | What it is |
|---|---|
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | a Modal API token (the dashboard's Settings, API tokens, or `modal token new`) |
| `MODEL_API_KEY_DEMO` | the Model API key the host uses, with its own spend limit; empty = recorded answers |
| `DEMO_ACCESS_CODE` | the access code; empty = an open demo |
| `CLOUDFLARE_API_TOKEN` | a Cloudflare API token with the *Cloudflare Pages: Edit* permission |
| `CLOUDFLARE_ACCOUNT_ID` | the account id from the Cloudflare dashboard |

| Variable | What it is |
|---|---|
| `HOSTED_DEPLOY` | `true` lets the workflow run; anything else keeps it inert |
| `WEB_ORIGIN` | the origin browsers use, `https://orphan-parts.pages.dev` or a custom domain attached to the project; it becomes the backend's `CORS_ORIGINS` |
| `PAGES_PROJECT` | the Pages project name (default `orphan-parts`) |
| `API_URL` | optional: the backend URL for a web-only run; a backend job in the same run wins over it |
| `OPL_FAKE_API` | `1` for recorded answers, `0` for the live models (default `1`) |
| `SPEND_CAP_USD` | the ledger's cap on the host (default `20`) |
| `OPL_MIN_CONTAINERS` | `1` keeps the container warm, `0` lets it scale to zero (default `1`) |

A `WEB_ORIGIN` on `pages.dev` that is not the project's own is refused before anything is
published, so the backend never allows one origin while browsers use another. The workflow
uses only `actions/checkout`, `actions/setup-python` and `actions/setup-node`; `modal` is
installed with pip and `wrangler` runs with `npx`. The ssh deploy job of the release workflow
is a different path (a host of your own) and stays inert on its own switch.

Across origins the gate's cookie cannot travel, so the web app keeps the session token from
`POST /api/access` for the tab and sends it as a bearer header; the phone does the same from
its pairing code, which then carries the Modal URL. Same-origin set-ups (the dev stack, the
Docker images behind nginx) keep the cookie and need nothing of this.

### The modes

| Mode | Secret | Who gets in | What it spends |
|---|---|---|---|
| open demo | `OPL_FAKE_API=1`, no `DEMO_ACCESS_CODE` | anyone with the URL | nothing |
| gated, live | a key, `OPL_FAKE_API=0`, a code, `SPEND_CAP_USD` | whoever has the code | up to the cap |

## From a published release

```bash
export IMAGE_PREFIX=ghcr.io/nikolareljin/orphan-parts TAG=0.1.0
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## From source

```bash
./dev build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Putting a release on the host

A release is tagged on `main` (`./dev release`, or the merge of a `release/x.y.z` pull request),
the workflow publishes its images, and then the host pulls them:

```bash
./dev deploy             # web and, when there is an app, android; VERSION says which release
./dev deploy web --version 0.2.0
```

The host needs Docker with Compose 2.24 or later (the production file keeps the dev file's bind
mounts out with `!override`), a directory holding `docker-compose.yml`, `docker-compose.prod.yml` and
its own `.env`, and SSH access for the user in `DEPLOY_HOST`. `.env` here (or the shell) names
it: `DEPLOY_HOST=user@host`, `DEPLOY_PATH=/srv/orphan-parts`, and `IMAGE_PREFIX` when the images
are not under `ghcr.io/<owner>/<name>`. The deploy runs one command on the host: pull the
release's two images and start them, with `TAG` set to the version. Nothing is built on the
host. With `DEPLOY_HOST` empty the web deploy says so and is skipped.

The same runs from the release workflow when the repository variable `DEPLOY_ENABLED` is `true`
and the secrets `DEPLOY_HOST`, `DEPLOY_PATH` and `DEPLOY_SSH_KEY` (a private key the host
accepts) are set; until then that job does not run.

**Android.** `./dev deploy android` builds the release APK and says where it is, and the
workflow attaches it to the release as `orphan-parts-<version>.apk`. It is signed with the
release key when the keystore settings are given ([Android app](../guides/android.md)) and
with the debug key otherwise. The app is pointed at this host's URL and the access code on its
first page. Publishing it to the store is a later step: it needs a developer account, the
signing key and a service account, none of which are in this repository; the APK on the
release is the artifact that step will take.

## What runs

- `backend`: `python:3.12-slim`, non-root, uvicorn with one worker, health check on `/healthz`.
  One process on purpose: the spend cap is counted in memory per process and the inventory
  serialises its writes per process, so a second worker would let both drift. The demo load
  does not need more; the path to more is a shared ledger, not more workers. With one worker
  uvicorn runs the server in the container's own process: a crash ends the container and
  `restart: unless-stopped` brings it back with the ledger and the inventory read from `/data`.
- `frontend`: static build served by nginx, which proxies `/api`, `/healthz`, `/readyz` and
  `/docs` to the backend. Listens on `WEB_PORT` (default 8080).
- `.env` on the host supplies configuration; nothing is baked into the images.

Set `CORS_ORIGINS` to the public origin and give the deployment its own API key with a low
`SPEND_CAP_USD`. On any host other people can reach, set `DEMO_ACCESS_CODE` (twelve characters
at least) and, on https, `DEMO_COOKIE_SECURE=1`; the production compose file already tells the
backend to trust the address nginx forwards. See [Demo access](demo-access.md) for the
allowances and the operator's switch.

## Status of the images

Nothing is published until a release pull request is merged or a SemVer tag is pushed (by
hand, or with `./dev release`); other pull requests and merges build nothing.
The images exist for two reasons: the live demo host pulls them instead of building on the
host, and anyone can run a tagged version with the two commands above. The demo host is not
set up yet, so the workflow is kept for that step. After the first release, check the package
visibility under the repository's packages: the pull commands above need it public.
