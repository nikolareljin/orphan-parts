# Orphan Parts Lens

Orphan Parts Lens helps people identify, evaluate, list and reuse spare parts and used devices
with Meta's Muse models: photos become an evidence-backed spec, a listing is checked against what
you need, a Facebook Marketplace draft is written for you, a candidate part is verified for fit,
and a device you own gets a safe second use.

A drawer full of orphan power adapters is the first category. The engine is built around
category profiles, so any physical part can be added as data.

Documentation: https://nikolareljin.github.io/orphan-parts/

## Quickstart

Docker and bash are the only requirements.

```bash
cp .env.example .env        # add MODEL_API_KEY, or set OPL_FAKE_API=1 to run without a key
./dev up
```

- Web app: http://localhost:5173
- API and OpenAPI docs: http://localhost:8000/docs
- Docs site: `./dev docs` then http://localhost:8001

`./dev test` runs the whole check suite inside the same images CI uses. `./dev help` lists every command.
Changes go through pull requests; releases are SemVer tags that publish images to GHCR.

## Set up

1. **Docker** with Compose v2, and bash. Nothing else is required; the native loop
   (`./dev up --native`) additionally needs Python 3.12 and Node 24 (`.nvmrc`).
2. **A Model API key.** Sign in at https://dev.meta.ai, add a payment method under Billing,
   create a key under API keys, and put it in `.env` as `MODEL_API_KEY`. The key never leaves
   the backend. With `OPL_FAKE_API=1` instead, every call is answered from recorded fixtures,
   which is how the tests and CI run.
3. **Muse Code**, the coding agent used on this repository:

   ```bash
   curl -fsSL https://dev.meta.ai/install.sh -o muse-install.sh   # read it, then run it
   sh muse-install.sh && muse --version
   cd orphan-parts && muse        # sign in with the browser or paste an API key; trust the workspace
   ```

   `./dev test` is the check Muse runs after a change. Details in the docs under
   *Development > Working with Muse Code*.

## Meta models in the app

| Model | Job |
|---|---|
| Muse Spark | reads labels into structured fields, drives the agent, explains verdicts |
| Muse Wonder | orchestrates the buyer comparison and drafts new category profiles |
| SAM 3.1 | isolates the part, its label and its connector in photos and video |
| Muse Voice Transcribe | voice notes from sellers and from WhatsApp |
| Muse Image | background cleanup of the cover photo, always labeled, original kept |
| Muse Glimmer, Muse Spark Open | open-weight pre-check and alternative extraction provider |

Built with Muse Code.

## Layout

```
backend/    FastAPI service (Python 3.12)
frontend/   React + Vite app (Node 24)
docs/       MkDocs site, published to GitHub Pages
scripts/    bash helpers used by ./dev
docker/     images that are not part of backend/ or frontend/
```

## Built during the Meta Global AI Developer Hackathon, Oct 27 - Nov 4, 2026

The dated feature log lives in the docs under *Project > Built during the hackathon*.

## License

MIT, see `LICENSE`.
