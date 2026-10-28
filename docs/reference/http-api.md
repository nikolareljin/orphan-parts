# HTTP API

Interactive documentation is served by the running backend at http://localhost:8000/docs.
The same OpenAPI document is rendered below.

<swagger-ui src="openapi.json"/>

## Feature endpoints

| Path | Purpose |
|---|---|
| `POST /api/extract` | multipart `photos` (one to `MAX_PHOTOS` images, each at most `MAX_UPLOAD_MB`): reads the label into typed fields, each with `value`, `unit`, `confidence`, `source` and `raw`, plus `item_type`, `label_text`, `warnings`, the model used, `from_fixture` and `cost_usd` |

Errors: `400` for a bad or oversized photo (by upload size or pixel count), a HEIC file, or too
many photos, `422` when the `photos` field is missing, `502` when the model answer was incomplete or the Model API failed, `503` when the spend
cap is reached or fixture mode has no recorded answer. The `detail` text is safe to show.

## Operational endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | process is up |
| `GET /readyz` | config loaded, Model API mode (`live`, `record` or `fixture`), data directory writable, spend so far against the cap, `paused` once the cap is reached |
| `GET /api/version` | package version, the configured model IDs and the upload `limits` (`max_photos`, `max_upload_mb`) the web form follows |
| `GET /api/spend` | the spend ledger: total, cap, remaining, calls per model with token counts, live versus fixture calls |

Every response carries `X-Request-ID`. Send your own to have it echoed back and used in the logs
and in the spend ledger.
