"""The demo gate: two doors on one deployment. The access code (the configured master code or
a code issued as a record) opens a signed session: the live door, the full inventory and the
live models when a key is configured. Without one a visitor is the demo: the stateless tries
on recorded answers and what is public, every write refused with one line. Allowances on what
costs money, a limit on everything else, and a switch the operator throws. One process keeps
the counts; the spend ledger on disk is the floor under all of it."""

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import Settings
from app.keys import AccessKeys, master_tag
from app.ops.door import live_request

log = logging.getLogger("app.gate")

COOKIE = "opl_access"
# What a visitor may read without the code; everything else needs it when a code is set.
OPEN_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
        "/docs",
        "/openapi.json",
        "/api/version",
        "/api/access",
        "/api/pair/code",
    }
)
# The calls that spend: each one is a Model API call, counted before it is made.
EXPENSIVE = [
    ("POST", re.compile(r"^/api/extract$")),
    ("POST", re.compile(r"^/api/segment$")),
    ("POST", re.compile(r"^/api/items/\d+/drafts$")),
    ("POST", re.compile(r"^/api/items/\d+/voice$")),
    ("POST", re.compile(r"^/api/items/\d+/price$")),
    ("POST", re.compile(r"^/api/items/\d+/picture$")),
    ("POST", re.compile(r"^/api/items/\d+/uses$")),
    ("POST", re.compile(r"^/api/items/\d+/scenarios$")),
    ("POST", re.compile(r"^/api/searches/\d+/candidates$")),
    ("POST", re.compile(r"^/api/projects/propose$")),
    ("POST", re.compile(r"^/api/captures/\d+/process$")),
]
# What the demo visitor may do without the code: look (the items and captures the owner marked
# public, their values, photos and drawn pictures; never a clip, a note, a location or a
# draft), and try the stateless readings on recorded answers. Everything that saves, drafts,
# prices, plans, draws or captures needs the code.
DEMO_ALLOWED = [
    ("GET", re.compile(r"^/api/items$")),
    ("GET", re.compile(r"^/api/items/\d+$")),
    ("GET", re.compile(r"^/api/items/\d+/photos(/\d+)?$")),
    ("GET", re.compile(r"^/api/items/\d+/pictures(/\d+)?$")),
    ("GET", re.compile(r"^/api/captures$")),
    ("GET", re.compile(r"^/api/captures/\d+$")),
    ("GET", re.compile(r"^/api/captures/\d+/photos/\d+$")),
    ("GET", re.compile(r"^/api/profiles(/[A-Za-z0-9_-]+/(features|rules))?$")),
    ("GET", re.compile(r"^/api/templates$")),
    # the address alone, so a phone joins as the demo visitor too; a session is never in it
    ("GET", re.compile(r"^/api/pair(\.svg)?$")),
    ("POST", re.compile(r"^/api/extract$")),
    ("POST", re.compile(r"^/api/segment$")),
    ("POST", re.compile(r"^/api/assess$")),
    ("POST", re.compile(r"^/api/measure$")),
]
DEMO_LINE = "demo: the code unlocks saving, drafts, prices, projects and captures"
# sid.expiry.door.key.binding.signature. The door: 0 the demo, 1 a session opened with a code,
# 2 a pairing (a QR's short session, the live door, and the one kind that claims a phone code)
_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9_-]{8,64}\.\d{1,12}\.[012]\.\d{1,12}\.[0-9a-f]{16}\.[0-9a-f]{32}$"
)
# the shape before the binding, with the record's issue time signed in directly; still verified
# for the sessions issued before it, which end within DEMO_SESSION_HOURS of a restart
_OLD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}\.\d{1,12}\.[01]\.\d{1,12}\.[0-9a-f]{32}$")


def demo_allowed(method: str, path: str) -> bool:
    return any(m == method and p.match(path) for m, p in DEMO_ALLOWED)


def expensive(method: str, path: str) -> bool:
    return any(m == method and p.match(path) for m, p in EXPENSIVE)


