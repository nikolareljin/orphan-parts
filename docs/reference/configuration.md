# Configuration

All configuration comes from environment variables, read from `.env` in development and from the
host's secret store in production. Settings are validated at startup; a missing key in live mode
stops the service with a clear message instead of failing on the first user request.

| Variable | Default | Required | Meaning |
|---|---|---|---|
| `MODEL_API_KEY` | | yes, unless fixture mode | Model API key from https://dev.meta.ai |
| `MODEL_API_BASE_URL` | `https://api.meta.ai/v1` | | Model API base URL |
| `MODEL_SPARK` | `muse-spark-1.3` | | Muse Spark model ID |
| `MODEL_WONDER` | `muse-wonder-1.0` | | Muse Wonder model ID |
| `MODEL_IMAGE` | `muse-image-1.0` | | Muse Image model ID |
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
| `RETENTION_HOURS` | `24` | | uploaded images are deleted after this many hours |
| `CORS_ORIGINS` | `http://localhost:5173` | | comma-separated browser origins allowed to call the API |
| `DATA_DIR` | `./data` | | uploads, the spend ledger and the SQLite database |
| `MAX_UPLOAD_MB` | `12` | | upload size limit per file |
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
