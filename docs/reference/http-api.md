# HTTP API

Interactive documentation is served by the running backend at http://localhost:8000/docs.
The same OpenAPI document is rendered below.

<swagger-ui src="openapi.json"/>

## Feature endpoints

| Path | Purpose |
|---|---|
| `POST /api/extract` | multipart `photos` (one to `MAX_PHOTOS` images, each at most `MAX_UPLOAD_MB`) and optional `crops` (label crops from `/api/segment`): reads the label into typed fields, each with `value`, `unit`, `confidence`, `source` (`photo`, or `label_crop` when crops were sent) and `raw`, plus `item_type`, `label_text`, `warnings`, the counts of photos and crops, the model used, `from_fixture` and `cost_usd` |
| `POST /api/segment` | multipart `photo` (one image) and optional repeated `concepts` (default `item`, `label`, `connector`; an unknown key is sent to the model as its own phrase): one region per match with `concept`, `box` (half-open pixels of the prepared photo), `confidence`, `coverage`, a JPEG `crop` data URL and the mask outline as `svg_path`; plus the `overlay` (the photo with the masks drawn over it), `warnings`, `width`, `height`, the model, `from_fixture` and `cost_usd` |

Errors, for both: `400` for a bad or oversized photo (by upload size or pixel count), a HEIC
file, too many photos or concepts, `422` when the required file field is missing, `502` when the model answer was incomplete or the Model API failed, `503` when the spend
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
