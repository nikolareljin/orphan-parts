import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.api.deps import GateDep, SettingsDep
from app.keys import AccessKeyError
from app.pairing import (
    BadOriginError,
    Pairing,
    PhoneCode,
    pairing,
    phone_code,
    served_origins,
    svg,
)

router = APIRouter(prefix="/api", tags=["ops"])
log = logging.getLogger("app.gate")
PAIR_EXPIRES = "X-Pair-Expires-At"
PAIR_EXPIRES_IN = "X-Pair-Expires-In"
PAIRING_ENDED = "the pairing has ended; reload the signed-in page and scan its new code"
BROWSER_CLAIM = "a browser's session does not claim a phone's code; scan the QR code with the app"


def _pairing(
    request: Request, origin: str, gate: GateDep, settings: SettingsDep, api: str = ""
) -> Pairing:
    session = gate.verify(gate.token_of(request)) if gate.enabled else None
    # only a browser through the door hands out a pairing; a pairing does not beget another
    if session is not None and (not session.live or session.pairing):
        session = None
    served = served_origins(request.headers, settings.cors_origin_list)
    try:
        kid, stamp = (session.kid, session.stamp) if session is not None else (0, "")
        return pairing(
            origin, gate, api, kid=kid, stamp=stamp, visitor=session is None, served=served
        )
    except BadOriginError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/pair", response_model=Pairing)
def pair(
    request: Request,
    response: Response,
    gate: GateDep,
    settings: SettingsDep,
    origin: str = Query(description="the web app's origin"),
    api: str = Query(default="", description="the API's origin, when it is not the web app's"),
) -> Pairing:
    """What the phone needs: the origin to talk to and, when the demo is gated and the caller
    is through the door, a pairing of its own (PAIR_TOKEN_MINUTES long). The demo visitor gets
    the origin alone, so a phone paired from an anonymous page is the demo visitor as well.
    Both origins must be ones this server is reached at: the request's own, or CORS_ORIGINS."""
    found = _pairing(request, origin, gate, settings, api)
    response.headers["Cache-Control"] = "no-store"
    return found


@router.get("/pair.svg", response_class=Response)
def pair_svg(
    request: Request,
    gate: GateDep,
    settings: SettingsDep,
    origin: str = Query(description="the web app's origin"),
    api: str = Query(default="", description="the API's origin, when it is not the web app's"),
) -> Response:
    """The same, as a QR code the phone scans; when it carries a pairing, X-Pair-Expires-At
    says when that ends (Unix seconds) and X-Pair-Expires-In how many seconds are left, by
    this server's clock, so the page draws a new one before then whatever its own says."""
    found = _pairing(request, origin, gate, settings, api)
    headers = {"Cache-Control": "no-store"}
    if found.expires_at:
        headers[PAIR_EXPIRES] = str(found.expires_at)
        headers[PAIR_EXPIRES_IN] = str(max(0, found.expires_at - int(time.time())))
    return Response(svg(found), media_type="image/svg+xml", headers=headers)


@router.post("/pair/code", response_model=PhoneCode)
def pair_code(request: Request, gate: GateDep, settings: SettingsDep) -> PhoneCode:
    """The phone's own access code, claimed once with the pairing its QR carried and shown
    once: it opens a session through ``POST /api/access`` like a typed code. Without a gate
    there is nothing to give. Each try counts against the address's code attempts (429 once
    spent), and a claim that works clears the count; no live pairing, 401; a browser's
    session, a second claim, a pairing whose code has ended, or a code that has paired
    PAIR_CODE_MAX phones already, 403."""
    if not gate.enabled:
        return PhoneCode(gated=False)
    ip = gate.client_ip(request)
    ok, retry = gate.attempts.take(ip)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many tries; wait {retry} s",
            headers={"Retry-After": str(retry)},
        )
    session = gate.verify(gate.token_of(request))
    if session is None or not session.live or gate.keys is None:
        raise HTTPException(status_code=401, detail=PAIRING_ENDED)
    if not session.pairing:
        raise HTTPException(status_code=403, detail=BROWSER_CLAIM)
    try:
        code, key = phone_code(session, gate.keys, settings.pair_code_days, settings.pair_code_max)
    except AccessKeyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # a claim that worked is no guess: the address keeps its tries, as with a correct code
    gate.attempts.forget(ip)
    log.info("a phone claimed its code", extra={"label": key.label})
    return PhoneCode(gated=True, code=code, label=key.label, expires_at=key.expires_at)
