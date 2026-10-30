# Capture from the phone

The phone is where a thing gets photographed and where a person says what they know about it
while holding it. A capture is what the phone sends in one go: photos, a short clip, a spoken
note and a line of text. The backend keeps it, and reads it into an item when asked.

## On the phone

The **Capture** tab is one session: **Take a photo** as many times as needed (four go in one
capture; the next capture takes more), **Record a clip** through the phone's camera app (30
seconds at most), **Hold to talk** for what you know (what it is, what is wrong, what you
tested), a name if you know it, a line, then **Send**. Photos are re-encoded on the phone
before they leave it, pixels only; the clip is sent as recorded. **Captures** lists what was
sent and whether the backend has read it: **Read it now** asks for that, and a capture that
could not be read says why and can be tried again.

## In the Inbox

The web app's **Inbox** shows every capture newest first: the thumbnails, the clip to play,
the note to hear, the line, the status. **Read it** turns a capture into an item: the photos
go through the same reading as the web form (the label found first by SAM 3.1, the fields read
by Muse Spark, every value marked as observed and waiting for you to confirm), the note is
transcribed by Muse Voice Transcribe and kept on the item as your words, the line becomes the
item's notes, and a clip is noted as having come with it. The capture's photos pass to the
item, shown above its values. **Open item** goes to the inventory. **Delete** removes the
capture and its files; an item made from it stays, photos included.

## What is kept

Everything a capture holds stays under `DATA_DIR/captures/<id>/` on the backend, private,
until the capture is deleted: the photos (re-encoded on arrival, no metadata), the clip as
sent (a clip keeps whatever metadata the phone wrote into it), the note. Reading a capture
sends the photos and the note to the Meta Model API; the clip is sent nowhere.

## From the API

```bash
curl -s -X POST localhost:8000/api/captures -F photos=@label.jpg -F audio=@note.wav \
  -F 'request={"note": "the old adapter from the drawer", "find_label": true}'
curl -s -X POST localhost:8000/api/captures/1/process
curl -s localhost:8000/api/captures
```

## Not yet

A frame picked from the clip for reading, and the next-steps questions after a capture is
read (what to do with it, what to build), are on the [roadmap](../project/roadmap.md).
