# Orphan Parts Lens on your phone, in ten minutes

This page is for judges and anyone trying the app for the first time. It gets the Android app
onto your phone and connects it to the hosted server with the code you were given. Nothing
here needs a development setup; a computer is optional.

## 1. What you need

- **An Android phone from 2020 or newer.** The app runs on Android 8.0 (2017) and every
  version after it. Pairing by QR code uses Google's code scanner, so it needs a phone with
  Google Play services (every Samsung, Pixel, OnePlus, Motorola, Xiaomi and Sony sold outside
  China). A phone without Play services installs and runs the app the same way; it types the
  address instead of scanning, as step 4 says.
- **The access code** you were given (the submission carries it; it is never in this
  repository). Without a code the server is the recorded demo: everything shows, nothing of
  yours is kept.
- **The hosted site:** `https://orphan-parts.pages.dev`. No computer is needed for it.
- Optional: a computer with a USB cable, for path B in step 3.

## 2. Install the app from the phone (no computer)

<img src="https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/docs/assets/apk-qr.svg" alt="QR code that opens the newest release's APK" width="160">

The app is not on Google Play: its Play listing was started and not finished within the
hackathon window, so the APK comes from this repository's releases. The QR code, shown on
another screen and scanned with the phone's camera, opens
`https://github.com/nikolareljin/orphan-parts/releases/latest/download/orphan-parts.apk`, the
newest release's APK; the same link opened in the phone's browser downloads it too. Either
way, continue at item 3 of the list below (open the download). The release page is the other
way to the same file:

1. On the phone, open `https://github.com/nikolareljin/orphan-parts/releases/latest` in the
   browser.
2. Under **Assets**, tap `orphan-parts-<version>.apk`. The download starts; the file is
   about 8 MB.
