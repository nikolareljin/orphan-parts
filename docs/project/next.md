---
description: What Orphan Parts Lens would ideally have next, each with what it is, why, and what it needs.
---

# Next steps

What the app would ideally have, after the hackathon scope. This page took over the roadmap;
each item says what it is, why, and what it needs. What is still listed is not built, and the
pages about each say so; what was on the list and has since been built is at the end, with
where to find it.

## Accounts instead of a shared code

**What.** A person signs in as themselves, and what they may see and change follows from that:
their own inventory, their own phone, their own allowance.
**Why.** Today one deployment has one inventory, and every access code it accepts opens it as
its owner; the codes are issued, revoked and logged by label, but they are not people. The
sign-in dialog says so: *For now, signing in uses an access code only. Proper accounts come
later.*
**What it needs.** An identity provider or a passkey sign-in, an owner on every record, the
gate's allowances per account rather than per session, and the phone's own code tied to the
account that paired it. See [Demo access](../operations/demo-access.md).

## The app on Google Play

**What.** The Android app installed from the Play Store, signed with a store key and updated in
place.
**Why.** Today the APK comes from the releases as an app from an unknown source, with a Play
Protect warning to click through, and each release carries a fresh development key, so the
previous one has to be uninstalled first ([For judges](../start/judges.md)).
**What it needs.** The Play listing finished (it was started and not completed within the
hackathon window), a release key kept out of the repository, and the release workflow
uploading the signed bundle.

## Capture through Meta glasses

**What.** Hands-free capture: look at the item, say what you know about it, and the photo, the
label and the spoken note arrive in the same [Inbox](../guides/capture.md) as a capture from
the phone, read by the same backend on request. The glasses would reach the backend through
the [Android app](../guides/android.md), which already holds the session and the address; a
short answer (what was read, what is still to confirm) comes back as speech.
**Why.** Both hands are on the thing: the frappé maker on its side, the adapter behind the
desk.
**What it needs.** The Wearables Device Access Toolkit in the companion app, the glasses in
hand to test with, and a capture path on the backend that accepts a frame and a note without
the phone's camera app in between. See [Meta glasses](../guides/glasses.md).

## WhatsApp for services

**What.** Send an item's record, its photos and the question to a service: a repair shop, a car
garage, an electronics repairer, an electrician. The record is the message: the confirmed
values with their sources, the photos you choose, the faults and the tests done, and the one
question. The answer comes back on the item, as a note with its date and who gave it.
**Why.** A repairer asks for the label and the symptom every time; the record already holds
both, with what was tested and what was not.
**What it needs.** By handoff first: a message written by the rules from the record, copied
into WhatsApp like the listing draft is copied into Marketplace. Direct sending waits for the
Business API: a business number, the webhook, media upload, the signature check, and consent
per item on what leaves. See [Messaging agent](../guides/messaging-agent.md).

## Posting to Marketplace

**What.** The listing posted from the app rather than by hand.
**Why.** Today the draft is copied and the create page is opened; the fields are typed over
again on the other side ([Marketplace handoff](../guides/marketplace.md)).
**What it needs.** A listing API for individuals, which does not exist; the catalog and commerce
APIs serve businesses with a catalog, and the app will not automate facebook.com. Until that
changes, the handoff stays, with the draft shaped to the create page's fields. The same holds
for search: a search is handed off, a listing is brought back by you.

## The evidence set

**What.** Three kinds of record that make a fit or a reuse checkable by someone else. A
*compatibility experiment* asks for the one measurement that decides the fit (the opening
against the wand, the barrel against the jack) and records the outcome either way. *What one
purchase unlocks* names the single missing piece that turns two idle items into a working set,
with the search for it. A *rescue record* is the outcome of a build, with the kinds of items,
the set-up, the test and the limits, shared by choice.
**Why.** A verdict is only as good as its evidence, and the evidence that decides is usually one
number. Recording which number, and what it was, is what a second person can trust.
**What it needs.** An experiment as a record on the item with a feature, a method and a result;
the search request carrying the project it unlocks; the shared outcome text, which exists,
kept as a record with a date. See [Evidence model](../concepts/evidence.md).

## A second model route

