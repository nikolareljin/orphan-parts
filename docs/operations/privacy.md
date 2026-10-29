# Privacy

- Photos are stripped of EXIF and GPS metadata on ingest, before anything else happens.
- Uploads live under `DATA_DIR` and are deleted after `RETENTION_HOURS`.
- What leaves the machine: crops and prompts, the listing brief (the confirmed values and the details you typed: condition, faults, tests, accessories, pickup, price) the price brief (the same values and details, the currency and the place you give, which the Model API also turns into web searches) and voice recordings go to the Meta Model API; nothing goes anywhere else.
  With Muse Glimmer running locally, the usability pre-check happens before any upload.
- No accounts, no tracking, no third-party scripts in the web app.

!!! note
    Ingest and retention are not built yet; this page states the rules they implement.
