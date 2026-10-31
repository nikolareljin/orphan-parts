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

## Frontend shows "Cannot reach the server"

The backend is still starting or failed. `./dev logs backend` shows why.

## Docs site does not publish

The `docs` workflow builds the site with `mkdocs build --strict` and publishes it to GitHub
Pages from `main`; a broken link or a missing page fails the build. `./dev docs-build` runs the
same build locally. In a git worktree, where the page dates cannot be read,
`DOCS_GIT_DATES=false ./dev docs-build` skips them.

## "Sign in with the access code to read your own photos."

The demo visitor's photo was refused: without the code, **Read a label** and **Measure a
feature** take the demo set's own photos from the gallery. Sign in to upload.

## A sample says "No recorded answer for this sample yet."

The demo set has no recording for that exact selection. `./dev record-fixtures` (with a key)
records every reading a sample click can ask for.
