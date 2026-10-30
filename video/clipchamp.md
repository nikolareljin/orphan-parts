# Editing in Clipchamp (and Kdenlive)

Clipchamp in the browser or the Windows app, signed in with a personal Microsoft account, on
the free plan: 1080p export, and only assets that carry no premium mark. Nothing in this kit
needs a paid plan.

## First, a short test

1. New video, aspect 16:9.
2. Import `brand/card-open.png`, one screen recording, `brand/corner-overlay.png` and
   `scripts/main.srt`.
3. Five seconds of each on the timeline, the overlay on a track above.
4. **Export**, 1080p. Check the file: sharp text, the logo crisp in the corner, no watermark,
   the length right. Only then build the whole cut.

## The cut

1. Import everything under `brand/`, `titles/` and `diagrams/` (the PNG files), the takes, and
   the narration.
2. Track order, bottom to top: picture (takes, cards, diagrams), titles, corner overlay,
   captions; narration and any music on the audio tracks.
3. Lay the picture by the storyboard's times (`storyboard/main.md`). Stills: cards 6 to 10 s,
   diagrams by the shot list, with a slow zoom to 105 percent.
4. Titles: each `titles/*.png` on its track for the first 4 s of its shot, fade in and out
   0.3 s. Full-frame transparent PNGs, so no repositioning.
5. Corner overlay: `brand/corner-overlay.png` over every screen recording and phone shot, not
   over the cards (they carry the logo). Over dark footage, `corner-overlay-plate.png`.
6. Narration: place each section at its time; trim the silences, not the words.
7. Captions: if your Clipchamp offers a captions file upload, upload `scripts/main.srt`.
   Otherwise turn on its automatic captions from the narration track and correct every line
   against `main.srt` word for word. Style: white, plain sans, a dark box, bottom center.
8. Music (optional): a track from Clipchamp's free audio library with no premium mark, at
   about -24 dB under the voice; write its title in `assets.md`.
9. Export 1080p. Check the length is under 3:00 (target 2:50).

The short video: the same project duplicated, cut to `storyboard/short.md` and
`scripts/short.srt`.

## Kdenlive, the local alternative

```bash
sudo apt install kdenlive
```

**Project, Project Settings**: HD 1080p 30 fps. Import the same files; titles and overlays on
video tracks above the picture (PNG transparency is kept). Captions: **Project, Subtitles,
Import Subtitle File**, `scripts/main.srt`. **Render**: *MP4-H264/AAC*, 1920x1080.

Burning the captions into a finished file without an editor (for the short video's post):

```bash
ffmpeg -i main.mp4 -vf "subtitles=video/scripts/main.srt:force_style='FontName=Noto Sans,FontSize=22,BorderStyle=3,BackColour=&H66000000'" -c:a copy main-captioned.mp4
```

## A silent animatic

`video/animatic.sh` strings the cards, titles and diagrams into a silent MP4 at the
storyboard's times, the captions burned in and a dark frame naming the shot where a take
goes, as `video/out/animatic-main.mp4`. It is
a timing check, not footage for the video.
