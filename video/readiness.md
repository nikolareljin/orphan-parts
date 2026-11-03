# Capabilities and scene readiness

What the app does today (release 0.3.2), what it does not, and what each scene needs before it
can be cut. The video shows only features built during the hackathon, as working, and labels
recorded answers and sample data; what is not built is not shown.

## Capabilities

| Capability | In the app | Shown as |
|---|---|---|
| Capture on the phone: photos, a short clip, a spoken note, Send; Captures, **Read it now** | built (Android app) | working (S19 shows photos only) |
| The phone asks which device a part came from, under a read capture | built (Android app) | named in the notes, not on screen unless the phone take shows it |
| Pairing the phone by QR code from the web app (**Pair the phone**) | built | not shown (a QR code carries a pairing token) |
| Sign in with the access code, **Sign out** | built | working (S21 signs out) |
| Sample gallery for visitors: signed out, Read a label offers the demo set's photos, each answer a recording | built | working |
| Upload a capture from a laptop (**Inbox**, *Send a capture from this computer*) | built | not shown |
| Read a label: SAM 3.1 finds the label crop, Muse Spark reads it, values stay *to confirm* | built | working, on recordings (S21: SAM 3.1's regions, then the reading) |
| Which device did this part come from? A part with no model of its own asks; the owner answers in words or with a photo of the device (one Muse Spark reading) | built | working (S05, S07) |
| Spoken notes kept as the owner's words (Muse Voice Transcribe) | built | working (S18, a voice note in the listing details) |
| Measure a feature against a ruler, with method and uncertainty | built (no model) | not shown; the demo set's rod diameter is its result (4.7 ± 0.49 mm) |
| Agitator profile `blender_agitator` (rod diameter, tab span, tab width, tab length, rod length, head diameter, material rule) | built (data) | working |
| Find a part: **Plan the search** (phrasings, a match pattern, exclusion words, **Score** listings with no model call) | built | not shown (the stand-in plan is a charger's) |
| **Search the web** for a part: one Muse Spark call with web search; a find is kept only when its page is in the search's results | built | working (S08) |
| **Check fit**: a listing read by Muse Spark, the verdict from the profile's rules, unknowns as seller questions | built | working (S08) |
| Decide: **What should I do with it?** Keep and fix, reuse it, sell or give away, for the skills profile | built | working (S09) |
| Skills profile (none to pro) and what I want from a build | built | working (S11) |
| **Propose** (Muse Spark, up to five, through tools), the rules keep only backed allocations | built | working (S12) |
| Templates: arcade coffee table, smart mirror, home automation server, home server, retro console, and five more | built (data) | working |
| Select and commit: one item per selected build, conflicts with **Move it here** | built | working (S13) |
| **Draw it** on reuse cards and projects: one Muse Image call, captioned as drawn | built | working (S14) |
| **Find it on Marketplace** for a missing requirement; **Search Marketplace** opens the search for you to run | built | working, by handoff (S15) |
| Build pack: Markdown written by the rules, versioned, stale on change, **Download** | built | working (S16) |
| Value an item; Facebook Marketplace (US) sell or give-away drafts, **Copy**, **Download photos**, **Open Marketplace** | built | working (S17, S18; Open Marketplace pointed at, never opened) |
| Outcome in your words, shared only as a redacted text when switched on | built | not shown |
| Evaluation loop: `./dev eval` scores the demo set load against the rules | built | not shown |
| Hosted demo (Cloudflare Pages and Modal) | built | not shown; the drafts are recorded locally |
| Donor-appliance search, another device for the same result | not built | not claimed |
| Re-planning when the display changes, connection diagrams, assembly views | not built | not shown |
| Downloadable CAD, bracket or housing designs | not built | not shown |
| Posting to or searching Marketplace automatically | not built, out of scope | never implied |
| Muse Spark Open on Baseten or Fireworks | not integrated; backlog | not shown |

## Scenes

**Summary: 22 shots in the main video. 14 are web takes recorded by `video/generate.sh`, all on
recorded answers (the shots marked *record* were recorded once with `--record`, last on Nov 3),
1 is the phone, 4 are the owner's photos, 3 are cards rendered here. No concept previews.**

| Shot | Scene | Status | What it needs |
|---|---|---|---|
| S01, S02, S04, S06 | The owner's photos: the mixer, unused electronics, the mixer's side and the worn agitator, the label | photos | `demo/photos/` (in the repository) |
| S03, S20, S22 | Cards | card | `brand/card-*.png` |
| S05 | The app asks which device the part came from | now | the stage (the demo set, the agitator's device unanswered) |
| S07 | The label answers it | record | the reading of `hamilton-729-label.jpg` alone (op `extract`) |
| S08 | Search the web, Check fit | record | the web search for the agitator search with the device read in S07 (op `part-search`); the reading of the first page found (op `listing-text`) |
| S09 | Decide: keep and fix | record | the agitator's scenarios for the skills profile at that point (op `scenarios`) |
| S10, S11 | The inventory; skills and what I want from a build | now | the stage |
| S12 | Five proposals | record | the proposals for the preferences typed in S11 (recorded: three kept, no arcade; the shots follow the home automation server base) (ops `propose-1`, `propose-2`, ... one per tool round) |
| S13, S15, S16 | Select, Find it on Marketplace, the build pack | now | S12's project (no model call) |
| S14 | Draw it | record | the drawing of S12's project (Muse Image, op `picture`) |
| S17 | The graphics card: what it is worth | now | the price guidance the demo set records (op `price`) |
| S18 | A voice note, then the draft | record | the note's transcript (op `transcribe`); the sell draft with it (op `draft-sell`) |
| S19 | On the phone | now | the phone take (`--phone`), else the app's screenshots |
| S21 | Signed out, the sample gallery, SAM 3.1 | now | the sample recordings already in the repository (ops `segment-*`, `extract`) |

Short video: K1 and K9 are cards, K2 the owner's photos, K3 to K8 reuse S07, S08, S12, S14,
S15 and S18.

## The live recordings

The answers below are recorded (`backend/tests/fixtures/api`) and replay in fixture mode. To
record again after a change (the stage, the preferences of S11, the photos), one run records
every answer the shots need, with the owner's key from the shell; it is
never written to a file, and the run stops at `VIDEO_SPEND_CAP_USD` (1 USD unless set):

```bash
export MODEL_API_KEY=...        # in this shell only
video/generate.sh --record
git status backend/tests/fixtures/api   # the new recordings: review, then commit them
unset MODEL_API_KEY
video/generate.sh               # the drafts, now on the recorded answers
```

| Shot | Operation | Model | Estimated cost |
|---|---|---|---|
| S07 | read the label photo of the device (`extract`) | Muse Spark | $0.003 to $0.008 |
| S08 | Search the web (`part-search`, up to `PART_MAX_SEARCHES`=4 searches) | Muse Spark with web search | $0.04 to $0.07 |
| S08 | Check fit on the first page found (`listing-text`) | Muse Spark | $0.002 to $0.006 |
| S09 | What should I do with it? (`scenarios`) | Muse Spark | $0.003 to $0.01 |
| S12 | Propose, five projects (the tool loop, `propose-N`) | Muse Spark | $0.02 to $0.06 |
| S14 | Draw it on the project (`picture`) | Muse Image | $0.01 |
| S18 | the voice note (`transcribe`), then the sell draft (`draft-sell`) | Muse Voice Transcribe, Muse Spark | $0.005 to $0.02 |
| | **Total** | | **about $0.09 to $0.19** |
| S19 | the phone's capture, read once (`--phone --record`, still to do) | Muse Spark (and SAM 3.1) | about $0.01 |

Outside the shots, the demo set's agitator is answered by reading its four device photos (the
label, the badge, the mixer and its side view), nothing typed; that reading is recorded
(`extract`, about $0.01, Nov 2) with `PICTURE_ENABLED=0 ./dev record-fixtures`, which leaves
the set's unrecorded item drawings out.

The ranges are the live check's per-operation figures (`livecheck/README.md`); the cap holds
the worst case. A request already recorded is replayed, not bought again, so a run that stops
half-way is resumed for free. The recordings are keyed on what is sent: the shots must run in
the same order on the same stage, which the generator does; a change to the demo set, the
preferences typed in S11 or `EXTRACT_ENHANCE`/`IMAGE_MAX_PX` means recording again.
