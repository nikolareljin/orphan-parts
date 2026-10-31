"""Pairing the phone: the web origin it should talk to and, when the demo is gated, a session
of its own, as JSON, as a QR code or as text for a terminal. The access code never leaves the
server; what the phone gets is a pairing, a session of minutes, and, once it has scanned, a
code of its own claimed with that pairing, so it stays through the gate after the pairing
ends. The demo visitor's QR carries the address alone: the phone joins as the demo too."""

import io
import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

import segno
from pydantic import BaseModel, Field

from app.keys import AccessKey, AccessKeys
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


def served_origins(headers: Mapping[str, str], configured: Iterable[str] = ()) -> set[str]:
    """The origins this server answers for, as the request shows them: the browser's Origin
    and Referer, the Host it asked for (either scheme: a proxy in front may end TLS), a proxy's
    forwarded host, and the configured CORS origins. Nothing else may go into a pairing, so a
    QR drawn here points only back at this server."""
    found = {o.rstrip("/").lower() for o in configured}
    for name in ("origin", "referer"):
        parts = urlsplit(headers.get(name, ""))
        if parts.scheme in ("http", "https") and parts.netloc:
            found.add(f"{parts.scheme}://{parts.netloc}".lower())
    for name in ("x-forwarded-host", "host"):
        host = headers.get(name, "").split(",")[0].strip().lower()
        if host:
            found |= {f"http://{host}", f"https://{host}"}
    return found


def pairing(
    origin: str,
    gate: Gate,
    api: str = "",
    kid: int = 0,
    stamp: str = "",
    *,
    visitor: bool = False,
    served: set[str] | None = None,
) -> Pairing:
    """The phone talks to ``api`` when the web app is served from another origin (Cloudflare
    Pages in front of Modal), and to the web origin otherwise, which proxies the API. Over
    HTTP both must be among the origins this server is ``served`` at (served_origins); the
    command line, which prints for this machine, passes none. For the demo ``visitor`` (no
    session) the gated pairing is the address alone; otherwise it carries a pairing, the
    short session that claims the phone's own code."""
    for given in (origin, api):
        if given and not ORIGIN.match(given):
            raise BadOriginError(
                "origin must be a scheme, a host and an optional port, nothing more"
            )
        if given and served is not None and given.lower() not in served:
            raise BadOriginError(f"{given} is not an origin this server is reached at")
    if not origin:
        raise BadOriginError("origin must be a scheme, a host and an optional port, nothing more")
    url = api or origin
    if not gate.enabled:
        return Pairing(url=url, gated=False)
    if visitor:
        # nothing issued and nothing stored: the phone is the demo visitor, as the browser is
        return Pairing(url=url, gated=True)
    # the pairing is the caller's: from an issued code, it ends with that code
    token, expires_at = gate.issue(kid=kid, stamp=stamp, pairing=True)
    return Pairing(url=url, gated=True, token=token, expires_at=expires_at)


def phone_code(session: Session, keys: AccessKeys, days: int) -> tuple[str, AccessKey]:
    """The phone's own code, claimed with its pairing: an issued record labeled after the
    pairing (``phone`` and the first eight characters of its id), so one pairing claims
    once; the label is kept with the record whatever becomes of it, and a second claim with
    the same pairing is refused for as long as the record exists, revoked or not. It lasts
    ``days``, never past the code that opened the pairing, and stands only while that code
    does: an issued record revoked or expired, or a master code changed, ends it."""
    return keys.issue_child(
        f"phone {session.sid[:8]}", days, parent=session.kid, stamp=session.stamp
    )


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
