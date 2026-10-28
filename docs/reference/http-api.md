# HTTP API

Interactive documentation is served by the running backend at http://localhost:8000/docs.
The same OpenAPI document is rendered below.

<swagger-ui src="openapi.json"/>

## Operational endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | process is up |
| `GET /readyz` | config loaded, Model API mode (`live` or `fixture`), data directory writable |
| `GET /api/version` | package version and the configured model IDs |

Every response carries `X-Request-ID`. Send your own to have it echoed back and used in the logs.
