from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import GateDep
from app.pairing import BadOriginError, Pairing, pairing, svg

router = APIRouter(prefix="/api", tags=["ops"])


def _pairing(origin: str, gate: GateDep) -> Pairing:
    try:
        return pairing(origin, gate)
    except BadOriginError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/pair", response_model=Pairing)
def pair(gate: GateDep, origin: str = Query(description="the web app's origin")) -> Pairing:
    """What the phone needs: the origin to talk to and, when the demo is gated, a session of
    its own. Reached only with a session, so only someone already in can hand the phone one."""
    return _pairing(origin, gate)


@router.get("/pair.svg", response_class=Response)
def pair_svg(gate: GateDep, origin: str = Query(description="the web app's origin")) -> Response:
    """The same, as a QR code the phone scans."""
    return Response(
        svg(_pairing(origin, gate)),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )
