import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import GateDep
from app.ops.gate import COOKIE

router = APIRouter(prefix="/api", tags=["ops"])
log = logging.getLogger("app.gate")


class AccessRequest(BaseModel):
    code: str = Field(max_length=200)


class Access(BaseModel):
    gated: bool = Field(description="whether an access code is required at all")
    granted: bool = Field(description="whether this caller is through the code's door")
    live: bool = Field(
        default=False,
        description="whether this caller reaches the live models: the code's door and a key",
    )
    token: str = Field(default="", description="the session, for a caller without cookies")
    expires_at: int = Field(default=0, description="when the session ends, Unix seconds")


@router.get("/access", response_model=Access)
def access_status(request: Request, gate: GateDep) -> Access:
    """Whether a code is required, and whether this caller has a current session."""
    if not gate.enabled:
        return Access(gated=False, granted=True, live=gate.live_models)
    session = gate.verify(gate.token_of(request))
    granted = session is not None and session.live
    return Access(gated=True, granted=granted, live=granted and gate.live_models)


@router.post("/access", response_model=Access)
def grant_access(
    body: AccessRequest, request: Request, response: Response, gate: GateDep
) -> Access:
    """The access code for a session. Right: a session cookie, and the same token in the body
    for a caller that keeps no cookies. Wrong: nothing, and only so many tries per address."""
    if not gate.enabled:
        return Access(gated=False, granted=True, live=gate.live_models)
    ip = gate.client_ip(request)
    ok, retry = gate.attempts.take(ip)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many tries; wait {retry} s",
            headers={"Retry-After": str(retry)},
        )
    found = gate.which_key(body.code)
    if found is None:
        raise HTTPException(status_code=401, detail="that is not the access code")
    which, kid = found
    gate.attempts.forget(ip)
    log.info("session opened", extra={"code": which})
    token, expires_at = gate.issue(kid=kid)
    response.set_cookie(
        COOKIE,
        token,
        max_age=gate.session_seconds,
        httponly=True,
        samesite="strict",
        secure=gate.cookie_secure,
        path="/",
    )
    return Access(
        gated=True, granted=True, live=gate.live_models, token=token, expires_at=expires_at
    )


@router.delete("/access", response_model=Access)
def leave(response: Response, gate: GateDep) -> Access:
    """End this session on this browser."""
    response.delete_cookie(COOKIE, path="/")
    return Access(
        gated=gate.enabled, granted=not gate.enabled, live=not gate.enabled and gate.live_models
    )
