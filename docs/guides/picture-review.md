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
as not reviewed. The run keeps its own ledger, in memory, under the same cap; a redraw buys
whole drawings only within what is left after a review of each. With `--data` a redraw also
goes on the stack's spend ledger under `SPEND_CAP_USD`. A redraw is one Muse Image call
(0.01 USD) and one more review.

## The report

`picture-review/report.md` (and `report.json`, the same as data; the folder is git-ignored):

- the totals: drawings, verdicts, the spend;
- a summary table: id, what it is, verdict, the first issue;
- one section per drawing: its thumbnail (under `pictures/`, named after its id:
  `project-2-1.jpg` for `project:2#1`), the verdict with its
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

The briefs are written before the drawings are bought: when a redraw stops part way,
`git diff demo/set.yaml` shows what it wrote, and `git checkout demo/set.yaml` takes it back.

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
`DecideAnswer`): each item's latest Decide cards and its ideas against the item's facts and the
owner's other items, and each project's allocations against the allocated items' facts. A flag names where,
the claim, the fact it contradicts and a severity (`major` when following it would fail, such as
DDR4 memory allocated to a laptop that takes DDR3). Report only: nothing is changed; a flagged
recommendation is fixed by the owner, by the rules that pick allocations, or by the text
parameters ([Tuning the text parameters](#tuning-the-text-parameters)).

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

## People's votes

Under every drawing in the web app (an item's, a reuse card's, a project's) and under each set
of Decide cards, the ideas, a draft, price guidance, a search plan, a web find, a candidate, a
project proposal and a build pack there is a small 👍 / 👎 pair. The owner and a judge's code
vote; the demo visitor sees neither button. A dislike asks, in one optional line of at most 200
characters, what is wrong (*drawn as a TV, not an 18 inch monitor*). A second click on the
pressed button takes the vote back. A vote calls no model: the votes are kept in the
inventory (the `feedback` table, [Data model](../reference/data-model.md)) and read by these
tools as a person's signal beside the reviewer's.

A dislike of a drawing also steers the next drawing of the same thing, in the app (**Draw it**
again on that item, reuse card or project): the request gets an *Avoid:* segment with the
reasons of the dislikes of its earlier drawings (*Avoid: drawn as a TV, not an 18 inch
monitor*), newest first, each said once, at most three, each one plain line of at most 200
characters with any private value masked; a dislike without a reason says *a different
composition than the disliked one*. Up to two more come from dislikes of drawings of other
projects of the same kind (template, such as *arcade table*). A liked drawing's own correction
(its brief), when it had one, adds *Keep:* with it. The caption then says *Drawn again
avoiding: ...* (and *Keeping: ...*), and the picture's record keeps `avoided` and `kept`. Your
votes steer your own drawings alone: the owner's the owner's, a judge's code's that code's;
the demo visitor's drawings never. With no votes the request is word for word what it was, so
every recording still answers; the demo loader and these review tools draw without the votes
([How the request is built](../models/muse-image.md#how-the-request-is-built)).

- Every review reads them from the stack's inventory (`DATA_DIR`) and keeps them in the report:
  each drawing's likes, dislikes and the reasons, with who gave them (*owner*, *judge code 3*),
  and a *People's votes* table in `report.md`. With the demo set the drawings are matched by
  the item, card or project and the picture's number, as `./dev demo` loads them; a vote cast
  on a drawing redrawn since under the same number is counted as stale, not as a vote on the
  new one. Nothing of them goes into a review call.
- `--only disliked` (or `liked`) reviews just the drawings people voted on:

    ```bash
    ./dev picture-review --only disliked --max-usd 0.5
    ./dev picture-review --redraw disliked --briefs picture-review/briefs.yaml
    ```

- `--tune` counts a dislike as an issue a person flagged, with its reason, ahead of the
  reviewer's: the drawing's kind of project is up for a correction even when the reviewer
  found it matching, the phrasing call reads the reasons, and `tune.md` lists the votes. A
  reviewer's brief or the phrasing call writes the correction; a reason alone is a complaint,
  not a brief.
- A drawing a person liked and nobody disliked is kept as it is: `--redraw all-wrong` and
  `--candidates` (without `--only`) leave it out.
- `./dev decide-review` does the same for the recommendations: a dislike of a set of Decide
  cards, of the ideas or of a project proposal is kept beside the check of that answer, and
  `--tune` takes it as a flag a person raised (*flagged by a person*) with the reason as the
  claim. Only the latest set of cards and ideas is checked, so a vote on an earlier one is not
  counted.

A judge's code votes on what it can see (the demo set's public items and what it made itself);
its vote is tagged with its code and counted for it alone; the owner counts every vote. The
review tools read the owner's and the judges' votes alike and say whose each is.

## Tuning the drawing parameters

A brief fixes one drawing. What every drawing is asked with is data: the drawing parameters,
`backend/app/picture/params.yaml`, versioned and read on each drawing
([How the request is built](../models/muse-image.md#how-the-request-is-built)):

| Section | What it holds |
|---|---|
| `version` | bumped by each `--tune --apply`; each version's score is `eval/pictures/params-v<N>.json` |
| `facts` | which accepted values of a part are said: `first` (size facts before the rest), `left_out` (brand, model, part number, certifications, voltages, condition notes), `item_values` and `part_values`, `from_name` (the sizes in the owner's name: *18 inch*, *480 GB*), `condition` (an item's condition in its own picture) |
| `kinds` | by item type: `looks`, how the part looks at its real size, and `size`, what a size in its name is called (a monitor's is its *screen size*, said in cm too) |
| `projects` | by project template id: the `correction` every drawing of that kind of project carries, and the `match` words that find it in an item's use or a reuse card's title |
| `views` | words in a view and the preset they add (*from above*: seen straight down, every part at its true size) |
| `negatives` | said after the brief in every request |
| `rules` | the closing words of an item drawn as itself, a use, a reuse card, a project |

Muse Image is not fine-tuned (the Model API has no path for it); these are the levers. The
loop that moves them is six commands:

```bash
./dev picture-review --max-usd 1          # review every drawing as it is (report.md)
./dev picture-review --evaluate           # keep the score of this version, compare
./dev picture-review --tune --max-usd 0.1 # propose edits (tune.md, tune.json)
./dev picture-review --tune --apply       # write them: version one up
./dev picture-review --redraw-set --max-usd 1.5   # draw the whole set again, review it
./dev picture-review --evaluate --prune   # score it, compare, drop unused recordings
```

- **`--tune`** reads the last review and counts its issues by category, by kind of drawing and
  by subject (the kind of project a drawing is of; an item drawn as *a smart mirror on a hall
  wall* is a `smart_mirror`). Fixed rules turn the counts into edits: lettering found while the
  requests name brands and model numbers leaves those fields out and adds a negative; sizes
  written on the picture add a negative against dimension labels; condition notes in a request
  leave them out; a scale or device issue says the sizes from the name and puts size facts
  first; an issue on a view adds its preset; an item drawn as a use with its setting missing
  is drawn in a home. For each kind of project with build issues, and each kind of part drawn
  at the wrong size, one Muse Spark call (operation `picture-tune`, about 0.01 USD) phrases a
  correction or a looks line from the reviews' own issues and briefs; with `--dry-run`, or
  without a key, the shortest proposed brief is kept as it is. A correction the owner approved
  in the demo set for a kind of project (`propose.corrections`) becomes that kind's
  correction. `picture-review/tune.md` lists each edit with why and the drawings behind it,
  then the diff; `tune.json` is the same list.
- **Approve.** Read `tune.md`. To drop or change an edit, edit its entry in `tune.json`; never
  the parameters file. Watch for a line that holds for one part but not for its whole kind.
- **`--tune --apply`** writes the list into `params.yaml` with `version` one up; it refuses a
  proposal made for another version.
- **`--redraw-set`** loads the set once with the key, in a record run where only drawings are
  bought: a drawing whose request is unchanged replays its recording, every other request
  answers from its recording or not at all. The drawings take what the reviews of the set
  leave of `--max-usd` (whole drawings only); then every drawing is reviewed. A parameter that
  every request says (a negative, a rule) redraws all 32: about 0.32 USD and 0.20 USD of
  reviews.
- **`--evaluate`** keeps the score of the last review for the version it was made with, in
  `eval/pictures/params-v<N>.json` (verdicts, issues by category, each drawing's verdict and
  the digest of its recording, the parameters themselves), writes `picture-review/compare.md`
  and the history table into *How the drawings were improved*, makes a contact sheet
  `picture-review/sheet-v<N>.jpg`, and lists the recordings the version before used and this
  one does not. `--prune` deletes them; nothing under `backend/tests/fixtures` is ever
  modified.

The first run, version 1 to 3, is in
[How the drawings were improved](../project/picture-review-results.md#tuning-the-parameters-version-1-to-3):
text issues 19 to 2, matches 11 to 21, wrong 1 to 5. With the review reading each part as built
and the best of three to five candidates kept for every drawing that still missed, a fresh
review of the final set: 29 matches, 2 partly, 1 wrong
([Best-of-N](../project/picture-review-results.md#best-of-n)); after the proposals were tuned
and their 17 drawings drawn again the same way, 28 matches and 2 partly of 30, none wrong.

### Best of N

Muse Image draws a different picture for every request; one request can miss where the next
lands. `--candidates N` draws a drawing N more times, each candidate a request of its own,
reviews every candidate against the drawing's facts and keeps the best:

```bash
./dev picture-review --candidates 3 --max-usd 1.5                    # every drawing not matching
./dev picture-review --candidates 3 --only project:4,project:7 --max-usd 1   # these, even matching
./dev picture-review --evaluate --stage best3 --prune                # score it beside the version
```

- **The candidates.** The first is drawn with the last review's corrected brief (or, for a
  drawing that matched, the brief it has); the next ones add a variant: another framing for a
  drawing with no view of its own (*seen at eye level from across the room*, *a three-quarter
  view from slightly above*, ...), a narrower scene for a close-up or a view from above (*only
  the parts listed, nothing extra on the table*, ...). Each brief is at most 400 characters,
  the variant kept whole. No candidate repeats the request the drawing already has.
- **The pick.** Better verdict first, then a surer review (confidence), then fewer issues. The
  drawing as it stands is scored by the last review and keeps its place on a tie, so a run
  never makes a drawing worse.
- **What is kept.** Only the winner's brief is written into `demo/set.yaml` (the item's
  `picture_brief` or `reuse_picture_brief`, the project's `propose.corrections` entry) and only
  its recording is copied into `backend/tests/fixtures/api/images-generations/`; the set is
  replayed after (0 not recorded, 0 stand-in answers). Every candidate, winner or not, is
  copied under `picture-review/candidates/<drawing>/`, with `picture-review/candidates.md`
  (each candidate's verdict, confidence, issues and brief) and `best-before.jpg` /
  `best-after.jpg`; none of it goes into the repository. The last review (`report.json`) takes
  the winners' reviews, so `--evaluate` scores the set as it now replays.
- **Cost.** A candidate is a drawing and its review, about 0.017 USD; the run stops before a
  candidate whose drawing and review could pass `--max-usd`, cutting the last candidates of
  every drawing rather than every candidate of the last drawings.
- **`--evaluate --stage WORD`** keeps the score as a later stage of the same version of the
  parameters (`eval/pictures/params-v<N>-<WORD>.json`), next to its first score in the history
  table; `--prune` then removes the recordings the stage before used and this one does not
  (the drawings replaced).

### The review gate

The same check runs on the owner's own drawings with `PICTURE_REVIEW_GATE` (unset: on with a
key, off in fixture mode); a demo visitor's drawing is answered from the recordings and never
checked or drawn again, and the demo set's loader never goes through the gate. A new drawing
is reviewed once and, when it is wrong or shows the main part at the wrong size or as another
device, drawn once more with the review's brief and reviewed again. Both are kept and the better one is shown; the caption says what the check
found. A bad drawing costs two drawings and two checks, about 0.035 USD.

`PICTURE_CANDIDATES` (default 1) is the best of N for the owner's own clicks: when the first
drawing misleads, the gate draws that many corrected candidates instead of one, each with the
review's brief and its own framing, checks each, and shows the best (verdict, then confidence,
then fewer issues; the first drawing stays when no candidate beats it). Every drawing is kept,
the others marked hidden. A candidate after the first is drawn only while the spend cap
(`SPEND_CAP_USD`) leaves room for it and its check; at 3, a bad drawing costs at most four
drawings and four checks, about 0.07 USD. A judge's code (its own limits,
[Demo access](../operations/demo-access.md)) always gets the one corrected drawing, and a
visitor or a code kept on the recordings none.

## Tuning the text parameters

The Decide cards, the ideas and the proposals are written by Muse Spark from a brief and fixed
instructions. What they are told beyond that is data too: the text parameters,
`backend/app/textparams/params.yaml`, versioned and read on each request:

| Section | What it changes |
|---|---|
| `version` | bumped by each `--tune --apply`; each version's score is `eval/decide/text-v<N>.json` |
| `scenarios` | the Decide cards (operation `scenarios`) |
| `uses` | the ideas, what an item is good for (operation `uses`) |
| `propose` | the proposals (operation `propose`) |

Each section has `facts_first` (the brief opens with the item's compatibility facts as the
rules read them: memory generation and form, socket, interface, size; the rules' pairings follow
the item's fields, before the profile), `constraints` (rules every answer respects),
`corrections` (mistakes the checks found, said as rules) and `banned` (phrases never to write,
such as *with the processor you own* when no owned processor fits). An empty section adds
nothing: its requests are word for word what they were, so their recordings still answer.

```bash
./dev decide-review --max-usd 1           # check every recommendation (picture-review/decide/report.md)
./dev decide-review --evaluate            # keep the score of this version
./dev decide-review --tune --max-usd 0.1  # propose edits (tune.md, tune.json)
./dev decide-review --tune --apply        # write them: version one up
./dev decide-review --rerecord --max-usd 2.5   # record the changed text again, check again
./dev decide-review --evaluate --prune    # score it, drop the recordings replaced
```

- **The check** is the one `picture-review --decide` runs (operation `decide-review`): each
  item's latest Decide cards, each item's ideas and each project's allocations against the
  items' facts and the owner's other items; a flag names where, the claim, the fact it
  contradicts and a severity.
- **`--tune`** groups the flags by section. Fixed rules: a flag on a part that does not fit
  (memory generation, socket, slot, interface) turns on `facts_first`; a card resting on what
  the owner lacks adds the owned-items constraint; a flag on a recorded condition (missing,
  bare) adds the condition constraint. One Muse Spark call (operation `decide-tune`, about
  0.01 USD) phrases at most four corrections and four banned phrases per section from the flags,
  general rules that name kinds of part, never one item.
- **Approve** by editing `picture-review/decide/tune.json`; drop a banned phrase that can be true
  (*works as it is* for an item with nothing wrong). An edit to `propose` records every project
  and its drawings again.
- **`--rerecord`** loads the set once with the key in a record run where only the Decide cards,
  the ideas, the proposals and Muse Image are bought; every other request must replay its
  recording or the run says it is not recorded. A changed Decide card changes its reuse-card
  drawing, which is drawn and recorded in the same run. Then every recommendation is checked.
- **`--only cards,ideas,project`** checks those kinds alone (11 project checks are about
  0.08 USD): run it two or three times on a version to see past the check's own spread, which
  is two or three flags a run. A partial check is never kept as a version's score.
- **Version numbers** go one above the file and above every version evaluated, so a version
  tried and not kept (`--keep`) keeps its number and its score.
- **`--evaluate`** keeps the score in `eval/decide/text-v<N>.json` (counts by section, each
  check's flags, the recordings the set's replay answered from, the parameters), writes the
  history table between the `text-history` markers of
  [How the drawings were improved](../project/picture-review-results.md#text-tuning), and with
  `--prune` deletes the recordings any earlier version used and this one does not (a version tried and not kept
  is earlier too).

`/decide-tune` (`tools/muse/decide-tune/SKILL.md`) is the Muse Code skill that walks the owner
through the same loop, with the same approval points and caps as `/picture-tune`.

## With Muse Code: the skill that tunes the parameters

`/picture-tune` is the Muse Code skill that evaluates and improves the drawing parameters. Its
source is `tools/muse/picture-tune/SKILL.md`; install it as the other one:

```bash
mkdir -p .agents/skills && ln -s ../../tools/muse/picture-tune .agents/skills/picture-tune
muse skills validate tools/muse/picture-tune
```

The skill file says its inputs (the demo set, the parameters, the earlier scores, the owner's
cap), its outputs (the report, the proposal, the new version, the recordings, the scores and
the table, a pull request), its rules (only `./dev`, the key never shown, a cap on every paid
step, never a hand edit of the parameters or the recordings, never a merge) and its approval
points: before the first paid step, before `--apply`, before `--redraw-set`, before the pull
request. In a session from the repository root, `/picture-tune` or *the drawings keep getting
the sizes wrong, tune the parameters*.

The first run, as the skill's steps ran it (the commands and what they printed, cut):

```text
$ ./dev picture-review --max-usd 1
set load (fixture): 32 picture(s), 0 not recorded, 0 stand-in answer(s), 0 skipped
32 drawing(s): 11 matches, 20 partly, 1 wrong; 0.2136 USD

$ ./dev picture-review --evaluate
parameters version 1: 32 drawing(s), 11 matches, 20 partly, 1 wrong

$ ./dev picture-review --tune --max-usd 0.1
23 edit(s) proposed, version 1 to 2; 0.0134 USD
  | 1 | facts.left_out | 19 issue(s) of legible text or logos; 30 request(s) name a brand,
  |   |                | a model or a part number, which the drawing then letters |
  | 5 | facts.from_name | the sizes (18 inch, 2.5 inch, 480 GB) are in the item's name ... |
  | 18 | kinds.monitor.looks | a computer monitor, far smaller than a television |
  ...
(the first proposal gave the monitor "a wide 16:9 monitor about 55 cm wide", wrong for the
 18 inch one; the phrasing now keeps a kind's line free of sizes, proposed again: 0.0134 USD)
(owner: yes to all 23)

$ ./dev picture-review --tune --apply
wrote params.yaml: version 2

$ ./dev picture-review --redraw-set --max-usd 1.5
record run: set load (record): 32 picture(s), 0 not recorded, 0 stand-in answer(s), 0.3200 USD
replay: set load (fixture): 32 picture(s), 0 not recorded, 0 stand-in answer(s)
32 drawing(s): 21 matches, 5 partly, 6 wrong; 0.5136 USD

$ ./dev picture-review --evaluate --prune
parameters version 2: 32 drawing(s), 21 matches, 5 partly, 6 wrong
removed 64 file(s) of 32 unused recording(s)

$ ./dev picture-review --tune --max-usd 0.1
10 edit(s) proposed, version 2 to 3; 0.0109 USD
(owner: drop projects.home_server, it would draw the laptop disassembled; yes to the rest)

$ ./dev picture-review --tune --apply
wrote params.yaml: version 3

$ ./dev picture-review --redraw-set --max-usd 1.5
32 drawing(s): 21 matches, 6 partly, 5 wrong; 0.5189 USD

$ ./dev picture-review --evaluate --prune
parameters version 3: 32 drawing(s), 21 matches, 6 partly, 5 wrong
removed 64 file(s) of 32 unused recording(s)
```

Then the checks of step 9 and the pull request; the owner merges.

## Try the skills yourself

Both skills, `/picture-review` (fix single drawings with a brief) and `/picture-tune` (change
what every drawing is asked with), step by step.

**1. Prerequisites.**

- Muse Code installed and signed in (`muse --version`; [Working with Muse Code](../development/muse-code.md)).
- A clone of the repository on `main`, with Docker running (`./dev setup --check`).
- `MODEL_API_KEY` in your shell or in `.env` for the paid steps. The hackathon's Model API
  credit ended with November 4, 2026: after that every live call bills the card on the Model
  API account. Nothing below needs the key until step 5.

**2. Install the skills** (once, from the repository root; `.agents/` stays out of git):

```bash
mkdir -p .agents/skills
ln -s ../../tools/muse/picture-review .agents/skills/picture-review
ln -s ../../tools/muse/picture-tune .agents/skills/picture-tune
muse skills validate tools/muse/picture-review
muse skills validate tools/muse/picture-tune
muse skills list --source project     # both listed once the workspace is trusted
```

**3. Start Muse Code in the repository root** with `muse`, and trust the workspace when asked
(project skills load only in a trusted workspace). Approve the `./dev` and `docker compose`
commands when the sandbox asks.

**4. The zero-cost path.** Nothing spent, no key:

```bash
./dev picture-review --dry-run           # every drawing and the facts it must show
```

`picture-review/report.md` lists the 32 drawings with their thumbnails, facts and requests.
`/picture-review` starts with this step and stops to say how many drawings there are; tell it
to stop there. The tests run in fixture mode and never spend (`./dev test`).

**5. A first live run with a small cap** (one drawing, about 0.01 USD):

```bash
./dev picture-review --only project:2 --max-usd 0.10    # the hall smart mirror, reviewed
./dev picture-review --tune --dry-run                    # rule edits from that review, free
```

`--tune --dry-run` needs a review with verdicts in `picture-review/report.json`; it proposes
the rule edits alone (no phrasing call) into `picture-review/tune.md`. Do not `--apply` a
proposal made from one drawing.

**6. `/picture-review`.** Ask *review the drawings* or type `/picture-review`. It runs the dry
run, says the cap and runs the review (`--max-usd 1`, about 0.21 USD for the 32 drawings),
shows a table of verdicts and the briefs for the wrong ones, and **stops for your approval of
each drawing to redraw** (yes, no, or your own brief). Then it redraws only those (0.01 USD a
drawing, about 0.01 USD a review), shows `picture-review/before.jpg` and `after.jpg`, checks that
nothing else moved, and **stops before the pull request**.

**7. `/picture-tune`.** Ask *tune the drawing parameters* or type `/picture-tune`. It says the
version, the number of drawings and the cost ahead and **stops before the first paid step**;
scores the current version (review and `--evaluate`); proposes edits (`--tune`, about 0.01
USD) and shows them from `picture-review/tune.md`, then **stops for your approval of each
edit**; applies them; **stops before `--redraw-set`** (about 0.32 USD of drawings and 0.20 USD
of reviews when every request changes); compares the versions (`--evaluate --prune`), and
**stops before the pull request**. One round is about 0.55 USD (the proposal, the set drawn
again and reviewed), 0.75 USD when the current version is scored first; it offers a second
only when drawings are still wrong.

**8. Where the outputs land.**

| File | Written by |
|---|---|
| `picture-review/report.md`, `report.json`, `pictures/` | a review, `--redraw-set` |
| `picture-review/redraw.md`, `before.jpg`, `after.jpg` | `--redraw` |
| `picture-review/tune.md`, `tune.json` | `--tune` |
| `picture-review/compare.md`, `sheet-v<N>.jpg` | `--evaluate` |
| `demo/set.yaml` (a brief) | `--redraw` |
| `backend/app/picture/params.yaml` | `--tune --apply` |
| `backend/tests/fixtures/api/images-generations/` (new drawings) | `--redraw`, `--redraw-set` |
| `eval/pictures/params-v<N>.json`, the table in *How the drawings were improved* | `--evaluate` |

`picture-review/` is not in git; everything else is, so `git status` shows what a run changed.

**9. Undo.** Before a commit, put everything back with git:

```bash
git checkout -- demo/set.yaml backend/app/picture/params.yaml eval/pictures \
  docs/project/picture-review-results.md backend/tests/fixtures   # restores pruned recordings too
git clean -n backend/tests/fixtures/api/images-generations eval/pictures   # list new files
git clean -f backend/tests/fixtures/api/images-generations eval/pictures   # delete them
./dev picture-review --dry-run   # set load: 0 not recorded, 0 stand-in answers again
```

The money spent is not undone: the spend is in the Model API account's billing.

## Getting better drawings over time

Muse Image is a hosted model. The Model API documents image generation and image edits for
it, and post-training only for the open-weight models (Muse Spark Open, Muse Glimmer); no
fine-tuning path for Muse Image was found as of November 3, 2026. The drawings get better
through what the app sends and what it does with the answer:

- **Facts first.** Built: the parameters' `facts` section (sizes from the name, size facts
  first, no brand or model number).
- **Negative constraints.** *not a TV*, *no text or labels*, *no tower case for a laptop
  board*: the review's briefs say them, and they work.
- **A corrections library.** Built: the parameters' `projects` and `kinds`, filled by `--tune`.
- **View presets.** Built: the parameters' `views`.
- **Reference photos.** The images API takes input images on its edits endpoint
  (`POST /v1/images/edits`); a drawing conditioned on the owner's photo of the part would get its
  shape and proportions right. Not built: it sends the owner's photo to the image model, which
  the privacy check of photos has to clear first.
- **A review gate.** Built: `PICTURE_REVIEW_GATE` ([The review gate](#the-review-gate)).
- **An evaluation set.** Built: `eval/pictures/params-v<N>.json`, one per version.
- **The review's facts for an item drawn as a use.** Built: the item as built, with the rest of
  the build its kind of project needs as what may appear.
- **Best of N.** Built: `--candidates N` for the demo set, `PICTURE_CANDIDATES` for the owner's
  drawings ([Best of N](#best-of-n)).
