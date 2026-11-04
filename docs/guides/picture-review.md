# Review and redraw the drawings

Muse Image draws what a project, a reuse card or an item could become, from a prompt the app
writes by the rules. Most drawings match; some do not. The demo set's hall smart mirror, built
from an 18 inch Dell monitor, came back as a wall television of 50 inches or more. `./dev
picture-review` finds those: it checks every drawing against the facts the app holds, proposes
a corrected brief for each one that misses, and, once the owner approves, draws those again with
the brief and checks the new drawing.

The results of the first run on the demo set are in
[How the drawings were improved](../project/picture-review-results.md).

## What it checks

For every drawing (each project's picture and its views, each reuse card's picture, each item's
picture) the tool builds the facts it had to show from the app's own records:

| Drawing | Facts |
|---|---|
| project | its title, what it results in (the room, the use), each allocated item: its kind, the owner's name for it (which often says its size: *Dell 1800FP monitor, 18 inch*) and its accepted values (screen size, form factor, capacity), what is still to get, the view asked for |
| reuse card | the card's title and what it does, the item, the kinds of item the card names from the rest of the inventory, the extra parts it lists |
| item | the use it was drawn as, the item with its accepted values |

A value that identifies an item or its owner (a serial, a MAC address) or names money never
goes in, as for the drawing itself. The report also shows the request Muse Image was sent, so a
fact the request left out (the screen size, for one) is plain to see.

**What is still to get may be drawn.** A finished build includes what the owner buys for it
(the two-way glass and the frame of a mirror, the power supply of a NAS); the facts list those
parts under *still to get* and the review does not count them as invented.

One Muse Spark call per drawing (operation `picture-review`, low effort, the drawing at 768
pixels and the facts as text, strict schema `ReviewAnswer`) answers:

- **verdict**: `matches`, `partly` (small issues the owner could live with) or `wrong` (it
  misleads about what gets built: another device, the main part at the wrong scale, another
  project);
- **issues**, each with a category: `scale`, `missing_part`, `invented_part`, `wrong_device`,
  `wrong_setting`, `text` (legible words or logos; the request asks for none), `implausible`;
- a **confidence** from 0 to 1, a one-line **summary** of what the drawing shows;
- a **brief**: the corrected drawing brief, at most 350 characters, concrete (*an 18 inch 5:4
  monitor behind a two-way mirror in a slim frame about 45 x 40 cm, on a hall wall at eye level;
  not a TV*), empty when the drawing matches.

## Run it

```bash
./dev picture-review --dry-run            # the drawings and their facts; no key, nothing spent
./dev picture-review --max-usd 1          # review every drawing (about 0.01 USD each)
./dev picture-review --only project:2     # one project's drawings (project:2#1 is the first)
./dev picture-review --decide --max-usd 1 # also check the recommendations (below)
```

The demo set is loaded in fixture mode into a folder of its own, so nothing is spent on the
load and the stack's inventory is untouched. `--data` reviews the inventory of the running
stack (`DATA_DIR`) instead, as it stands. The key is `MODEL_API_KEY` from the shell, else from
`.env`; it reaches the container by name and is never printed or written. Without Docker,
`NATIVE=1 ./dev picture-review ...` runs it in the backend's virtualenv, and
`python -m app.picture.review --help` (from `backend/`) is the same tool.