3. Open the download (the notification, or the browser's Downloads page). The APK is signed
   with the build's own development key, not a Google Play key, so Android treats it as an
   app from an unknown source and asks before installing: on the prompt tap **Settings**,
   turn on **Allow from this source** for the browser, go back. On Android 8 and newer that
   permission is given per app, under **Settings**, **Apps**, **Special app access**,
   **Install unknown apps** (the menu names vary a little by maker); on older phones it is
   one switch, **Settings**, **Security**, **Unknown sources**.
4. Tap **Install**. If Play Protect says the app is from an unknown developer, tap **More
   details**, then **Install anyway**. The warning means the key is not a store's, which is
   so for every app installed outside Google Play.
5. Tap **Open**. The app opens on its **Backend** tab.
6. Check the install with Google Play Protect: open the **Google Play Store** app, tap the
   profile icon at the top right, tap **Play Protect**, then **Scan**. The scan goes over
   every installed app, this one included, and reports any harm it finds; for this app it
   should report none. The permission from item 3 can then be turned off again: **Settings**,
   **Apps**, **Special app access**, **Install unknown apps**, the browser, **Allow from this
   source** off. Go to step 4.

## 3. Install from a computer (optional, path B)

Only if you prefer a cable, or the phone's browser refuses the download. First the phone:

1. **Settings, About phone** (on Samsung: **About phone, Software information**), tap
   **Build number** seven times until it says you are a developer.
2. Back in **Settings**, open **Developer options** (under **System** on some phones) and turn
   on **USB debugging**.
3. Plug the phone into the computer with a cable that carries data. If the phone asks what
   the connection is for, choose **File transfer**.
4. When the phone shows **Allow USB debugging?**, tick **Always allow from this computer**
   and tap **Allow**.

Then one command on the computer. It downloads Google's `platform-tools` (about 10 MB) when
`adb` is not installed, downloads the latest release's APK, installs it and opens the app. No
Java, no Android SDK, no Docker.

- **macOS, Linux, or WSL on Windows:**

  ```bash
  curl -fsSL https://raw.githubusercontent.com/nikolareljin/orphan-parts/main/scripts/phone-install.sh | bash
  ```

  From a clone of the repository: `bash scripts/phone-install.sh`.

- **Windows, in PowerShell** (from a clone, or after downloading the script):

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1
  ```

  If Windows does not see the phone at all, install the phone maker's USB driver (Samsung
  Smart Switch, Google USB Driver, and so on) and run the command again.

`--version 0.3.0` (`-Version 0.3.0` on Windows) picks a release; `--apk file.apk` (`-Apk`)
installs a file you already have.

## 4. Connect the phone to the server with your code

The pairing code never carries your access code; it carries the server's address and, once
you are signed in, a pairing the server made for the phone, good for fifteen minutes. With it
the app claims an access code of its own, which it keeps. Every screen of this step, pictured:
[Pair the phone with the web app](https://nikolareljin.github.io/orphan-parts/start/pairing/).

1. On the phone's browser or on a laptop, open `https://orphan-parts.pages.dev`.
2. Tap **Sign in with the code** in the header, enter the code, **Enter**. The header line
   now says you are through the door. **Sign out**, in the same place, ends the session in
   this browser; closing the tab ends the hosted one as well.
3. Scroll to the foot of the page and open **Pair the phone**. A QR code is there.
4. In the app, on the **Backend** tab, tap **Scan to pair** and point the camera at the QR
   code (on a laptop screen, or on the phone's own screenshot opened on another device). The
   app says **Paired with https://….modal.run; this phone now has a code of its own (phone …,
   until …)**.
5. Tap **Check**. It should say **Backend ok, Model API live for the code, recorded otherwise,
   demo gated. The phone's own code (phone …, until …) opens it.**

**Without Google Play services, or without a second screen:** under the QR code the page
shows the address to type. On the **Backend** tab type it into **Backend URL**
(`https://….modal.run`), type your access code into the second field, tap **Save**, then
**Check**. The answer should end with **The code opens it.**

The phone's own code lasts thirty days, or until the code you were given ends if that is
sooner, so the phone stays through the gate with no second scan. Scanning the code on a page
that is not signed in pairs the phone as the demo (recorded answers, nothing kept): sign in
first.

When you are done testing, **Unpair** on the **Backend** tab releases the phone: it forgets the address, its code and its session; the code itself is revoked on the server with `./dev keys revoke "phone …"`.

## 5. Connect to a local server instead (alternative)

If you would rather run everything on your own computer (Docker Desktop on macOS or Windows,
Docker Engine on Linux; on Windows run these in WSL):

```bash
git clone https://github.com/nikolareljin/orphan-parts.git
cd orphan-parts
cp .env.example .env          # put MODEL_API_KEY=... in it, or leave OPL_FAKE_API=1 for recorded answers
./dev up                      # the web app on http://localhost:5173, the API on :8000
```

To try the gate on your own machine (the code, the sign-in, a code for the phone), `./dev gate
on` prints an access code for you and one for the phone; `./dev gate off` turns it off again.

Open the web app at your computer's network address, for example `http://192.168.1.20:5173`
(the page at `localhost` explains why it shows no pairing code: on the phone, localhost is the
phone), and pair from its footer as in step 4. The phone and the computer must be on the same
network. With the Android tools installed (`./dev setup --android`), `./dev phone` builds the
app, installs it over USB and prints the pairing code in the terminal.

## 6. Use it

- **Capture tab:** take photos of the item and its label (the label fills the frame), a short
  clip if it moves or makes a sound, hold to talk and say what you know, a name, **Send**.
- **On the site, Inbox:** the capture is there. **Read** turns it into an item: the label
  read into values you confirm one by one, your words kept as yours, the photos beside the
  values.
- **My inventory:** confirm or reject each value, measure a feature against a ruler, ask
  **Does it fit?**, prepare a listing, ask what it is worth, build something from what you
  have. At the end of the item, **Draw it** shows what the item could look like as what you type
  (a picture, labeled as drawn, only when that server has pictures on).

- **Decide**, on the item below its values: what it is, what it is worth, what it is good for
  (**Ask for ideas**), what would complete it; then **Keep and build**, **Sell**, **Give
  away** or **Not worth it**, with a note the item keeps.
- **From a laptop instead of the phone:** the Inbox's **Send a capture** form takes photos
  and a short video (MP4 or 3GP) straight from the computer.
- **Talk tab:** for an item already in the inventory, hold and say what you know; the
  transcript is kept as your words.

What is kept: your items, photos, clips and notes, privately, on the server you paired with,
until you delete them; nothing is published or posted anywhere. The details are in
[Privacy](https://nikolareljin.github.io/orphan-parts/operations/privacy/).

## 7. If it does not work

| What you see | What to do |
|---|---|
| The browser will not open the APK, or "blocked by your admin" | Use the browser's Downloads page; or path B in step 3 |
| "App not installed" | An earlier release is on the phone: each release is signed with a fresh development key, and Android refuses an update under another key. Uninstall it (**Settings**, **Apps**, **Orphan Parts Lens**, **Uninstall**), then install again |
| Play Protect: "unsafe app blocked" or "unknown developer" | **More details**, **Install anyway**; the app carries a development key, not a Google Play key, as every app installed outside the store does. A Play Protect scan afterwards (step 2, item 6) checks it |
| `phone-install`: "the phone has not allowed this computer" | Unlock the phone, tick **Always allow**, tap **Allow** on its prompt, run again |
| `phone-install`: "no phone found" | A cable that carries data; **USB debugging** on; **File transfer** chosen; on Windows the maker's USB driver |
| The app: "that code points at localhost" | The site was opened at `localhost`; open it at the computer's network address, or use the hosted site |
| **Check**: "Not reachable" | The phone is off the network the server is on, or the address has a typo; the hosted address is `https://`, a local one `http://…:5173` |
| **Check**: "The code is refused" | The code was typed wrong or has expired; ask for a new one |
| "This phone's code has ended or was revoked; scan the code on a signed-in page" | The code you were given has ended or was revoked, or the phone's own was; the app has cleared it from the Backend tab: sign in on the site with a current code and scan its pairing code again |
| After a scan: "no code of its own: the pairing has ended" | The pairing's minutes ran out before the claim: reload the signed-in page and scan its new code |
| After a scan: "no code of its own: the code that paired this phone has ended" | The code the page was signed in with has ended or was revoked: sign in again with a current code and scan the new pairing code |
| After a scan: "no code of its own: … does not claim a phone's code" or "… already" | The pairing was spent or did not come from a scan: reload the signed-in page and scan its new code within fifteen minutes |
| After a scan: "no code of its own: a phone's own code does not pair another phone" | The page was signed in with a phone's code: sign in with the code you were given and scan again |
| After a scan: "no code of its own: this code has paired 10 phones already" | Your code has paired as many phones as it may: have one revoked with `./dev keys revoke "phone …"` on the server, or ask for another code |
| After a scan: "no code of its own: too many tries" | The address has used its code attempts: wait the seconds it names and scan again |
| A page says "this visitor's hourly allowance is used" | The demo's per-person limit; wait the minutes it names |
