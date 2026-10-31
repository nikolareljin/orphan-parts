"""Pairing the phone: the web origin it should talk to and, when the demo is gated, a session
of its own, as JSON, as a QR code or as text for a terminal. The access code never leaves the
server; what the phone gets is a session that ends like any other, and, once it has scanned,
a code of its own claimed with that session, so it stays through the gate after the session
ends. The demo visitor's QR carries the address alone: the phone joins as the demo too."""

import io
import re
from datetime import UTC, datetime, timedelta

import segno
from pydantic import BaseModel, Field

from app.keys import AccessKey, AccessKeyError, AccessKeys
from app.ops.gate import Gate, Session

ORIGIN = re.compile(r"^https?://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.\-]+)(:\d{1,5})?$")
APP_NAME = "Orphan Parts Lens"


class BadOriginError(ValueError):
    pass


class Pairing(BaseModel):
    name: str = APP_NAME
    url: str = Field(description="the web origin the phone talks to; it proxies the API")
    gated: bool
    token: str = Field(default="", description="a session for the phone, when the demo is gated")
    expires_at: int = Field(default=0, description="when that session ends, Unix seconds")

    def payload(self) -> str:
        """What the QR carries: the origin, whether gated, the token. Nothing else."""
        return self.model_dump_json(include={"url", "gated", "token"})


class PhoneCode(BaseModel):
    gated: bool
    code: str = Field(default="", description="the phone's own access code, shown once")
    label: str = Field(default="", description="its record's label, for ./dev keys revoke")
    expires_at: str | None = Field(default=None, description="when it stops working")


def pairing(
    origin: str,
    gate: Gate,
    api: str = "",
    kid: int = 0,
    stamp: str = "",
    *,
    visitor: bool = False,
) -> Pairing:
    """The phone talks to ``api`` when the web app is served from another origin (Cloudflare
    Pages in front of Modal), and to the web origin otherwise, which proxies the API. For the
    demo ``visitor`` (no session) the gated pairing is the address alone."""
    for given in (origin, api):
        if given and not ORIGIN.match(given):
            raise BadOriginError(
                "origin must be a scheme, a host and an optional port, nothing more"
            )
    if not origin:
        raise BadOriginError("origin must be a scheme, a host and an optional port, nothing more")
    url = api or origin
    if not gate.enabled:
        return Pairing(url=url, gated=False)
    if visitor:
        # nothing issued and nothing stored: the phone is the demo visitor, as the browser is
        return Pairing(url=url, gated=True)
    # the phone's session is the caller's: from an issued code, it ends with that code
    token, expires_at = gate.issue(kid=kid, stamp=stamp)
    return Pairing(url=url, gated=True, token=token, expires_at=expires_at)


def phone_code(session: Session, keys: AccessKeys, days: int) -> tuple[str, AccessKey]:
    """The phone's own code, claimed with its pairing session: an issued record labeled after
    the session (``phone`` and the first eight characters of its id), so one session claims
    once; the label is kept with the record whatever becomes of it, and a second claim with
    the same session is refused for as long as the record exists, revoked or not. It lasts
    ``days``, and never past the code that opened the session: a session from an issued
    record gets a code that ends with that record, or nothing when the record has ended; the
    master code's session gets the full count."""
    now = datetime.now(UTC)
    until = now + timedelta(days=days)
    if session.kid:
        parent = keys.get(session.kid)
        if parent is None or parent.state(now) != "current":
            raise AccessKeyError("the code that paired this phone has ended")
        if parent.expires_at is not None:
            until = min(until, datetime.fromisoformat(parent.expires_at))
    return keys.issue(f"phone {session.sid[:8]}", until=until, once=True)


def svg(found: Pairing) -> bytes:
    code = segno.make(found.payload(), error="m")
    out = io.BytesIO()
    code.save(out, kind="svg", scale=6, border=2, dark="#1b1f24", light=None)
    return out.getvalue()


def terminal(found: Pairing) -> str:
    """The QR as text for a terminal (./dev phone prints it)."""
    code = segno.make(found.payload(), error="m")
    out = io.StringIO()
    code.terminal(out=out, border=1)
    return out.getvalue()
