# Deployment

Production runs the same two images the release workflow publishes.

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
