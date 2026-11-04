# How the drawings were improved

The demo set's 32 drawings (13 of items and reuse cards, 19 of projects and their views) were
checked on November 3, 2026 with `./dev picture-review --decide`, each against the facts it had
to show ([Review and redraw the drawings](../guides/picture-review.md)). Five were drawn again
with a corrected brief and checked again.
Later the same day the requests themselves were changed: the drawing parameters were tuned
from these reviews, twice, and every drawing of the set was drawn again
([Tuning the parameters, version 1 to 3](#tuning-the-parameters-version-1-to-3)). The drawings
shown in the first sections are the ones version 1 drew.

## The review

| Verdict | Drawings |
|---|---|
| matches | 8 (7 item pictures, 1 project view) |
| partly | 22 (17 project drawings, 4 reuse cards, 1 item) |
| wrong | 2 |

Issues found, by category: legible text or logos 24, implausible 7, scale 4, missing part 3,
invented part 2, wrong setting 1. Most *partly* verdicts rest on text alone: the drawings
carry brand names (*DELL* on a bezel, *Kingston* on a drive) although every request asks for
none. They mislead nobody about the build and were left as they are.

The two **wrong**:

- **Hall smart mirror from 18 inch monitor** (`project:2#1`). Drawn as a widescreen television
  of 50 inches or more filling the wall above a bench, with *DELL 1800FP* written on the
  screen. The request named the monitor by *brand DELL, input voltage 100-240 V, model number
  1800FP*: a part carries at most three accepted values into the prompt, in alphabetical order,
  and the screen size was not among them.
- **The powerline adapter as a home automation link** (`item:powerline#1`). Drawn still in its
  plastic wrap, hanging off its cable. The item's own picture carries its condition (*still in
  its plastic wrap*), which the request said before the use (*unwrapped and plugged into the
  wall socket*).

Three more were redrawn as clearly off, though *partly*: the home server with a memory stick
drawn inside the laptop's lid (`project:5#1`), the NAS from above with a second drive and a
2.5 inch SSD drawn at 3.5 inch size (`project:4#3`), and the arcade coffee table from above with
its 24 inch monitor no wider than the laptop (`project:7#3`).

## Before and after

| Drawing | Before | After |
|---|---|---|
| Hall smart mirror (`project:2#1`) | ![before](../assets/picture-review/project-2-1-before.jpg){ width="240" } wrong | ![after](../assets/picture-review/project-2-1-after.jpg){ width="240" } matches |
| Powerline adapter (`item:powerline#1`) | ![before](../assets/picture-review/item-powerline-1-before.jpg){ width="240" } wrong | ![after](../assets/picture-review/item-powerline-1-after.jpg){ width="240" } matches (second brief) |
| Arcade coffee table, from above (`project:7#3`) | ![before](../assets/picture-review/project-7-3-before.jpg){ width="240" } partly | ![after](../assets/picture-review/project-7-3-after.jpg){ width="240" } matches |
| Home server and backup (`project:5#1`) | ![before](../assets/picture-review/project-5-1-before.jpg){ width="240" } partly | ![after](../assets/picture-review/project-5-1-after.jpg){ width="240" } partly (second brief) |
| Custom NAS, from above (`project:4#3`) | ![before](../assets/picture-review/project-4-3-before.jpg){ width="240" } partly | ![after](../assets/picture-review/project-4-3-after.jpg){ width="240" } partly (second brief) |

The briefs, as `demo/set.yaml` keeps them (`propose.corrections` and the adapter's
`picture_brief`):

- **smart_mirror**: *an 18 inch 5:4 computer monitor, about 46 cm across the diagonal, hidden
  behind a two-way mirror in a slim wooden frame about 45 x 40 cm, hung at eye level on a hall
  wall above a small bench; only a clock and weather icons glow through the glass; a small
  mirror, not a TV; no words or logos*
- **the adapter**: *exactly one small white powerline adapter, the size of a deck of cards, out
  of its wrap and plugged straight into the wall socket under the shelf, an Ethernet cable from
  it up to a small hub beside the router; the plastic wrap named above is how it lies in the
  drawer today, do not draw it; no second adapter, no words or logos*. The first brief, without
  the line on the wrap, came back *wrong* again: two adapters, one still wrapped.
- **arcade_table / from above**: *seen from above: a wooden coffee table with a glass top; under
  the glass a 24 inch widescreen monitor lies flat, about 53 x 30 cm, much wider than the opened
  laptop that runs it at one end; two joysticks and buttons along the edge; no words or logos*
- **home_server**: *an opened laptop about 35 cm wide on a wooden desk, wired to a router with
  antennas and to one bare 2.5 inch hard drive by a single cable; the memory is inside the
  laptop and not shown; no second drive, no extra box, no words or logos, not a desktop tower*.
  After: the memory is gone from the lid; the drive is drawn with network ports it does not
  have.
- **custom_nas / from above**: *seen from above: an open ATX mid-tower case on a desk, the
  desktop motherboard with a cooler and one full-length memory stick in the slot beside it, one
  2.5 inch SSD in a drive bay, a short PCIe card holding two M.2 drives in a slot, an ATX power
  supply and a network cable; no second drive, no words, logos or model numbers*. After: one
  drive, the adapter card in place; lettering on the board remains.

Each brief is its own request with its own recording; every other drawing sends what it sent
before, so its recording is unchanged. The set loads in fixture mode with 0 not recorded and 0
stand-in answers.

## The recommendations

The same run checked the 44 sets of Decide cards and the 11 projects' allocations against the
items' facts (55 text calls). 27 came back with flags, 36 of them major. They are reported,
not changed:

- **DDR4 memory on a DDR3 laptop.** The home automation server allocates the SK hynix 8 GB
  DDR4 laptop stick to the ThinkPad T510, which takes DDR3: the stick does not fit
  (`project:3`). The SK hynix card's own reuse line says the same of both ThinkPads.
- **No processor for any desktop board.** The cards for the three desktop boards, the desktop
  memory, the drives and the SSD suggest desktop builds *with the processor you own*; the only
  processor is a Slot 1 part of the Pentium II and III years, which fits none of the boards (LGA1155, AM4).
- **The M.2 USB enclosure as a project box.** Five cards for the UNO board and its modules
  build into *the enclosure*; the only one is an M.2 SSD enclosure, too small for an UNO board.
- **Adapters with nothing to adapt.** The M.2 adapters' cards plan for M.2 and U.2 drives the
  inventory does not have; every drive is SATA.
- **The weather station's logger** (`project:10`) logs over time with no storage allocated, and
  its breadboard power module has no breadboard.

These come from the model's reading of the cards; each is for the owner to confirm. The
allocations are kept by the rules on item kinds, not on memory generation or socket, which is
where the DDR4 stick on the T510 slipped through.

## Cost

| Step | Calls | USD |
|---|---|---|
| Review of 32 drawings and 55 recommendation checks | 87 Muse Spark | 0.69 |
| Redraw, first round: 5 drawings, 5 reviews | 5 Muse Image, 5 Muse Spark | 0.09 |
| Redraw, second round: 3 drawings, 3 reviews | 3 Muse Image, 3 Muse Spark | 0.05 |

An earlier run of the same review was stopped part way to make the calls concurrent, about
0.07 USD of reviews. In all, under 1 USD.

## The drawing parameters, version by version

Each version of the drawing parameters (`backend/app/picture/params.yaml`) scored on the whole
demo set: every drawing drawn with that version and reviewed
([Tuning the drawing parameters](../guides/picture-review.md#tuning-the-drawing-parameters)).

<!-- params-history:start -->

*Written by `./dev picture-review --evaluate` from `eval/pictures/`.*

| | params v1 | params v2 | params v3 |
|---|---|---|---|
| drawings | 32 | 32 | 32 |
| matches | 11 | 21 | 21 |
| partly | 20 | 5 | 6 |
| wrong | 1 | 6 | 5 |
| issues: text | 19 | 2 | 2 |
| issues: scale | 2 | 1 | 2 |
| issues: wrong_device | 0 | 2 | 3 |
| issues: missing_part | 2 | 4 | 2 |
| issues: invented_part | 1 | 5 | 4 |
| issues: wrong_setting | 0 | 1 | 2 |
| issues: implausible | 2 | 2 | 4 |
| spent on the run, USD | 0.21 | 0.51 | 0.52 |

Moved from v2 to v3:

- `project:10#1`: wrong to matches
- `project:6#1`: wrong to matches
- `item:dht11#1`: partly to matches
- `project:4#2`: wrong to partly
- `project:4#3`: partly to matches
- `project:7#2`: partly to matches
- `item:monitor_1800fp#1`: matches to partly
- `item:powerline#1`: matches to partly
- `project:9#1`: matches to partly
- `item:joystick#1`: matches to wrong
- `project:8#3`: matches to wrong

<!-- params-history:end -->

## Tuning the parameters, version 1 to 3

On November 3, 2026, after the redraws above, the Muse Code skill `/picture-tune` ran its loop
on the demo set: the 32 drawings reviewed as they were (version 1), the parameters tuned from
the review, the whole set drawn again and reviewed, twice.

**Version 2** (23 edits: 11 by the rules, 11 phrased by one Muse Spark call, 1 promoted from the
set; all approved):

- *Facts first*: the sizes in an item's name said (*screen size 18 inch, about 46 cm across
  the diagonal*), size facts before the rest, six values a part instead of three.
- *Nothing to letter*: brand, model and part numbers, certifications and voltages left out of
  every request (30 of 32 requests named a brand or a model), and a negative said before the
  closing words.
- *No condition*: an item drawn as a use no longer carries its condition notes (7 requests did).
- *In a home*: an item drawn as a use and a reuse card are drawn finished in their place, no
  longer on a plain background.
- *Corrections* for the home automation server, the home server and the kitchen dashboard
  (phrased from their issues and briefs), the smart mirror's approved brief promoted to every
  smart mirror, and how eight kinds of part look at their real size (*a tiny credit-card-sized
  bare board*).

At the approval step the first phrasing gave the monitor *a wide 16:9 monitor about 55 cm
wide*, true of the 24 inch one and wrong for the 18 inch 5:4 one behind the mirror; the
phrasing instructions now keep a kind's line free of sizes, and the proposal was made again.

**Version 3** (one more round on version 2's review): the sizes said for scale had come back
written on two drawings (*40 cm* beside the mirror), so a negative against dimension labels;
presets for the close-up and the view from above; corrections for the arcade table, the NAS,
the retro console and the weather station; the laptop's and the monitor's looks. One edit was
dropped at approval: a home server correction that would have drawn the laptop disassembled
(the review had judged the item's picture against the item as it lies in the drawer).

| Drawing | Version 1 | Version 3 |
|---|---|---|
| A second screen for the kitchen (`item:monitor_u2419h#1`) | ![v1](../assets/picture-review/tune-item-monitor-u2419h-1-v1.jpg){ width="200" } wrong: no kitchen | ![v3](../assets/picture-review/tune-item-monitor-u2419h-1-v3.jpg){ width="200" } matches |
| Second screen for a computer (`card:monitor_u2419h#1`) | ![v1](../assets/picture-review/tune-card-monitor-u2419h-1-v1.jpg){ width="200" } partly: a clamp, tools, lettering | ![v3](../assets/picture-review/tune-card-monitor-u2419h-1-v3.jpg){ width="200" } matches |
| Home automation server (`project:3#1`) | ![v1](../assets/picture-review/tune-project-3-1-v1.jpg){ width="200" } partly: the memory stick twice its size, lettering | ![v3](../assets/picture-review/tune-project-3-1-v3.jpg){ width="200" } matches |
| Smart desk calendar (`project:8#1`) | ![v1](../assets/picture-review/tune-project-8-1-v1.jpg){ width="200" } partly: lettering | ![v3](../assets/picture-review/tune-project-8-1-v3.jpg){ width="200" } matches |
| Arcade coffee table (`project:7#1`) | ![v1](../assets/picture-review/tune-project-7-1-v1.jpg){ width="200" } partly: lettering | ![v3](../assets/picture-review/tune-project-7-1-v3.jpg){ width="200" } wrong: the monitor upright on the glass |

What the numbers say:

- **Lettering is solved by not saying it.** Text issues went from 19 to 2: a request that
  names no brand and no model number gets none drawn; the two left are sizes written on the
  picture.
- **Matches went from 11 to 21**, and the partly verdicts from 20 to 6.
- **Wrong went from 1 to 5.** Without the lettering, the review looks at the build: an
  invented second monitor on the 18 inch monitor's reuse card, the arcade table's monitor
  standing on the glass, a calendar drawn with a joystick. Two of the five are partly the
  review's own: the facts of an item drawn as a use still list its condition (*disassembled*)
  and the item alone as its parts, so the router of a home server is called invented. Verdicts
  also move from run to run on the same request; every request changed between versions, so
  one drawing's move is not a measure, the set's counts are.

| Step | Calls | USD |
|---|---|---|
| Version 1 reviewed | 32 Muse Spark | 0.21 |
| Version 2 proposed (twice) | 2 Muse Spark | 0.03 |
| Version 2 drawn and reviewed | 32 Muse Image, 32 Muse Spark | 0.51 |
| Version 3 proposed | 1 Muse Spark | 0.01 |
| Version 3 drawn and reviewed | 32 Muse Image, 32 Muse Spark | 0.52 |
| In all | | 1.28 |

The recordings of versions 1 and 2 that version 3 no longer uses were removed
(`--evaluate --prune`); every other recording is unchanged, and the set loads with 0 not
recorded and 0 stand-in answers.

## What it says about the prompt

- **Facts first.** The size of the main part is what a drawing gets wrong most visibly, and the
  prompt leaves it out whenever three other values sort before it. The name the owner gave the
  item (*Dell 1800FP monitor, 18 inch*) says it and is never sent, by design.
- **The item as it is today is not the item as used.** An item drawn *as* a use still carries
  its present condition; the project prompt already leaves the condition out.
- **No logos is asked and not kept.** A third of the issues are lettering; a brief that says
  *no words, logos or model numbers* removed most of it, the general request did not.

Each of these is now a parameter (version 2 and 3 above). Still open: the review's facts for
an item drawn as a use, which should be the item as built.

The next steps are in
[Getting better drawings over time](../guides/picture-review.md#getting-better-drawings-over-time).
