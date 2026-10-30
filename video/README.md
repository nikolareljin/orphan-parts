# The demo video kit

Everything needed to make the two videos for the Meta Global AI Developer Hackathon entry:
the main video (2:50, the limit is under 3:00) and a short one (55 s) for the social post.
Two stories: **A**, a favorite frappé routine stopped by a worn mixer agitator; **B**, unused
electronics turned into a tabletop arcade.

## What is here

| Path | What |
|---|---|
| [readiness.md](readiness.md) | what the app does today, and for each scene: recordable now, needs the key, needs the owner's photos, or a concept preview, with the exact app actions |
| [scripts/main.md](scripts/main.md), [scripts/short.md](scripts/short.md) | the narration, with every correction to the draft explained |
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

1. **Read `readiness.md`.** Nine scenes record from working features, six wait for the
   owner's photos or footage, four are concept previews, three are cards.
2. **Film the owner's things** (S01, S02, S04): the mixer, the worn agitator, the shelf.
   Photograph the mixer's label and the agitator next to a ruler for S05 to S07.
3. **Rehearse in fixture mode**: `./dev up`, `./dev demo`, every *now* scene once.
4. **Record** with OBS (`recording.md`): the fixture scenes, then the live ones with the key.
   `./dev demo` before every take.
5. **Check the timing**: `video/animatic.sh` and watch `video/out/animatic-main.mp4`.
6. **Cut** in Clipchamp (`clipchamp.md`) by `storyboard/main.md`; export a short test first.
7. **Record the narration** to the cut, retime the captions (`recording.md`, *Narration*).
8. **Export** both videos and go through `checklist.md`.

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

Videos and takes are never committed: `video/out/` is ignored.
