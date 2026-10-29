# Repository layout

```
backend/
  app/
    main.py           app factory, middleware, routers
    config.py         settings, validated at startup
    api/routes.py     HTTP endpoints
    model_api/        the Model API client, pricing, spend ledger, recorded fixtures
    ops/              logging, request context, security headers
    openapi_export.py prints the OpenAPI document for the docs site
  tests/
    fixtures/api/     recorded Model API responses, one JSON file per request or operation
  pyproject.toml      dependencies, ruff, mypy, pytest config
  Dockerfile          dev and prod targets

frontend/
  src/
    App.tsx           shell
    lib/api.ts        the only place that talks to the backend
  vite.config.ts      dev proxy to the backend, vitest config
  Dockerfile          build + nginx
  nginx.conf          static files, API proxy

scripts/
  lib/                bash helper modules used by ./dev
  tests/              their tests

docker/docs/          image that builds and serves the docs site
docs/, mkdocs.yml     this site
overrides/            the theme override: the share metadata every page carries
.github/workflows/    ci.yml (checks), tag-release.yml (merged release/x.y.z -> tag), release.yml (tags to GHCR + GitHub release), docs.yml (Pages)
dev                   command runner
docker-compose.yml    development stack
docker-compose.prod.yml
```

Directories that arrive with later features: `backend/app/pipeline/`, `profiles/`, `agent/`,
`providers/`, `channels/`, `meta/`; `frontend/src/pages/`, `components/`; `demo/`.
