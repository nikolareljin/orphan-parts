# dev CLI

`./dev` is the one entry point for running, testing and building. `make` targets are aliases.

| Command | What it does |
|---|---|
| `./dev setup [--check] [--android]` | checks Docker, Python, Node and what the app's build needs, creates `.env` from `.env.example` if missing; `--android` installs the JDK and the Android command-line tools; `--check` changes nothing |
| `./dev phone [--release]` | builds the app, installs it on the connected phone, launches it and prints the pairing code (the stack must be up) |
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
| `scripts/scan-security.sh [--json] [<ref>]` | gitleaks over the history reachable from the ref and foxguard over the tracked files at it, checked out clean so nothing uncommitted is scanned; `--json` writes `scan/*.json` and prints the counts |
| `scripts/phone-install.sh [--version x.y.z] [--apk file]`, `scripts\phone-install.ps1 [-Version x.y.z] [-Apk file]` | the released app onto a phone over USB from a computer with nothing installed: `adb` downloaded when missing, the APK from the release page, the install, the launch; macOS, Linux and WSL for the first, Windows PowerShell for the second |
| `./dev build` | builds the production images |
| `./dev version <x.y.z>` | sets the version in every manifest and starts a changelog section |
| `./dev release [--dry-run]` | tags `VERSION` on `main` and pushes the tag (the repository admin's command); the tag starts the release workflow |
| `./dev deploy modal` | the backend on Modal from this tree (`modal deploy deploy/modal_app.py`); prints the URL for the web app's `VITE_API_URL` |
| `./dev deploy hosted [secret\|backend\|web\|all]` | the hosted demo from settings in the environment, the steps the deploy workflow runs: the Modal secret, the backend with its `/readyz` check, the web app built against it and published to Pages |
| `./dev deploy [web\|android\|all] [--version x.y.z]` | a published release onto a host over ssh (`DEPLOY_HOST`, `DEPLOY_PATH`), and the APK when there is an app |
| `./dev gate on [--label <who>] [--days N]`, `./dev gate off`, `./dev gate show` | the access code on this machine: `on` makes a master code when `.env` has none, restarts the backend with the gate (starts it alone when the stack is down; `./dev up` keeps the gate), issues a code for the phone or a guest (`--label phone --days 7` by default; a label with a current code is refused: revoke it or pick another) and prints both to copy; `off` clears the code and restarts the backend if it is running; `show` prints the master. Never run by CI; the hosted demo's code is a repository secret |
| `./dev keys issue --label <who> [--days N]`, `./dev keys list`, `./dev keys revoke <label>` | access codes as records beside `DEMO_ACCESS_CODE`: a new code printed once and kept as a hash with its label and expiry, the list with each one's state, one ended by label with every session it opened; the running backend picks the change up without a restart. `./dev keys --hosted ...` runs the same on the Modal deployment's inventory (`modal run deploy/modal_app.py::keys --args '...'`). A demo reset (`./dev demo`, `load_demo`) takes the records with the inventory: issue the codes after it |
| `./dev demo [--keep]` | resets the inventory, the issued access codes with it (`--keep` adds instead) and loads `demo/set.yaml` in fixture mode; the backend is stopped for it and started again |
| `./dev eval [--keep] [--live]` | resets the inventory (`--keep` adds instead), loads `demo/set.yaml` as `./dev demo` does and scores the load by the rules into `eval/` (`report.json`, `report.md`, `charts/`); fixture mode unless `--live`, which uses the key from `.env` and spends; the backend is stopped for it and started again |
| `./dev record-fixtures [--keep]` | resets the inventory (`--keep` adds instead) and loads the set once with the key from `.env` under `OPL_RECORD_FIXTURES=1`, so every model answer is kept under `backend/tests/fixtures/api/`; spends credits once; the backend is stopped for it and started again however the run ends |
| `./dev demo-scrub <dir>` | re-encodes the raw photos in `<dir>` into `demo/photos/` without metadata, copies WAV notes into `demo/notes/` |
| `./dev shell [service]` | shell in a running service |

`python -m app.extract <photo> [<photo> ...]` (inside the backend container or the native venv)
reads a label and prints the extraction as JSON; fixture mode needs no key.
`python -m app.segment <photo> [--concepts item,label] [--out DIR]` prints the regions as JSON
and, with `--out`, writes `overlay.jpg` and one crop per region.
`python -m app.pairing --origin http://192.168.1.20:5173 [--json]` prints the pairing code for
the phone, with a session when the demo is gated.
`python -m app.demo <load|record|scrub>` is what the three demo commands run inside the
container: `load [--set FILE] [--reset]`, `record [--set FILE] [--reset]`,
`scrub <raw dir> [--out DIR]`.
`python -m app.eval <run|export|diff>` is behind `./dev eval`: `run [--set FILE] [--out DIR] [--keep]`
scores a load, `export [--out DIR]` writes `train.jsonl` from the accepted reads, `diff a.json b.json`
puts two reports side by side.

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
