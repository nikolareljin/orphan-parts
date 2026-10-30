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
| `captures` | v8 | what the phone sent in one go: `status` (received, processed, failed), `content` (the line, the name, the counts, the item it became, the error), times; the media under `DATA_DIR/captures/<id>/` |

`content` columns hold JSON validated by the Pydantic models of the owning package; the
shape of each is the one the [HTTP API](http-api.md) returns.

## What is kept, and for how long

- A photo sent to a reading route (`/api/extract`, `/api/segment`) is read in memory and dropped
  with the request. The web form then keeps the photos a saved item was read from under
  `DATA_DIR/items/<id>/` (`POST /api/items/{id}/photos`), and an item read from a capture gets
  the capture's photos the same way; they are shown in the item dialog beside the values to
  confirm and removed when the item is deleted. The photo a measurement was made on is kept
  with the measurement, on the item. Photos are re-encoded on ingest, so no metadata is ever
  stored.
- A capture from the phone is kept as sent, re-encoded photos, the clip and the WAV note, under
  `DATA_DIR/captures/<id>/`, until the capture is deleted; the item read from it stays.
- A voice recording sent to `/api/items/{id}/voice` is transcribed and dropped; the transcript
  stays on the item. A capture's note stays with the capture.
- Assertions, events and drafts are never rewritten: a correction is a new row beside the old
  one, and a hidden item keeps its history.
- The spend ledger is appended to and survives restarts; delete the file to reset the total.
- `RETENTION_HOURS` is a setting without a job behind it yet: nothing is purged on a timer;
  captures are deleted by hand, from the Inbox.

## Backups

Stop the stack, copy `DATA_DIR`, start it again. The database is plain SQLite and opens with any
client; the measurement photos are JPEG blobs inside it, and the captures' media and the
items' photos are files beside it under `captures/` and `items/`.