**What.** Muse Spark Open, hosted on Baseten or Fireworks, for the planning operations: project
proposals and listing drafts, where the prompt and the tools are the same and the answer is
checked by the rules anyway.
**Why.** A second provider when the Model API is busy, a cost per token that can be chosen per
job, and an open-weight route for anyone who runs the stack on their own.
**What it needs.** The provider routing the [client](../models/model-api-client.md) is shaped
for: one `respond`, structured output and tool calls on the second route at parity, fixtures
recorded per provider, and the ledger pricing each route from its own rates. See
[Providers and routing](../models/providers.md) and [Muse Spark Open](../models/muse-spark-open.md).

## The demo samples on the phone, and voice-note samples

**What.** On the web, a visitor without a code already picks the demo set's photos in a gallery
and gets the recording of that exact photo. The phone does not have that yet: a phone paired
as the demo visitor can only send, which is refused. The set has no voice notes either, so the
voice features have nothing a visitor can try.
**Why.** The phone and the voice notes are where a first-time visitor without a code sees the
least.
**What it needs.** The phone's Capture tab listing the samples from `GET /api/samples` and
reading one with `POST /api/samples/read`, as the web does; a few WAV notes recorded for the
set's items under `demo/notes/`, recorded once with a key and offered beside the photos.

## Public items at a link

**What.** An item the owner marks public already shows to the demo visitor, its values, photos
and drawn pictures and never its location, its notes, a clip or a draft. What is missing is a
link of its own: a redacted record a buyer or a repairer opens from a listing, with the kind
of item, the confirmed values and their sources, the photos chosen for it, the faults and the
tests, and never a serial, a location or a note.
**Why.** A listing says what the seller wrote; a record says what the label said, what was
measured and what was tested, and when.
**What it needs.** A public read path with the same redaction as the shared outcome text,
consent per item, revocation that works at once, and a link that carries nothing about the
owner.

## From the roadmap

The shorter items, in rough order.

- **The build pack as a PDF**, with the candidate listings cited by page.
- **Candidates side by side.** The listings brought back are ranked by the pattern; the
  candidates read from them are not yet compared in one table, with the fit, the price and the
  open questions of each ([Find and rank](../guides/evaluate.md)).
- **On the phone.** A calibrated capture marked on the phone, a spoken question answered from
  the inventory, a frame picked from a clip for reading.
- **More profiles.** Bike cassettes, light bulbs, power-tool batteries, camera lenses, appliance
  parts, fasteners with a coin for scale; a profile drafted by Muse Wonder from a few photos
  ([Creating a new category](../guides/new-category.md)).
- **Declutter mode.** One photo of a drawer, SAM 3.1 segments every item, a batch of records
  and drafts.
- **Seller questions on WhatsApp Business.** Answers to a buyer's questions from the listing's
  evidence, approve-to-send; product cards from the catalog; a Page post.
- **Price alerts.** Watch a search and be told when a documented candidate appears.
- **Community rescue.** Another person's offer of an item, a tool or help joins a project, with
  evidence tasks per participant.
- **Reuse or recycle fallback.** A repair cafe or an e-waste drop-off when a part has no resale
  value.
- **Storage.** SQLite and local files serve one household; Postgres and object storage are the
  path when more than one does ([Data model](../reference/data-model.md)).

## Done since this page was first written

| Before | Now |
|---|---|
| What to do with an item after it is read | **Decide** on the item: three cards for your profile and one recommendation ([Decide what it becomes](../guides/decide.md)) |
| A plain search for the missing part | **Plan the search**: Marketplace search links, a match pattern and exclusion words, the listings brought back ranked with no model call ([Find a part](../guides/search.md)) |
| A draft shaped to the Marketplace create page | **Prepare to sell or give away**: listing details, a Facebook Marketplace (US) draft in its fields, copy, photos in order, handoff, and what happened after ([Seller flow](../guides/seller.md)) |
| A picture of a finished build | **Draw it** on a reuse card and on a Build project ([Muse Image](../models/muse-image.md)) |
| The demo visitor's photos answered by some other recording | The sample gallery on the web: the set's photos picked, each answered by its own recording ([Demo access](../operations/demo-access.md)) |
| Leaving the session and the phone | **Sign out** in the header; **Unpair** on the app's Backend tab ([Pair the phone](../start/pairing.md)) |
| The first demo set, a vacuum and its crevice tool | A drawer of the owner's own things, photographed with serials and MAC addresses masked ([Demo walkthrough](../start/demo.md)) |

## Out of scope, stated as such

Autonomous Marketplace search or posting, purchases, payments, universal geometry recognition,
unreviewed disassembly, fabricated prices, guaranteed compatibility. The
[limitations](limitations.md) page says what the version at hand does not do.
