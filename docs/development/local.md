# Local development

## Docker first

`./dev up` builds the backend image on first run, starts the backend with reload and the frontend
with Vite's dev server. Source directories are bind-mounted, so edits apply immediately.
`node_modules` lives in a named volume, which keeps the host tree clean and avoids platform
mismatches.

`./dev test`, `./dev lint` and `./dev fmt` run inside the same images. The host needs nothing
but Docker and bash.

## Native loop

`./dev up --native` creates `backend/.venv` with Python 3.12, installs the package in editable
mode, picks Node 24 through nvm (`.nvmrc`), runs `npm ci` when the lockfile changed, and starts
uvicorn and Vite in the foreground. Ctrl-C stops both.

The virtualenv is re-synced whenever `pyproject.toml` is newer than its stamp file; the same for
`package-lock.json`.

## Environment

`.env` is read by Docker Compose and by the native loop. `.env.example` lists every variable.
Never commit `.env`.

## Ports

| Port | Service | Override |
|---|---|---|
| 8000 | backend | `BACKEND_PORT` |
| 5173 | frontend | `FRONTEND_PORT` |
| 8001 | docs | `DOCS_PORT` |
| 8080 | Muse Glimmer (openweight profile) | `GLIMMER_PORT` |
