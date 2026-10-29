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
| Oct 28 | Segmentation with SAM 3.1: item, label and connector found one concept per call, masks decoded with Meta's parser, overlay and crops rendered, `POST /api/segment`, a command line; the label crop feeds extraction and evidence is sourced `label_crop`. |
| Oct 28 | Web: upload form and evidence table; Playwright end-to-end checks in Docker (`./dev e2e`) and the `e2e` CI job. |
| Oct 29 | Private inventory: items saved from a reading with every value's provenance and review state, owner values beside observations, intent and availability, separated parts, versions and history, in SQLite under `DATA_DIR`; the My inventory page. |
| Oct 29 | Measurement from a photo: two-point scale or a homography from a known rectangle, quality checks that refuse a capture with the reason, an uncertainty derived from the marks and the reference, profile features with tolerances (`vacuum_attachment`, `power_adapter`, `generic_item`), captures stored on the item and proposed as observed values; the marking canvas on the item page. |
| Oct 29 | Evidence-backed assessment: rules as data in each profile (hard or soft, equal, within, at least, at most, identity), pass / fail / unknown per rule with the candidate's provenance and measurement uncertainty, the verdict ladder, seller questions for every unknown, `POST /api/assess` and `GET /api/profiles/{id}/rules`; the Does it fit? panel on the item page. |
