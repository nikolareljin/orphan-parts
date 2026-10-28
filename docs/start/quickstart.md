# Quickstart

Docker and bash are the only requirements. Everything else runs inside containers.

## 1. Configure

```bash
cp .env.example .env
```

Put your Model API key into `MODEL_API_KEY`: sign in at https://dev.meta.ai, add a payment method
under Billing, create a key under API keys. The key is read by the backend only and never reaches
the browser. Without a key, set `OPL_FAKE_API=1` and the service answers from recorded fixtures
instead of calling the API; that is how the tests and CI run.

## 2. Run

```bash
./dev up
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API, interactive docs | http://localhost:8000/docs |
| Readiness | http://localhost:8000/readyz |

The backend reloads on source changes and the frontend has hot module replacement.
`./dev down` stops everything, `./dev logs backend` follows a service.

## 3. Check

```bash
./dev test
```

Runs the bash helper tests, then ruff, mypy and pytest in the backend image, then eslint, tsc,
vitest and a production build in the frontend image. CI runs the same steps.

## Without Docker

```bash
./dev up --native
```

Needs Python 3.12 and Node 24 (`nvm install 24`). A virtualenv is created in `backend/.venv`
and packages are installed on first run.

## Docs site

```bash
./dev docs        # http://localhost:8001, live reload
./dev docs-build  # writes site/
```

## Muse Code

Muse Code is the coding agent used on this repository. Install it, sign in, open the repository
and trust the workspace:

```bash
curl -fsSL https://dev.meta.ai/install.sh -o muse-install.sh   # read it before running it
sh muse-install.sh && muse --version
cd orphan-parts && muse
```

`./dev test` is the check it runs after a change. More under *Development > Working with Muse Code*.
