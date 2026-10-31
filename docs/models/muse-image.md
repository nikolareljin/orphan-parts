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

## When it is called

Never by itself. One call per click on the live door. The demo visitor is refused (`403`) like
every other call that spends, and sees only the pictures already drawn for a public item; the
key is never used without the code. The switch is `PICTURE_ENABLED` (off by
default): while it is off the route answers `503` with *pictures are off on this server
(PICTURE_ENABLED)*, and the section shows one line saying pictures are off, no field and no button.
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
  `GET /api/items/{id}/pictures/{n}`, never cached; gone with the item.

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
