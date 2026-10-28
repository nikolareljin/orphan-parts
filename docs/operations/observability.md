# Observability

- **Logs** are JSON lines on stdout (`LOG_FORMAT=json`), one per request, with `request_id`,
  `method`, `path`, `status` and `ms`. Set `LOG_FORMAT=text` for a readable local view.
- **Request IDs**: an incoming `X-Request-ID` is honoured, otherwise one is generated. It is
  echoed in the response and attached to every log line written while handling the request.
- **Health**: `GET /healthz` says the process is up. `GET /readyz` reports whether configuration
  loaded, which Model API mode is active, whether the data directory is writable, and the spend
  so far against the cap.

## Model API calls

Every call writes one log line from `app.model_api` with `op`, `model`, `attempts`, `ms`,
`input_tokens`, `output_tokens`, `usd` and the running `total_usd`. Retries log a warning with
the delay and the error. Reaching the cap logs a warning and `GET /readyz` turns `paused` on.

## Spend ledger

`DATA_DIR/model_api_spend.jsonl` holds one JSON line per call (timestamp, request ID, operation,
model, endpoint, usage, price, fixture flag, attempts, duration). The file survives restarts, so
the cap is cumulative for the deployment, not per process. `GET /api/spend` summarises it per
model. Delete the file to reset the total.
