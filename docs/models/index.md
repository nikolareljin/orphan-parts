# Meta models

Every call to a Meta model goes through one client against the Model API at `https://api.meta.ai/v1`.
Model IDs are configuration, never literals in code (see [Configuration](../reference/configuration.md)).

| Model | ID (default) | Used for |
|---|---|---|
| Muse Spark | `muse-spark-1.3` | structured extraction from label crops, listing-screenshot parsing, candidate ranking and deal checks, agent steps, explanations, search grounding |
| Muse Wonder | `muse-wonder-1.0` | orchestrating the buyer comparison, drafting category profiles |
| Muse Image | `muse-image-1.0` | cover-photo background cleanup |
| Muse Voice Transcribe | `muse-voice-transcribe-1.0` | spoken questions on the phone, voice notes |
| SAM 3.1 | `sam-3.1` | segmentation of part, label and connector; video tracking |
| Muse Glimmer | local, open weights | privacy-first usability pre-check before upload, offline fallback |
| Muse Spark Open | partner-hosted, open weights | alternative extraction provider |

Each model page covers its job in the app, the exact request shape, the settings that affect it,
cost notes and failure modes.

## Fixture mode

With `OPL_FAKE_API=1` the client serves recorded responses from `backend/tests/fixtures/` and
spends nothing. Tests always run this way.
