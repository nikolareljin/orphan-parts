# Demo walkthrough

Sixty seconds through what is built, in the order a person meets it, on a stack started with
`./dev up` in fixture mode (no key: every model answer is a recorded one and nothing is spent).
With a key, the same steps run live. The demo set is a drawer of idle things, photographed by
the owner: three monitors, two ThinkPads and a spare laptop board, an old graphics card, a slot 1
processor, a powerline adapter still in its wrap, and the worn agitator of a frappé maker.

## The set, loaded

`demo/set.yaml` names the things in the walkthrough: each one's photos, what the owner knows
about it, whether a draft or price guidance is written for it, the searches with the listings
brought back (written examples labelled as such), and the proposal brief. Three commands:

```bash
./dev demo-scrub ~/raw-photos   # re-encoded copies into demo/photos/, WAV notes into demo/notes/
./dev record-fixtures           # with a key: the inventory reset, one run, every answer kept;
                                # a run that stopped half-way picks up where it was (what is
                                # recorded is replayed, not bought again) and fails when a part
                                # of the set was skipped; delete a fixture file to record it afresh
./dev demo                      # the inventory reset and the set loaded, in fixture mode
```

`./dev demo` leaves the stack with the whole set in the inventory, every observed value
accepted, drafts, guidance, searches with their candidates and the proposals in place, so
every take and every visitor starts from the same screen. Once the fixtures for the set are
recorded, the demo spends nothing: the service line at the foot of every page says *recorded answers only (nothing spent)*.
The fixtures are keyed on what is sent, so a change to `EXTRACT_ENHANCE` or `IMAGE_MAX_PX` means
recording again. A photo not in the set gets the recorded answer for that operation, which is why the public
demo is the set, not an open reader. The set loads with whatever files are present; a photo
named but missing is skipped with a note.

## 1. Read a label and save it

**Read a label** takes up to four photos. With *Find the label in the photo first* on, SAM 3.1 finds the
item, the label and the connector and the overlay shows where; Muse Spark reads the label crop
into typed fields, each with its confidence and its source. **Save privately** makes it an item
in [My inventory](../guides/inventory.md): every observed value waits for you to confirm or
reject it, and anything you add beside it carries your word as its provenance.

## 2. Measure the thing that decides fit

On the agitator's page, **Measure a feature**: the rod photographed from the side with a ruler
along it, two marks on the ruler and two on the rod, and the number comes from geometry, with
its uncertainty and the method. A blurred or oblique capture is refused with the reason.
[Measure a feature](../guides/measure.md).

## 3. Does a listed rod fit?

**Does it fit?** checks a candidate against the agitator's profile rule by rule: the all-metal
rod of the same size passes, the plastic one is rejected on its material and its diameter, the metal
one with wider tabs is rejected on the span, and the listing with no measurements stays at
*needs evidence*, its unknowns turned into questions. The verdict is one of five on the
[ladder](../concepts/verdicts.md), decided by the rules, never by the model.
[Does it fit?](../guides/match.md).

## 4. Find the missing piece

**Find a part** records what the agitator needs (all metal, a 4 mm rod, two tabs 9 mm across)
and hands off a Marketplace search for you to run.
A listing brought back as its text is read by Muse Spark into fields, dated, assessed by the
same rules and placed where it stands; **Ask the seller** turns the open questions into a
message. [Find a part](../guides/search.md).

## 5. What could the monitors become?

**Build and reuse**: say what you want from a build, ask for proposals, and Muse Spark reads the
inventory through tools and proposes projects from templates kept as data; only what names
items you own is shown: a homework workstation on the 24 inch Dell and a retro console on the
18 inch one. Select the homework workstation: its items are committed, the budget line says what
is left, the missing cable becomes a search, and the build pack is one document from
what stands. Record the outcome once it works. [Build and reuse](../guides/reuse.md).

## 6. Sell the graphics card, give the processor away

On the graphics card, **What is it worth?** has Muse Spark search for listings and sales of the
same model and keeps only the comparables a page backs; asking, sold, reported and estimated
stay four numbers. **Prepare to sell** writes an honest draft from confirmed values with the
disclosures the rules append; the slot 1 processor goes as a free-pickup draft, and the older
ThinkPad as one with the data-removal steps. **Open Marketplace** hands the draft over; posting is yours.
[Value an item](../guides/value.md), [Seller flow](../guides/seller.md).

## 7. On the phone

The Android app points at the same backend: a photo of a label read and saved into the same
inventory, and a voice note held to the item, kept as your words and read back.
[Android app](../guides/android.md).

## Running it in public

Behind an access code with allowances per visitor and per day, a spend cap and an operator's
switch: [Demo access](../operations/demo-access.md).
