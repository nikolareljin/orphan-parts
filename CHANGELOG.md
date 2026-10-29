# Changelog

All notable changes to Orphan Parts Lens. Versions follow SemVer.

## Unreleased

### Added
- Releases by hand and in full: `VERSION` is the one place the version is read from, and `./dev version` writes it with the manifests; `./dev release` tags `VERSION` on a clean, level `main` and pushes the tag, which only the repository admin may do; the release workflow assembles the release notes from the changelog section, the pull requests merged since the previous release, the compare link and the images, and carries two jobs that stay inert until there is something for them: a release APK when an Android app is in the tree, and a deploy to the host when the repository variable `DEPLOY_ENABLED` and the host secrets are set; `./dev deploy` does the same from a machine.
- Sell or give away: `POST /api/items/{id}/drafts` writes a listing draft with Muse Spark from the item's accepted values; the rules append the faults, what was tested, what is included and the price or free pickup, and drop any line that rests on nothing confirmed; a checklist before handover (preparation, photos, data removal when the item holds data) kept per draft; drafts versioned and marked stale when the item changes; copy the draft and open the Marketplace create page. `POST /api/items/{id}/voice` transcribes a WAV note with Muse Voice Transcribe and keeps it as the owner's words. The Prepare to sell or give away panel on each item.

## 0.1.0 - 2026-10-29

### Added
- Release on merge: a pull request from `release/x.y.z` merged into `main` tags the merge commit and publishes the images and the GitHub release, after the version is checked against every manifest and the changelog; an existing tag is never moved.
- Assessment: `POST /api/assess` checks a candidate against what is needed, rule by rule from the profile (`GET /api/profiles/{id}/rules`): pass, fail or unknown, never a guess; measured values carry their uncertainty into the check; one verdict from the ladder (`EXACT_MATCH`, `COMPATIBLE_LIKELY`, `VISUALLY_SIMILAR`, `CONFLICT`, `INSUFFICIENT_INFO`); a question for every unknown on the candidate's side. The Does it fit? panel on each item.
- Measurement: `POST /api/measure` and `POST /api/items/{id}/measurements` compute a dimension from marks on a photo with a scale reference (two points of known length, or four corners of a known rectangle through a homography), refuse captures that are blurred, short on reference, off the photo, too small or not straight on, and report the uncertainty with its basis; profile features with tolerances in `GET /api/profiles`; accepted captures are proposed on the item as observed values. The marking canvas under each item.
- Docs site: every page carries share metadata (title, description, one card image), so a link pasted into a chat or a post shows the project card.
- Private inventory: `POST /api/items` saves a reading as an item whose observed values are confirmed or rejected one by one; owner values sit beside observations with their provenance; condition, faults, tests, accessories, location, notes, intent and availability; parts separated into their own records; versions, optimistic writes and a per-item history; SQLite under `DATA_DIR`. The My inventory page and Save privately in the web app.
- Segmentation with SAM 3.1: `POST /api/segment` finds the item, the label and the connector (one concept per call, more on request), decodes the masks with Meta's parser, and returns one region per match with a box, a confidence, a crop and the mask outline, plus the overlay; `python -m app.segment`; recorded fixtures per concept. `POST /api/extract` takes label crops and sources their evidence `label_crop`; the web form finds the label first by default and shows the overlay and the crops.
- `./dev up` starts in fixture mode when `.env` has no `MODEL_API_KEY`, and shows the backend log when the stack fails to start.
- Web: upload up to four photos and read the evidence table (value, unit, confidence, source, text as printed), warnings and the label transcription. `GET /api/version` reports the upload limits and the form follows them, refusing an oversized photo before it is sent. Playwright end-to-end checks against the dev stack in fixture mode, `./dev e2e`, and an `e2e` CI job.
- Label extraction with Muse Spark: `POST /api/extract` reads up to four photos into typed fields with a confidence, a source and the raw text per field; deterministic normalisers for volts, amps, watts, codes, connectors, polarity and lists; photos re-encoded without metadata; `python -m app.extract`; a recorded fixture so tests and the offline demo need no key.
- Model API client: bearer auth, timeouts, retries with backoff for 429/500/503 honouring `Retry-After`, strict structured output, a spend cap with a persistent cost ledger priced from the published rates, fixture and record modes, `GET /api/spend`, `./dev check-api`.
- Backend service skeleton: settings validated at startup, `/healthz`, `/readyz`, `/api/version`, JSON logs with request IDs.
- Frontend shell that shows API status.
- `./dev` command runner with a small bash helper library, Docker dev and production stacks.
- CI on Linux and macOS, docs site skeleton published to GitHub Pages.
