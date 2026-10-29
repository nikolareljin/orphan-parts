# Muse Voice Transcribe

Transcribes seller voice notes in the web app and voice messages sent to the WhatsApp agent, with vocabulary biasing toward brand names and part-number patterns.

## Built so far

- **Request.** `POST /v1/asr/transcribe`, multipart: a `request` part (JSON with `model`
  `muse-voice-transcribe-1.0`, `audioEncoding` `WAV`, `mode` `PUSH_TO_TALK`) and the `audio`
  part. WAV only, ten minutes at most, 32 MB at most; the service reads the WAV header first
  and refuses anything else before a call is made (`VOICE_MAX_SECONDS`).
- **Response.** `transcript` for the whole clip and `audioDurationMs`; priced by the seconds
  heard, recorded in the ledger under `transcribe`. Fixture mode answers from
  `tests/fixtures/api/asr-transcribe/transcribe.json`.
- **Where it lands.** The item's `condition_notes` field with the source `voice_note`, accepted
  as the owner's words; see [voice notes](../guides/voice-and-video.md).
