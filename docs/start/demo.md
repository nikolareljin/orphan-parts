# Demo walkthrough

Sixty seconds through what is built, in the order a person meets it, on a stack started with
`./dev up` in fixture mode (no key: every model answer is a recorded one and nothing is spent).
With a key, the same steps run live. The demo set is a drawer of idle things: a vacuum that
lost its tool and a few loose tools, two old laptops, a spare monitor, a keyboard, a broken
phone, a power adapter.

## The set, loaded

`demo/set.yaml` names the things in the walkthrough: each one's photos, what the owner knows
about it, whether a draft or price guidance is written for it, the searches with the listings
brought back (written examples labelled as such), and the proposal brief. Three commands:

```bash
./dev demo-scrub ~/raw-photos   # re-encoded copies into demo/photos/, WAV notes into demo/notes/
./dev record-fixtures           # with a key: the inventory reset, one run, every answer kept
./dev demo                      # the inventory reset and the set loaded, in fixture mode
```

`./dev demo` leaves the stack with the whole set in the inventory, every observed value
accepted, drafts, guidance, searches with their candidates and the proposals in place, so
every take and every visitor starts from the same screen. Once the fixtures for the set are
recorded, the demo spends nothing: the Service card says *fixture mode (recorded answers)*.
A photo not in the set gets the recorded answer for that operation, which is why the public
demo is the set, not an open reader. The set loads with whatever files are present; a photo
named but missing is skipped with a note.

## 1. Read a label and save it

**Read a label** takes up to four photos. With *Find the label first* on, SAM 3.1 finds the
item, the label and the connector and the overlay shows where; Muse Spark reads the label crop
into typed fields, each with its confidence and its source. **Save privately** makes it an item
in [My inventory](../guides/inventory.md): every observed value waits for you to confirm or
reject it, and anything you add beside it carries your word as its provenance.

## 2. Measure the thing that decides fit

On the vacuum's page, **Measure a feature**: the opening photographed straight on with a ruler
across it, two marks on the ruler and two on the opening, and the number comes from geometry,
with its uncertainty and the method. A blurred or oblique capture is refused with the reason.
[Measure a feature](../guides/measure.md).

## 3. Does the loose tool fit?

**Does it fit?** checks a candidate against the vacuum's profile rule by rule: the near-fit tool
is rejected on the dimension it misses, the right one passes with the latch still unknown, and
that unknown becomes a question. The verdict is one of five on the
[ladder](../concepts/verdicts.md), decided by the rules, never by the model.
[Does it fit?](../guides/match.md).

## 4. Find the missing piece

**Find a part** records what the vacuum needs and hands off a Marketplace search for you to run.
A listing brought back as its text is read by Muse Spark into fields, dated, assessed by the
same rules and placed where it stands; **Ask the seller** turns the open questions into a
message. [Find a part](../guides/search.md).

## 5. What could the laptops become?

**Build and reuse**: say what you want from a build, ask for proposals, and Muse Spark reads the
inventory through tools and proposes projects from templates kept as data; only what names
items you own is shown. Select the homework workstation: its items are committed, the budget line
says what is left, the missing cable becomes a search, and the build pack is one document from
what stands. Record the outcome once it works. [Build and reuse](../guides/reuse.md).

## 6. Sell the phone, give the keyboard away

On the broken phone, **What is it worth?** has Muse Spark search for listings and sales of the
same model and keeps only the comparables a page backs; asking, sold, reported and estimated
stay four numbers. **Prepare to sell** writes an honest draft from confirmed values with the
disclosures the rules append, and the keyboard goes as a free-pickup draft with the
data-removal steps. **Open Marketplace** hands the draft over; posting is yours.
[Value an item](../guides/value.md), [Seller flow](../guides/seller.md).

## 7. On the phone

The Android app points at the same backend: a photo of a label read and saved into the same
inventory, and a voice note held to the item, kept as your words and read back.
[Android app](../guides/android.md).

## Running it in public

Behind an access code with allowances per visitor and per day, a spend cap and an operator's
switch: [Demo access](../operations/demo-access.md).
