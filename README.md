<p align="center"><img src="docs/assets/logo.svg" alt="Orphan Parts Lens" width="160"></p>

# Orphan Parts Lens

Show it, ask it, sell it, or find the one that fits. Evidence-backed answers about used things,
on Meta's Muse models.

**This repository is the entry for the Meta Global AI Developer Hackathon (Oct 27 to Nov 4, 2026).**
Everything in it was built during the hackathon; the dated log is
[docs/project/hackathon.md](docs/project/hackathon.md) (*Project > Built during the hackathon*
on the docs site).

Orphan Parts Lens is an assistant for things you own and things you are about to buy. Point the
camera at an item, or paste a listing, and ask: What is this? What is it worth, and is it worth
selling? Does this listing fit what I need, and is it a good deal? What else could this device
become? The answers come with their evidence: a label it read, a source it cited with a date, or
a plain "cannot verify". Used tech and spare parts are the first categories; the engine takes any
item as a data profile.

## Five uses

| Use | You ask | You get |
|---|---|---|
| Identify | What is this? | a typed spec with a confidence and a source crop per field, the part number confirmed with citations |
| Value | What is it worth, is it worth selling? | an estimated resale value from cited comparables, labelled as an estimate, and a plain answer |
| List | Help me sell it | a Facebook Marketplace-ready draft and the questions still to resolve before posting |
| Find | I need one that fits | your needs as a profile, candidates ranked against it with a fit score, a deal check from the photos and the text, questions for the seller |
| Reuse | What else could this become? | safe project ideas with a parts list, manufacturer guidance and local e-waste rules |

On the web, drop photos or paste a listing. On the phone, talk to it and show it the camera; the
answer is spoken back. Hands-free through Meta glasses later.

Documentation: https://nikolareljin.github.io/orphan-parts/

## Quickstart

Docker and bash are the only requirements.

```bash
cp .env.example .env        # add MODEL_API_KEY; without one the stack runs on recorded answers
./dev up
```

- Web app: http://localhost:5173
- API and OpenAPI docs: http://localhost:8000/docs
- Docs site: `./dev docs` then http://localhost:8001

`./dev test` runs the whole check suite inside the same images CI uses. `./dev help` lists every command.
Changes go through pull requests; a release is a pull request from a `release/x.y.z` branch whose merge becomes the tag that publishes images to GHCR.

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
| Muse Spark | reads labels and listings into structured fields, ranks candidates, drives the agent, explains verdicts |
| Muse Wonder | plans the buyer comparison, drafts new category profiles |
| SAM 3.1 | isolates the item, its label and its connector in photos and video |
| Muse Voice Transcribe | spoken questions on the phone, voice notes from sellers |
| Muse Image | background cleanup of the cover photo, always labeled, original kept |
| Muse Glimmer, Muse Spark Open | on-device pre-check and alternative extraction provider |

Built with Muse Code.

## Layout

```
backend/    FastAPI service (Python 3.12)
frontend/   React + Vite app (Node 24)
docs/       MkDocs site, published to GitHub Pages
scripts/    bash helpers used by ./dev
docker/     images that are not part of backend/ or frontend/
```

## License

MIT, see `LICENSE`.
