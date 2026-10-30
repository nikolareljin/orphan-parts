"""Pairing the phone: the web origin it should talk to and, when the demo is gated, a session
of its own, as JSON, as a QR code or as text for a terminal. The access code never leaves the
server; what the phone gets is a session that ends like any other."""

import io
import re

import segno
from pydantic import BaseModel, Field

from app.ops.gate import Gate

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


def pairing(origin: str, gate: Gate) -> Pairing:
    if not ORIGIN.match(origin):
        raise BadOriginError("origin must be a scheme, a host and an optional port, nothing more")
    if not gate.enabled:
        return Pairing(url=origin, gated=False)
    token, expires_at = gate.issue()
    return Pairing(url=origin, gated=True, token=token, expires_at=expires_at)


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
