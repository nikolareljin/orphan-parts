# Android app

The phone is the capture device for the same inventory: a photo of a label read by the backend
and saved privately, and a voice note kept on an item as your words and read back to you. The
backend does the work; the app talks to it and nothing else.

## Built so far

**Backend.** The first page is where the backend is. **Scan to pair** reads the code the web
app shows under *Pair the phone* (at the foot of every page) or the one `./dev phone` prints:
it carries the web app's address (the web app proxies the API, so one address serves both)
and, when the demo is gated and the page is signed in, a session of its own, so the access
code never leaves the server. On that first scan the app claims an access code of its own
with the session (`POST /api/pair/code`): a record like any issued code, labeled `phone` and
the first eight characters of the session's id, good for `PAIR_CODE_DAYS` (30) and never past
the code that paired it. The session ends on its own; the phone's code then opens a new one,
with no second scan. The Backend tab names the code by its label and expiry, never the code
itself, and `./dev keys revoke "phone …"` on the server cuts that phone off. A code scanned
from a page that is not signed in carries the address alone: the phone is the demo visitor
there (recorded answers, nothing kept) until it scans a signed-in page. The address and the
code can also be typed. **Check** reads `/readyz` and says whether the backend answers, which
Model API mode it is in and whether the gate is on, then which code opens it. What is kept
stays in the app's private storage.

**Capture.** One session per thing: photos through the system camera app (so the app asks for
no camera permission; four per capture), a clip of at most 30 seconds through the same app,
hold to talk for what you know, a name and a line, then **Send**. Each photo is decoded, scaled
to at most 1600 pixels on the long side and re-encoded as a JPEG on the phone, so nothing but
pixels leaves it; the clip is sent as recorded. The bundle goes to `/api/captures` and waits
in the web app's Inbox; **Captures** lists what was sent, and **Read it now** has the backend
read it into an item (the label found first, the note kept as your words). See
[Capture from the phone](capture.md). For a feature to measure, the hint says what the web
page needs: a ruler in the same plane, straight on; the marking stays on the web.

**Talk.** For an item already in the inventory: hold the button and say what you know about
it. The phone records 16 kHz mono PCM and sends it as a WAV file to `/api/items/{id}/voice`;
the backend transcribes it with Muse Voice Transcribe and keeps it as your words on the item.
The transcript comes back on screen and is read aloud with the phone's own speech, so you hear
what was kept. The item is the one a capture was read into, or any other from the inventory.

**The look.** The app draws itself in the web app's colors: the same seven tones in light
and dark (the page, the text, the muted text, the cards, the hairlines, the accent and the
error tone), following the phone's dark mode as the web app follows the browser's; the header
with the mark and the name, the pages as tabs underlined by the accent, bordered panels, one
scale of buttons (filled for the action, outlined for the rest), pills for status, and the
service line at the foot saying where the backend is and whether it answers with recorded
answers or the live models. A unit test keeps the palette equal to the web app's stylesheet.

## Installing the released app

The release page carries `orphan-parts-<version>.apk`; [On your phone in ten
minutes](../start/judges.md) is the path for a phone with no development setup (download on the
phone, or `scripts/phone-install.sh` / `scripts/phone-install.ps1` over USB, which bring their
own `adb`). The app runs on Android 8.0 and newer; the QR scanner needs Google Play services,
the typed address works everywhere. On Windows the development path below runs in WSL; the
install scripts run natively.

## Building and running it

```bash
./dev setup --android    # a JDK and the Android command-line tools, installed when missing
./dev phone              # build, install on the connected phone, launch, print the pairing code
./dev phone --release    # the same with the release build
./dev android test       # the unit tests, on the JVM
./dev android build      # the debug APK
./dev android install    # onto the connected phone (USB debugging on) or the running emulator
./dev android smoke      # install, launch, confirm the app is on screen, keep a screenshot
./dev android release    # the release APK, with the release key when one is given
```

`./dev setup --check` says what is missing without installing; `./dev setup --android`
installs a JDK 17 (apt or Homebrew) and the Android command-line tools from Google's archive,
their checksum checked, with `platform-tools`, `platforms;android-35` and
`build-tools;35.0.0`, under `ANDROID_HOME` (default `~/Android/Sdk`). On Windows, use WSL.
`./dev phone` prints the pairing code with this machine's first network address; `LAN_ADDRESS`
in the shell or `.env` overrides it (a VPN or a bridge can come first; under WSL the phone needs
the Windows host's address, with the port forwarded). A phone that has not yet accepted this computer is said as such: unlock it and accept the
USB debugging prompt. The build needs a JDK 17 or 21 (Gradle 8.13 refuses a newer one) and the Android SDK
(`ANDROID_HOME`, or `~/Android/Sdk`);
`ANDROID_AVD=<name>` lets the smoke run boot a headless emulator when no phone is connected.
The release APK is signed with the release key when `KEYSTORE_PATH`, `KEYSTORE_PASSWORD`,
`KEY_ALIAS` and `KEY_PASSWORD` are set (or `android/keystore.properties`, which is ignored by
git), and with the debug key otherwise: that one installs on a phone but is not for a store.
The version is the repository's `VERSION`; each release attaches `orphan-parts-<version>.apk`.

The app allows plain HTTP, because the dev stack on a home network answers that way; the
demo host answers over HTTPS.

The launcher icon is rendered from `docs/assets/logo.svg`: `scripts/app-icon.sh` (Inkscape
required) writes the adaptive icon's foreground and the legacy icons for every density under
`android/app/src/main/res/mipmap-*/`, and the web header's mark (`frontend/public/brand.svg`,
the same crop); run it again after a change to the logo.

## Allow the phone

`./dev phone` installs over USB, which the phone has to allow once:

1. On the phone, open **Settings**, then **About phone** (on some phones **About phone**, then
   **Software information**), and tap **Build number** seven times; the phone says you are now
   a developer.
2. Back in **Settings**, open **Developer options** (under **System** on some phones) and turn
   on **USB debugging**.
3. Connect the phone with a cable that carries data (some only charge). On the phone, choose
   **File transfer** if it asks what the connection is for.
4. The phone shows **Allow USB debugging?** with this computer's key: tick **Always allow
   from this computer** and tap **Allow**. Until then `./dev phone` says the phone has not
   allowed this computer and stops.
5. If the phone asks to allow installing apps over USB (some makers add this under Developer
   options as **Install via USB**), allow that too.

With several phones connected, `./dev phone` lists them and asks which one; `ANDROID_SERIAL`
picks one without asking. The emulator is a device like any other once it is running.

## Not yet

A calibrated capture marked on the phone, a spoken question answered from the inventory, and
the store listing are under [Next steps](../project/next.md).
