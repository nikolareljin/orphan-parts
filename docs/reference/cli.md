# dev CLI

`./dev` is the one entry point for running, testing and building. `make` targets are aliases.

| Command | What it does |
|---|---|
| `./dev setup` | checks Docker, Python and Node, creates `.env` from `.env.example` if missing |
| `./dev up` | starts the Docker stack and waits for the backend to be healthy; with no `MODEL_API_KEY` in `.env` it starts in fixture mode (recorded answers) and says so |
| `./dev up --build` | rebuilds the images first |
| `./dev up --with-glimmer` | also starts the local Muse Glimmer server (openweight profile) |
| `./dev up --native` | runs backend and frontend on the host with a virtualenv and nvm |
| `./dev down` | stops the stack |
| `./dev status` | `compose ps` plus the readiness response |
| `./dev logs [service]` | follows logs |
| `./dev test [backend\|frontend\|scripts]` | the full check suite, in the images |
| `./dev e2e` | Playwright against the dev stack in fixture mode; `E2E_KEEP=1` leaves the stack running, `E2E_VIDEO=on` records every test |
| `./dev check-api` | one `GET /models` with the key from `.env`; prints the mode, the reachable models and the spend ledger |
| `./dev lint` | ruff, mypy, eslint, tsc |
| `./dev fmt` | ruff format, eslint --fix |
| `./dev docs` | serves the docs site at :8001 with live reload |
| `./dev docs-build` | exports the OpenAPI document and builds `site/` |
| `./dev build` | builds the production images |
| `./dev version <x.y.z>` | sets the version in every manifest and starts a changelog section |
| `./dev shell [service]` | shell in a running service |

`python -m app.extract <photo> [<photo> ...]` (inside the backend container or the native venv)
reads a label and prints the extraction as JSON; fixture mode needs no key.
`python -m app.segment <photo> [--concepts item,label] [--out DIR]` prints the regions as JSON
and, with `--out`, writes `overlay.jpg` and one crop per region.

Flags: `-v` turns on debug logging for the helpers, `-d` adds `set -x`.
`NATIVE=1 ./dev test` runs the checks on the host instead of in Docker.

## Helper library

`scripts/lib/` holds the bash functions `./dev` is built from, bash 3.2-safe so they run on
macOS as well as Linux:

| Module | Functions |
|---|---|
| `log.sh` | `log_info`, `log_ok`, `log_warn`, `log_error`, `log_debug`, `die` |
| `os.sh` | `os_name`, `is_macos`, `is_linux`, `is_wsl`, `has_cmd`, `require_cmd`, `abs_path` |
| `env.sh` | `project_root`, `env_load`, `env_require` |
| `python.sh` | `py_find`, `venv_ensure`, `venv_run` |
| `node.sh` | `node_ensure`, `node_run` |
| `docker.sh` | `compose_cmd`, `compose`, `wait_http`, `docker_running` |
| `ports.sh` | `port_who`, `port_free`, `ports_check` |
| `traps.sh` | `on_exit <function>`, `tmp_dir <variable>`, `kill_group_on_exit` |
| `help.sh` | `script_help`, `parse_common_args` |

Tests live in `scripts/tests/` and run with `bash scripts/tests/run.sh`.
