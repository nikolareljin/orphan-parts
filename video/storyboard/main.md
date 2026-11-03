# Main video: storyboard and shot list (2:52)

22 shots, cut to the narration's estimated timing (`scripts/main.srt`). Times are the edit's
timeline; durations in seconds. Status is the one in [readiness.md](../readiness.md): **now**
(fixture mode, recorded answers), **record** (working; its model answer is recorded once with
`video/generate.sh --record`, then replayed), **photos** (the owner's photos from the demo
set), **card** (rendered here). Every shot is something the app does: no concept previews. Overlays: `brand/corner-overlay.png`
on every screen recording; titles from `titles/`, top left, in for 4 s from the time given
(0 unless said otherwise). Captions bottom center, from `scripts/main.srt`; none is burned in over the closing card, whose own lines they repeat (the narrator still reads them).

`video/generate.sh` records every web shot with Playwright from the actions below
(`video/scenes/*.spec.ts`, one test per shot) and cuts the draft with `video/assemble.py`,
whose shot list follows this table: change both together. The browser is 1920x1080 with the
page at 150 percent, so the text reads on a phone. The stage is the demo set as `./dev demo`
loads it, with the agitator's device left unanswered so S05 can ask for it; the shots run in
order on one stage, no reset between them.

| Shot | Time | Dur | Picture | Exact actions | Source | Title | Status |
|---|---|---|---|---|---|---|---|
| S01 | 0:00 | 6 | The frappé maker on the counter | Still, slow push in | `demo/photos/hamilton-729-mixer.jpg` | none | photos |
| S02 | 0:06 | 6 | Unused electronics: a graphics card, a slot 1 processor, a powerline adapter | Three photos side by side, slow push in | `demo/photos/evga-9800gt-front.jpg`, `intel-slot-cpu.jpg`, `tplink-pa2010.jpg` | none | photos |
| S03 | 0:12 | 5 | Opening card | Hold | `brand/card-open.png` | none | card |
| S04 | 0:17 | 7 | The mixer with the agitator fitted, then the worn head and the coupling | Three photos side by side, slow push in | `demo/photos/hamilton-729-side.jpg`, `agitator-head.jpg`, `agitator-coupling.jpg` | `t01-story-a` | photos |
| S05 | 0:24 | 8 | The app asks which device the part came from | **My inventory**, *Frappé maker agitator, worn*, **Open**; the photos, then the question *We couldn't tell which device this part came from* | web take | `t21-which-device` | now |
| S06 | 0:32 | 5 | The label under the mixer's base | Still, slow push in | `demo/photos/hamilton-729-label.jpg` | `t22-label` | photos |
| S07 | 0:37 | 7 | The label answers it | The agitator again, **Add a photo of the device**, the label photo; *Came from: ...*, *Read from the photo: ... Confirm it in the fields*, the device photo | web take | `t23-device-read` | record |
| S08 | 0:44 | 16 | Search the web, then Check fit | **Find a part**, *all-metal agitator rod for the frappé maker*, **Open**; **Search the web**; *Added N pages*; the first page *found on the web*, its link (pointed at, never opened); **Check fit**; the state and *Ask the seller* | web take | `t24-search-web` at 0, `t29-fit` at 9 | record |
| S09 | 1:00 | 8 | Decide: keep and fix | The agitator, **Decide**, **What should I do with it?**; the three cards; *Keep and fix*, its steps, **Choose this: Keep and fix** | web take | `t25-decide` | record |
| S10 | 1:08 | 6 | The inventory | **My inventory**, scroll the list down and back | web take | `t08-story-b` | now |
| S11 | 1:14 | 9 | Skills, and what I want from a build | **Profile**: *software* confident, *electronics and soldering* some, **Save profile**; **Build and reuse**, **What I want from a build**, **Edit**, Interests *a tabletop arcade for the living room; home automation; a smart mirror in the hall*, Budget *120*, **Save** | web take | `t09-preferences` | now |
| S12 | 1:23 | 9 | Five proposals | **Propose projects**, How many **5**, **Propose**; the projects table | web take | `t10-propose` | record |
| S13 | 1:32 | 8 | The home automation server selected | **Open** the first proposal (an arcade when the proposals keep one): *From your inventory*, *Still needed*; **Select and commit the items** (**Move it here** if another build holds an item) | web take | `t11-select` | now, after S12 |
| S14 | 1:40 | 7 | Draw it | On the project, **Draw it**; the picture, captioned as drawn | web take | `t26-draw` | record |
| S15 | 1:47 | 8 | What is missing, as a search | *Still needed*, **Find it on Marketplace**; **Find a part**, the new search, **Open**; **Search Marketplace** pointed at, never opened | web take | `t12-marketplace` | now, after S12 |
| S16 | 1:55 | 6 | The build pack | The project, **Write the build pack**; *version 1*, **Download** pointed at | web take | `t13-pack` | now, after S12 |
| S17 | 2:01 | 6 | The graphics card: what it is worth | **My inventory**, *EVGA GeForce 9800 GT graphics card*, **Open**, **Value**; the price guidance's figures (*Quantities*), then the first of the *Comparables* | web take | `t30-value` | now |
| S18 | 2:07 | 11 | A voice note, then the draft | **Sell or give away**; *Voice note (WAV)*, the note (`scenes/notes/gpu-note.wav`); *Transcribed and saved as condition notes*; **Write the draft**; *draft 2* in *Fields to paste*, **Copy** pointed at, **Download photos** and **Open Marketplace** pointed at, never opened | web take | `t31-sell` | record |
| S19 | 2:18 | 6 | On the phone | The Android app on a real phone: Capture, two photos of the agitator from the gallery, a name, **Send**, *Sent as capture*; Captures, **Read it now** | phone take (`--phone`), else the app's screenshots | `t27-phone` | now |
| S20 | 2:24 | 6 | Meta models in the app | Hold | `brand/card-models.png` | none | card |
| S21 | 2:30 | 13 | Try it: the sample gallery, SAM 3.1 | **Sign out**; **Read a label**: the gallery; *Sun flat panel monitor*, its label photo, *Find the label in the photo first (SAM 3.1)* on, **Read the label**; the label region over the photo, the label crop, the reading and *Recorded answer for this sample* | web take | `t28-gallery` | now |
| S22 | 2:43 | 9 | Closing card | Hold; fade to black over the last second | `brand/card-close.png` | none | card |