class Allowance:
    """So many hits per key in a sliding window; says how long until the next one is allowed."""

    SWEEP_EVERY = 1000  # takes between sweeps of keys whose window has passed

    def __init__(self, limit: int, seconds: float) -> None:
        self.limit = limit
        self.seconds = seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._takes = 0

    def _sweep(self, now: float) -> None:
        """Keys nobody has used for a whole window are dropped, so a long-running demo does
        not keep a deque for every address that ever called."""
        gone = [k for k, h in self._hits.items() if not h or now - h[-1] >= self.seconds]
        for k in gone:
            del self._hits[k]

    def take(self, key: str, now: float | None = None) -> tuple[bool, int]:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._takes += 1
            if self._takes % self.SWEEP_EVERY == 0:
                self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, int(self.seconds - (now - hits[0])) + 1)
            hits.append(now)
            return True, 0

    def forget(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


class DailyAllowance:
    """So many hits for everyone, per UTC day."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day = ""
        self._used = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._used = today, 0

    def take(self) -> bool:
        with self._lock:
            self._roll()
            if self._used >= self.limit:
                return False
            self._used += 1
            return True

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used


class Session:
    """Who a current token stands for: its id, whether it opens the live door, the issued
    record it came from (0 and an empty stamp for the master code or the demo), and whether
    it is a pairing's short session rather than a browser's."""

    __slots__ = ("kid", "live", "pairing", "sid", "stamp")

    def __init__(
        self, sid: str, live: bool, kid: int = 0, stamp: str = "", pairing: bool = False
    ) -> None:
        self.sid = sid
        self.live = live
        self.kid = kid
        self.stamp = stamp
        self.pairing = pairing


class Gate:
    def __init__(self, settings: Settings, keys: AccessKeys | None = None) -> None:
        code = settings.demo_access_code.get_secret_value() if settings.demo_access_code else ""
        self.enabled = bool(code)
        # the codes issued as records, beside the master code; set once the inventory is open
        self.keys = keys
        # whether a key is configured, so the live door reaches the live models at all
        self.live_models = settings.model_api_mode != "fixture"
        # the code is the only secret there is: the session key is derived from it, so a
        # changed code ends every session
        self._code_digest = hashlib.sha256(code.encode("utf-8")).digest()
        self._key = hashlib.sha256(b"opl-session:" + code.encode("utf-8")).digest()
        # what a phone's record keeps of the master code, so rotating it ends those phones
        self.master_tag = master_tag(code)
        self.session_seconds = settings.demo_session_hours * 3600
        self.pair_seconds = settings.pair_token_minutes * 60
        # a token of the old shape was issued before this process started, so it has ended
        # by then; past it one is refused before anything is read
        self._old_until = time.time() + self.session_seconds
        self.visitor = Allowance(settings.demo_visitor_calls_per_hour, 3600)
        # the demo visitor's tries cost nothing but work: so many per address and hour
        self.tries = Allowance(settings.demo_visitor_calls_per_hour, 3600)
        self.daily = DailyAllowance(settings.demo_daily_calls)
        self.attempts = Allowance(settings.demo_code_attempts, 900)
        self.cheap = Allowance(settings.demo_requests_per_minute, 60)
        self.paused = settings.demo_paused
        self.trust_proxy = settings.demo_trust_proxy
        self.cookie_secure = settings.demo_cookie_secure

    # --- the code and the session ------------------------------------------

    def which_key(self, given: str) -> tuple[str, int, str] | None:
        """What this code is: (``master``, 0, '') for the configured one, (label, id, issued
        at) for an issued record, None for anything else. The master is checked first and
        the records always, so a miss takes as long as a hit."""
        digest = hashlib.sha256(given.encode("utf-8")).digest()
        master = self.enabled and hmac.compare_digest(digest, self._code_digest)
        record = self.keys.match(given) if self.enabled and self.keys is not None else None
        if master:
            return "master", 0, ""
        return (record.label, record.id, record.created_at) if record is not None else None

    def which_code(self, given: str) -> str | None:
        """The name of the code this is, or None."""
        found = self.which_key(given)
        return found[0] if found is not None else None

    def code_matches(self, given: str) -> bool:
        return self.which_code(given) is not None

    def _mac(self, text: str, size: int) -> str:
        return hmac.new(self._key, text.encode(), hashlib.sha256).hexdigest()[:size]

    def _bind(self, sid: str, stamp: str) -> str:
        return self._mac(f"bind:{sid}.{stamp}", 16)

    def issue(
        self,
        now: float | None = None,
        *,
        live: bool = True,
        kid: int = 0,
        stamp: str = "",
        pairing: bool = False,
    ) -> tuple[str, int]:
        """A session token and when it ends: ``sid.expiry.door.key.binding.signature``,
        nothing stored. The door is ``1`` for a session opened with a code and ``2`` for a
        pairing, which lasts PAIR_TOKEN_MINUTES; the key is the issued record's id (``0`` for
        the master code) and the binding signs in its issue time, so revoking the record ends
        the sessions it opened and a record with the same id after a reset is a stranger. The
        signature covers the rest and is checked before the record is read (for this shape;
        the old one signs the issue time itself, so its record is read first)."""
        door = "2" if pairing else str(int(live))
        seconds = self.pair_seconds if pairing else self.session_seconds
        exp = int((time.time() if now is None else now) + seconds)
        sid = secrets.token_urlsafe(16)
        head = f"{sid}.{exp}.{door}.{kid}.{self._bind(sid, stamp)}"
        return f"{head}.{self._mac('v2:' + head, 32)}", exp

    @staticmethod
    def needs_record(token: str) -> bool:
        """Whether verifying this token reads a record (a token from an issued code)."""
        if _TOKEN_RE.match(token) or _OLD_TOKEN_RE.match(token):
            return token.split(".")[3] != "0"
        return False

    def verify(self, token: str, now: float | None = None) -> Session | None:
        """The session when the token is ours and current, else None."""
        if not self.enabled or not token:
            return None
        moment = time.time() if now is None else now
        if _OLD_TOKEN_RE.match(token):
            return self._verify_old(token, moment)
        if not _TOKEN_RE.match(token):
            return None
        sid, exp_text, door, kid_text, bind, sig = token.split(".")
        if int(exp_text) <= moment:
            return None
        head = token.rsplit(".", 1)[0]
        # a forged token of this shape ends here, before any record is read (one of the old
        # shape, taken for DEMO_SESSION_HOURS after a start, reads its record first: the
        # record's issue time is part of what it signs)
        if not hmac.compare_digest(sig, self._mac("v2:" + head, 32)):
            return None
        kid = int(kid_text)
        stamp = ""
        if kid:
            # the record must stand, and be the one the session was opened with
            found = self.keys.stamp(kid) if self.keys is not None else None
            if found is None:
                return None
            stamp = found
        if not hmac.compare_digest(bind, self._bind(sid, stamp)):
            return None
        return Session(sid, door != "0", kid, stamp, pairing=door == "2")

    def _verify_old(self, token: str, now: float) -> Session | None:
        sid, exp_text, door, kid_text, sig = token.split(".")
        exp = int(exp_text)
        if exp <= now or exp > self._old_until:
            return None
        kid = int(kid_text)
        stamp = ""
        if kid:
            found = self.keys.stamp(kid) if self.keys is not None else None
            if found is None:
                return None
            stamp = found
        if not hmac.compare_digest(sig, self._mac(f"{sid}.{exp}.{door}.{kid}.{stamp}", 32)):
            return None
        return Session(sid, door == "1", kid, stamp)

    # --- who is asking ---------------------------------------------------

    def client_ip(self, request: Request) -> str:
        """The caller's address; the proxy's forwarded header only when told to trust it. The
        last entry is the one the proxy appended, the address it saw; anything before it the
        caller may have written."""
        if self.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            last = forwarded.split(",")[-1].strip()
            if last and re.fullmatch(r"[0-9A-Fa-f.:]{3,45}", last):
                return last
        return request.client.host if request.client else "unknown"

    def token_of(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return request.cookies.get(COOKIE, "")


def _refused(status: int, detail: str, retry_after: int = 0) -> Response:
    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


class GateMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, gate: Gate) -> None:
        super().__init__(app)
        self.gate = gate

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        gate = self.gate
        path, method = request.url.path, request.method
        if method == "OPTIONS" or path in OPEN_PATHS or path.startswith("/docs/"):
            return await call_next(request)
        ip = gate.client_ip(request)
        ok, retry = gate.cheap.take(ip)
        if not ok:
            log.info("limit: requests per minute", extra={"path": path, "retry_after": retry})
            return _refused(429, f"too many requests; try again in {retry} s", retry)
        # no gate: a machine of your own, every request is the owner's; with a gate, the
        # session decides the door, and no session is the demo visitor
        visitor, live = ip, True
        if gate.enabled:
            # a token from an issued code is checked against its record: a read, off the loop
            given = gate.token_of(request)
            if gate.needs_record(given):
                session = await asyncio.to_thread(gate.verify, given)
            else:
                session = gate.verify(given)
            if session is None:
                live = False
            else:
                visitor, live = session.sid, session.live
        if not live and not demo_allowed(method, path):
            log.info("demo: a write was refused", extra={"path": path})
            return _refused(403, DEMO_LINE)
        if not live and method == "POST":
            # the four tries: recordings cost nothing to answer but work to decode, so many per
            # address and hour
            ok, retry = gate.tries.take(ip)
            if not ok:
                log.info("limit: demo tries per hour", extra={"path": path, "retry_after": retry})
                return _refused(
                    429, f"this address's hourly allowance of tries is used; wait {retry} s", retry
                )
        # the demo visitor's tries are answered from the recordings and cost nothing, so only
        # the live door is counted against what spends
        if live and expensive(method, path):
            if gate.paused:
                log.info("paused: a call that spends was refused", extra={"path": path})
                return _refused(503, "paused by the operator; nothing is sent to the models")
            ok, retry = gate.visitor.take(visitor)
            if not ok:
                log.info(
                    "limit: visitor calls per hour", extra={"path": path, "retry_after": retry}
                )
                return _refused(
                    429, f"this visitor's hourly allowance is used; try again in {retry} s", retry
                )
            if not gate.daily.take():
                log.info("limit: daily calls", extra={"path": path})
                return _refused(429, "the demo's daily allowance is used up; back tomorrow (UTC)")
        token = live_request.set(live)
        try:
            return await call_next(request)
        finally:
            live_request.reset(token)
