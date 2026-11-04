import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import GateDep
from app.keys import AccessKey
from app.ops.gate import COOKIE, Gate

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
    judge: "JudgeAccess | None" = Field(
        default=None, description="set when the session is a judge's code: what it may still do"
    )


class JudgeAccess(BaseModel):
    """A judge's code: read-only on the demo set, its own items its own, its limits."""

    code_id: int = Field(description="the code's record id; items with this owner_code are its")
    recorded: bool = Field(description="answered from the recorded answers only, never live")
    calls_per_day: int | None
    calls_left: int | None = Field(description="live calls left today (UTC); null = no cap")
    max_usd: float | None
    usd_left: float | None = Field(description="dollars left of the code's cap; null = no cap")


Access.model_rebuild()


def judge_of(gate: Gate, key: AccessKey | None) -> JudgeAccess | None:
    if key is None or not key.judge or gate.keys is None:
        return None
    used = gate.keys.usage(key.id)
    return JudgeAccess(
        code_id=key.id,
        recorded=key.recorded,
        calls_per_day=key.calls_per_day,
        calls_left=None
        if key.calls_per_day is None
        else max(0, key.calls_per_day - used.calls_today),
        max_usd=key.max_usd,
        usd_left=None if key.max_usd is None else round(max(0.0, key.max_usd - used.usd), 4),
    )


@router.get("/access", response_model=Access)
def access_status(request: Request, gate: GateDep) -> Access:
    """Whether a code is required, and whether this caller has a current session."""
    if not gate.enabled:
        return Access(gated=False, granted=True, live=gate.live_models)
    session = gate.verify(gate.token_of(request))
    granted = session is not None and session.live
    judge = judge_of(gate, session.key) if session is not None and granted else None
    live = granted and gate.live_models and not (judge is not None and judge.recorded)
    return Access(gated=True, granted=granted, live=live, judge=judge)


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
    which, kid, stamp = found
    gate.attempts.forget(ip)
    log.info("session opened", extra={"label": which})
    token, expires_at = gate.issue(kid=kid, stamp=stamp)
    judge = judge_of(gate, gate.keys.current(kid)) if kid and gate.keys is not None else None
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
        gated=True,
        granted=True,
        live=gate.live_models and not (judge is not None and judge.recorded),
        token=token,
        expires_at=expires_at,
        judge=judge,
    )


@router.delete("/access", response_model=Access)
def leave(response: Response, gate: GateDep) -> Access:
    """End this session on this browser. Sessions are not stored, so the token stays good until
    it expires; what ends here is the browser's hold on it. Revoking the code ends them all."""
    # a browser drops the cookie only when the attributes match the ones it was set with
    response.delete_cookie(
        COOKIE, path="/", httponly=True, samesite="strict", secure=gate.cookie_secure
    )
    return Access(
        gated=gate.enabled, granted=not gate.enabled, live=not gate.enabled and gate.live_models
    )
