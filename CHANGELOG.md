# Changelog

All notable changes to Orphan Parts Lens. Versions follow SemVer.

## Unreleased

### Added
- Web: upload up to four photos and read the evidence table (value, unit, confidence, source, text as printed), warnings and the label transcription. Playwright end-to-end checks against the dev stack in fixture mode, `./dev e2e`, and an `e2e` CI job.
- Label extraction with Muse Spark: `POST /api/extract` reads up to four photos into typed fields with a confidence, a source and the raw text per field; deterministic normalisers for volts, amps, watts, codes, connectors, polarity and lists; photos re-encoded without metadata; `python -m app.extract`; a recorded fixture so tests and the offline demo need no key.
- Model API client: bearer auth, timeouts, retries with backoff for 429/500/503 honouring `Retry-After`, strict structured output, a spend cap with a persistent cost ledger priced from the published rates, fixture and record modes, `GET /api/spend`, `./dev check-api`.
- Backend service skeleton: settings validated at startup, `/healthz`, `/readyz`, `/api/version`, JSON logs with request IDs.
- Frontend shell that shows API status.
- `./dev` command runner with a small bash helper library, Docker dev and production stacks.
- CI on Linux and macOS, docs site skeleton published to GitHub Pages.
