# How the drawings were improved

The demo set's 32 drawings (13 of items and reuse cards, 19 of projects and their views) were
checked on November 3, 2026 with `./dev picture-review --decide`, each against the facts it had
to show ([Review and redraw the drawings](../guides/picture-review.md)). Five were drawn again
with a corrected brief and checked again.

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

## What it says about the prompt

- **Facts first.** The size of the main part is what a drawing gets wrong most visibly, and the
  prompt leaves it out whenever three other values sort before it. The name the owner gave the
  item (*Dell 1800FP monitor, 18 inch*) says it and is never sent, by design.
- **The item as it is today is not the item as used.** An item drawn *as* a use still carries
  its present condition; the project prompt already leaves the condition out.
- **No logos is asked and not kept.** A third of the issues are lettering; a brief that says
  *no words, logos or model numbers* removed most of it, the general request did not.

The next steps are in
[Getting better drawings over time](../guides/picture-review.md#getting-better-drawings-over-time).
