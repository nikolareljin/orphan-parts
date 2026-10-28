# Security

## Controls in place

- API keys are `SecretStr` settings read from the environment. They never reach logs, errors or the browser.
- CORS allowlist from `CORS_ORIGINS`; only `GET`, `POST` and `DELETE`.
- Security headers on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- Containers run as an unprivileged user; the production image has no dev tooling.

## Planned with the features that need them

- Upload type and size limits, EXIF and GPS stripping on ingest.
- Per-IP rate limiting on the pipeline endpoints.
- `X-Hub-Signature-256` verification on the WhatsApp and Messenger webhooks.
- Retention purge of uploads after `RETENTION_HOURS`.

## Threat model

The service handles photos of objects and the text of listings. It stores no accounts and no
payment data. The assets worth protecting are the Model API key, the user's photos while they
are retained, and any Meta platform tokens a user chooses to configure for catalog push.

Reports: see `SECURITY.md` in the repository.
