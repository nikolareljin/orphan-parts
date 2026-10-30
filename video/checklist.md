# Final export checklist

Tick every line before uploading.

## Content and claims

- [ ] Every scene shown as working is in the app on `main` (`readiness.md`, *Capabilities*).
- [ ] S15 to S18 carry the *Concept preview, not built* badge for their whole duration.
- [ ] The donor-appliance and other-device routes appear only with `t07-routes`.
- [ ] Story B scenes recorded in fixture mode carry `t08-story-b` (*recorded demo answers*).
- [ ] Sample listings and typed values carry `t06-sample-values` or `t18-candidates`.
- [ ] No price, saving, compatibility or completion claim that the app did not show on screen.
- [ ] No Marketplace page, no Meta or Facebook logo, no other people's listings or faces.
- [ ] Marketplace is described only as a search the owner runs and a create page he fills.
- [ ] Meta's models named as implemented: Muse Spark, SAM 3.1, Muse Voice Transcribe.
  Baseten and Fireworks only as *planned*, on the models card.
- [ ] The mixer: no model number, part name or fit stated unless the label photo and the
  measurement in the video show it. No 3D-printed food-contact or rotating part suggested.
- [ ] S06 shows the mixer's own label values, read live, not the recorded adapter answer.
- [ ] The hosted demo is not named as live unless it is on the day of upload.
- [ ] A Runway clip, if any, carries its label; music, if any, is in `assets.md`.

## Picture and sound

- [ ] 1920x1080, 30 fps, H.264, AAC.
- [ ] Main video under 3:00 (target 2:50); short video 45 to 60 s.
- [ ] Corner logo on every screen recording, not on the cards; not over captions or titles.
- [ ] Titles readable for at least 3 s; none in the bottom 200 px.
- [ ] Captions match the narration word for word and in time; two lines at most.
- [ ] Narration peaks around -6 dB, music (if any) about -24 dB under it, no clipping.
- [ ] No notifications, personal tabs, file paths with personal names, keys or access codes
  on screen. `.env` never on screen.
- [ ] The first and last frames are the cards, not a black frame or a desktop.

## Export and upload

- [ ] A short test export checked first (`clipchamp.md`).
- [ ] The full export watched once from start to end, sound on.
- [ ] The file name: `orphan-parts-main-1080p.mp4`, `orphan-parts-short-1080p.mp4`.
- [ ] Uploaded with the captions file (`main.srt`, `short.srt`) where the platform takes one.
- [ ] No video files committed to the repository (`video/out/` is ignored).
