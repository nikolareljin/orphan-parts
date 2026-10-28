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

- `backend`: `python:3.12-slim`, non-root, uvicorn with two workers, health check on `/healthz`.
- `frontend`: static build served by nginx, which proxies `/api`, `/healthz`, `/readyz` and
  `/docs` to the backend. Listens on `WEB_PORT` (default 8080).
- `.env` on the host supplies configuration; nothing is baked into the images.

Set `CORS_ORIGINS` to the public origin and give the deployment its own API key with a low
`SPEND_CAP_USD`.

!!! note
    The live demo host and its deploy step in the release workflow are not set up yet.
