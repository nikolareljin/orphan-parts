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
`SPEND_CAP_USD`.

## Status of the images

Nothing is published until a SemVer tag is pushed; pull requests and merges build nothing.
The images exist for two reasons: the live demo host pulls them instead of building on the
host, and anyone can run a tagged version with the two commands above. The demo host is not
set up yet, so the workflow is kept for that step. After the first release, check the package
visibility under the repository's packages: the pull commands above need it public.
