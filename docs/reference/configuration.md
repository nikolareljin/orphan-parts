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
| `SPEND_CAP_USD` | `25` | | stop calling the Model API once this much is spent in the process |
| `RETENTION_HOURS` | `24` | | uploaded images are deleted after this many hours |
| `CORS_ORIGINS` | `http://localhost:5173` | | comma-separated browser origins allowed to call the API |
| `DATA_DIR` | `./data` | | uploads and the SQLite database |
| `MAX_UPLOAD_MB` | `12` | | upload size limit per file |
| `LOG_FORMAT` | `json` | | `json` or `text` |
| `LOG_LEVEL` | `INFO` | | Python log level |

Keys are `SecretStr` values: they never appear in logs, error messages or `repr()`.
