# Changelog

All notable changes to Orphan Parts Lens. Versions follow SemVer.

## Unreleased

### Added
- Model API client: bearer auth, timeouts, retries with backoff for 429/500/503 honouring `Retry-After`, strict structured output, a spend cap with a persistent cost ledger priced from the published rates, fixture and record modes, `GET /api/spend`, `./dev check-api`.
- Backend service skeleton: settings validated at startup, `/healthz`, `/readyz`, `/api/version`, JSON logs with request IDs.
- Frontend shell that shows API status.
- `./dev` command runner with a small bash helper library, Docker dev and production stacks.
- CI on Linux and macOS, docs site skeleton published to GitHub Pages.
