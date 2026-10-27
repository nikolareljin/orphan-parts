# Security

## Reporting

Email nikola.reljin@gmail.com with a description and, if possible, steps to reproduce.
Please do not open a public issue for anything that could expose user data or API keys.

## What the service does to protect users

- API keys come only from the environment. They are never logged, never stored, never sent to the browser.
- Uploaded images are checked for type and size, stripped of EXIF and GPS metadata, and deleted after `RETENTION_HOURS`.
- The browser talks to the backend through a CORS allowlist (`CORS_ORIGINS`).
- Responses carry standard security headers.
- Webhooks from Meta platforms are accepted only with a valid `X-Hub-Signature-256`.
- Containers run as a non-root user.

The threat model and the full list of controls are in the docs under *Operations > Security*.
