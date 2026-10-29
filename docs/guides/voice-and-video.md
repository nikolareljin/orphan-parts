# Voice notes and video capture

Dictate the condition of a part with Muse Voice Transcribe, or record a short turnaround video and let SAM 3.1 pick the sharpest label frame.

## Built so far

**Voice note.** On an item's page, under *Prepare to sell or give away*, pick a WAV recording
(ten minutes at most). Muse Voice Transcribe turns it into text, kept on the item as the field
`condition_notes` with the source `voice_note`, accepted as your own words; the draft reads it
from there. `POST /api/items/{id}/voice`. The sharpest label frame from a short video is not
wired in yet.