Drawing ids: `project:<id>#<n>`, `card:<item key>#<n>`, `item:<item key>#<n>` (with `--data`,
the item's id in place of its key). `project:2` alone picks every drawing of project 2.

### Cost and the cap

A review is one Muse Spark call with an image, about 0.01 USD; a check of one set of Decide
cards or one project is a text call, about 0.005 USD. `--max-usd` (default 1.00) is the run's
own cap: a call is made only when the most it could cost (its input allowance and every output
token it may write, with the calls still under way) still fits; the drawings past it are listed
as not reviewed. The spend ledger's own cap (`SPEND_CAP_USD`) holds as well. A redraw is one
Muse Image call (0.01 USD) and one more review.

## The report

`picture-review/report.md` (and `report.json`, the same as data; the folder is git-ignored):

- the totals: drawings, verdicts, the spend;
- a summary table: id, what it is, verdict, the first issue;
- one section per drawing: its thumbnail (`pictures/<id>.jpg`), the verdict with its
  confidence and cost, what it shows, the facts, the request Muse Image was sent, the issues,
  the proposed brief;
- with `--decide`, the recommendations with flags.

## Approve, redraw, review again

```bash
./dev picture-review --redraw project:2#1,card:monitor_1800fp#1 --max-usd 1
./dev picture-review --redraw all-wrong --max-usd 1
./dev picture-review --redraw project:2#1 --brief "an 18 inch monitor behind a two-way mirror ..."
./dev picture-review --redraw project:4 --briefs picture-review/briefs.yaml
```

`--redraw` takes the brief the last report proposed for each drawing named (or `--brief` for a
single drawing, or `--briefs`, a YAML map of id to brief, for briefs the owner edited), then:

1. writes each brief into `demo/set.yaml`, beside what it corrects, comments and order kept:
   an item's `picture_brief`, its first reuse card's `reuse_picture_brief`, a project's under
   `propose: corrections:` by its template id (or its title when two kept projects share a
   template), a view's as `<template> / <view>`:

    ```yaml
    propose:
      corrections:
        "smart_mirror": "an 18 inch 5:4 monitor behind a two-way mirror in a slim frame ..."
        "custom_nas / from above, as it is used": "a mid-tower case seen from above ..."
    ```

2. loads the set once in record mode in which only drawings are bought: every other request
   answers from its recording or not at all, so nothing else is asked again. The brief is said
   in the request before its closing words (*...; an 18 inch monitor ..., finished and in use in
   a home, no text, no logos, no people*), so a drawing with a brief is a new request with its
   own recording; a drawing without one sends exactly what it sent before, and its recording
   still answers. Recordings are only added, never changed;
3. loads the set again in fixture mode, as `./dev demo` will, and reviews each new drawing;
4. writes `picture-review/redraw.md` (before and after verdict, the brief, both reviews) and two
   contact sheets, `before.jpg` and `after.jpg`, and puts the new reviews into `report.json`
   and `report.md`, so a second `--redraw` of the same drawing starts from the drawing as it is
   now.

A drawing redrawn twice leaves the first redraw's recording behind, never read again; when it
was never committed, delete it before committing (a fixture load of the set touches every
recording it reads, the rest are left over).

With `--data` a redraw is drawn live into the stack's inventory, after the drawings already
there (`picture-<n+1>.jpg`), so the old ones stay as its history, and reviewed.

After a redraw of the demo set, `git status` shows `demo/set.yaml` and new files under
`backend/tests/fixtures/api/images-generations/`; `git diff --diff-filter=MD --
backend/tests/fixtures` is empty; `./dev demo` loads with 0 not recorded and 0 stand-in
answers. Commit the set and the new recordings together.

## Recommendations (`--decide`)

The same tool checks the advice, one text call each (operation `decide-review`, strict schema
`DecideAnswer`): each item's latest Decide cards against the item's facts and the owner's other
items, and each project's allocations against the allocated items' facts. A flag names where,
the claim, the fact it contradicts and a severity (`major` when following it would fail, such as
DDR4 memory allocated to a laptop that takes DDR3). Report only: nothing is changed; a flagged
recommendation is fixed by the owner, or by the rules that pick allocations.

## With Muse Code

The skill's source is `tools/muse/picture-review/SKILL.md`. Muse Code reads a project's skills
from `.agents/skills/<id>/`, which this repository keeps out of git, so install it once from the
repository root with a link (it follows the file as it changes):

```bash
mkdir -p .agents/skills && ln -s ../../tools/muse/picture-review .agents/skills/picture-review
muse skills list --source project    # picture-review, once the workspace is trusted
```

`muse skills install tools/muse/picture-review` installs a copy for your user instead. In a
session from the repository root:

```text
/picture-review
```

or *review the drawings and fix the wrong ones*. The skill runs the dry run, the review with a
cap, shows the summary and the briefs, asks which to redraw, redraws only those, reviews them
again, checks that no other recording moved, and opens a pull request when asked. The owner
merges. `muse skills validate tools/muse/picture-review` checks the file.

## Getting better drawings over time

Muse Image is a hosted model. The Model API documents image generation and image edits for
it, and post-training only for the open-weight models (Muse Spark Open, Muse Glimmer); no
fine-tuning path for Muse Image was found as of November 3, 2026. The drawings get better
through what the app sends and what it does with the answer:

- **Facts first.** The prompt names at most three accepted values per part, in alphabetical
  order, so *brand, input voltage, model number* went out for the 1800FP and *screen size* did
  not. Leading with the values that set the look (a screen's size and aspect, a board's form
  factor, a count) is a change to the prompt builder; it changes every drawing's request, so it
  goes with a full re-record of the drawings.
- **Negative constraints.** *not a TV*, *no text or labels*, *no tower case for a laptop
  board*: the review's briefs say them, and they work.
- **A corrections library.** The briefs the reviews approve, kept by project template and kind
  of item (`propose.corrections` holds them for the demo set today), applied by the prompt
  builder to every new drawing of that kind.
- **View presets.** A fixed set of views (in its room, a close-up of the parts, from above) with
  their wording settled, so a view never drifts into another room.
- **Reference photos.** The images API takes input images on its edits endpoint
  (`POST /v1/images/edits`); a drawing conditioned on the owner's photo of the part would get its
  shape and proportions right. Not built: it sends the owner's photo to the image model, which
  the privacy check of photos has to clear first.
- **A review gate.** Review a new drawing before it is shown and, when the verdict is `wrong`,
  draw it once more with the brief: two calls more per bad drawing, behind a setting.
- **An evaluation set.** Each `report.json` is a labeled set: the share of `matches` before and
  after a change to the prompt builder measures it, as `./dev eval` does for the readings.
