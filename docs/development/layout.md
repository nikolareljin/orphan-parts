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

android/
  app/src/main/kotlin/com/orphanparts/lens/
    api/              the backend by its paths: transport, multipart, client
    audio/            hold-to-talk recording, WAV framing
    ui/               the three pages: backend, capture, talk
  app/src/test/       unit tests on the JVM
  build.gradle.kts, settings.gradle.kts, gradlew

scripts/
  lib/                bash helper modules used by ./dev
  android.sh          the app's tests, APKs, install and smoke run (./dev android)
  release-tag.sh      the version a release branch names, checked before it becomes a tag
  release-notes.sh    the notes of one release, assembled from the changelog and the history
  release.sh          tag VERSION on main and push the tag, by hand (./dev release)
  deploy.sh           put a published release on the host, build the APK (./dev deploy)
  tests/              their tests
VERSION               the version, the one place it is read from by hand

docker/docs/          image that builds and serves the docs site
docs/, mkdocs.yml     this site
overrides/            the theme override: the share metadata every page carries
.github/workflows/    ci.yml (checks), android.yml (the app's checks), tag-release.yml (merged release/x.y.z -> tag), release.yml (tags to GHCR + GitHub release + APK), docs.yml (Pages)
dev                   command runner
docker-compose.yml    development stack
docker-compose.prod.yml
```

Directories that arrive with later features: `backend/app/pipeline/`, `profiles/`, `agent/`,
`providers/`, `channels/`, `meta/`; `frontend/src/pages/`, `components/`; `demo/`.
