# Demo access

One deployment, two doors. The **access code** opens the live door: the full inventory and,
when the host has a Meta Model API key, the live models. Without it a visitor is the
**demo**: the pages are there to look at, the stateless readings (a label, a crop, a fit, a
measurement) run on the demo set's own photos, clicked in a gallery, are answered from the
recordings made of those photos and cost nothing, and nothing is kept. Every
write is refused with one line: *demo: the code unlocks saving, drafts, prices, projects and
captures*. Allowances, a daily cap, upload limits and a spend cap stand behind the live door.

## The code

Two kinds of code open the same door. The configured `DEMO_ACCESS_CODE` (twelve characters at
least) is the master code; with it empty there is no gate at all, which is the setting for a
machine of your own. To try the gate there, `./dev gate on [--label <who>] [--days N]` writes a
master code into `.env` when it has none, restarts the backend with it (or starts the backend
alone when the stack is down; `./dev up` afterwards keeps the gate, since the code is in `.env`)
and issues a code for the phone (label `phone`, 7 days by default), printing both. A second
`gate on` while that code is current stops at the issue step, the gate on with the master
printed: `./dev keys revoke phone` first, or pass another `--label`. `./dev gate show` prints
the master again and `./dev gate off` clears it. The command refuses to run in CI, and when the
shell sets a `DEMO_ACCESS_CODE` other than the one in `.env` (Compose would prefer the shell's).
Beside it, **codes issued as records**: `./dev keys issue --label judges
--days 7` prints a code once (`opl_` and 24 random bytes) and keeps only its SHA-256 hash with
the label and the expiry; `./dev keys list` shows each record and whether it is current,
expired or revoked; `./dev keys revoke judges` ends one. The running backend reads the same
file, so a new code works at once and a revoked one stops at once, its open sessions with it.
On the hosted demo the codes are on the Modal volume: `./dev keys --hosted issue --label
judges --days 7` (`modal run deploy/modal_app.py::keys --args '...'`) issues there. The records
live in a SQLite file of their own under `DATA_DIR` (`KEYS_DB_FILE`, `access_keys.sqlite3`),
apart from the inventory, so a demo reset (`./dev demo`, `load_demo`) keeps them, with what each
code has used, and the sessions they opened stay signed in. Records an older build kept in the
inventory's `access_keys` table move to that file the first time it is opened (the backend's
start, a `./dev keys` command or a reset, which opens it before the inventory goes), with their
ids, as owner codes. A code is compared in constant time against the master and every current
record, so a miss takes as long as a hit.

## Judge codes

An issued code has a **scope**. `owner` (the default, and every code issued before scopes)
is the master code's full access. `judge` is for the people judging the entry, so they never
need the master code:

```bash
./dev keys --hosted issue --label jury --days 10 --scope judge --calls-per-day 20 --max-usd 5
./dev keys --hosted issue --label jury-tape --days 10 --scope judge --recorded
./dev keys --hosted list
```

`--calls-per-day` (default 20) and `--max-usd` (default 5.00) go with `--scope judge` only;
`--recorded` keeps the code on the recorded answers, as the demo visitor is, so it never
reaches the key. `list` prints, per code: id, label, scope, state, live calls today against the
daily cap, dollars spent against the cap (and `recorded`), the dates.

What a judge's code may do, enforced on the server (the gate in `app/ops/gate.py`, the
inventory in `app/inventory/service.py`); the web app only mirrors it:

