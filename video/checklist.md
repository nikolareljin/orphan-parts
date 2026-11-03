# Final export checklist

Tick every line before uploading.

## Content and claims

- [ ] Every scene shown as working is in the app on `main` (`readiness.md`, *Capabilities*).
- [ ] No red DRAFT line anywhere: every model answer on screen is a recording of that very
  request (`video/out/work/standins.txt` is empty), never an operation's stub.
- [ ] S17 and S18 (K8) carry the *Concept preview, not built* badge for their whole duration.
- [ ] S07 shows the model read off the mixer's own label; S08 names the part number only as
  the recorded page shows it, and no price the page did not state.
- [ ] S12 to S16: the narration names the project the recorded proposals actually hold.
- [ ] Story B carries `t08-story-b` (*recorded demo answers*).
- [ ] No price, saving, compatibility or completion claim that the app did not show on screen.
- [ ] No Marketplace page, no Meta or Facebook logo, no other people's listings or faces.
- [ ] Marketplace is described only as a search the owner runs and a create page he fills.
- [ ] Meta's models named as implemented: Muse Spark, SAM 3.1, Muse Voice Transcribe, Muse
  Image. Baseten and Fireworks only as *planned*, on the models card. No other AI tool named.
- [ ] The mixer: no model number, part name or fit stated unless the label photo and the
  takes in the video show it. No 3D-printed food-contact or rotating part suggested.
- [ ] The hosted demo is not named as live unless it is on the day of upload.
- [ ] A Runway clip, if any, carries its label; music, if any, is in `assets.md`.

## Picture and sound

- [ ] 1920x1080, 30 fps, H.264, AAC.
- [ ] Main video under 3:00 (the draft is 2:42); short video 45 to 60 s (`ffprobe`).
- [ ] Corner logo on every screen recording, not on the cards; not over captions or titles.
- [ ] Titles readable for at least 3 s; none in the bottom 200 px.
- [ ] Captions match the narration word for word and in time; two lines at most.
- [ ] Narration at -16 LUFS integrated (`ffmpeg -i out/main-draft.mp4 -af ebur128=peak=true
  -f null -`), true peak under -1 dBTP; music (if any) about -24 dB under it, no clipping.
- [ ] No notifications, personal tabs, file paths with personal names, keys, access codes or
  pairing QR codes on screen (the phone's Backend tab is never on camera). `.env` never on
  screen.
- [ ] No spinner or *Thinking...* frame held, no cut-off panel; check `out/main-shots.jpg`.
- [ ] The first and last frames are the cards, not a black frame or a desktop.

## Export and upload

- [ ] A short test export checked first (`clipchamp.md`).
- [ ] The full export watched once from start to end, sound on.
- [ ] The file name: `orphan-parts-main-1080p.mp4`, `orphan-parts-short-1080p.mp4`.
- [ ] Uploaded with the captions file (`main.srt`, `short.srt`) where the platform takes one.
- [ ] No video files committed to the repository (`video/out/` is ignored).
