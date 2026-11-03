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

## Screenshots for the docs

Every picture of the web app in the guides is taken by one command, so the guides can be shot
again after the interface changes:

```bash
./dev docs-shots                 # every guide
./dev docs-shots --only profile  # the tests whose file name or title matches
./dev docs-shots --keep          # leave the stack up afterwards to look around
```

What it does (`docs/shots/generate.sh`):

- Starts a stack of its own (`opl-docs-shots`, ports 18410 and 18473, so a running `./dev up`
  is never touched) in fixture mode: no key is handed to the backend, whatever `.env` or the
  shell holds, and nothing is spent. Pictures are on (`PICTURE_ENABLED=1`), answered from the
  recordings.
- Loads the demo set as `./dev demo` does, with the parts' devices left unanswered, so the
  inventory guide can show the question and the label photo that answers it.
- Turns the gate on with a throwaway code made in the process and handed to the backend and the
  browser by name only; it is never printed, written to a file, or typed into a page that is
  shot.
- Runs the Playwright specs in `docs/shots/` (one file per guide, `NN-guide.spec.ts`) in the
  browser checks' image at 1280 by 800, light scheme, with a fixed clock and fixed times in
  lists. The specs that come first follow the demo video's scenes in order, so each model
  request is the one recorded for the video and replays as such; the run lists any answer that
  was a stand-in for want of a recording.
- Runs `02b-examples.spec.ts` right after the search guide's spec, before anything later
  changes the set, for [Examples](../start/examples.md): each picture is one element whole (a
  project panel, its drawings, a draft, a reading), the window made as tall as the element
  needs for the shot (`Shots.element` in `docs/shots/lib.ts`), signed in and as the visitor.
  It only reads, so the specs after it find the set as before.
- The privacy guide's pictures use the made-up label the browser checks use
  (`e2e/tests/fake-sticker.png`, every value on it fake), mounted read-only; no real photo.
- Before each picture: the pairing QR code is swapped for a fixed pattern and blurred, and every
  password or code field (and anything marked `data-shot-blur`) is blurred.
- Writes `docs/assets/shots/<guide>/<nn-name>.png` with the pixels alone (no text, time or
  color-profile chunks, `docs/shots/png_clean.py`). A picture that is the same as the one already
  there (a few pixels of decoding noise aside) is left untouched, so a second run changes nothing; `--force` writes them all.
- Tears the stack down, volumes included.

A run with `--only` starts from the fresh demo set too, so a guide whose steps build on earlier
ones (the build proposals after the profile, say) may get stand-in answers: run them all before
committing the pictures.

The web app gets a private address of its own on the stack's network (`192.168.250.10`, set
with `SHOTS_LAN_PREFIX`), standing in for a computer's address on the Wi-Fi in the pairing
pictures. The phone pictures under `docs/assets/phone/` are frames of a recording of the app on
a phone (`video/phone.sh`), cut below the status bar and written the same way. `./dev test`
checks that no picture under `docs/assets/shots/` or `docs/assets/phone/` carries metadata.
