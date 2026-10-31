# Training and improving the reads

The model reads labels; the rules decide. Improving the reads means measuring them on the
demo set, changing what the repository controls (the rules and the prompts), and measuring
again. Tuning the model itself comes
last, and only for what the measurements show is weak.

## The loop as it exists

1. **Record the set.** `./dev record-fixtures` loads `demo/set.yaml` once with the key from
   the shell or `.env` and keeps every model answer under `backend/tests/fixtures/api/`. This spends
   credits once; every later run replays the recordings at no cost.
2. **Score it.** `./dev eval` resets the inventory, loads the set the way `./dev demo` does
   (fixture mode unless `--live`), and scores what the rules can check. It writes
   `eval/report.json`, `eval/report.md`, `eval/charts/fields.png` and
   `eval/charts/proposals.png`. Per item: how many values were read from the photos, how many
   the owner accepted, the mean confidence, and against the item's `expect:` block in the set
   whether each expected value matches (numbers within 5 percent, same unit; text by the
   field's own normalizer), whether the fit verdict against another item is right (`fits` is
   `EXACT_MATCH` or `COMPATIBLE_LIKELY`, `conflict` is `CONFLICT`), and whether the item is
   in as many kept proposals as expected. The summary adds the proposals the model wrote
   against those the rules kept, the stub answers, the spend and the mode.
3. **Read the stub count first.** An answer that comes from an operation's stub rather than a
   recording of this set is counted, and the report says so. A report on stubs describes the
   stubs: record the set before trusting any other number. The set's photos and their
   recordings are in the repository, so a fresh checkout scores the recorded reads with no
   stub answers; a photo changed or a setting that changes what is sent (`EXTRACT_ENHANCE`,
   `IMAGE_MAX_PX`) brings the stubs back until the set is recorded again.
4. **Change the rules or the prompts.** The rules are data: `backend/app/profiles/data/*.yaml` (the keys,
   the tolerances, hard or soft, the questions). The prompts are the `INSTRUCTIONS` strings (and their `LISTING_`, `PLAN_` and `SCENARIOS_` siblings) in
   `backend/app/extract/service.py` (label reading), `backend/app/listing/service.py` (the
   drafts), `backend/app/value/service.py` (price guidance), `backend/app/find/service.py`
   (reading a listing and the search plan), `backend/app/decide/service.py` (the uses and the
   decision cards) and `backend/app/projects/service.py` (proposals); the field list the
   reading prompt asks for is `backend/app/extract/fields.py`, and the normalizers beside it.
5. **Re-record and compare.** A changed prompt changes the request, so its recording is new:
   run `./dev record-fixtures` again, then `./dev eval`. Keep the earlier `report.json` under
   another name and run `python -m app.eval diff before.json after.json` in the backend
   container: it prints the summary counts side by side and every expected value or fit
   verdict whose result changed.

## The data the app collects for improvement

Every value the model proposes is kept with its review state, and every change to an item is
an event, so what the owner accepted and rejected is on record per field (`GET
/api/items/{id}` for the assertions, `GET /api/items/{id}/events` for the history). Every
assessment and every candidate's verdict is kept with the search. Build outcomes record
whether a project worked and what its limits were. Attempt and rescue records (a read that
was retaken, a value the owner corrected by hand) are on the roadmap and would join the same
export.

`python -m app.eval export` writes `eval/train.jsonl` from the inventory as it stands: one
line per item that has accepted observed values, in chat format. The system message is the
extraction instruction the app sends; the user message names the item's photos by id (`GET
/api/items/{id}/photos`) and lists the fields the prompt asks for; the assistant message is
the accepted values as JSON. Rejected values are left out; owner values are not model output
and are left out too. The photos stay on the server: the export carries references, not
pixels, so it can be shared without the owner's images.

## Fine-tuning, as the providers offer it today

Stated as of October 30, 2026, from the providers' own pages; check them before spending.

Meta's post-training guide for Muse Spark Open
(<https://dev.meta.ai/docs/muse-spark-open/post-training>) lists supervised fine-tuning, DPO,
ORPO, distillation and reinforcement learning as the methods the open weights support. The
training data is JSONL conversations, the shape `train.jsonl` has.

- **Fireworks** trains LoRA adapters of Muse Spark Open through its training API, as a limited
  preview that an account has to have enabled. A tuned adapter is served from an on-demand
  deployment; training is priced per token of training data.
- **Baseten** hosts Muse Spark Open for inference and can serve a tuned adapter on dedicated
  inference. No Baseten training path for this model was found as of October 30, 2026.

This version makes no model call to either provider: every call goes to the Meta Model API
through one [client](../models/model-api-client.md). A tuned adapter would be one more
provider behind it, chosen per job, as the [next steps](../project/next.md) describes.

## What is never tuned

The rules decide whether a part fits, what a price rests on, and which proposals and which
lines of a draft are kept. The model proposes values, text and projects; the rules and the
owner accept or drop them. A tuned model reads better; it does not get a say it did not have.

## When it is worth it

Not before the report says so. A profile needs about fifty accepted reads before a tuned
adapter has anything to learn from, and the report tells which operation is weak: expected
values missed on a field the normalizer cannot fix, a listing read that keeps losing a key,
proposals dropped for naming items that are not there. Tune for that operation, re-record the
set, and compare the two reports. A change the report cannot see is not an improvement.
