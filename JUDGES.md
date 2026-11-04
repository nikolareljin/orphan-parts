# Orphan Parts Lens for judges

Orphan Parts Lens turns the things in a drawer into a private inventory with evidence, and
helps decide for each one: keep and fix, reuse in a build, sell or give away, or find the part
it is missing on Facebook Marketplace. **Watch the [demo video](https://www.youtube.com/watch?v=3USMv4zCeD0)
(2:52)**, then run it yourself below.

There is no access code for judges and none is needed: on your own computer every page is open,
and the demo set's recorded answers are in the repository. No Model API key, nothing spent,
nothing leaves the computer.

- **[Part 1: Start it and see results](#part-1-start-it-and-see-results)**, about 10 minutes:
  Docker, one block of commands, a browser.
- **[Part 2: The phone](#part-2-the-phone-optional)** (optional), about 10 minutes: the Android
  app, paired with the web app.
- [If something does not work](#if-something-does-not-work)

## Part 1: Start it and see results

**Step 0. Check Docker.** On macOS and Windows, start **Docker Desktop** first. Then, in a
terminal:

```bash
docker --version && docker compose version && docker run --rm hello-world
```

You should see two version lines and *Hello from Docker!* If not, install Docker:
[Get Docker](https://docs.docker.com/get-docker/) (Docker Desktop on macOS and Windows; Docker
Engine with the Compose plugin on Linux, with your user in the `docker` group). **On Windows**,
use [WSL 2](https://learn.microsoft.com/windows/wsl/install) (Ubuntu) with Docker Desktop's
[WSL integration](https://docs.docker.com/desktop/features/wsl/) turned on, run every command in
the Ubuntu terminal, and clone into the WSL home directory (not under `/mnt/c`). You also need
`git`, about 5 GB of free disk, and ports 5173 and 8000 free.

**Step 1. Start it.** Copy and paste the whole block; nothing in `.env` needs editing:

```bash
git clone https://github.com/nikolareljin/orphan-parts.git
cd orphan-parts
cp .env.example .env
./dev up
./dev demo
```

You should see `./dev up` say *starting in fixture mode (recorded answers, no credits)* and end
with `[ok] web  http://localhost:5173`; the first run builds the backend image and installs the
web app's packages, a few minutes. Then `./dev demo` (about a minute) ends with
`[ok] demo set loaded`: 49 items, 9 searches and 11 projects, with everything the models
produced for them.

**Step 2. Open <http://localhost:5173>.** You should see **Open server (no code needed)** at
the right of the header, and *recorded answers only (nothing spent)* at the foot of the page.
The page opens on **Read a label**; the **?** beside each section explains what it does.

**Step 3. See the results in two minutes.** Click, in this order:

1. **My inventory**, then **Open** on **Dell U2419H monitor, 24 inch** (the last row: scroll
   down). The item opens with its tabs. **Decide**: the three cards Muse Spark wrote (*Keep and
   fix*, *Reuse it*, *Sell or give away*), the one it recommends, the plan chosen, and the
   picture Muse Image drew for the reuse idea, captioned as drawn. **Facts**: every value beside
   its photo, with where it came from. Close the item (**×** or **Esc**).
2. **Open** on **EVGA GeForce 9500 GT graphics card**. **Sell or give away**: the whole
   Marketplace listing (title, price, category, condition, description, tags, photo order and
   the checklist). **Value**: the price guidance, its four figures kept apart (asking, sold,
   reported by you, the model's estimate), each with its page and date.
3. **Build and reuse**: eleven projects proposed from what the inventory holds. **Open** on
   **Family photo NAS from the ASRock board** (*selected: items committed*): the items it uses
   and why they fit, what is still missing, three drawings, and the build pack. The two other
   selected ones are **Gaming coffee table shell** and **Smart desk calendar with clock and
   buzzer**.
4. **Find a part**: **Open** on **all-metal agitator rod for the frappé maker** (the last row):
   the search plan (phrasings, each a Marketplace link), four candidates with the questions to
   ask each seller, and the maker's part (OEM 990010200) that **Search the web** found, with its
   link.

More to look at, when you have time: **Read a label** with the SAM 3.1 regions, and measuring a
feature from a photo, in [More of the tour](#more-of-the-tour).

**Step 4. Stop it** when you are done (after Part 2, if you try the phone): `./dev down` (what you saved stays; `./dev down -v` also removes the data).
`./dev demo` puts the demo set back as loaded, whatever you clicked.

### Recorded answers, and requests with none

Everything Part 1 shows was saved from real model calls when the demo set was recorded; each
carries a *recorded answer* badge and costs nothing. A stack without a key never calls a model:

- **Plan the search**, **Search the web** and the price guidance come back as recorded.
- A request with no recording of its own (**Ask again** under **Decide**, **Check fit** on a new
  listing, a photo of your own) is refused and nothing is saved: the page says *No recorded
  answer for this request: the demo answers only what was recorded. Add a Meta Model API key in
  .env (MODEL_API_KEY, OPL_FAKE_API=0) to run it live.* The recorded results stay as they were.
- **Draw it** is off without a key (*Pictures are off on this server.*); the drawings already
  made stay. **Propose** says the same *No recorded answer* line; the eleven recorded projects
  stay.

## Part 2: The phone (optional)

The Android app (Android 8.0 or newer) takes photos, a short video and a voice note, and sends
them to the web app's **Inbox** over the Wi-Fi. Start with Part 1's stack up.

### 2.1 Sign in on the web app, at the computer's network address

**Turn the sign-in on.** In the `orphan-parts` folder:

```bash
./dev gate on
```

It writes a master access code into `.env` (`DEMO_ACCESS_CODE`, git-ignored), restarts the
backend with it (no other restart needed; the web app keeps running), issues a second code for
the phone, and prints both:

```text
access code (the master, for you):     <24 letters and digits>
issued code (for phone, 7 days):    opl_<…>
```

`./dev gate show` prints the master again; `./dev gate off` turns the sign-in off. (You can skip
this step: on an open server the phone pairs with the address alone, no code.)

**Find the computer's address on the Wi-Fi**; on the phone, `localhost` is the phone itself:

| On | Run | Use |
|---|---|---|
| macOS | `ipconfig getifaddr en0` | the line it prints, such as `192.168.1.20` |
| Linux | `hostname -I` | the first address |
| Windows (WSL included) | `ipconfig` in PowerShell | the Wi-Fi adapter's *IPv4 Address*; Docker Desktop serves port 5173 on Windows itself, so not the WSL address |

**Open the web app at that address** on the computer, such as `http://192.168.1.20:5173` (the
web app listens on the network, not only on `localhost`). Click **Sign in with the code** at the
top right, type the master code, press **Enter**. The header now shows **Sign out**.

The phone must be on the **same Wi-Fi**. If the phone cannot reach the address later, allow port
5173 through the computer's firewall for private networks (see
[If something does not work](#if-something-does-not-work)).

### 2.2 Install the app

**Option A: over USB from the computer (most likely).** Once per phone (names are Samsung's;
other makers differ a little):

1. **Settings**, **About phone**, **Software information** (on Pixel and most others, **About
   phone** directly), tap **Build number** seven times. The phone asks for its PIN, then says
   *Developer mode has been turned on*.
2. **Settings**, **Developer options** (at the bottom; on Pixel under **System**), turn on
   **USB debugging**.
3. Samsung with One UI 6 or newer: **Settings**, **Security and privacy**, **Auto Blocker**
   off. While it is on, it blocks installs over USB.
4. Plug in a cable that carries data; choose **File transfer** if asked. On **Allow USB
   debugging?** (the computer's RSA key fingerprint), tick **Always allow from this computer**
   and tap **Allow**.

Then, in the `orphan-parts` folder:

```bash
bash scripts/phone-install.sh                                        # macOS, Linux, WSL
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1   # Windows, in PowerShell
```

It uses `adb` if you have it, or downloads Google's platform-tools (about 10 MB, into
`~/.orphan-parts`); downloads the latest release's APK; installs it on the phone and opens the
app. No Java, Android SDK or Docker needed. You should see it end with *done. In the app, open
the Backend tab and tap 'Scan to pair'*. On Windows, if no phone is found, install the maker's
USB driver (Samsung Smart Switch, Google USB Driver) and run it again.

**Option B: on the phone only.** Open this link in the phone's browser, or scan the QR code with
its camera:
<https://github.com/nikolareljin/orphan-parts/releases/latest/download/orphan-parts.apk>

<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/apk-qr.svg" alt="QR code that opens the newest release's APK" width="140">

1. Open the download (about 8 MB). Android asks before installing an app from outside Google
   Play: tap **Settings**, turn on **Allow from this source** for the browser, go back, tap
   **Install**.
2. If Play Protect warns about an unknown developer: **More details**, **Install anyway**. The
   APK is signed with the build's own key, not a Google Play key.
3. Tap **Open**. Afterwards you can turn **Allow from this source** off again (**Settings**,
   **Apps**, **Special app access**, **Install unknown apps**) and scan with Play Protect
   (**Play Store**, profile icon, **Play Protect**, **Scan**).

Either way the app opens on its **Backend** tab.

### 2.3 Pair the phone

1. On the computer, on the signed-in web app at the network address, open **Pair the phone** at
   the foot of the page. A QR code appears, with *Or type http://…:5173 into the app.* under it.
2. In the app, **Backend** tab, tap **Scan to pair** and point the camera at the QR code. The
   phone gets an access code of its own from it (never yours); the QR code is good for fifteen
   minutes, so keep it off screen shares.
3. Tap **Check**. You should see *Backend ok, Model API fixture, demo gated. The phone's own
   code (…) opens it.* (typed by hand: *… The code opens it.*)

**No camera scanner (no Google Play services) or no second screen:** on the **Backend** tab,
type the address from under the QR code into **Backend URL** and the phone code `./dev gate on`
printed into the **Access code** field, tap **Save**, then **Check**.

Every screen, pictured: [Pair the phone with the web app](https://nikolareljin.github.io/orphan-parts/start/pairing/).

### 2.4 First capture

1. In the app, **Capture** tab: **Take a photo** (the label filling the frame), optionally a
   name, then **Send**. You should see *Sent as capture #1*.
2. On the web app, **Inbox**: the capture is listed. **Read it** turns it into an item.
3. Without a key, a new photo has no recorded answer: **Read it** says *No recorded answer for
   this request* and no item is made (see
   [Recorded answers, and requests with none](#recorded-answers-and-requests-with-none)); the
   demo items show what the models produced. To read your own photos live, see
   [Your own key](#optional-live-models-with-your-own-key).

The app's **Talk** tab keeps a voice note on an item already in the inventory. From a laptop
instead of the phone, the Inbox's **Send a capture from this computer** takes photos and a
short video.

## If something does not work

| What you see | What to do |
|---|---|
| `docker is not running`, or `hello-world` fails | Start Docker Desktop (Linux: `sudo systemctl start docker`), wait until it says it is running, try again |
| `ports in use` / `free the ports above` | Something else listens on 5173 or 8000: stop it, or `FRONTEND_PORT=5174 BACKEND_PORT=8001 ./dev up` (then use port 5174 everywhere below) |
| The footer says *Cannot reach the server* | The backend is still starting or failed: wait a moment, or `./dev logs backend` |
| The app: *that code points at localhost* | The web app was opened at `localhost`: open it at the computer's network address (2.1), sign in there, scan again |
| **Check**: *Not reachable* | The phone is on another network (guest Wi-Fi, mobile data); the address has a typo (it is `http://…:5173`); or the firewall blocks port 5173: allow it for private networks (Windows: tick **Private networks** when Windows Defender Firewall asks about Docker; Linux with ufw: `sudo ufw allow 5173/tcp`) |
| WSL with Docker Engine inside WSL (not Docker Desktop) | The phone cannot reach the WSL address: forward the port from Windows, `netsh interface portproxy add v4tov4 listenport=5173 connectport=5173 connectaddress=<WSL address>`, and use the Windows Wi-Fi address |
| **Check**: *The code is refused* | The code was mistyped or has ended: `./dev gate on` issues a fresh phone code |
| After a scan: *no code of its own: the pairing has ended* | The fifteen minutes ran out: reload the signed-in page and scan the new QR code |
| `phone-install`: *no phone found* | A cable that carries data; **USB debugging** on; **File transfer** chosen; on Windows the maker's USB driver |
| `phone-install`: *the phone has not allowed this computer* (`adb devices` says *unauthorized*) | Unlock the phone and answer **Allow USB debugging?** with **Always allow**; if it never shows, **Developer options**, **Revoke USB debugging authorizations**, unplug and plug in again |
| The USB install fails on a Samsung phone | **Auto Blocker** is on: **Settings**, **Security and privacy**, **Auto Blocker**, off |
| Play Protect: *unsafe app blocked* or *unknown developer* | **More details**, **Install anyway** |
| The browser will not open the APK, or *blocked by your admin* | Open it from the browser's Downloads page, or use Option A (USB) |
| *App not installed* | An earlier release is on the phone under another key: uninstall it (**Settings**, **Apps**, **Orphan Parts Lens**, **Uninstall**) and install again |
| The QR code will not scan | Type the address under it into **Backend URL** and the phone code into **Access code**, **Save**, **Check** |
| A photo of your own says *No recorded answer for this request* | The stack has no key: see [Your own key](#optional-live-models-with-your-own-key) |

More of the app's own messages: [Pair the phone with the web app](https://nikolareljin.github.io/orphan-parts/start/pairing/)
and [Troubleshooting](https://nikolareljin.github.io/orphan-parts/operations/troubleshooting/).

## More of the tour

- **Read a label**, with the SAM 3.1 regions: on an open stack this page is the upload form; the
  sample gallery is what a signed-out visitor sees. With `./dev gate on`, reload and stay signed
  out (or **Sign out**). Tick a photo, leave *Find the label in the photo first* on, press **Read
  the label**: each reading shows the regions SAM 3.1 found (and a note for each of item, label
  and connector it did not), then every value Muse Spark read with its unit, confidence, source
  and the text as printed.
- **Measure a feature**, in an item's **Measure and fit**: marks a ruler and a feature on one
  of the set's photos and computes the dimension, with its uncertainty, with no model call.
- **Dell U2419H**, **Picture** tab: the drawings kept for the item.

## The hosted demo, read-only, while it is up

<https://orphan-parts.pages.dev>: nothing to install, and it may be taken down after judging.
Without a code it is the visitor view of the same demo set, read-only: buttons that would save,
ask again, draw, plan or search show *Sign in with the access code to use this.*; nothing is
saved and nothing is spent. The foot of the page says *Demo: recorded answers only*.

## Optional: live models with your own key

Not needed to review it. Get a key at <https://dev.meta.ai> (**Billing**: a payment method;
**API keys**: create one), set `MODEL_API_KEY=<your key>` and `OPL_FAKE_API=0` in `.env`
(`PICTURE_ENABLED=1` for drawings), and run `./dev up` again. Each call is charged to your key;
`SPEND_CAP_USD` in `.env` (25 by default) stops every model call once that much has been spent
through the stack.

## What to look for

**What the models produced**, from the demo set, more on
[Examples](https://nikolareljin.github.io/orphan-parts/start/examples/):

<p>
<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/shots/examples/02-arcade-drawings.png" alt="The gaming coffee table drawn three times by Muse Image" width="49%">
<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/shots/examples/02-nas-drawings.png" alt="The family photo NAS drawn three times by Muse Image" width="49%">
<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/shots/examples/60-visitor-decide-build.png" alt="The Decide cards Muse Spark wrote for the Dell U2419H monitor, the reuse card with its Muse Image picture" width="49%">
<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/shots/examples/20-9500gt-value.png" alt="Muse Spark's price guidance for the EVGA 9500 GT, the four figures kept apart" width="49%">
</p>

**Meta models, each with one job.**

| Model | Where you see it |
|---|---|
| Muse Spark | reads a label into typed values with a confidence each; finds the private details on each photo (product keys, MAC addresses, serials, passwords, QR codes) for the shared copies to black out; writes the decision cards, the reuse ideas, the Marketplace draft, the search plan and the build proposals; reads a listing brought back; searches the web for price guidance with citations |
| SAM 3.1 | finds the item, the label and the connector in a photo, so the label crop is what gets read |
| Muse Image | **Draw it**: what an item could become or a finished project, on a click only, always captioned as drawn and never used as evidence |
| Muse Voice Transcribe | a voice note from the phone, kept on the item as the owner's words |

Model IDs and request shapes: [Meta models](https://nikolareljin.github.io/orphan-parts/models/).

**The rules decide, the model proposes.**

- Every value carries its source (a photo, a label crop, a measurement, a listing, the owner)
  and stays *to confirm* until accepted.
- **Does it fit?** ends in one verdict from a five-step
  [ladder](https://nikolareljin.github.io/orphan-parts/concepts/verdicts/) decided by the
  category's rules, never by the model. An unknown is never a pass; it becomes a question for
  the seller.
- A measurement is geometry from marks on a photo with a ruler, with its uncertainty; a blurred,
  oblique or unreferenced capture is refused with the reason.
- A draft line that rests on nothing confirmed is dropped and listed; faults and what was not
  tested are always disclosed; a serial number, MAC address or IMEI never reaches the model.
- Nothing is posted, searched or fetched on Marketplace for you: no public API posts a personal
  listing or searches Marketplace, so the app prepares the fields and the search links and you
  run them.

## Costs and limits

- **On your own computer without a key, nothing is spent**: the Model API is never called.
- **On the hosted demo, nothing is spent either**: a visitor gets the recordings, 20 tries per
  address and hour.
- **With your own key**, each call is charged to it, and `SPEND_CAP_USD` (25 USD by default)
  stops every model call once the stack's ledger reaches it. Rough cost per call: a label read
  $0.003 to $0.008, finding the label $0.0025, a draft, the decision cards or a search plan
  under $0.01, a drawing $0.01, price guidance with web search $0.04 to $0.07, a build proposal
  $0.01 to $0.03.
- Limits: four photos per reading, 12 MB per file, a video of 60 MB, a voice note of ten
  minutes.

## Privacy

Items are private by default; the demo set loads as public. A signed-out visitor never sees
where an item is kept, the owner's notes, voice notes, the lowest acceptable price, private
searches or the Inbox. Photos are re-encoded on arrival with EXIF and GPS dropped; product keys,
MAC addresses, serial numbers, passwords, QR codes and barcodes found on a photo are blacked out
on every shared copy. Issued codes are kept as hashes. Details:
[Privacy](https://nikolareljin.github.io/orphan-parts/operations/privacy/) and
[Private details on photos](https://nikolareljin.github.io/orphan-parts/guides/private-details/).
