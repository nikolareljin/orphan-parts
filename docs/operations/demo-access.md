# Demo access

The public demo runs the full product behind an access code, with per-visitor limits, a daily
cap, upload limits and a spend cap that pauses the service when reached. The demo set replays
recorded fixtures and costs nothing.

## Built so far

**The code.** With `DEMO_ACCESS_CODE` set (twelve characters at least), every page and every
API call needs a session; without it, nothing is gated, which is the setting for a machine of
your own. `POST /api/access` with the code opens a session: a cookie the browser keeps
(`HttpOnly`, `SameSite=Strict`, `Secure` when `DEMO_COOKIE_SECURE=1`), and the same token in
the answer for a caller that keeps no cookies, sent as `Authorization: Bearer`. A session lasts
`DEMO_SESSION_HOURS` (12) and is signed with a key derived from the code, so changing the code
ends every session at once; nothing is stored on the server. A wrong code is refused and only
`DEMO_CODE_ATTEMPTS` (5) tries per address and quarter hour are taken. `GET /api/access` says
whether a code is needed and whether this caller has a session; `DELETE /api/access` ends one.
The web app asks for the code on its first page and again whenever a call answers 401.

**What is open without the code**: `/healthz`, `/readyz`, `/api/version`, `/api/access` and
the API documentation. Nothing else.

**Allowances on what spends.** Every call that reaches the Model API (reading a label or a
listing, finding the label, writing a draft, a voice note, price guidance) is counted before it
is made: `DEMO_VISITOR_CALLS_PER_HOUR` (20) per session, and `DEMO_DAILY_CALLS` (300) for
everyone per UTC day. Over either, the answer is 429 with `Retry-After` and a line that says
which allowance ran out. Reads and writes to the private inventory are not counted here; every
request of any kind has `DEMO_REQUESTS_PER_MINUTE` (120) per address. The counts live in the
one backend process and start over when it restarts; the spend cap in the ledger on disk is
the floor under all of them.

**The operator's switch.** `DEMO_PAUSED=1` refuses every call that spends with 503 and leaves
everything else working; `/readyz` reports it under `demo`, apart from the spend cap's own
`paused`. The spend cap (`SPEND_CAP_USD`) still ends calls on its own when reached.

**The phone.** *Pair the phone* at the foot of every page shows a QR code with this web
origin and, when gated, a session for the phone (`GET /api/pair.svg`); the code needs a
session to reach, so only someone already in can hand the phone one, and the access code
itself is never in the QR. The phone's session ends like any other, after `DEMO_SESSION_HOURS`.

**The set, at no cost.** The public demo is the recorded set (`./dev demo` on the machine
that runs the stack, [Demo walkthrough](../start/demo.md)): with `OPL_FAKE_API=1` on the host nothing is sent to the
models and nothing is spent, whoever visits. Live mode is a window the operator opens, with
`SPEND_CAP_USD` set to the amount they accept for it; the ledger survives restarts, so the cap
counts across them.

**Across origins.** When the web app is served from another origin than the backend (Cloudflare
Pages in front of Modal), the cookie cannot travel; the web app keeps the session token from
`POST /api/access` for the tab and sends it as a bearer header, and the pairing code carries the
backend's own origin. See [Deployment](deployment.md).

**Behind nginx.** The production image forwards the caller's address and scheme; the backend
reads the forwarded address only with `DEMO_TRUST_PROXY=1`, which the production compose file
and the Modal secret set, so that the per-address limits count visitors, not the proxy. It takes the last address
in the header, the one the proxy appended; anything before it the caller may have written.
That is one hop: with a TLS terminator or another proxy in front of nginx, the last address is
that proxy's and every visitor shares it; then the front proxy has to be the one that forwards
the address, with nginx passing its header through.

**What is logged.** A refusal is logged with the path and which limit or switch refused it,
never with the code or a token. See [Observability](observability.md).

**The browser checks** run through the gate: `./dev e2e` starts the stack with a code of its
own (`DEMO_ACCESS_CODE` set in the shell overrides it; the value in `.env` is not used for the
run), opens one session before the run and gives it to every test, and
`tests/access.spec.ts` starts without one to check the gate itself.
