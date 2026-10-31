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

## One path through: the frappé agitator

The demo set is a drawer of idle things; this is the frappé maker in it, whose agitator wore
out, and the rods listed to replace it.

1. The agitator is photographed on the phone's **Capture** tab beside a tape measure, with a
   spoken word on what is known (*the base runs; the rod no longer mixes*), and sent.
   [Capture from the phone](../guides/capture.md).
2. In the web app's **Inbox**, **Read it**: there is no label to read, so the item keeps its
   photos and the owner's words. [My inventory](../guides/inventory.md).
3. **Measure a feature** on the side photo: two marks on the ruler, two on the rod, and the
   diameter comes back with its uncertainty and the method. Under **Add what you know** go the
   tab span, width and length, the rod's length, and the material wanted: metal.
   [Measure a feature](../guides/measure.md).
4. **Find a part** records what the agitator needs with a top price and hands off the
   Marketplace search for you to run. Four listings brought back as their text are read by Muse
   Spark and checked by the rules of the `blender_agitator` profile, one at a time: the
   all-metal rod of the same size is a documented candidate (`COMPATIBLE_LIKELY`), the plastic
   rod fails on its material and its diameter and the metal one with wider tabs on the span
   (`CONFLICT`), and the listing with no measurements needs evidence (`INSUFFICIENT_INFO`).
   **Ask the seller** turns the open questions into a message.
   [Find a part](../guides/search.md), [Verdict ladder](../concepts/verdicts.md).

## Another path: the homework desk

1. The Dell U2419H and Dell 1800FP monitors, read from their rating labels, and the ThinkPad
   T510, opened with its keyboard off, are in the inventory with the intent *use in a build*.
   [My inventory](../guides/inventory.md).
2. Under **Build and reuse**, what you want from a build is kept once: *a quiet desk for
   homework*, low effort, a budget of 50 USD. [Build and reuse](../guides/reuse.md).
3. **Propose**: Muse Spark reads the inventory and the project templates through tools and
   proposes projects; the homework workstation names the 24 inch monitor and lists the laptop,
   the cable, the keyboard and the mouse as missing, since the T510 is not yet known to work.
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
