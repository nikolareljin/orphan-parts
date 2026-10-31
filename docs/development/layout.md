# Repository layout

```
backend/
  app/
    main.py           app factory, middleware, routers
    config.py         settings, validated at startup
    api/              one router per feature (items, photos, extract, segment, measure,
                      assess, drafts, voice, value, decide, find, projects, picture,
                      captures, pair, samples, profiles, access); routes.py holds the
                      operational paths
    extract/, segment/, measure/, match/, listing/, value/, decide/, find/, projects/,
    picture/, captures/
                      one package per feature: schema, service, data
    inventory/        the SQLite store, its migrations and the item service
    photos/           the photos kept with an item
    keys/, pairing/   access codes issued as records; the phone's pairing and its own code
    samples/          the demo set's photos as the visitor's gallery, read by id
    eval/             the evaluation loop over the demo set and the training export
    profiles/         the category profiles as data, and their loader
    demo/             the demo set loaded through the services, recorded once, replayed
    model_api/        the Model API client, pricing, spend ledger, recorded fixtures
    ops/              logging, request context, security headers, the demo gate
    openapi_export.py prints the OpenAPI document for the docs site
  tests/
    fixtures/api/     recorded Model API responses, one JSON file per request or operation
  pyproject.toml      dependencies, ruff, mypy, pytest config
  Dockerfile          dev and prod targets

frontend/
  src/
    App.tsx           shell
    components/       one component per page and panel
    lib/api.ts        the only place that talks to the backend
    public/           the header's mark and the favicon
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

deploy/
  modal_app.py        the backend on Modal: image, volume, secret, one container (./dev deploy modal)

demo/
  set.yaml            the demo set: items, searches, listings, the proposal brief
  photos/, notes/     scrubbed photos and WAV notes (written by ./dev demo-scrub)
  listings/           written listing examples, labelled as demo data

livecheck/
  README.md           the live check: one real Model API call per operation (./dev live-check),
                      its price table, its two modes; mounted read-only into every
                      development backend container, never in an image or deployed

scripts/
  lib/                bash helper modules used by ./dev
  android.sh          the app's tests, APKs, install, launch and smoke run (./dev android, ./dev phone)
  app-icon.sh         the launcher icon PNGs and the web header's mark, cut from docs/assets/logo.svg
  setup-android.sh    the JDK and the Android command-line tools, installed when missing (./dev setup --android)
  release-tag.sh      the version a release branch names, checked before it becomes a tag
  release-notes.sh    the notes of one release, assembled from the changelog and the history
  release.sh          tag VERSION on main and push the tag, by hand (./dev release)
  deploy.sh           put a published release on the host, build the APK (./dev deploy)
  deploy-hosted.sh    the hosted demo: the Modal secret, the backend, the web app on Pages
                      (./dev deploy hosted; the deploy workflow's steps)
  tests/              their tests
VERSION               the version, the one place it is read from by hand

e2e/                  the Playwright browser checks (./dev e2e)
eval/                 where ./dev eval writes its report and charts
video/                the demo video kit: scripts, storyboards, captions
docker/docs/          image that builds and serves the docs site
docs/, mkdocs.yml     this site
  assets/             the logo, the share image, the flow diagram, the stylesheet, and
                      apk-qr.svg, the QR code that opens the newest release's APK
                      (development/ci.md says how it is made)
overrides/            the theme override: the share metadata every page carries
.github/workflows/    ci.yml (checks), android.yml (the app's checks), tag-release.yml (merged release/x.y.z -> tag), release.yml (tags to GHCR + GitHub release + APK), deploy.yml (the hosted demo on Modal and Cloudflare Pages), docs.yml (Pages)
dev                   command runner
docker-compose.yml    development stack
docker-compose.prod.yml
```

