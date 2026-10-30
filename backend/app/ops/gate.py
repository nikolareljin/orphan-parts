"""The demo gate: an access code exchanged for a signed session, allowances on what costs
money, a limit on everything else, and a switch the operator throws. One process keeps the
counts; the spend ledger on disk is the floor under all of it."""

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

log = logging.getLogger("app.gate")

COOKIE = "opl_access"
# What a visitor may read without the code; everything else needs it when a code is set.
OPEN_PATHS = frozenset(
    {"/healthz", "/readyz", "/docs", "/openapi.json", "/api/version", "/api/access"}
)
# The calls that spend: each one is a Model API call, counted before it is made.
EXPENSIVE = [
    ("POST", re.compile(r"^/api/extract$")),
    ("POST", re.compile(r"^/api/segment$")),
    ("POST", re.compile(r"^/api/items/\d+/drafts$")),
    ("POST", re.compile(r"^/api/items/\d+/voice$")),
    ("POST", re.compile(r"^/api/items/\d+/price$")),
    ("POST", re.compile(r"^/api/searches/\d+/candidates$")),
    ("POST", re.compile(r"^/api/projects/propose$")),
    ("POST", re.compile(r"^/api/captures/\d+/process$")),
]
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}\.\d{1,12}\.[0-9a-f]{32}$")


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


class Gate:
    def __init__(self, settings: Settings) -> None:
        code = settings.demo_access_code.get_secret_value() if settings.demo_access_code else ""
        self.enabled = bool(code)
        # the code is the only secret there is: the session key is derived from it, so a
        # changed code ends every session
        self._code_digest = hashlib.sha256(code.encode("utf-8")).digest()
        self._key = hashlib.sha256(b"opl-session:" + code.encode("utf-8")).digest()
        self.session_seconds = settings.demo_session_hours * 3600
        self.visitor = Allowance(settings.demo_visitor_calls_per_hour, 3600)
        self.daily = DailyAllowance(settings.demo_daily_calls)
        self.attempts = Allowance(settings.demo_code_attempts, 900)
        self.cheap = Allowance(settings.demo_requests_per_minute, 60)
        self.paused = settings.demo_paused
        self.trust_proxy = settings.demo_trust_proxy
        self.cookie_secure = settings.demo_cookie_secure

    # --- the code and the session ------------------------------------------

    def code_matches(self, given: str) -> bool:
        digest = hashlib.sha256(given.encode("utf-8")).digest()
        return self.enabled and hmac.compare_digest(digest, self._code_digest)

    def _sign(self, sid: str, exp: int) -> str:
        return hmac.new(self._key, f"{sid}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]

    def issue(self, now: float | None = None) -> tuple[str, int]:
        """A session token and when it ends: ``sid.expiry.signature``, nothing stored."""
        exp = int((time.time() if now is None else now) + self.session_seconds)
        sid = secrets.token_urlsafe(16)
        return f"{sid}.{exp}.{self._sign(sid, exp)}", exp

    def verify(self, token: str, now: float | None = None) -> str | None:
        """The session id when the token is ours and current, else None."""
        if not self.enabled or not token or not _TOKEN_RE.match(token):
            return None
        sid, exp_text, sig = token.split(".")
        exp = int(exp_text)
        if exp <= (time.time() if now is None else now):
            return None
        if not hmac.compare_digest(sig, self._sign(sid, exp)):
            return None
        return sid

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
        visitor = ip
        if gate.enabled:
            sid = gate.verify(gate.token_of(request))
            if sid is None:
                return _refused(401, "access code required")
            visitor = sid
        if expensive(method, path):
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
        return await call_next(request)
