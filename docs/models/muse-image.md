# Muse Image

Draws a picture of what an item could become, on the item dialog, only when the owner clicks
**Draw it**. The picture is illustrative: it is labeled as drawn wherever it is shown, no value
is read from it, and nothing rests on it.

## What it draws

The dialog's last section, *What it could look like*, has a field *as a...* (empty, with an
example use as its placeholder; a project template id such as `smart_mirror` names that
project, anything else is the owner's own words) and the button. The prompt is written by the
rules from the item as it is known: its type, its accepted values (never one that identifies the item or its owner, such as
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
results in and the items allocated to it (each its kind and up to three accepted values). A
value that identifies an item (serial, MAC, IMEI, by the same filter as above) or names a price
never goes out, nor a name, the location or the notes. The title is cut to 120 characters, the
line to 200, a value to 60, and at most six parts are named, each once.

## When it is called

Never by itself. One call per click on the live door; showing an item, writing scenarios,
proposing projects, opening a project or deciding draws nothing. The demo visitor is refused (`403`) like
every other call that spends, and sees only the pictures already drawn for a public item; the
key is never used without the code. Scenarios and projects are not shown to the demo visitor,
so a card's or a project's **Draw it** is disabled for them with *Sign in with the access code
to draw.* The switch is `PICTURE_ENABLED` (off by
default): while it is off the route answers `503` with *pictures are off on this server
(PICTURE_ENABLED)*, and the section shows one line saying pictures are off, no field and no button; a card or a
project shows *Pictures are off on this server.* in place of **Draw it**.
The hosted demo turns it on with the repository variable `PICTURE_ENABLED`, which the deploy
writes into the Modal secret ([deployment](../operations/deployment.md)).

## Request and response

- **Request.** `POST /v1/images/generations`, JSON: `model` (`MODEL_IMAGE`, `muse-image-1.0`),
  `prompt`, `n` 1, `size` `1024x1024`, `response_format` `b64_json`, `output_format` `jpeg`,
  `reasoning_strength` `low` (the model's own refinement pass is skipped: a sketch of a use, not
  a product shot).
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
