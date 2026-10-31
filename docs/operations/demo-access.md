# Demo access

One deployment, two doors. The **access code** opens the live door: the full inventory and,
when the host has a Meta Model API key, the live models. Without it a visitor is the
**demo**: the pages are there to look at, the stateless readings (a label, a crop, a fit, a
measurement) are answered from the recorded set and cost nothing, and nothing is kept. Every
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
On the hosted demo the inventory is the Modal volume's: `./dev keys --hosted issue --label
judges --days 7` (`modal run deploy/modal_app.py::keys --args '...'`) issues there. A demo
reset (`./dev demo`, `load_demo`) replaces the inventory file, the records with it: issue the
codes after the set is loaded. A code is
compared in constant time against the master and every current record, so a miss takes as
long as a hit. The records live in the inventory database ([Data model](../reference/data-model.md)).

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
the profiles and their rules, the templates, and the four stateless tries: `POST /api/extract`,
`/api/segment`, `/api/assess` (on values written in; an item by its id is the inventory and
answers 403), `/api/measure`, each so many times per address and hour
(`DEMO_VISITOR_CALLS_PER_HOUR`, 429 over it). Everything else answers `403` with the line
above (the items and captures the owner marked public are the exception: their values,
photos and drawn pictures are shown, never a location, a note, a clip or a draft; the demo set loads as public):
the rest of the inventory, the captures, the searches, the projects, every save, draft, price,
proposal, picture drawn and capture. The web app shows the pages, a *Sign in with the code* link in the
header, and the line on whatever a visitor tries to save; the phone says the same on its
Capture tab when no code is set.

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
finding the label, writing a draft, a voice note, price guidance, a proposal, a capture read)
is counted before it is made: `DEMO_VISITOR_CALLS_PER_HOUR` (20) per session, and
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

The public demo is the recorded set (`./dev demo` on the machine that
runs the stack, [Demo walkthrough](../start/demo.md)):
with `OPL_FAKE_API=1` on the host nothing is sent to the models and nothing is spent, whoever
visits. Live mode is a window the operator opens with a key and `SPEND_CAP_USD` set to the
amount they accept for it; the ledger survives restarts, so the cap counts across them. The
demo visitor never reaches the key either way.

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
and gives it to every test, and `tests/access.spec.ts` starts without one to check both doors.

Local gate labels must be one line, 1 to 60 characters. Invalid labels are refused before any local setting or running service changes. Duplicate settings use the last value in the file; exported shell settings still take priority. Quoted values end before a trailing comment.

`gate show` also refuses a shell override so it cannot print a file value as the active master. Bare names without an assignment are ignored by the environment helpers.
