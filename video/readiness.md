# Capabilities and scene readiness

What the app does today, what it does not, and what each proposed scene needs before it can
be recorded. The video shows built features as working, labels recorded answers and sample
data, and labels everything else a concept preview.

## Capabilities

| Capability | In the app | Shown as |
|---|---|---|
| Capture on the phone: photos, a short clip, a spoken note, Send | built (Android app) | working |
| Upload a capture from a laptop (**Inbox**, *Send a capture from this computer*) | built | working |
| Read a label: SAM 3.1 finds the label crop, Muse Spark reads it, values stay *to confirm* | built | working with the key; a recorded answer otherwise |
| Spoken notes kept as the owner's words (Muse Voice Transcribe) | built | working |
| Measure a feature against a ruler, with method and uncertainty | built (no model) | working |
| *Does it fit?*: one verdict from the rules, unknowns as questions | built | working |
| Agitator profile `blender_agitator` (rod diameter, tab span, tab width, tab length, rod length, head diameter, material rule) | built (data) | working |
| Find a part: a search request, **Search Marketplace** opens the search for you to run | built | working, by handoff |
| Bring a listing back as text, a screenshot or values you know; assessed and dated | built | working; listings are written samples |
| Preferences, **Propose** (Muse Spark, up to five, through tools), the rules keep only backed allocations | built | working with the key; recorded proposals otherwise |
| Templates: arcade coffee table, smart mirror, home automation server, home server, retro console, and five more | built (data) | working |
| Select and commit: one item per selected build, conflicts with **Move it here** | built | working |
| Budget across the selected set; **Find it on Marketplace** for a missing requirement | built | working |
| Build pack: Markdown written by the rules, versioned, stale on change, **Download** | built | working |
| Outcome in your words, shared only as a redacted text when switched on | built | not shown (no build is finished) |
| Evaluation loop: `./dev eval` scores the demo set load against the rules | built | working, on recorded answers |
| Demo set replayed from recordings (`./dev demo`) | built; most answers are operation stubs until the owner's photos are recorded | labeled *recorded demo answers* |
| Hosted demo (Cloudflare Pages and Modal) | built, not yet live | not shown; record locally |
| Donor-appliance search, another device for the same result | not built | concept preview |
| Re-planning when the display changes | not built | concept preview |
| Connection diagrams, exploded or assembly views | not built | concept preview (drawn for the video) |
| Downloadable CAD, bracket or housing designs | not built | concept preview (unvalidated source in `cad/`) |
| Image generation | not built | not shown |
| Posting to or searching Marketplace automatically | not built, out of scope | never implied |
| Muse Spark Open on Baseten or Fireworks | not integrated; backlog | *planned* on the models card |

## Scenes

**Summary: 22 scenes. 9 record from working features (5 now in fixture mode, 4 with a live
key run), 6 need the owner's photos or footage, 4 are concept previews, 3 are cards rendered
here.**

| Shot | Scene | Status | What it needs | Exact app actions |
|---|---|---|---|---|
| S01 | The frappé routine | needs owner footage | the mixer, a cup, the worn agitator | phone camera |
| S02 | The shelf of unused electronics | needs owner footage | the shelf; or Runway clip R2, labeled | phone camera |
| S03 | Opening card | card | nothing | `brand/card-open.png` |
| S04 | The mixer and the worn agitator, close | needs owner footage | the appliance and the part | phone camera |
| S05 | Capture on the phone | needs owner photos | the app installed and paired, the appliance | Capture tab, photos, hold to talk, name, **Send** |
| S06 | Read the label | needs owner photos and the key | S05's capture; `OPL_FAKE_API=0` with the key | **Inbox**, **Read it**, **Accept** |
| S07 | Measure the rod | needs owner photos | a side photo of the rod with a ruler in the same plane | **My inventory**, the agitator, **Measure a feature**, *Rod diameter*, marks, **Measure** |
| S08 | The replacement search and its questions | recordable now | `./dev demo`; check the *Needs* line (storyboard note) | **Find a part**, the agitator search, hover **Search Marketplace**, **Bring a listing back**, **Values I know**, **Assess it**, **Ask the seller** |
| S09 | The inventory | recordable now | `./dev demo`; a drive item, or say "monitors" | **My inventory**, scroll, open *Third laptop, works* |
| S10 | What I want from a build | recordable now | `./dev demo` | **Build and reuse**, **What I want from a build**, fields, **Save** |
| S11 | Five proposals | recordable with the key | live Muse Spark run (fixture mode proposes the homework desk, not the arcade) | **Propose projects**, How many **5**, **Propose** |
| S12 | Select the arcade, resolve a conflict | recordable with the key | S11's arcade proposal; a second selected project that wants the same laptop | open the arcade, **Select and commit the items**, **Move it here** |
| S13 | Missing controls as a Marketplace search | recordable with the key | S12 | *Still needed*, **Find it on Marketplace**, hover **Search Marketplace** |
| S14 | The build pack | recordable with the key | S12 | **Write the build pack**, **Download** |
| S15 | Connection diagram | concept preview | nothing | `diagrams/arcade-connections.png` |
| S16 | Assembly layout | concept preview | nothing | `diagrams/arcade-placement.png` |
| S17 | A different display | concept preview | nothing | `diagrams/arcade-swap.png` |
| S18 | Bracket and housing designs | concept preview | a text editor | `cad/arcade_panel.scad`, not rendered |
| S19 | Meta models in the app | card | nothing | `brand/card-models.png` |
| S20 | Candidates side by side | recordable now | `./dev demo` | **Find a part**, *crevice tool for the upright vacuum*, the candidates table |
| S21 | The evaluation loop | recordable now | Docker | `./dev eval`, open the report under `eval/` |
| S22 | Closing card | card | nothing | `brand/card-close.png` |

Short video: K2 and the S08 part of K6 record now; K3 and K4 need the key; K1 and K6 need the
owner's footage; K5 is the concept preview; K1 and K7 use the cards.

## What changes when the owner's photos are recorded

Add the mixer's photos to the agitator item in `demo/set.yaml` (`photos: [...]`), then
`./dev demo-scrub <raw dir>` puts scrubbed copies in `demo/photos/`, `./dev record-fixtures`
(with the key, spends once) records every answer for them, and from then on `./dev demo`
replays real readings instead of operation stubs. S06 can then be recorded in fixture mode,
and the *recorded demo answers* label on Story B stays true.
