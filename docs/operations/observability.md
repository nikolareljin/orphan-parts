# Observability

- **Logs** are JSON lines on stdout (`LOG_FORMAT=json`), one per request, with `request_id`,
  `method`, `path`, `status` and `ms`. Set `LOG_FORMAT=text` for a readable local view.
- **Request IDs**: an incoming `X-Request-ID` is honoured, otherwise one is generated. It is
  echoed in the response and attached to every log line written while handling the request.
- **Health**: `GET /healthz` says the process is up. `GET /readyz` reports whether configuration
  loaded, which Model API mode is active and whether the data directory is writable.

Token and cost accounting per model and request, with an admin view, lands with the Model API client.
