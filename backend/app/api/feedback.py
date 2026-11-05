"""Like or dislike what the app generated: a drawing, a set of Decide cards, the ideas, a draft,
price guidance, a search plan, a web find, a candidate, a project proposal, a build pack. The
owner and a judge's code vote on what they can see; the demo visitor is refused at the gate.
Nothing is sent to a model: the votes are read by the review tools (./dev picture-review,
./dev decide-review) as a person's signal."""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    DeciderDep,
    FeedbackDep,
    FinderDep,
    InventoryDep,
    PicturesDep,
    PlannerDep,
    ValuerDep,
)
from app.feedback import PICTURE_KINDS, Tally, Target, TargetKind, VoteCreate, ref_ok
from app.inventory import NotFoundError
from app.ops.door import sandbox

router = APIRouter(prefix="/api", tags=["feedback"])

NOT_THERE = "nothing to vote on there"

# the record each kind hangs off, as the gate names it for a judge's code
_ROOT = {
    "item_picture": "item",
    "card_picture": "item",
    "scenarios": "item",
    "uses": "item",
    "price_guidance": "item",
    "project_picture": "project",
    "project": "project",
    "draft": "draft",
    "search_plan": "search",
    "web_find": "search",
    "candidate": "candidate",
    "pack": "pack",
}


class Services:
    """What a target is looked up in, gathered so one function resolves every kind."""

    def __init__(
        self,
        inventory: InventoryDep,
        pictures: PicturesDep,
        decider: DeciderDep,
        valuer: ValuerDep,
        finder: FinderDep,
        planner: PlannerDep,
    ) -> None:
        self.inventory = inventory
        self.pictures = pictures
        self.decider = decider
        self.valuer = valuer
        self.finder = finder
        self.planner = planner


ServicesDep = Annotated[Services, Depends(Services)]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _resolve(t: Target, sv: Services) -> str:
    """The target, looked up as the caller may see it (404 otherwise); the drawing's digest
    for a picture, else empty. A judge's code sees what it made and the owner's records the
    demo visitor sees, never another judge's: the same rule the gate keeps for its reads."""
    if not ref_ok(t.target_kind, t.target_ref):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"target_ref does not name a {t.target_kind}",
        )
    ref = [int(p) for p in t.target_ref.split("/")] if t.target_ref else []
    judge = sandbox()
    public_only = False
    if judge:
        owner = sv.inventory.owner_of(_ROOT[t.target_kind], t.target_id)
        if owner is not None and owner != judge:
            raise NotFoundError(NOT_THERE)
        public_only = owner is None
    kind, tid = t.target_kind, t.target_id
    if kind == "item_picture":
        return _digest(sv.pictures.read(tid, ref[0], public_only=public_only))
    if kind in ("card_picture", "scenarios", "uses", "price_guidance"):
        sv.inventory.get(tid, public_only=public_only)
    if kind == "card_picture":
        scenarios = sv.decider.scenarios_by_id(tid, ref[0])
        return _digest(sv.pictures.card_read(scenarios, ref[1], ref[2]))
    if kind == "scenarios":
        sv.decider.scenarios_by_id(tid, ref[0])
    elif kind == "uses":
        if not any(u.id == ref[0] for u in sv.decider.all_uses(tid)):
            raise NotFoundError(NOT_THERE)
    elif kind == "price_guidance":
        if not any(g.id == ref[0] for g in sv.valuer.guidances(tid)):
            raise NotFoundError(NOT_THERE)
    elif kind in ("project", "project_picture"):
        sv.planner.project(tid, public_only=public_only)
        if kind == "project_picture":
            return _digest(sv.pictures.project_read(tid, ref[0]))
    elif kind == "pack":
        sv.planner.pack(tid, public_only=public_only)
    elif kind == "draft":
        sv.inventory.get(int(sv.inventory.draft(tid)["item_id"]), public_only=public_only)
    elif kind == "search_plan":
        if sv.finder.search(tid, public_only=public_only).plan is None:
            raise NotFoundError(NOT_THERE)
    elif kind == "web_find":
        if not any(x.id == ref[0] for x in sv.finder.listings(tid, public_only=public_only)):
            raise NotFoundError(NOT_THERE)
    elif kind == "candidate":
        sv.finder.candidate(tid, public_only=public_only)
    return ""


def _target(
    target_kind: Annotated[TargetKind, Query()],
    target_id: Annotated[int, Query(ge=1, le=10**12)],
    target_ref: Annotated[str, Query(max_length=40)] = "",
) -> Target:
    return Target(target_kind=target_kind, target_id=target_id, target_ref=target_ref)


TargetDep = Annotated[Target, Depends(_target)]


@router.get("/feedback", response_model=Tally)
def tally(target: TargetDep, feedback: FeedbackDep, sv: ServicesDep) -> Tally:
    """The likes and dislikes of one target and the caller's own vote with its reason. The
    owner counts every vote; a judge's code counts its own alone. Refused for the demo
    visitor."""
    _resolve(target, sv)
    return feedback.tally(target)


@router.post("/feedback", response_model=Tally)
def vote(spec: VoteCreate, feedback: FeedbackDep, sv: ServicesDep) -> Tally:
    """Like or dislike a target, with an optional one-line reason (at most 200 characters): the
    caller's vote, in place of the one they cast before. A judge's code votes on what it can
    see, its vote tagged with the code. Never sent to a model; refused for the demo visitor."""
    digest = _resolve(spec, sv)
    if spec.target_kind not in PICTURE_KINDS:
        digest = ""
    return feedback.vote(spec, digest)


@router.delete("/feedback", response_model=Tally)
def withdraw(target: TargetDep, feedback: FeedbackDep, sv: ServicesDep) -> Tally:
    """The caller's own vote on the target taken back."""
    _resolve(target, sv)
    return feedback.withdraw(target)
