from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.api.deps import GateDep
from app.pairing import BadOriginError, Pairing, pairing, svg

router = APIRouter(prefix="/api", tags=["ops"])


def _pairing(request: Request, origin: str, gate: GateDep, api: str = "") -> Pairing:
    session = gate.verify(gate.token_of(request)) if gate.enabled else None
    try:
        return pairing(origin, gate, api, kid=session.kid if session is not None else 0)
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
    """What the phone needs: the origin to talk to and, when the demo is gated, a session of
    its own. Reached only with a session, so only someone already in can hand the phone one."""
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
