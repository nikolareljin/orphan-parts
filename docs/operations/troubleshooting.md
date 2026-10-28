# Troubleshooting

## Backend refuses to start: `MODEL_API_KEY is empty`

Live mode needs a key. Put it in `.env`, or set `OPL_FAKE_API=1` to run on recorded fixtures.

## Model API answers 401, 402, 403 or 404

| Status | Meaning | Fix |
|---|---|---|
| 401 | key rejected | regenerate the key at https://dev.meta.ai, check for whitespace |
| 402 / 403 | billing or credits not active | add a payment method, confirm credits landed in Billing |
| 404 `model_not_found` | wrong model ID | compare `MODEL_*` in `.env` with `GET /v1/models` |

## Ports already in use

`./dev up` lists what holds 8000 or 5173. Stop it, or set `BACKEND_PORT` / `FRONTEND_PORT`.

## Docker is not running

`./dev up` and `./dev test` need the Docker daemon. Start Docker, or use the native path:
`./dev up --native` and `NATIVE=1 ./dev test`.

## Frontend shows "API not reachable"

The backend is still starting or failed. `./dev logs backend` shows why.

## Docs site does not publish

GitHub Pages on a personal account publishes only from public repositories. The `docs` workflow
still builds and uploads the site on every push so the build is verified; publishing starts once
the repository is public and Pages is set to "GitHub Actions" as the source.