| | the owner's records (the demo set) | its own records | another judge code's records |
| --- | --- | --- | --- |
| read | as the demo visitor reads them: public ones only, location, notes, voice notes, the device a part came from, the lowest price and the owner's reasons left out, photos as the shared copy | whole | not there (404) |
| change, delete, decide, draft, price, draw, search from, plan | refused (403, *judge access: the demo set is read-only; ...*) | yes, live calls within its limits | not there (404) |
| make | | items, captures, searches, project proposals (tagged with the code's id), and the stateless readings | |

- What it makes is its **sandbox**: each item, capture, search and project carries the code's
  record id (`owner_code`). Lists show the demo set's public records and its own; another
  judge's never, and the demo visitor never sees any judge's. A search or project it makes
  may name a demo item: the item's history gets no line and is not reserved.
- Never: marking anything public, the owner's profile (`PUT /api/preferences`), the spend
  ledger, a record's history or a capture's clip on the owner's records, pairing a phone (the
  pairing QR carries the address alone for a judge's session).
- **Limits.** Before a route that spends runs, the gate reads the code's use: the day's calls
  used, *this code's daily calls are used; more tomorrow (UTC)* (429); the dollars spent,
  *this code's budget is spent* (403). The model client checks again before every call that
  bills (a route may make several) and charges the code beside the spend ledger line, with
  what the call cost, so a code at its limit sends nothing. Use is kept per code and UTC day in
  the codes' file (`key_usage`) and survives a reset; the owner's allowances, the daily cap,
  the pause and `SPEND_CAP_USD` still stand under it. The master code and owner codes have no
  per-code limits.
- `GET /api/access` answers a judge's session with `judge`: `code_id`, `recorded`, the caps and
  what is left (`calls_left`, `usd_left`); the footer shows *Judge access: N live calls left
  today, $X left*, and the item dialog turns read-only (Delete, Save details, the drawing and
  the public mark off, with the reason as a tooltip) on what the code did not add.
- A refusal never starts with `demo:`, so the browser keeps the session.

`POST /api/access` with a code opens a session: a cookie the browser keeps (`HttpOnly`,
`SameSite=Strict`, `Secure` when `DEMO_COOKIE_SECURE=1`), and the same token in the answer for
a caller that keeps no cookies, sent as `Authorization: Bearer`. The token is
`sid.expiry.door.key.signature`, signed with a key derived from the master code: changing the
master code ends every session at once, and revoking an issued code ends the sessions it
opened as well as new ones (the token names the record, which is read on every request
that carries it); a session runs `DEMO_SESSION_HOURS` (12) otherwise. Nothing else is stored
on the server. A wrong code is refused and only `DEMO_CODE_ATTEMPTS` (5) tries per address and quarter
hour are taken. `GET /api/access` says whether a code is needed, whether this caller is through
the door, and whether that reaches the live models (`live`). `DELETE /api/access` (**Sign out**
in the header) forgets the session in this browser: the cookie is cleared with the attributes it
was set with, and the web app drops the token it keeps across origins even when the call fails.
The token itself is good until it expires, since nothing is stored to end it; revoking the code
ends every session it opened.
Which code opened a session is logged by its label, never the code itself.

## The demo door

Without a session on a gated host, every request is the demo visitor's. Open to the visitor:
the open paths (`/healthz`, `/readyz`, `/api/version`, `/api/access`, the API documentation),
the profiles and their rules, the templates, the demo samples (`GET /api/samples` and each
sample's file and thumbnail), and the stateless tries: `POST /api/samples/read`,
`/api/extract`, `/api/segment`, `/api/assess` (on values written in; an item by its id is the
inventory and answers 403), `/api/measure`, each so many times per address and hour
(`DEMO_VISITOR_CALLS_PER_HOUR`, 429 over it). The tries that take a photo take a sample, by its
id, never a file: a photo, a crop or a measurement photo sent by the visitor answers `403`
with *Sign in with the access code to read your own photos.* Everything else answers `403` with the line
above (the items and captures the owner marked public are the exception: their values,
photos, drawn pictures and saved results are shown, never a location, a note, a clip, the
lowest price or the reason for selling; the demo set loads as public):
the rest of the inventory, the captures, every save, draft, price, plan, web search, fit
check, proposal, picture drawn and capture.

**Saved results, read-only.** What the owner already asked for a public item is read as it was
saved, by `GET` alone with plain-digit ids, and reading it never asks a model:
`/api/items/{id}/decide` (the view: the latest cards and ideas, the worth line, the open
searches and the projects the visitor may read, the last decision without the owner's note),
`/api/items/{id}/scenarios` and `/api/items/{id}/uses` (every set of cards and every answer of
ideas, oldest first), `/api/items/{id}/drafts` and `/api/drafts/{id}` (the whole listing: title,
price, category, condition, description, tags, facts, photo order, warnings and checklist),
`/api/items/{id}/price` (every guidance), `/api/items/{id}/sell-details` (without the lowest
price, the reason and the area), `/api/items/{id}/marketplace` (listed, sold, given), the
pictures of a reuse card (`/api/items/{id}/scenarios/{s}/reuse/{card}/pictures` and each
picture) and `/api/marketplace/us`. A private item's answer 404. The model's text in each is
masked as on a label (a serial number, a MAC address or a key), and the pickup area of the
owner's listing details reads *the owner's area* in a draft the visitor is shown. Asking again,
writing a draft, pricing, deciding, ticking a step, recording an outcome, the sales the owner
reported (`/price/reports`) and the photo zip stay behind the code. The web app shows the saved
cards, drafts and guidance with no button that asks, and the sign-in line where the owner would
act; the inventory list marks which items have saved results and shows the plan chosen.

**Find a part, Build and reuse and the profile, read-only.** The visitor reads them as the
owner left them, by `GET` alone with plain-digit ids: `/api/searches` (and one search, its
`candidates` and `listings`), `/api/candidates/{id}` (and its `questions`),
`/api/preferences`, `/api/projects` (and one project, its `packs` and `pictures`) and
`/api/packs/{id}` (and `.md`). Only what rests on public items is there: a search made for a
public item, a project every item of which is public, their candidates, listings, packs and
pictures; a search from values written in, one for a private item and a project with a private
item on it answer 404, as a private item does. The owner's words and money stay out wherever
these are answered: a search's notes and a candidate's note are blank, the radius, the budget
left, the budget and what remains of it are left out, an outcome is shown only once shared,
and a pack comes without its budget line, its condition notes (where a voice note is kept),
the searches under what is still needed (their title, their top price, which is the budget
left, and their candidates) and its outcome section; a serial number, a MAC address or a key
in a listing's text, the values read from it or a pack is masked as on a label. Every write and every call
that spends on these pages (**Start the search**, **Plan the search**, **Search the web**,
**Bring back listings**, **Check fit**, **Propose**, **Select**, **Write the build pack**,
**Save profile**) is still `403`; the web app shows the sign-in line in their place, so a
visitor's page never meets a refusal. The demo set's search for the agitator rod is loaded
with **Search the web** already run (`web: true` in `demo/set.yaml`, answered only by the
recording of that very request), so the visitor sees the maker's part with its link. The web app shows the pages, a *Sign in with the code* link in the
header, and the line on whatever a visitor tries to save; the phone says the same on its
Capture tab when no code is set.

**The samples.** The visitor reads the demo set's photos, not their own: the web app shows no
file input, drop zone or record button to a visitor anywhere. *Read a label* is a gallery of
the set's 19 photos, grouped by item, each with a checkbox, *Select all photos of this item*
and **Read the label** (with *Find the label in the photo first* as before). An item's every
photo picked is one reading of them all, the one the set was loaded with; any other photo is
read on its own, and several readings are shown side by side, each under *Recorded answer for
this sample.* The server reads the stored file the id names and runs the normal flow (SAM 3.1
on the first photo, Muse Spark on the photos and the label crops), so the recording made of
that exact photo answers. Only an exact recording answers a sample: a selection with none says
*No recorded answer for this sample yet.* rather than passing an operation's stub off as a
reading. *Measure* in the item dialog marks a sample photo (the geometry needs no recording);
the Inbox's capture form, the listing's voice note and *Find a part*'s new search show one
line, *Sign in with the access code to use this.*, since the set has no sample a visitor could
send there and those routes are behind the code. Signed in, every upload is back and read live where the
server has a key. The set's photos are the samples wherever the set is shipped (`DEMO_SET`, by
default `demo/set.yaml` beside the backend, which the dev stack mounts; the Modal image ships
the set at `/root/demo` and the Modal app sets `DEMO_SET` to it); without it the gallery says there are none.
A reading of several samples costs the visitor one try per reading (an item's group is one), so
a large selection is paid for as the readings it makes; a reading answered from the recordings
is kept in memory, and the same pick again is answered without decoding anything.

The header always carries one door on a gated host: *Sign in with the code* without a session
(and while the browser has not heard back from `GET /api/access` yet), *Sign out* with one. The
web app asks `GET /api/access` on its own, apart from `/readyz` and `/api/version`, tries again
after a failure (1 s, doubling up to 30 s) and asks again when the tab comes back into view,
so a slow start or a failed service check never takes the door away. A 401 or a write refused
as the demo visitor turns it back to *Sign in with the code*. On a host without a code
(`gated: false`) the header says *Open server (no code needed)* instead.

For now, signing in uses a shared access code only. Accounts and a proper sign-in come later
([Next steps](../project/next.md)).

The visitor's tries are answered by a second model client in fixture mode, the **twin**: the
same recorded answers the browser checks and `./dev demo` use, a ledger of its own that goes
nowhere, nothing sent to the Model API and nothing spent. Only a request through the code's
door reaches the key, and only those calls enter the spend ledger. `/readyz` reports
`model_api` as *live for the code, recorded otherwise* on such a host, and `demo.live_models`
says whether a key is there at all; the service line at the foot of every page says which door
the browser is on. With `OPL_FAKE_API=1` on the host (the open demo after the hackathon) both
doors get the recordings; the code still decides who may save.

## Allowances on what spends

Every call through the live door that reaches the Model API (reading a label or a listing,
finding the label, writing a draft, a voice note, price guidance, the decision cards, the
uses, a search plan, a listing screenshot or **Check fit**, a proposal, a drawing, a capture
read) is counted before it is made: `DEMO_VISITOR_CALLS_PER_HOUR` (20) per session, and
`DEMO_DAILY_CALLS` (300) for everyone per UTC day. Over either, the answer is 429 with
`Retry-After` and a line that says which allowance ran out. The demo visitor's tries are
recordings and are not counted. Reads and writes to the inventory are not counted here; every
request of any kind has `DEMO_REQUESTS_PER_MINUTE` (120) per address. The counts live in the
one backend process and start over when it restarts; the spend cap in the ledger on disk is
the floor under all of them.

**The operator's switch.** `DEMO_PAUSED=1` refuses every call that would spend with 503 and
leaves everything else working, the demo door included; `/readyz` reports it under `demo`,
apart from the spend cap's own `paused`. The spend cap (`SPEND_CAP_USD`) still ends calls on
its own when reached.

## The phone

*Pair the phone* at the foot of every page shows a QR code with this web origin (`GET
/api/pair.svg`), drawn when the section is opened and redrawn while it stays open. The origin
must be one this server is reached at, so the QR never points elsewhere: the `Host` the request
carries (either scheme), the host and port in `X-Forwarded-Host` with the scheme in
`X-Forwarded-Proto` (the dev server rewrites the `Host` and forwards the one the browser asked
for; nginx passes it on in both), one in `CORS_ORIGINS`, or the page's `Origin` or `Referer`
only on a request the browser marks `Sec-Fetch-Site: same-origin`. A browser sends no such mark
from a plain `http://` page on the LAN, so the proxies' headers are what name it there; another
site's page is marked cross-site and cannot draw a QR naming itself. For a caller through the
door the QR carries a pairing as well: a short session of its own kind, good for
`PAIR_TOKEN_MINUTES` (15, at most 60), that opens the door while it lasts and is the only token
that claims a phone's code. For those minutes the QR is a live credential: anyone who scans it
is through the door, so keep it off a projector and out of a recording. The access code itself
is never in the QR, and the QR stores nothing. On its first scan the app claims a code of its
own with the pairing (`POST /api/pair/code`, once per pairing; a browser's session is refused
with 403, and each try counts against the address's `DEMO_CODE_ATTEMPTS`, which a claim that
works clears, as a correct code does): an issued record labeled `phone` and the first eight
characters of the pairing's id, good for `PAIR_CODE_DAYS` (30) and never past the code that
signed the page in. The app then opens a session with that code, as a typed code would, and
opens a new one with it whenever a session ends, with no second scan.

The phone's code stands only while the code that paired it does. Revoking a guest's code
(`./dev keys revoke judges`) ends that code, every session it opened and every phone code it
paired, with their sessions; a guest code that expires does the same. A phone paired from a
page signed in with the master code ends when `DEMO_ACCESS_CODE` changes. Revoking a phone's
label (`./dev keys revoke "phone …"`) ends that phone alone. **Unpair** on the app's Backend tab
releases the phone from its side (`DELETE /api/access`, then the address, code and session are
forgotten on the phone) and revokes nothing: the record stands until it is revoked here or runs
out. `./dev keys list` shows the phone codes beside the rest, each with what paired it, and
`ended` for one whose parent has ended. A phone's own code does not pair another phone. Two
phones need two scans of a fresh page: reopening *Pair the phone*, or a reload, draws a new
pairing. One code pairs at most
`PAIR_CODE_MAX` (10) phones with current codes; past that the claim answers 403 until
`./dev keys revoke "phone …"` ends one or one runs out. For the demo visitor the QR carries the address
alone: a phone paired from it is the demo visitor too, its captures refused with the line,
and the Capture tab says so before anything is sent; a scan of a signed-in page later gives
it a code.

## The set, at no cost

The public demo is the recorded set (`./dev demo` on the machine that runs the stack,
`modal run deploy/modal_app.py::load_demo` on the hosted one;
[Demo walkthrough](../start/demo.md)). The demo visitor never reaches the key: their answers
are the recordings, whoever visits. Through the code's door, a host with a key spends up to
`SPEND_CAP_USD`; the ledger survives restarts, so the cap counts across them. With
`OPL_FAKE_API=1` on the host nothing is sent to the models at all, through either door.

## Across origins

When the web app is served from another origin than the backend (Cloudflare Pages in front of
Modal), the cookie cannot travel; the web app keeps the session token from `POST /api/access`
for the tab and sends it as a bearer header, and the pairing code carries the backend's own
origin. See [Deployment](deployment.md).

## Behind nginx

The production image forwards the caller's address and scheme; the backend reads the forwarded
address only with `DEMO_TRUST_PROXY=1`, which the production compose file and the Modal secret set, so that the
per-address limits count visitors, not the proxy. It takes the last address in the header, the
one the proxy appended; anything before it the caller may have written. That is one hop: with
a TLS terminator or another proxy in front of nginx, the last address is that proxy's and every
visitor shares it; then the front proxy has to be the one that forwards the address, with nginx
passing its header through.

## What is logged

A refusal is logged with the path and which limit, door or switch refused it, never with the
code or a token; a session opened is logged with the code's label. See
[Observability](observability.md).

## The browser checks

`./dev e2e` starts the stack with a code of its own (`DEMO_ACCESS_CODE` set in the shell
overrides it; the value in `.env` is not used for the run), opens one session before the run
and gives it to every test, and `tests/access.spec.ts` and `tests/samples.spec.ts` start
without one to check both doors: no file input for the visitor, the gallery, several samples
read side by side with their own answers, and the inputs back once signed in. The visitor's
*Find a part* (a public part's search with its candidates and web finds) and *Build and reuse*
and *Profile* (`tests/build.spec.ts`: the homework desk, the skills) are checked to show no
input and to meet no 403.

Local gate labels must be one line, 1 to 60 characters. Invalid labels are refused before any local setting or running service changes. Duplicate settings use the last value in the file; exported shell settings still take priority. Quoted values end before a trailing comment.

`gate show` also refuses a shell override so it cannot print a file value as the active master. Bare names without an assignment are ignored by the environment helpers.
