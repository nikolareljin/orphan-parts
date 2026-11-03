# Assets and licenses

Everything in the finished videos, where it comes from and under what terms. Add a row for
every take, clip or track that goes into the cut.

## In this folder

| Asset | Source | License |
|---|---|---|
| `brand/logo.svg` | the project's logo, a byte-for-byte copy of `docs/assets/logo.svg` | the owner's; the repository is MIT |
| `brand/logo.png`, `logo-plate.png`, `corner-overlay*.png` | rendered from `logo.svg` by `render.sh` | as above |
| `brand/card-*.svg`, `card-*.png` | drawn for the video; the logo linked, not copied | MIT, with the repository |
| `titles/*.svg`, `*.png` | drawn for the video | MIT |
| `scenes/notes/gpu-note.wav` | the voice note of S18: the condition the demo set states for the graphics card, spoken by Piper with `en_US-norman-medium`, not the owner | the voice model's card lists its dataset as public domain; the clip is the owner's |
| `scripts/*.md`, `*.srt` | the narration, written for a neutral narrator; each section notes what the app does and what is not claimed | the owner's |
| Text in every PNG | Noto Sans, rendered into the pictures; the font file is not distributed | SIL Open Font License 1.1 |

## Recorded for the video

| Asset | Source | License |
|---|---|---|
| Screen recordings of the web app | `generate.sh`, Playwright against the owner's local stack (or OBS Studio) | the owner's |
| Phone recordings | the owner's phone, `phone.sh` (`adb shell screenrecord`) or scrcpy; without one, the app's screenshots in `docs/assets/pairing/` | the owner's |
| The mixer, its label, the agitator, the electronics | the owner's own photos, the scrubbed copies in `demo/photos/` | the owner's |
| Narration | a synthetic narrator: `tts.py` reads the captions with Piper (the `piper-tts` package, GPL-3.0-or-later, run locally and not distributed) and the voice model `en_US-ljspeech-high` from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/high), trained on the LJ Speech dataset; neither is kept in the repository. With `--voice en_US-norman-medium`, the model trained on LibriVox recordings | the voice models' cards list their datasets as public domain; the generated track is the owner's |
| Demo set data: the items, the sample listings L1 to L4 | `demo/set.yaml`, `demo/listings/`; the listings are written examples, labeled as such | MIT |

## Optional, add a row when used

| Asset | Source | License |
|---|---|---|
| Establishing clips R1 to R3 | Runway, from `runway-prompts.md`; labeled *Illustrative clip, made with Runway* | per the Runway plan's terms at the time of use; check them first |
| Music | Clipchamp's free audio library (no premium mark), or the YouTube Audio Library | per the library's terms; write the track's title and source here |

## Not used, by rule

- No Marketplace or facebook.com pages, no Meta or Facebook logos, no imitation of either.
- No other people's names, faces, listings or photos.
- No stock photos of products, no images or clips that imitate the app's screens.
- No generated images other than the app's own **Draw it** picture, shown as the app labels it
  (drawn, not a photo). Meta's model names appear as text only.
