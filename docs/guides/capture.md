# Capture from the phone

The phone is where a thing gets photographed and where a person says what they know about it
while holding it. A capture is what the phone sends in one go: photos, a short clip, a spoken
note and a line of text. The backend keeps it, and reads it into an item when asked.

## On the phone

The **Capture** tab is one session: **Take a photo** as many times as needed (four go in one
capture; the next capture takes more), **Record a video** through the phone's camera app (30
seconds at most), **Hold to talk** for what you know (what it is, what is wrong, what you
tested), a name if you know it, a line, then **Send**. Photos are re-encoded on the phone before
they leave it, pixels only; the clip is sent as recorded. **Captures** lists what was
sent and whether the backend has read it: **Read it now** asks for that, and a capture that
could not be read says why and can be tried again.

## From a computer

The Inbox's **Send a capture from this computer** form takes the same bundle the phone
sends: up to `MAX_PHOTOS` photos of the item and its label, one short video (an MP4 or 3GP
file, at most `MAX_CLIP_MB`; a recording from a phone's camera or a laptop's webcam saved as
MP4 is what it takes, a MOV or WebM file is refused by its bytes), a name and a line. What
the form can tell before sending (too many photos, a photo or a video over the limit, a
file that is not MP4) it says at once; the backend's own check answers the rest. The
capture waits in the Inbox like one from the phone. The demo visitor sees no form, only
*Sign in with the access code to use this.* On the phone, **Photos from the gallery** and **A video from the gallery** on
the Capture tab take media already on the phone, re-encoded and checked the same way.

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

## After the capture

The item a capture becomes is like any other: its **Decide** section asks what to do with it
(keep and fix, reuse it, sell or give away; see [Decide what it becomes](decide.md)).

## Not yet

A frame picked from the clip for reading is under [Next steps](../project/next.md).
