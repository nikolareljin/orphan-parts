# Configuration

All configuration comes from environment variables, read from `.env` in development and from the
host's secret store in production. Settings are validated at startup; a missing key in live mode
stops the service with a clear message instead of failing on the first user request.

| Variable | Default | Required | Meaning |
|---|---|---|---|
| `MODEL_API_KEY` | | yes, unless fixture mode | Model API key from https://dev.meta.ai |
| `MODEL_API_BASE_URL` | `https://api.meta.ai/v1` | | Model API base URL |
| `MODEL_SPARK` | `muse-spark-1.3` | | Muse Spark model ID |
| `MODEL_WONDER` | `muse-wonder-1.0` | | Muse Wonder model ID; listed and checked, no call in this version |
| `MODEL_IMAGE` | `muse-image-1.0` | | Muse Image model ID; listed and checked, no call in this version |
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
| `IMAGE_MAX_PX` | `1280` | | photos are downscaled to this long edge before upload |
| `SEGMENT_MAX_PX` | `800` | | the copy SAM 3.1 sees is downscaled to this long edge; boxes are scaled back onto the photo |
| `MAX_PHOTOS` | `4` | | photos accepted per item |
| `RETENTION_HOURS` | `24` | | reserved for a purge of stored photos; nothing but measurement photos is kept today, and no purge runs |
| `CORS_ORIGINS` | `http://localhost:5173` | | comma-separated browser origins allowed to call the API |
| `DATA_DIR` | `./data` | | uploads, the spend ledger and the SQLite database |
| `MAX_UPLOAD_MB` | `12` | | upload size limit per file |
| `INVENTORY_DB_FILE` | `inventory.sqlite3` | | the inventory database, inside `DATA_DIR` |
| `MEASURE_MIN_SHARPNESS` | `150` | | least edge response (Laplacian variance) around every mark before a capture is measured |
| `MEASURE_MIN_REFERENCE_PX` | `80` | | least span of the scale reference in pixels |
| `VOICE_MAX_SECONDS` | `600` | | longest voice note accepted; the transcription service takes ten minutes at most, and `MAX_UPLOAD_MB` bounds the file first |
| `PRICE_SEARCH_CONTEXT` | `low` | | how much of each page the search hands the model: `low`, `medium` or `high`; more costs tokens and time |
| `PRICE_COUNTRY` | | | ISO 3166-1 country for local price results when the request names none |
| `DEMO_ACCESS_CODE` | | | the code the demo runs behind, twelve characters at least; empty = no gate |
| `DEMO_SESSION_HOURS` | `12` | | how long a session lasts |
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
