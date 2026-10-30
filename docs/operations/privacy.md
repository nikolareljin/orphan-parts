# Privacy

- Photos are stripped of EXIF and GPS metadata on ingest, before anything else happens.
- Uploads live under `DATA_DIR` and are deleted after `RETENTION_HOURS`.
- What leaves the machine: crops and prompts, the listing brief (the confirmed values and the details you typed: condition, faults, tests, accessories, pickup, price) the price brief (the same values and details, the currency and the place you give, which the Model API also turns into web searches) voice recordings, the listing text or screenshot you bring back for a search, and the build brief (your preferences and, through the tools the model calls, the items a build may use with their fields, condition, faults, tests, accessories and parts) go to the Meta Model API; the build pack, the outcome and its share text are written by the rules on this machine and sent nowhere; the phone app sends its photos (re-encoded on the phone, pixels only) and its recordings to your backend and nowhere else, and keeps the backend URL and the access code in its private storage; nothing goes anywhere else. A listing's link is kept as you gave it and never opened. With an access code set, the browser keeps one session cookie that holds no account and nothing about you; it ends after `DEMO_SESSION_HOURS` or when you leave.
  With Muse Glimmer running locally, the usability pre-check happens before any upload.
- No accounts, no tracking, no third-party scripts in the web app.

!!! note
    Ingest and retention are not built yet; this page states the rules they implement.
