# Security

## Controls in place

- API keys are `SecretStr` settings read from the environment. They never reach logs, errors or the browser.
- CORS allowlist from `CORS_ORIGINS`; only `GET`, `POST` and `DELETE`.
- Security headers on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- Containers run as an unprivileged user; the production image has no dev tooling.
- Upload type and size limits; photos are re-encoded on ingest, which drops EXIF and GPS.
- The demo gate ([Demo access](demo-access.md)): an access code for every page, sessions signed
  with a key derived from the code and kept nowhere, so many tries of the code per address,
  allowances per visitor and per day on every call that spends, a per-address limit on every
  request, an operator's switch, and the forwarded address trusted only when told to.

## Planned with the features that need them

- `X-Hub-Signature-256` verification on the WhatsApp and Messenger webhooks.
- Retention purge of uploads after `RETENTION_HOURS`.

## Threat model

The service handles photos of objects and the text of listings. It stores no accounts and no
payment data. The assets worth protecting are the Model API key, the user's photos while they
are retained, and any Meta platform tokens a user chooses to configure for catalog push.

Reports: see `SECURITY.md` in the repository.