## Notes per shot

- **Owner photos (S01, S02, S04, S06).** The scrubbed copies in `demo/photos/` (no metadata,
  serial numbers and keys masked); no faces. Portrait photos sit on a blurred fill of
  themselves.
- **S07.** The model on screen is what Muse Spark read off the label photo, *to confirm*. Until
  that reading is recorded, fixture mode answers with the operation's stub (a power adapter's
  model), and the draft carries the red DRAFT line: never keep that take for the final.
- **S08.** Search the web keeps only pages among the search's own results. The recorded live
  answer brings back the maker's part for the model 729 (Hamilton Beach 990010200) with the
  price each page states; the fixture stand-in brings back example.org pages under the DRAFT line.
  The links are pointed at, never opened on camera. Never type a price no page stated.
- **S09.** The cards are Muse Spark's for the owner's skills profile; the stand-in cards are a
  laptop's (the DRAFT line says so) until the agitator's are recorded.
- **S12 to S16** run on the project S12 leaves: an arcade when the recorded proposals keep
  one, else the first proposal. The recorded run keeps three, no arcade, so the shots follow
  the home automation server base and the narration says the arcade was not kept; never stage the
  picture.
- **S14.** One Muse Image call; fixture mode shows a drawing only once it is recorded.
- **S15.** No Marketplace page on camera: no facebook.com page, no Meta or Facebook logo, no
  other people's listings.
- **S17.** The price guidance is the one the demo set records for the card; its figures are
  never typed. **S18.** The voice note is a synthetic voice reading the condition the set states
  for the card, never presented as the owner speaking; the transcript and the draft are
  recorded answers. No facebook.com page: Open Marketplace is pointed at, never opened.
- **S19.** The phone shows no access code: pairing happens before the recording starts.
- **S21.** The gallery's readings and SAM 3.1's regions are recordings of those very photos;
  the page says so.
