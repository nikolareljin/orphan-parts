---
description: What Orphan Parts Lens would ideally have next, each with what it is, why, and what it needs.
---

# Next steps

What the app would ideally have, after the hackathon scope. This page took over the roadmap;
each item says what it is, why, and what it needs. Nothing here is built, and the pages about
each say so.

## Capture through Meta glasses

**What.** Hands-free capture: look at the item, say what you know about it, and the photo, the
label and the spoken note arrive in the same [Inbox](../guides/capture.md) as a capture from
the phone, read by the same backend on request. The glasses would reach the backend through
the [Android app](../guides/android.md), which already holds the session and the address; a
short answer (what was read, what is still to confirm) comes back as speech.
**Why.** Both hands are on the thing: the vacuum on its side, the adapter behind the desk.
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

## The demo photos on the phone

**What.** The demo set's photos offered on the phone's Capture tab, so a visitor without a
code sends a photo the recordings know and sees a real reading instead of the recorded answer
for that operation.
**Why.** The public demo is the set; a photo of your own gets the set's answer, which is the
one thing a first-time visitor finds odd.
**What it needs.** The scrubbed photos packaged with the app and a picker beside the camera
button; the fixtures keyed on what is sent, so the phone's re-encoding has to produce the
bytes the recordings were made from, or the backend has to match the photo to the set by
content.

## Public items

**What.** An item the owner marks public: a redacted record at a link, with the kind of item,
the confirmed values and their sources, the photos chosen for it, the faults and the tests,
and never a serial, a location or a note. A buyer or a repairer reads the evidence rather than
a paragraph.
**Why.** A listing says what the seller wrote; a record says what the label said, what was
measured and what was tested, and when.
**What it needs.** A public read path with the same redaction as the shared outcome text,
consent per item, revocation that works at once, and a link that carries nothing about the
owner.

## From the roadmap

The shorter items, in rough order.

- **The build pack as a PDF**, with the candidate listings cited by page.
- **Ranking across candidates.** Several candidates for one need side by side, with the fit,
  the price and the open questions of each ([Find and rank](../guides/evaluate.md)).
- **On the phone.** A calibrated capture marked on the phone, a spoken question answered from
  the inventory, a frame picked from a clip for reading, and the store listing of the app.
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
- **Accounts and proper sign-in** instead of a shared access code: a person signs in as
  themselves, and what they may see and change follows from that
  ([Demo access](../operations/demo-access.md)).
- **Storage.** SQLite and local files serve one household; Postgres and object storage are the
  path when more than one does ([Data model](../reference/data-model.md)).

## Out of scope, stated as such

Autonomous Marketplace search or posting, purchases, payments, universal geometry recognition,
unreviewed disassembly, fabricated prices, guaranteed compatibility. The
[limitations](limitations.md) page says what the version at hand does not do.
