# Orphan Parts Lens

Show it, ask it, sell it, or find the one that fits. Evidence-backed answers about used things,
on Meta's Muse models.

**This repository is the entry for the Meta Global AI Developer Hackathon (October 27 to
November 4, 2026).** Everything in it was built during the hackathon; the dated log is on
[Built during the hackathon](project/hackathon.md).

Orphan Parts Lens is an assistant for things you own and things you are about to buy. Point the
camera at an item, or paste a listing, and ask: What is this? What is it worth, and is it worth
selling? Does this listing fit what I need, and is it a good deal? What else could this device
become? The answers come with their evidence: a label it read, a source it cited with a date, or
a plain "cannot verify". Used tech and spare parts are the first categories; the engine takes any
item as a data profile.

## The problem

Things sit unsold because nobody can name them, say what they are worth, or write the listing.
Buyers scroll through vague listings and near-identical items that differ in one detail, and end
up with the wrong one. Shoppers cannot tell whether a used item fits their plan or whether the
price is fair. Working devices get thrown out for lack of an idea.

## Five uses

**Identify.** Photograph the item, or its label, and get a typed spec: every field with a
confidence and a pointer to the crop or citation it came from. Unknown stays unknown rather than
guessed.

**Value.** Ask what it is worth and whether it is worth selling. The answer is an estimate built
from cited comparables, labelled as such, with the reasons.

**List.** Get a Facebook Marketplace-ready draft: title, category, description, keywords, and a
short list of things to check before posting. Every field shows where it came from.

**Find.** Say what you need. Search returns candidates ranked against that need with a fit score,
a deal check from the listing's photos and text, the gaps and conflicts, the questions to ask the
seller, and a comparison with the items you saved. A deterministic rule set decides fit; the model
explains. A hard conflict such as reversed polarity is never talked away.

**Reuse.** A device that has stopped earning its place gets safe ideas for what it could become,
with a parts list, manufacturer guidance and local e-waste rules.

**Any item.** A category is a data file (a profile) that says which fields matter, how to
normalise them, what counts as a match, what a fair price depends on, and what the listing should
say. New categories can be written by hand or drafted by Muse Wonder from a few example photos.

## Where it runs

On the web, drop photos or paste a listing. On the phone, talk to it and show it the camera; the
answer is spoken back. Hands-free through Meta glasses later. One backend serves all of them.

## In sixty seconds

1. `./dev up`
2. Open http://localhost:5173 and drop in a photo of a power adapter, the first demo category.
3. Read the evidence table, fix anything wrong, copy the listing.

See the [Quickstart](start/quickstart.md).

## Meta models

| Model | Job in the app |
|---|---|
| [Muse Spark](models/muse-spark.md) | label and listing reading into typed fields, candidate ranking, agent steps, explanations |
| [Muse Wonder](models/muse-wonder.md) | plans the buyer comparison, drafts new profiles |
| [SAM 3.1](models/sam-3-1.md) | isolates item, label and connector in photos and video |
| [Muse Voice Transcribe](models/muse-voice-transcribe.md) | spoken questions on the phone, voice notes in the web app and on WhatsApp |
| [Muse Image](models/muse-image.md) | background cleanup of the cover photo, always labeled |
| [Muse Glimmer](models/muse-glimmer.md), [Muse Spark Open](models/muse-spark-open.md) | on-device pre-check and alternative provider |

Development uses Muse Code; see [Working with Muse Code](development/muse-code.md).
