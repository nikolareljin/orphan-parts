---
description: Where Orphan Parts Lens ended up after the nine days of the hackathon, what had to change to get there, and what comes next.
---

# Hackathon conclusion

!!! success "Where it ended up"
    Orphan Parts Lens was built between October 27 and November 4, 2026, for the Meta Global AI
    Developer Hackathon. It reads what is in a drawer of old parts, decides with the owner what
    each thing becomes (keep and fix, reuse in a build, sell, give away) and finds the missing
    piece, with every answer backed by its evidence, on Meta's models: Muse Spark, SAM 3.1,
    Muse Voice Transcribe and Muse Image. The demo set is two drawers of the owner's own parts,
    49 items, each with the answers the models gave, readable by anyone on the
    [live demo](https://orphan-parts.pages.dev) (temporary, while the hackathon is judged) or on
    [your own computer](../start/local.md).

## What had to change on the way

The first plan was larger and more automatic than what shipped. Each change below came from
something that did not hold up once it met real parts, real photos or real rules.

!!! warning "Dropped or narrowed"
    - **A community exchange became one owner's inventory.** The first idea connected owners,
      donors and helpers around a repair. Nine days were enough to make one person's inventory
      trustworthy, not a network; the exchange is now [Marketplace](../guides/marketplace.md),
      both ways.
    - **Automatic Marketplace search and posting became a handoff.** There is no listing API for
      individuals, and fetching Marketplace pages on someone's behalf is against its terms. So the
      app writes the searches as Marketplace links the owner opens, ranks the listings the owner
      brings back (pasted text or a screenshot) by its rules, and writes the sale or giveaway
      draft in Marketplace's own fields, with the photos zipped in order, for the owner to paste
      into the create page. Slower by a few clicks, and nothing is ever posted or searched
      without the owner.
    - **The Meta glasses app was cut** for time and hardware: a second device target, and the
      glasses with their developer toolkit in hand, did not fit the window. The phone does the
      capture.
    - **Muse Wonder and Muse Spark Open were considered and not used** in this version; their
      pages say what for.
    - **Open uploads for visitors became a sample gallery.** A visitor's own photo got the
      recorded answer of another photo, which read as a wrong answer. Visitors now click the
      demo set's photos, and each answer is the recording of that exact photo.
    - **Concept previews left the demo video.** The video shows only what was built.

!!! tip "Added to make the results trustworthy"
    - **Rules decide, the model proposes.** Fit verdicts, kept comparables and project
      allocations come from rules in data files; a model answer that nothing backs is dropped.
    - **Web results backed by the search.** Muse Spark's web finds are kept only when the page is
      among the results the search actually returned, matched by host and path when the model
      trims a URL.
    - **The device a part came from.** A part with no model number of its own made the search
      guess, so the app now asks for the device it came from and reads it from a photo of that
      device's label.
    - **Measured, not typed.** The agitator's rod diameter is measured from a ruler photo
      (4.7 ± 0.5 mm) instead of values nobody had checked.
    - **Private details hidden in photos.** Real photos of real parts carry serial numbers,
      product keys, MAC addresses and codes. Muse Spark finds them and every copy that leaves the
      owner's view is blacked out; the owner reviews the outline before sharing.
    - **Saved results, never generated twice.** Every Decide answer, draft, price, search plan,
      drawing and build pack is kept with its date and model; opening it again shows what it
      said, and asking again adds a version.
    - **A second look at the drawings.** Muse Image drew a hall smart mirror from an 18-inch
      monitor as a 50-inch television, and project drawings came out with censor-like blots
      copied from the parts' condition notes. So the drawing prompt was rebuilt from what the
      finished build is made of (each part's kind, model and size, not its scratches), and a
      review step was added: Muse Spark looks at each drawing next to the facts it must show,
      flags what does not match (scale, missing or invented parts, the wrong device, fake
      labels), and writes a corrected brief; the owner approves, Muse Image draws again, and the
      new drawing is reviewed once more. The first review of the 32 demo drawings found 8 that
      matched, 22 that partly matched and 2 that were wrong (the mirror, and an adapter drawn in
      its plastic wrap); both wrong ones match after a corrected brief. Then the requests
      themselves were tuned (the drawing parameters, three versions), the review was made to
      read each part as built, and every drawing that still missed was drawn three to five
      times with the best kept: on a fresh review of the final set, 29 of the 32 drawings
      match, 2 partly and 1 is wrong, from 17, 7 and 8 just before. The tool is
      `./dev picture-review`, also a Muse Code skill: [Review and redraw the
      drawings](../guides/picture-review.md); the results, before and after: [How the drawings
      were improved](picture-review-results.md).
    - **A check of the recommendations themselves.** The same review read the Decide cards and
      project allocations against the facts and flagged 27 of 55, among them a DDR4 memory stick
      allocated to a DDR3 laptop and desktop builds that assume a processor the boards cannot
      take. Compatibility rules followed (generation, form, socket, interface), and then the
      cards' own instructions were tuned from the flags: the item's compatibility facts first,
      a card resting only on owned parts that fit, *with the processor you own* banned. Of the
      44 sets of Decide cards, 16 were flagged before and 10 after; a third round did no better
      and was not kept ([Text tuning](picture-review-results.md#text-tuning)).

The full list, in the order it was learned, is on [Lessons learned](lessons.md); the dated log
is [Built during the hackathon](hackathon.md).

## What comes next

!!! example "Next steps"
    - **WhatsApp:** an item's record, photos and question sent to a repair shop or a buyer, by
      handoff first.
    - **Email notifications:** a search that finds a fitting listing, a draft that went stale, a
      price that moved, sent to the owner instead of waiting to be looked at.
    - **Meta glasses:** hands-free capture of the item and its label with the spoken note, into
      the same Inbox.
    - **Accounts instead of a shared code,** so each person has their own inventory.
    - **The Android app on Google Play.**
    - **Posting to Marketplace** from the app, once there is a listing API for individuals.
    - **Better drawings over time:** the review gate on by default with best of three for the
      owner's own drawings (`PICTURE_CANDIDATES`), and the proposals tuned like the Decide
      cards, once their re-recording (every project and its drawings) fits the budget.
    - **A second model route** through Muse Spark Open for the planning steps.

Each one, with why and what it needs, is on [Next steps](next.md).
