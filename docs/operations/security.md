# Security

## Controls in place

- API keys are `SecretStr` settings read from the environment. They never reach logs, errors or the browser.
- CORS allowlist from `CORS_ORIGINS`, origins named one by one (`*` refused); `GET`, `POST`, `PUT`, `PATCH` and `DELETE`.
- Security headers on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`.
- Containers run as an unprivileged user; the production image has no dev tooling.
- Upload type and size limits; photos are re-encoded on ingest, which drops EXIF and GPS.
- The demo gate ([Demo access](demo-access.md)): an access code for every page, sessions signed
  with a key derived from the code and kept nowhere, so many tries of the code per address,
  allowances per visitor and per day on every call that spends, a per-address limit on every
  request, an operator's switch, and the forwarded address trusted only when told to.

## Not in this version

- No inbound webhooks: there is no messaging channel, so nothing verifies a platform signature.
- No purge on a timer: nothing but the measurement photos is kept, so `RETENTION_HOURS` has no
  job behind it yet.

## Threat model

The service handles photos of objects, the text of listings, and what the owner says about
their things. It stores no accounts and no payment data, and holds no platform token. The
assets worth protecting are the Model API key, the inventory (the measurement photos and the
owner's own words in it) and, on a public demo, the access code and the spend.

Reports: see `SECURITY.md` in the repository.
