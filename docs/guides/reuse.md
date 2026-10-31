# Build and reuse

What could you build from what you already own? Say what you want from a build, ask for
proposals, and pick the ones you will do. Every proposal rests on items in your inventory;
what is missing becomes a search you run on Marketplace.

## Built so far

**What I want from a build.** A few answers kept once and read by every proposal: your
interests, the effort you will put in, your skills, the tools you have, whether you open
devices up, a budget with its currency, a radius, and whether you buy used, new or either. It
is the same record as your [profile](profile.md); the skills are rated there, and the form
here shows them in a line.

**Proposals.** Muse Spark reads your inventory and the project templates through tools (the
items a build may count on, one item in full, the catalog of templates) and proposes up to five
projects, each with the item it would use for every requirement and a line of why, what is
missing, the effort, the extra spending it expects and the unknowns to check before starting.
The rules keep a proposal only where the inventory backs it: an allocation must name an item
you have, usable (not gone, not meant for sale or giving away) and of a kind the requirement
takes; anything else is dropped and said. Nothing is invented: a template the data does not
hold is not proposed, and a toaster called "old laptop" does not become a laptop.

**Templates are data.** A project is a YAML file under `backend/app/projects/data/`: what it is
for, the practical result, the effort and skills, a typical cost, the requirements (each with
the kinds of item that fill it, whether it blocks the build, and the profile a search for it
runs under), the steps, the safety lines and the guidance by name. Five ship: a homework
workstation, a document camera for calls, a home music setup, a vacuum restored with a fitting
tool, and a laptop with a broken screen used as a desktop. The model never changes them.

**Projects.** A proposal becomes a project in the **proposed** state with exploratory
allocations. **Shortlist** it, or **Select** it: selection commits its items, and a committed
item is reserved in the inventory, for as long as a selected, building or done project counts
on it. One item is committed to one such build at a time: a
second project that wants it is answered with the conflict, and moves the item only when you
say so, which opens the requirement again on the project that lost it. **Abandon** releases
what nobody else holds. A selected project moves to **building** once every blocking
requirement is filled, then to **done**.

**The budget.** What the selected set (selected, being built or done) expects to spend, against
the budget you set, is one line above the projects. **Find it on Marketplace** turns a missing requirement into a
[search request](search.md) under the requirement's profile, with the budget left as its top
price. **Use it** fills a requirement with an item of yours the proposal overlooked or you
bought since, saved in the inventory first; it must be of a kind the requirement takes, and a
search open for it is marked found.

**The build pack.** For a selected project, one Markdown document written by the rules from
what stands on the day: the goal, the items with their accepted values (never a serial number,
a location or a note), what is still needed with the search opened for it and its documented
candidates, the costs with their dates, the tools you said you have, the steps with your
progress, the safety lines, the unknowns to check, the guidance by name, the limits that always
apply, and the outcome once recorded. Nothing is asked of a model. Each pack carries a version,
the day it was written and a digest of its inputs; a change to an item on it, to the project
or to the budget marks it **stale**, and the next writing is the next version. **Download**
keeps it as a file.

**Progress and the outcome.** While a project is selected or being built, its steps are a
checklist. When it is being built, record the outcome in your words: what was set up, how it
was tested, the day, whether it works, and its limits. A working result marks the project
**done** and keeps its items reserved; a failed test keeps it being built, with the record
kept. Proposed, being built and working stay distinct. The outcome is yours; **Share the
outcome** turns it into a text for other people that names the kinds of items, the result, the
set-up, the test and the limits, and nothing else: no item names, ids, values, places or
prices. It is off until you switch it on.

## From the API

```bash
curl -s -X PUT localhost:8000/api/preferences -H 'content-type: application/json' \
  -d '{"interests": "a quiet desk for homework", "effort": "low", "budget": 50}'
curl -s -X POST localhost:8000/api/projects/propose -H 'content-type: application/json' -d '{"count": 3}'
curl -s -X POST localhost:8000/api/projects/1/select -H 'content-type: application/json' -d '{}'
curl -s -X POST localhost:8000/api/projects/1/requirements/video_cable/search
curl -s -X POST localhost:8000/api/projects/1/pack | jq -r .markdown
curl -s -X POST localhost:8000/api/projects/1/outcome -H 'content-type: application/json' \
  -d '{"configuration": "laptop on the monitor over HDMI", "test": "a full homework session", "tested_on": "2026-10-29", "working": true}'
```

## Not yet

The pack as a PDF, and a pack that cites the candidate listings' pages, are under
[Next steps](../project/next.md).
