---
description: What building Orphan Parts Lens in nine days taught its owner, from the dated log.
---

# Lessons learned

Notes from the [dated log](hackathon.md), in the order they were learned.

**The rules decide; the model proposes.** A confident wrong fit costs a trip across town and a
part that goes back in the drawer. So Muse Spark reads labels and listings and writes drafts,
and the profile's rules give the verdict, drop the draft line nothing confirms and keep only the
comparable a page backs. A model never moves a candidate up the ladder, and an unknown is never
a pass.

**Record every model answer, and the demo costs nothing.** The demo set is data: the photos,
what the owner knows, the searches, the brief. One run with a key keeps every answer as a
fixture; `./dev demo` replays it. Every visitor sees the same screen, the tests run on the same
recordings, and the spend ledger does not move. A fixture is keyed on what is sent, so a
change to the image size means recording again; that is a price worth paying.

**Two doors beat one switch.** The first gate was on or off. Now the access code opens the live
models and saving, and everyone else is the demo visitor: the recorded answers from a twin of
the model client, and one line on every write. The same deployment serves the judges and anyone
with the link, and the key is never reached without the code.

**A visitor should click the set, not upload.** With an open upload, a visitor's own photo got
the recorded answer of some other photo, which read as a wrong reading. The visitor now picks
the demo set's photos in a gallery and each answer is the recording of that exact photo; a
selection with none says so instead of passing a stub off as a reading. Uploads are for the
code's door.

**The phone is a capture device and nothing else.** Photos, a clip, a spoken note, a line,
Send. No model logic, no inventory on the phone; the backend reads a capture when asked. That
kept the app small enough to build in a day, test on the JVM and ship as an APK on each
release. Pairing by QR code came the day after, so the access code never leaves the server.

**Privacy by construction, not by policy.** The phone re-encodes every photo before it leaves,
so pixels go and the metadata does not. Nothing is posted, searched or fetched on anyone's
behalf; the Marketplace create page and the search are opened for you to use. The build pack
never carries a serial, a location or a note; the shared outcome names kinds of items and
nothing else. It is easier not to hold the data than to make promises about it.

**SAM masks in pure Python are slow; send fewer pixels.** The masks come back in a line grammar
and are decoded in plain Python, which was the slowest step of a read. The model now sees a copy
with its long edge at 800 pixels, the three concepts are in flight together, and the boxes are
scaled back onto the prepared photo. The read needs the label crop, and the boxes did not get
worse.

**A dimension is a number with an uncertainty, or it is nothing.** A ruler in the same plane,
two marks on the reference and two on the feature, and geometry does the rest; the uncertainty
follows from the marks and the reference's tolerance. A blurred or oblique capture is refused
with the reason. A measured 4.55 ± 0.3 mm against a rule of 4.5 ± 0.1 mm is unknown, not a
pass, and asks for a caliper. That cost an afternoon and saved a lot of confidence that would
otherwise have been faked.

**One SQLite file and plain files.** Items, assertions, events and measurements in one database
under `DATA_DIR`; captures and photos as files beside it. Every value with its provenance,
every change an event with a version. It moved to a volume on the hosting service without a
change to the service layer; the journal mode was the one setting the network filesystem
needed.

**Profiles and templates are data.** A category is a YAML file: fields, features with
tolerances, rules. A project is a YAML file: requirements, steps, safety lines. The model reads
them through tools and never changes them, so a new category is a file rather than a release,
and a toaster called "old laptop" does not become a laptop.

**A dead key should mean recorded answers, not errors.** The hosted backend probes its key at
startup; a refused, unpaid or misaddressed key puts the service on the recordings and
`/readyz` says so, while a busy API changes nothing and every request retries on its own. The
deploy treats the probe's answer as a check, so the web app is never built against a backend
whose key is wrong.

**Stacked pull requests, reviewed in passes.** Each feature on its own branch and pull request,
each one read through in passes before it merged, the next branch forward-merged with what
landed. The changelog and the dated log grew with each merge instead of at the end. Slower per
feature, and the only reason what landed on day two was still clear on day four.

**What time did not allow: the Meta Glasses app.** It was planned: hands-free capture of an
item and its label through the glasses' camera, the spoken note, the same Inbox. It was dropped
for two plain reasons. The day count did not allow a second device target beside the phone, and
testing it needs the glasses in hand with the developer toolkit, which could not be arranged in
the window. The phone flow does the job on its own; the glasses are under
[Next steps](next.md) with what they would plug into.
