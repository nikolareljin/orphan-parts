# Built during the hackathon

**This repository is the entry for the Meta Global AI Developer Hackathon**, Indie track, built
between October 27 and November 4, 2026. Everything in it was written in that window, with the
Meta Model API for the models and Muse Code as the coding agent. This log grows with each feature
and links to the commits.

| Date | What landed |
|---|---|
| Oct 27 | Project scaffold: FastAPI service with validated settings, health and version endpoints, JSON logs with request IDs; React shell; `./dev` runner with its bash helper library; Docker dev and production stacks; CI; this documentation site; release workflow. |
| Oct 27 | Model API client: retries with backoff, strict structured output, spend cap with a persistent ledger priced from the published rates, fixture and record modes. |
| Oct 28 | Label extraction with Muse Spark: photos in, typed fields with confidence and provenance out, deterministic normalisers, `POST /api/extract`, a command line, a recorded fixture for offline runs. |
