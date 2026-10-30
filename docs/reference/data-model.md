# Data model and storage

Everything lives in one SQLite file, `inventory.sqlite3` under `DATA_DIR`, beside the spend
ledger `model_api_spend.jsonl`. The schema is versioned; the service migrates forward at
startup and refuses to open a file written by a newer version.

## Tables

| Table | Since | Holds |
|---|---|---|
| `items` | v1 | one row per item: `name`, `item_type`, `condition`, `faults`, `tests_done`, `accessories`, `location`, `notes`, `intent`, `availability`, `parent_id` for a separated part, `profile` (v2), `version`, times, `deleted_at` (hidden, never erased) |
| `assertions` | v1 | every value ever recorded for a field of an item: `value`, `unit`, `provenance`, `confidence`, `source`, `raw`, `review`, `at`; the item's current fields are read off these ([evidence model](../concepts/evidence.md)) |
| `events` | v1 | the item's history: `actor`, `change`, the `version` it produced ([Events and history](events.md)) |
| `measurements` | v2 | a capture per feature: the `result` as JSON (method, value, uncertainty, checks, marks), the `photo` it was made on, the `assertion_id` it proposed |
| `drafts` | v3 | listing drafts per item and mode, each with the `item_version` it was written from, its `content` and its `checklist` state |
| `price_guidance` | v4 | each guidance written, with its `item_version` and `content` (the four quantities, comparables, sources, strategies) |
| `price_reports` | v4 | sales the owner reports: `price`, `currency`, `sold_on`, `note`; never merged with what a search finds |
| `searches` | v5 | missing-item requests: `need_item_id` or a `profile`, `title`, `content` (spec, radius, prices), `status`, `handoff_url` |
| `candidates` | v5 | listings brought back: `source_kind`, `observed_on`, `state`, `content` (the reading, the assessment, the questions) |
| `preferences` | v6 | one row: what the owner wants from a build |
| `projects` | v6 | `template`, `title`, `status`, `version`, `content` (requirements, result, effort, spend, unknowns, steps, progress, the outcome) |
| `allocations` | v6 | an item on a project for a requirement, `committed` or exploratory, with `why` |
| `packs` | v7 | build packs: `version` per project, `digest` of the inputs, the `markdown` |

`content` columns hold JSON validated by the Pydantic models of the owning package; the
shape of each is the one the [HTTP API](http-api.md) returns.

## What is kept, and for how long

- An uploaded photo is read in memory and dropped with the request; the only photo kept is the
  one a measurement was made on, with that measurement, on the item. Photos are re-encoded on
  ingest, so no metadata is ever stored.
- A voice recording is sent for transcription and dropped; the transcript stays on the item.
- Assertions, events and drafts are never rewritten: a correction is a new row beside the old
  one, and a hidden item keeps its history.
- The spend ledger is appended to and survives restarts; delete the file to reset the total.
- `RETENTION_HOURS` is a setting without a job behind it yet: nothing is purged on a timer,
  because nothing but the measurement photos is retained.

## Backups

Stop the stack, copy `DATA_DIR`, start it again. The file is plain SQLite and opens with any
client; the measurement photos are JPEG blobs inside it.
