import logging

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.api.deps import GateDep, SettingsDep
from app.keys import AccessKeyError
from app.pairing import BadOriginError, Pairing, PhoneCode, pairing, phone_code, svg

router = APIRouter(prefix="/api", tags=["ops"])
log = logging.getLogger("app.gate")


def _pairing(request: Request, origin: str, gate: GateDep, api: str = "") -> Pairing:
    session = gate.verify(gate.token_of(request)) if gate.enabled else None
    if session is not None and not session.live:
        session = None
    try:
        kid, stamp = (session.kid, session.stamp) if session is not None else (0, "")
        return pairing(origin, gate, api, kid=kid, stamp=stamp, visitor=session is None)
    except BadOriginError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/pair", response_model=Pairing)
def pair(
    request: Request,
    response: Response,
    gate: GateDep,
    origin: str = Query(description="the web app's origin"),
    api: str = Query(default="", description="the API's origin, when it is not the web app's"),
) -> Pairing:
    """What the phone needs: the origin to talk to and, when the demo is gated and the caller
    is through the door, a session of its own. The demo visitor gets the origin alone, so a
    phone paired from an anonymous page is the demo visitor as well."""
    found = _pairing(request, origin, gate, api)
    response.headers["Cache-Control"] = "no-store"
    return found


@router.get("/pair.svg", response_class=Response)
def pair_svg(
    request: Request,
    gate: GateDep,
    origin: str = Query(description="the web app's origin"),
    api: str = Query(default="", description="the API's origin, when it is not the web app's"),
) -> Response:
    """The same, as a QR code the phone scans."""
    return Response(
        svg(_pairing(request, origin, gate, api)),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/pair/code", response_model=PhoneCode)
def pair_code(request: Request, gate: GateDep, settings: SettingsDep) -> PhoneCode:
    """The phone's own access code, claimed once with the session its pairing carried and
    shown once: it opens a session through ``POST /api/access`` like a typed code after the
    pairing's session ends. Without a gate there is nothing to give; without a session, 401;
    a second claim, or a session whose code has ended, 403."""
    if not gate.enabled:
        return PhoneCode(gated=False)
    session = gate.verify(gate.token_of(request))
    if session is None or not session.live or gate.keys is None:
        raise HTTPException(status_code=401, detail="the pairing has ended; scan the code again")
    try:
        code, key = phone_code(session, gate.keys, settings.pair_code_days)
    except AccessKeyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    log.info("a phone claimed its code", extra={"label": key.label})
    return PhoneCode(gated=True, code=code, label=key.label, expires_at=key.expires_at)
