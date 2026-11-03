# The demo video kit

Everything needed to make the two videos for the Meta Global AI Developer Hackathon entry:
the main video (2:42, the limit is under 3:00) and a short one (55 s) for the social post.
Two stories: **A**, a favorite frappé routine stopped by a worn mixer agitator, the app asking
which device it came from and searching the web for the maker's part; **B**, unused
electronics turned into a tabletop arcade.

## What is here

| Path | What |
|---|---|
| [readiness.md](readiness.md) | what the app does today, each shot's status, and the live recordings still needed with their cost |
| `generate.sh` (`./dev video`) | the draft cuts, end to end: its own stack, the scenes recorded, the drafts cut into `out/` |
| `scenes/` | the web shots as Playwright tests, one per shot (`compose.video.yml` runs them) |
| `assemble.py` | the cut: shot lists, the photos' push in, titles, corner logo, captions, sound, contact sheet |
| `phone.sh` | the phone shot on a connected phone (`--phone`) |
| `tts.py` | a rough local text-to-speech narration for timing (`--tts`), when one is installed |
| [scripts/main.md](scripts/main.md), [scripts/short.md](scripts/short.md) | the narration, with a note per section of what the app does and what is not claimed |
| `scripts/main.srt`, `scripts/short.srt` | captions; `scripts/captions.py` writes them from the scripts |
| [storyboard/main.md](storyboard/main.md), [storyboard/short.md](storyboard/short.md) | the shot lists: times, durations, pictures, exact actions, overlays |
| [recording.md](recording.md) | OBS Studio on Ubuntu, the stack in fixture and live mode, the phone |
| [clipchamp.md](clipchamp.md) | the edit in Clipchamp (free plan, 1080p), Kdenlive as the local alternative |
| `brand/` | the logo (the SVG untouched, a 2048 px PNG), the cards, the overlays, [palette.md](brand/palette.md) |
| `titles/` | the on-screen titles: transparent 1920x1080 PNGs, top left, one per scene |
| `diagrams/` | the arcade's connection diagram, its layout and the display-swap concept, SVG and PNG |
| `cad/arcade_panel.scad` | an unvalidated control-panel concept, every size a named placeholder |
| [assets.md](assets.md) | every asset with its source and license |
| [runway-prompts.md](runway-prompts.md) | optional establishing clips, context only |
| [checklist.md](checklist.md) | the final export checklist |
| `render.sh` | renders every PNG from its SVG |
| `animatic.sh` | a silent timing check of the main video, written to `video/out/` |

## Production steps

1. **Generate the drafts**: `video/generate.sh` (or `./dev video`). It needs Docker, ffmpeg and
   python3, brings up its own stack (`opl-video`, ports 18310 and 18373; a running `./dev up`
   is not touched) in fixture mode with a throwaway access code, loads the demo set, records
   every web shot, cuts `out/main-draft.mp4`, `out/short-draft.mp4` and `out/main-shots.jpg`,
   and removes the stack. Shots whose answer is still an operation's stub carry a red DRAFT
   line; `out/work/standins.txt` lists them. `--assemble` cuts again from the takes already
   recorded, `--keep` leaves the stack up to look at.
2. **Record the live answers once** (`readiness.md`, *The live recordings still needed*, about
   $0.08 to $0.17): `export MODEL_API_KEY=...`, `video/generate.sh --record`, review and commit
   the new files under `backend/tests/fixtures/api`, `unset MODEL_API_KEY`, then step 1 again:
   the DRAFT lines are gone when every shot replays a recording.
3. **The phone shot**: unlock the phone, Stay awake on, the app installed, then
   `VIDEO_PHONE_SERIAL=<adb serial> video/generate.sh --phone` (with `--record` as well to have
   the capture read once live). Without it the app's screenshots stand in.
4. **Narrate**: the owner records his own voice to the draft, one section at a time from
   `scripts/main.md` (`recording.md`, *Narration*), as one WAV the length of the cut, then
   `video/generate.sh --assemble --narration narration.wav`. Nothing is retimed: shift the
   section times in the script and run `scripts/captions.py` again if the voice moves.
5. **Final**: watch `out/main-draft.mp4` end to end, go through `checklist.md`, then export or
   polish in an editor (`clipchamp.md`) if wanted.

The kit's earlier path (OBS takes cut by hand, `recording.md`, `animatic.sh`) still works for
any shot the generator does not cover.

## The logo

`brand/logo.svg` is the logo as it is in the repository (`docs/assets/logo.svg`): a 512 x 512
view box, no external references (its only links are to gradients inside the file), its own
dark rounded tile. The cards and overlays link to it and never change it. A newer logo
replaces it like this:

```bash
cp new-logo.svg video/brand/logo.svg
video/render.sh
```

Every PNG is rendered again from it. A logo that is not square is fitted inside the same
box, centered.

## Rendering

`video/render.sh` needs Inkscape (or `rsvg-convert`) and the Noto Sans font
(`sudo apt install inkscape fonts-noto-core`). It fails if a PNG comes out over 2 MB.
`video/animatic.sh` needs ffmpeg. The control-panel concept in `cad/` is OpenSCAD source; it
is not rendered here, and it is not a design to build from until every placeholder is
replaced by a measured value.

Videos, takes and the generator's work files are never committed: `video/out/` is ignored.
