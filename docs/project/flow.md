---
description: One diagram of Orphan Parts Lens, every box a link; two paths from the demo set walked step by step; where to try it.
---

# How it fits together

Two capture devices, one Inbox, three models that read, a private inventory in the middle, and
four paths out of it, with Marketplace at the end of two of them by handoff. Around all of it,
two doors. Every box in the diagram opens the page that describes it. Blue is where a model
answers; a dark border is where the rules decide; a dashed box is a step you run yourself on
Marketplace.

<div class="flow-diagram">
--8<-- "assets/flow.svg"
</div>

The split is the whole design: Muse Spark, SAM 3.1 and Muse Voice Transcribe read, write and
propose, and Muse Image draws a picture of what an item could become only when you ask; the
profile's rules, the inventory and your own confirmations decide what is kept. A model never
moves a candidate up the [verdict ladder](../concepts/verdicts.md), never adds a line to a
listing draft that no confirmed field backs, never changes a
[profile](../concepts/profiles.md) or a project template, and a drawn picture is never
evidence. The
[architecture](../development/architecture.md) page shows the same split from the inside.

## One path through: the crevice tool

The demo set is a drawer of idle things; this is the vacuum in it, the tool that fits and the
near miss.

1. The vacuum and the two loose crevice tools are photographed on the phone's **Capture** tab,
   each with a spoken word on what is known (*runs; the crevice tool is missing*), and sent.
   [Capture from the phone](../guides/capture.md).
2. In the web app's **Inbox**, **Read it**: SAM 3.1 finds the label crop, Muse Spark reads what
   the label says, the note is kept as the owner's words. Each capture becomes an item with its
   photos above the values to confirm. [My inventory](../guides/inventory.md).
3. On the vacuum, the wand's outer diameter goes in under **Add what you know**. On each tool,
   **Measure a feature**: the opening photographed straight on across a ruler, two marks on the
   ruler, two on the opening, and the inner diameter comes back with its uncertainty and the
   method: 32.2 mm on one tool, 35 mm on the other. [Measure a feature](../guides/measure.md).
4. **Does it fit?** on each tool against the vacuum: the rules of the `vacuum_attachment`
   profile, one at a time. The near miss fails the opening's tolerance and ends in `CONFLICT`.
   The right one passes on the dimension, with the latch still unknown, and that unknown
   becomes a question rather than a pass. [Does it fit?](../guides/match.md),
   [Verdict ladder](../concepts/verdicts.md).
5. **Find a part** records what the vacuum needs with a top price and hands off the Marketplace
   search for you to run. Two listings brought back as their text are read by Muse Spark,
   assessed by the same rules, dated and placed where they stand; **Ask the seller** turns the
   open questions into a message. [Find a part](../guides/search.md).

## Another path: the homework desk

1. The old laptop (*boots, battery weak*), the spare monitor (*works, one HDMI input*), the USB
   keyboard and the webcam are in the inventory with the intent *use in a build*.
   [My inventory](../guides/inventory.md).
2. Under **Build and reuse**, what you want from a build is kept once: *a quiet desk for
   homework*, low effort, a budget of 50 USD. [Build and reuse](../guides/reuse.md).
3. **Propose**: Muse Spark reads the inventory and the project templates through tools and
   proposes projects; the homework workstation names the laptop, the monitor and the keyboard.
   The rules keep only allocations the inventory backs: an item you have, usable, of a kind the
   requirement takes. [Agent tools](../reference/agent-tools.md).
4. **Select** it: the items are committed and reserved, one build per item; the budget line says
   what is left; the missing video cable becomes a search request with the budget left as its
   top price. [Find a part](../guides/search.md).
5. The **build pack** is one Markdown document written by the rules from what stands, with a
   version and a digest of its inputs, stale when an input changes. Once the desk works, the
   outcome in your words marks the project done. [Build and reuse](../guides/reuse.md).

## Try it

- The hosted site: [orphan-parts.pages.dev](https://orphan-parts.pages.dev).
- The release, with the Android app as an APK:
  [github.com/nikolareljin/orphan-parts/releases/latest](https://github.com/nikolareljin/orphan-parts/releases/latest).
- The app on your phone in ten minutes:
  [On your phone in ten minutes](https://nikolareljin.github.io/orphan-parts/start/judges/);
  from a machine of your own, the [Quickstart](../start/quickstart.md).

The hosted demo answers every visitor from recorded answers for the demo set and keeps
nothing; the access code opens the live models and saving. [Demo access](../operations/demo-access.md).
