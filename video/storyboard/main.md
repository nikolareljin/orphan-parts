# Main video: storyboard and shot list (2:50)

22 shots, cut to the narration's estimated timing (`scripts/main.srt`). Times are the edit's timeline; durations in seconds. Status is the one in
[readiness.md](../readiness.md): **now** (fixture mode), **key** (working, needs a live Muse
Spark run), **photos** (needs the owner's photos or footage), **concept** (concept preview),
**card** (rendered here). Overlays: `brand/corner-overlay.png` on every screen recording;
titles from `titles/`, top left, in for the first 4 s of a shot unless said otherwise.
Captions bottom center, from `scripts/main.srt`.

Browser: the web app at `http://localhost:5173`, window content 1920x1080, zoom 110 percent.
Before every web take: `./dev demo` (the inventory reset and the demo set loaded).

| Shot | Time | Dur | Picture | Exact actions | Source | Overlay | Status |
|---|---|---|---|---|---|---|---|
| S01 | 0:00 | 6 | The frappé routine: the mixer base on the counter, the cup, the worn agitator in hand | Handheld or tripod, 1080p30, daylight; no brand close-up beyond what is on the appliance | phone camera | none | photos |
| S02 | 0:06 | 6 | The shelf or drawer of unused laptops, tablets, monitors, cables | Slow pan, left to right | phone camera (or Runway clip R2, labeled) | none | photos |
| S03 | 0:12 | 6 | Opening card | 1 s fade in from black | `brand/card-open.png` | none | card |
| S04 | 0:18 | 8 | The mixer and the worn agitator, close: the tabs at the top of the rod | Macro or close focus; the label on the base visible in frame | phone camera | `t01-story-a` | photos |
| S05 | 0:26 | 6 | The phone's Capture tab | Capture tab: photograph the base, the label (fills the frame), the agitator; hold to talk: "the rod wobbles in the drive; the base runs"; type a name; **Send** | scrcpy window in OBS, or `adb shell screenrecord` | `t02-capture` | photos |
| S06 | 0:32 | 5 | The capture read into an item | **Inbox**, the new capture, **Read it**; the label crop and the values *to confirm*; **Accept** one value | OBS, browser | `t03-read` | photos (and key) |
| S07 | 0:37 | 5 | A dimension from a ruler | **My inventory**, *Frappé maker agitator, worn*, **Measure a feature**, feature *Rod diameter*, upload the side photo with the ruler, mark two points on the ruler and the two edges of the rod, **Measure**; the value with its method and uncertainty | OBS, browser | `t04-measure` | photos |
| S08 | 0:42 | 13 | The replacement search, its open questions | **Find a part**, the search *all-metal agitator rod for the frappé maker*; hover **Search Marketplace** (do not open it on camera); **Bring a listing back**, choose **Values I know**, type only what a seller might state, **Assess it**; the state (*needs evidence* expected), **Ask the seller**, the questions | OBS, browser | `t05-find` 0 to 3 s, `t07-routes` 3 to 7 s, `t06-sample-values` 7 to 11 s | now |
| S09 | 0:55 | 8 | The inventory: laptops, RAM, tablets, monitors, mice, switches | **My inventory**, scroll the list slowly; open *Third laptop, works* for 2 s | OBS, browser | `t08-story-b` | now |
| S10 | 1:03 | 9 | What I want from a build | **Build and reuse**, **What I want from a build**: Interests *an arcade table for the living room; home automation; a smart mirror*, Effort, Skills, Budget; **Save** | OBS, browser | `t09-preferences` | now |
| S11 | 1:12 | 8 | Five proposals | **Propose projects**, How many **5**, **Propose**; let the list settle; pan over the proposals, stop on the arcade | OBS, browser, live key | `t10-propose` | key |
| S12 | 1:20 | 7 | The arcade selected | Open the arcade proposal: *From your inventory*, *Check before starting*, *Still needed*; **Select and commit the items**; if another selected project holds the laptop, the conflict line and **Move it here** | OBS, browser, live key | `t11-select` | key |
| S13 | 1:27 | 9 | The missing controls as a search | On *Still needed*, the controls requirement, **Find it on Marketplace**; the new search with its top price; hover **Search Marketplace**, cut before any Marketplace page | OBS, browser | `t12-marketplace` | key |
| S14 | 1:36 | 6 | The build pack | Back on the project, **Write the build pack**; scroll the Markdown; **Download** | OBS, browser | `t13-pack` | key |
| S15 | 1:42 | 5 | Connection diagram | Still, slow push in (105 percent over the shot) | `diagrams/arcade-connections.png` | `t14-connections` (the badge is in the picture too) | concept |
| S16 | 1:47 | 5 | Assembly layout | Still, slow push in | `diagrams/arcade-placement.png` | `t15-placement` | concept |
| S17 | 1:52 | 12 | A different display | Still; reveal the four dashed rows one by one (crop or wipe in the editor, 2 s apart) | `diagrams/arcade-swap.png` | `t16-swap` | concept |
| S18 | 2:04 | 11 | Bracket and housing designs | A text editor showing `cad/arcade_panel.scad` from the top: the UNVALIDATED header, the placeholder parameters; scroll slowly. No render | OBS, editor, dark theme, 18 pt | `t17-brackets` for the whole shot | concept |
| S19 | 2:15 | 7 | Meta models in the app | Still | `brand/card-models.png` | none | card |
| S20 | 2:22 | 9 | Candidates side by side | **Find a part**, the search *crevice tool for the upright vacuum*; the candidates table, each with its state, asking price and the day seen; open one for its checks | OBS, browser | `t18-candidates` | now |
| S21 | 2:31 | 9 | The evaluation loop | A terminal: `./dev eval`, then the report under `eval/` in the browser or a viewer | OBS, terminal, then report | `t19-eval` | now |
| S22 | 2:40 | 10 | Closing card | Hold; fade to black over the last second | `brand/card-close.png` | none | card |

## Notes per shot

- **S01, S02, S04.** The owner's own things only. No people's faces, no other brands in focus.
  If S02 uses a Runway clip, put the line *Illustrative clip, made with Runway* in the
  bottom right for its whole duration.
- **S05 to S07** wait for the photos. Until then put `titles/t20-mixer-placeholder.png` over a
  black frame or S04's footage, so the edit holds its timing.
- **S06.** In fixture mode a new photo gets the recorded answer for the operation, which is the
  power adapter label from the test set, not the mixer. Record this shot only with the key
  (`OPL_FAKE_API=0`, `MODEL_API_KEY` set), and only keep it if the values shown are what the
  mixer's label says.
- **S07.** No model is involved: the number is geometry on the marks. A blurred or angled photo
  is refused with the reason; if it is, retake the photo, do not stage the refusal.
- **S08.** Check the *Needs* line first. The demo set records the worn rod's material as
  plastic, and the material rule is an equality: a candidate stated as metal is a conflict on
  that rule as the profile stands. Either leave the material out of the typed values (it
  becomes a question to the seller) or start a new search (**I need one that fits**, *Needed by*: **Values written in below**)
  under the agitator profile from the measurement of S07. The rod numbers in the demo set (4 mm rod, 9 mm
  across the tabs) are the set's entries: confirm them against S07 before they appear. Never
  type an asking price that a real listing did not state.
- **S11 to S14** need a live run: in fixture mode **Propose** answers with the recorded
  proposals (homework desk, vacuum, kitchen music; one of them dropped by the rules), not the
  arcade. Keep whatever five the live run proposes; the narration names three of them, so cut
  the narration if one is missing, never the picture.
- **S13.** Do not open the Marketplace page on camera: no facebook.com page, no Meta or
  Facebook logo, no other people's listings.
- **S15 to S18** are concept previews: the magenta badge stays in frame for the whole shot.
- **S20.** The two listings are written examples from `demo/listings/`; `t18-candidates` says so.
