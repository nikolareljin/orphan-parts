# Muse Image

Draws a picture of what an item could become, on the item dialog, only when the owner clicks
**Draw it**. The picture is illustrative: it is labeled as drawn wherever it is shown, no value
is read from it, and nothing rests on it.

## What it draws

The dialog's last section, *What it could look like*, has a field *as a...* (empty, with an
example use as its placeholder; a project template id such as `smart_mirror` names that
project, anything else is the owner's own words) and the button. The prompt is written by the
rules from the item as it is known (the example here is of version 1 of the drawing
parameters; [How the request is built](#how-the-request-is-built) says what version 2 asks):
its type, its accepted values (never one that identifies the item or its owner, such as
a serial number, a MAC address or an IMEI; at most eight), its condition and its known faults,
and the chosen use:
*a semi-realistic illustration of a smart mirror built from laptop (screen size 14 in);
condition: scuffed lid, on a plain background, no text, no logos, no people*. A value still to
confirm is left out. With no use given, the item is drawn as itself, cleaned up and ready to
use.

### A finished project

**Draw it** is also on each *Reuse it* scenario in the decision view and on each Build
project's panel: a picture of how the finished project could look, built from several items.
The prompt is written by the rules from what the card uses and nothing else: *a semi-realistic
illustration of Homework workstation built from laptop (screen size 14 in), monitor; a desk
set-up for homework, on a plain background, no text, no logos, no people*. For a reuse card,
the card's title, what it does, this item (its kind and up to three accepted values) and the
kinds of item the card names from the rest of the inventory; for a project, its title, what it
results in and the items allocated to it (each its kind and up to three accepted values, not
its condition or the marks printed on it, which say nothing of the finished build), drawn
*finished and in use in a home* rather than on a plain background. Another view of a project
(the demo set's `propose.views`, such as *as a close-up of how the parts fit together*) adds
*shown* and the view to the line, so each view is its own request. A
value that identifies an item (serial, MAC, IMEI, IMSI, ICCID, MEID, service tag, by the same
filter as above) or names money (price, cost, paid, MSRP, value, worth, resale, retail) never
goes out, nor the location or the notes. The title and the line are the model's words, and the
model read the items' names in its brief, so each item's name in them, in any letter case, is
replaced by its kind before the prompt goes out (*Nik's work laptop* becomes *laptop*). The
title is cut to 120 characters, the line to 200, a value to 60, and at most six parts are
named, each once.

## When it is called

Never by itself. One call per click on the live door; showing an item, writing scenarios,
proposing projects, opening a project or deciding draws nothing. The demo visitor is refused (`403`) like
every other call that spends, and sees only the pictures already drawn for a public item, a
reuse card of its saved cards or a project built on public items; the key is never used without
the code. In place of a card's or a project's **Draw it** the visitor reads *Sign in with the
access code to draw.* The switch is `PICTURE_ENABLED` (off by
default): while it is off the route answers `503` with *pictures are off on this server
(PICTURE_ENABLED)*, and the section shows one line saying pictures are off, no field and no button; a card or a
project shows *Pictures are off on this server.* in place of **Draw it**.
The hosted demo turns it on with the repository variable `PICTURE_ENABLED`, which the deploy
writes into the Modal secret ([deployment](../operations/deployment.md)).

## Request and response

- **Request.** `POST /v1/images/generations`, JSON: `model` (`MODEL_IMAGE`, `muse-image-1.0`),
  `prompt`, `n` 1, `size` `1024x1024`, `response_format` `b64_json`, `output_format` `jpeg`,
  `reasoning_strength` `low` (the model's own refinement pass is skipped: a sketch of a use, not
  a product shot). One try, never retried: an image that timed out may still have been drawn
  and billed, so a retry could charge one click twice; the error is shown and the owner
  decides whether to click again.
- **Response.** `data[0].b64_json` decoded to the JPEG (an answer that is not a JPEG, `FF D8 FF`
  first, is an incomplete answer: nothing is kept, the call is still charged); `revised_prompt`
  kept on the result; `usage` (input and output tokens) kept in the ledger entry. Fixture mode
  answers from `tests/fixtures/api/images-generations/picture.json`, a small gray JPEG, so tests,
  the browser checks and the demo set run without a key. Record mode stores each picture whole, in base64, in its
  fixture, so record pictures sparingly.
- **Where it lands.** `DATA_DIR/items/<id>/picture-<n>.jpg` with a `picture-<n>.json` record
  (what it was drawn as, the model, the cost, when; the number is claimed by creating the file
  exclusively, so two draws at once never overwrite each other), beside the item's photos and
  never counted as one: `GET /api/items/{id}/photos` does not see it. Served by
  `GET /api/items/{id}/pictures/{n}`, never cached; gone with the item. A reuse card's
  pictures go in `DATA_DIR/items/<id>/scenarios-<scenarios id>-reuse-<card>/`, numbered the
  same way, so they go with the item too and a new set of cards starts with none; a project's
  in `DATA_DIR/projects/<id>/`, cleared with the inventory by `./dev demo`. No schema change:
  the files and their records are the storage.

## How the request is built

The rules above are the mechanics; what they say is data, in the drawing parameters
`backend/app/picture/params.yaml` (versioned, read on each drawing). Since version 2 a request
says, in this order:

1. **What is drawn and its parts, facts first.** Each part is its kind with its facts: the
   sizes the owner's name for it states (*18 inch*, *2.5 inch*, *480 GB*; nothing else of the
   name), a monitor's as *screen size 18 inch, about 46 cm across the diagonal*, then its
   accepted values with those that set its size first, at most six for a part of a build and
   eight for an item's own picture. A brand, a model or part
   number, certifications, a voltage, condition notes and faults are never said: a drawing
   letters what it is told (*DELL 1800FP* on a bezel) and draws a condition as dust, blots and
   a plastic wrap. Then how that kind of part looks at its real size (*a tiny credit-card-sized
   bare board*), when the parameters keep one for it.
2. **What it does and how it is shown**, a view with its preset when the parameters keep one.
3. **The correction of its kind of project**: by template for a project, by the words of the
   use for an item drawn as one (*smart mirror*), by the card's title for a reuse card.
4. **The drawing's own brief**, from the demo set (a review's correction); said once when it is
   the correction above.
5. **The negatives** (*no lettering, logos, brand names, model numbers or labels on any part,
   case or screen*), then the closing rules: *on a plain background* for an item drawn as
   itself, *finished and in use in a home* for a use, a reuse card and a project.

Version 1 is the builder as it was before (three values a part, in alphabetical order, the
condition said, a plain background for a use); its parameters are kept in
`eval/pictures/params-v1.json` and reproduce its requests word for word. A change to the
parameters changes the requests, so the demo set's drawings are drawn and recorded again with
it; `./dev picture-review --tune` proposes the change from the reviews and `--evaluate` scores
it ([Tuning the drawing parameters](../guides/picture-review.md#tuning-the-drawing-parameters)).

## The review gate

With `PICTURE_REVIEW_GATE` on (unset: on when the calls are live, off in fixture mode), a
drawing the owner asks for is checked once by Muse Spark against its facts, as the review
checks the demo set's. When it shows another kind of device, or is wrong, or partly wrong with
the main part at the wrong size, it is drawn once more with the review's brief and checked
again. Both are kept; the better one is answered and shown, the other is marked `hidden`; each
picture's record carries its check (`verdict`, `issues`, `cost_usd`, `redraw_of`), and the
caption says *Checked against its facts by Muse Spark: matches, drawn again for picture 1*.
A click costs one drawing and one check (about 0.017 USD), at most two of each. A demo
visitor's drawing is answered from the recordings and never checked or drawn again, and the
demo loader never goes through the gate, so each of the set's drawings stays one request.

## Corrections and review

A drawing can carry a correction: a brief said in the request before its closing words
(*...; an 18 inch monitor behind a two-way mirror in a slim frame, not a TV, finished and in use
in a home, no text, no logos, no people*), at most 400 characters. Without one the request is
exactly what it was, so every recording still answers. The demo set keeps them as an item's
`picture_brief` and `reuse_picture_brief` and a project's `propose.corrections`; `./dev
picture-review` checks every drawing against its facts with Muse Spark, proposes the brief and,
once approved, draws again with it ([Review and redraw the drawings](../guides/picture-review.md)).

## Cost

Priced per image generated at the published rate ($0.01), recorded in the ledger under
`picture` with the model id, whatever the tokens; counted against the spend cap and the
demo allowances like every other call that spends. The caption under each picture says what
the call cost, or that a recorded answer cost nothing.

## Illustrative, never evidence

A picture is not a photo of the item and is never shown as one: it is drawn after the item's
photos, under its own heading, captioned *Illustrative picture drawn by Muse Image; not a
photo of the item*. Nothing in the inventory reads from it; no assertion, draft, verdict or
price rests on it; it is not part of the evidence set. The job Muse Image was first
considered for, a clean cover photo with the background replaced and the product's pixels
untouched, is not built: a listing ships with the photo checklist instead
([Seller flow](../guides/seller.md)).

Returned images are decoded and re-encoded before storage. Corrupt images are refused; metadata is stripped.
