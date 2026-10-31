# Configuration

All configuration comes from environment variables, read from `.env` in development and from the
host's secret store in production. Settings are validated at startup; a missing key in live mode
stops the service with a clear message instead of failing on the first user request.

| Variable | Default | Required | Meaning |
|---|---|---|---|
| `MODEL_API_KEY` | | yes, unless fixture mode | Model API key from https://dev.meta.ai |
| `OPL_KEY_PROBE` | `1` | | one `GET /models` at startup in live mode; a key that cannot work (401, 402, 403, 404) puts the service on recorded answers, said on `/readyz`; a busy or failing API changes nothing |
| `MODEL_API_BASE_URL` | `https://api.meta.ai/v1` | | Model API base URL |
| `MODEL_SPARK` | `muse-spark-1.3` | | Muse Spark model ID |
| `MODEL_WONDER` | `muse-wonder-1.0` | | Muse Wonder model ID; listed and checked, no call in this version |
| `MODEL_IMAGE` | `muse-image-1.0` | | Muse Image model ID; draws a picture of what an item could become when `PICTURE_ENABLED` is set and the owner clicks |
| `MODEL_VOICE` | `muse-voice-transcribe-1.0` | | Muse Voice Transcribe model ID |
| `MODEL_SAM` | `sam-3.1` | | SAM model ID |
| `OPL_FAKE_API` | `0` | | `1` serves recorded fixtures and never calls the Model API |
| `OPL_RECORD_FIXTURES` | `0` | | `1` calls the Model API and saves every response as a fixture |
| `SPEND_CAP_USD` | `25` | | stop calling the Model API once the ledger reaches this amount |
| `SPEND_LEDGER_FILE` | `model_api_spend.jsonl` | | ledger file name inside `DATA_DIR` |
| `MODEL_API_TIMEOUT_S` | `60` | | per-request timeout |
| `MODEL_API_MAX_ATTEMPTS` | `4` | | attempts for 429, 500 and 503 responses |
| `MODEL_API_RETRY_AFTER_MAX_S` | `30` | | longest wait honoured from a `Retry-After` header |
| `PROMPT_CACHE_NAME` | `orphan-parts` | | routing key sent with every call for prompt caching |
| `EXTRACT_REASONING_EFFORT` | `low` | | reasoning effort for label extraction |
| `MODEL_MAX_OUTPUT_TOKENS` | `0` | | ceiling on the `max_output_tokens` sent with a call: each operation's answer budget plus the room reasoning takes at its effort (1,024 at `minimal`, 4,096 at `low`, 8,192 at `medium`, 16,384 at `high`, 32,768 at `xhigh`), since reasoning tokens count against that cap; `0` = no ceiling. Tokens are billed as used, so the ceiling bounds the worst call, not the usual one |
| `IMAGE_MAX_PX` | `1280` | | photos are downscaled to this long edge before upload |
| `SEGMENT_MAX_PX` | `800` | | the copy SAM 3.1 sees is downscaled to this long edge; boxes are scaled back onto the photo |
| `MAX_PHOTOS` | `4` | | photos accepted per item |
| `PICTURE_ENABLED` | `0` | | `1` lets the item dialog draw a picture of what an item could become: one Muse Image call per click ($0.01 an image), counted in the ledger, never automatic; off, the route answers 503 and the button is disabled |
| `EXTRACT_ENHANCE` | `1` | | contrast stretched and edges sharpened on what goes to the model; what is kept is the photo as taken. Changing it changes what the model is shown, so fixtures recorded for a photo stop matching and the operation's fallback answers instead: record the set again |
| `EXTRACT_BLUR_THRESHOLD` | `150` | | the sharpness (variance of the Laplacian on a 512 px copy) under which a reading warns that the label looks blurred |
| `RETENTION_HOURS` | `24` | | reserved for a purge of stored photos; nothing but measurement photos is kept today, and no purge runs |
| `CORS_ORIGINS` | `http://localhost:5173` | | comma-separated browser origins allowed to call the API, named one by one (`*` is refused: calls carry credentials) |
| `API_DOCS` | `1` | | serve the interactive API docs at `/docs` and the schema at `/openapi.json`; `0` makes both answer 404 (the hosted demo's secret sets it) |
| `DATA_DIR` | `./data` | | uploads, the spend ledger and the SQLite database |
| `MAX_UPLOAD_MB` | `12` | | upload size limit per file |
| `MAX_CLIP_MB` | `60` | | size limit for a clip sent with a capture |
| `MAX_CAPTURES` | `200` | | how many captures the Inbox keeps at once; a send over it is refused until some are deleted |
| `INVENTORY_DB_FILE` | `inventory.sqlite3` | | the inventory database, inside `DATA_DIR` |
| `SQLITE_JOURNAL_MODE` | `WAL` | | the database's journal mode; `DELETE` on a network filesystem (the Modal volume sets it) |
| `MEASURE_MIN_SHARPNESS` | `150` | | least edge response (Laplacian variance) around every mark before a capture is measured |
| `MEASURE_MIN_REFERENCE_PX` | `80` | | least span of the scale reference in pixels |
| `VOICE_MAX_SECONDS` | `600` | | longest voice note accepted; the transcription service takes ten minutes at most, and `MAX_UPLOAD_MB` bounds the file first |
| `PRICE_SEARCH_CONTEXT` | `low` | | how much of each page the search hands the model: `low`, `medium` or `high`; more costs tokens and time |
| `PRICE_COUNTRY` | | | ISO 3166-1 country for local price results when the request names none |
| `DEMO_ACCESS_CODE` | | | the master code of the live door, twelve characters at least; empty = no gate (a machine of your own). Codes issued as records (`./dev keys`) open the same door beside it; without a code a visitor is the demo |
| `DEMO_SESSION_HOURS` | `12` | | how long a session lasts |
| `PAIR_TOKEN_MINUTES` | `15` | | how long the pairing in a QR code lasts, 1 to 60: the time to scan it and claim the phone's code; while it lasts the QR is a live session, so it stays off a projector and out of a recording |
| `PAIR_CODE_DAYS` | `30` | | how long the access code a phone claims on its first scan lasts, 1 to 3650; never past the code that paired it, and ended with it |
| `PAIR_CODE_MAX` | `10` | | how many phones with current codes one code may have paired, 1 to 100; past that a claim is refused until `./dev keys revoke` ends one or one runs out |
| `DEMO_VISITOR_CALLS_PER_HOUR` | `20` | | calls that spend, per session and hour |
| `DEMO_DAILY_CALLS` | `300` | | calls that spend, for everyone per UTC day |
| `DEMO_CODE_ATTEMPTS` | `5` | | tries of the code per address and quarter hour |
| `DEMO_REQUESTS_PER_MINUTE` | `120` | | requests of any kind per address and minute |
| `DEMO_PAUSED` | `0` | | `1` refuses every call that spends; `/readyz` says so |
| `DEMO_TRUST_PROXY` | `0` | | read the caller's address from the forwarded header; the production compose file sets it |
| `DEMO_COOKIE_SECURE` | `0` | | mark the session cookie `Secure`; set it on an https host |
| `MARKETPLACE_SEARCH_URL` | `https://www.facebook.com/marketplace/search/` | | the search page a request's handoff link opens, with the request's words and top price; the owner runs it |
| `CANDIDATE_DAYS` | `14` | | how long a candidate's observation is trusted before it is too old |
| `MARKETPLACE_CREATE_URL` | `https://www.facebook.com/marketplace/create/item` | | where Open Marketplace sends the owner with the draft copied; nothing is posted by the service |
| `MEASURE_MIN_IMAGE_PX` | `480` | | least short side of a measurement photo |
| `MEASURE_MARK_PX` | `1.5` | | marking precision per endpoint the uncertainty is derived from |
| `LOG_FORMAT` | `json` | | `json` or `text` |
| `LOG_LEVEL` | `INFO` | | Python log level |

Keys are `SecretStr` values: they never appear in logs, error messages or `repr()`.

## Modes

| `OPL_FAKE_API` | `OPL_RECORD_FIXTURES` | Mode | Network | Cost |
|---|---|---|---|---|
| `1` | any | `fixture` | none | none |
| `0` | `0` | `live` | Model API | billed |
| `0` | `1` | `record` | Model API, responses saved | billed |

`GET /readyz` reports the active mode.
