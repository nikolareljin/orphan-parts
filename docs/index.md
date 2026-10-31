# Orphan Parts Lens

Scan what you already own. Decide what it can become. Find the missing piece on Marketplace, or
prepare what you no longer need for sale or free pickup. Every answer carries its evidence, on
Meta's Muse models.

**This repository is the entry for the Meta Global AI Developer Hackathon (October 27 to
November 4, 2026).** Everything in it was built during the hackathon; the dated log is on
[Built during the hackathon](project/hackathon.md). One diagram of the whole, every box a
link: [How it fits together](project/flow.md). Trying it on a phone: the
[five steps](#on-a-phone-in-five-steps) below, or the long version,
[On your phone in ten minutes](start/judges.md).

## On a phone in five steps

1. **Install the app** on an Android 8.0 or newer phone. The QR code, scanned with the phone's
   camera, or `https://github.com/nikolareljin/orphan-parts/releases/latest/download/orphan-parts.apk`
   opened on the phone, downloads the newest release's APK.<br>
   <img src="assets/apk-qr.svg" alt="QR code that opens the newest release's APK" width="140"><br>
   Or, on the phone, open the
   [latest release](https://github.com/nikolareljin/orphan-parts/releases/latest) and tap either
   APK. Open the download with installing from the browser allowed (**Allow from this source**);
   if Play Protect warns, **More details**, **Install anyway**. Or over a USB cable, with **USB
   debugging** on in **Developer options**: from a clone, `scripts/phone-install.sh` on the
   computer (on Windows,
   `powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1`), or the one-line
   download in the long version.
2. **Open the web app**: the hosted site, `https://orphan-parts.pages.dev`, when it is
   deployed; or `./dev up` and `http://localhost:5173` on your own computer. To pair a phone
   with a local server, open the site at the computer's network address, not `localhost`
   (for example `http://192.168.1.20:5173`), with the phone on the same network.
3. **Sign in**: **Sign in with the code** in the header, then the access code you were given.
   A local stack has no door until `./dev gate on`, which prints a code for you and one for
   the phone; reload the page, then sign in with yours. Without it, go on to step 4.
4. **Pair the phone**: at the foot of the page, open **Pair the phone** for the QR code. In the
   app, on the **Backend** tab, tap **Scan to pair** and point the camera at the code on a
   second screen, then **Check**. Signed in, the phone gets an access code of its own on
   that scan; from a page that is not signed in, the phone joins as the demo. Without Google
   Play services or a second screen, type the address shown under the code into **Backend
   URL** and the access code, if the site has one, into the field under it, then tap **Save**
   and **Check**.
5. **Take a photo** on the app's **Capture** tab and tap **Send**; it shows in the site's
   **Inbox**.

Every phone screen, and what to do when a step fails:
[On your phone in ten minutes](start/judges.md).

## The problem

Drawers and shelves hold devices, chargers, tools and parts nobody can name, price or match any
more. They sit unsold because writing an honest listing is work, and a vacuum stays without its
attachment because nobody can say which one fits. Listings for the same thing differ in one
detail, and the wrong one is a trip wasted. Working devices get thrown out for lack of a plan.

## Four paths on one inventory

Everything starts from a private record of what you own. A scan never publishes; a listing is a
draft you approve; a search is one you run.

**Catalog.** Read a label with Muse Spark, with SAM 3.1 finding the label first. Every value
comes with its confidence and its source, and stays *to confirm* until you accept it. Add what
you know yourself, with how you know it. Keep the condition, faults, tests, accessories, parts
as records of their own, where it is, what you mean to do with it, and whether a plan may count
on it. [My inventory](guides/inventory.md).

**Measure.** Photograph a feature next to a ruler or a known rectangle, mark the reference and
the feature, and get the dimension with its method and uncertainty. A blurred, oblique or
unreferenced capture is refused with the reason; no reference, no number.
[Measure a feature](guides/measure.md).

**Does it fit?** A candidate is checked against what an item needs, rule by rule from the
category profile, and ends in one verdict from the [ladder](concepts/verdicts.md): an unknown is
never a pass, a conflict is never talked away, and every unknown becomes a question for the
seller. [Does it fit?](guides/match.md).

**Sell and give away.** A preparation checklist, with data-removal steps when the item holds
data. Price guidance from sourced comparables: asking, sold, what you reported and the model's
estimate, each with its page and date, never merged; weak evidence is called weak. A listing
draft written by Muse Spark from confirmed values only, with the disclosures the rules append;
a voice note kept as your words. The Marketplace create page, by handoff.
[Seller flow](guides/seller.md), [Value an item](guides/value.md).

**Find the one that fits.** What an item needs becomes a search you run on Marketplace. Bring a
listing back as its text, a screenshot or the values you know; it is read, assessed by the same
rules, dated, and placed where it stands, with the seller's questions as a message.
[Find a part](guides/search.md).

**Build and reuse.** Say what you want from a build; Muse Spark proposes projects from
templates kept as data, reading your inventory through tools, and the rules keep only what
names items you have. Select a project to commit its items, one build per item, with a budget
across the selected set; a missing piece becomes a search. A build pack written by the rules
from what stands, versioned and stale when an input changes; the outcome in your words, shared
only as a redacted text and only when you say so. [Build and reuse](guides/reuse.md).

## Any item

A category is a data file, a [profile](concepts/profiles.md), that names the fields that matter,
the features worth measuring with their tolerances and how to capture them, and the rules that
decide a fit. Power adapters and vacuum attachments ship as profiles; anything else goes through
a generic one until a profile exists for it.

## Where it runs

On the web today, behind an access code when it is public: a demo you can leave running, with
allowances per visitor and per day, a spend cap and an operator's switch
([Demo access](operations/demo-access.md)). On the phone, a photo into the same inventory and a
voice note kept as your words and read back ([Android app](guides/android.md)); hands-free
through Meta glasses, later. One backend serves all of them.

## In sixty seconds

1. `./dev up`
2. Open http://localhost:5173 and drop in a photo of a power adapter's label.
3. Save it privately, confirm the values, and ask whether the adapter in a listing fits.

See the [Quickstart](start/quickstart.md).

## Meta models

| Model | Job in the app |
|---|---|
| [Muse Spark](models/muse-spark.md) | label and listing reading into typed fields, listing drafts, price search with citations, project proposals through tools |
| [SAM 3.1](models/sam-3-1.md) | isolates item, label and connector in photos |
| [Muse Voice Transcribe](models/muse-voice-transcribe.md) | voice notes kept as the owner's words, from the web and from the phone; spoken questions later |
| [Muse Image](models/muse-image.md) | a picture of what an item could become, drawn only on a click when the switch is on; illustrative, never evidence |
| [Muse Wonder](models/muse-wonder.md), [Muse Glimmer](models/muse-glimmer.md), [Muse Spark Open](models/muse-spark-open.md) | considered, not used in this version; each page says what for |

Development uses Muse Code; see [Working with Muse Code](development/muse-code.md).
