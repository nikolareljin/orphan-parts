# Android app

The phone is the capture device for the same inventory: a photo of a label read by the backend
and saved privately, and a voice note kept on an item as your words and read back to you. The
backend does the work; the app talks to it and nothing else.

## Built so far

**Backend.** The first page asks where the backend is (the dev stack on your network, say
`http://192.168.1.20:8000`, or the demo host) and, when the demo is gated, the access code.
**Check** reads `/readyz` and says whether the backend answers, which Model API mode it is in
and whether the gate is on. Both values stay in the app's private storage on the phone. The
session the code opens is kept in memory and opened again after a 401.

**Capture.** A photo through the system camera app, so the app asks for no camera permission.
The photo is decoded, scaled to at most 1600 pixels on the long side and re-encoded as a JPEG
on the phone, so nothing but pixels leaves it. **Read it** sends it to `/api/extract` and shows
the fields with their confidence and source; **Save privately** posts the reading to
`/api/items` with a name and your line on the condition. Every value saved this way is an
observation to confirm on the web, as with any reading. For a feature to measure, the hint
says what the web page needs: a ruler in the same plane, straight on; the marking stays on
the web.

**Talk.** Hold the button and say what you know about the item: what it is, what is wrong
with it, what you tested. The phone records 16 kHz mono PCM and sends it as a WAV file to
`/api/items/{id}/voice`; the backend transcribes it with Muse Voice Transcribe and keeps it as
your words on the item. The transcript comes back on screen and is read aloud with the
phone's own speech, so you hear what was kept. The item is the one just captured, or any
other from the inventory.

## Building and running it

```bash
./dev android test       # the unit tests, on the JVM
./dev android build      # the debug APK
./dev android install    # onto the connected phone (USB debugging on) or the running emulator
./dev android smoke      # install, launch, confirm the app is on screen, keep a screenshot
./dev android release    # the release APK, with the release key when one is given
```

The build needs a JDK 17 or 21 (Gradle 8.13 refuses a newer one) and the Android SDK (`ANDROID_HOME`, or `~/Android/Sdk`);
`ANDROID_AVD=<name>` lets the smoke run boot a headless emulator when no phone is connected.
The release APK is signed with the release key when `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`,
`KEY_ALIAS` and `KEY_PASSWORD` are set (or `android/keystore.properties`, which is ignored by
git), and with the debug key otherwise: that one installs on a phone but is not for a store.
The version is the repository's `VERSION`; each release attaches `orphan-parts-<version>.apk`.

The app allows plain HTTP, because the dev stack on a home network answers that way; the
demo host answers over HTTPS.

## Not yet

A calibrated capture marked on the phone, a spoken question answered from the inventory, and
the store listing are on the [roadmap](../project/roadmap.md).
