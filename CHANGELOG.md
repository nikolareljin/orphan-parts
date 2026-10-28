# Changelog

All notable changes to Orphan Parts Lens. Versions follow SemVer.

## Unreleased

### Added
- Backend service skeleton: settings validated at startup, `/healthz`, `/readyz`, `/api/version`, JSON logs with request IDs.
- Frontend shell that shows API status.
- `./dev` command runner with a small bash helper library, Docker dev and production stacks.
- CI on every pull request, docs site skeleton published to GitHub Pages, release workflow that publishes images and a GitHub release from SemVer tags.
