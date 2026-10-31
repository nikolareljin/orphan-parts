from fastapi import APIRouter, status

from app.api.deps import DeciderDep
from app.api.model_errors import as_http
from app.decide import Decision, DecisionCreate, Scenarios, Uses
from app.inventory import Item

router = APIRouter(prefix="/api", tags=["decide"])


@router.post("/items/{item_id}/uses", response_model=Uses, status_code=status.HTTP_201_CREATED)
async def propose_uses(item_id: int, decider: DeciderDep) -> Uses:
    """What the item is good for. The rules name the project templates whose requirements the
    item fills; Muse Spark proposes up to three uses from the item's accepted values,
    condition, faults, tests and the owner's preferences, each with what else it needs and the
    effort. Kept on the item, labeled as the model's proposals."""
    try:
        return await decider.uses(item_id)
    except Exception as exc:
        raise as_http(exc) from exc


@router.post(
    "/items/{item_id}/scenarios", response_model=Scenarios, status_code=status.HTTP_201_CREATED
)
async def write_scenarios(item_id: int, decider: DeciderDep) -> Scenarios:
    """What to do with it, for this owner. One Muse Spark call writes three cards from the
    item's accepted values, condition, faults, tests, accessories and intent, the owner's
    profile (rated skills, tools, effort, whether they open devices, budget) and the kinds of
    item they own besides: keep and fix (the likely problems, the steps at their level, the
    difficulty for them and why, parts, cost, time, or that it is not worth fixing), two or
    three reuse scenarios naming what else they own, and what selling it takes; then one
    recommendation with a reason tied to the profile. Without a profile the cards are written
    for an average person and say so (`profiled` false). Kept on the item with its version;
    `stale` once the item changes."""
    try:
        return await decider.scenarios(item_id)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/items/{item_id}/decide", response_model=Decision)
def decision_view(item_id: int, decider: DeciderDep) -> Decision:
    """One view to decide from: the item and how many values are accepted, the latest price
    guidance with the strategy to start from, the latest uses and scenarios, the open searches
    from this item with their candidate counts, the templates it fills, its intent, the
    selected projects that count on it (`committed_to`) and the last decision. Nothing is
    asked of a model."""
    return decider.decision(item_id)


@router.post("/items/{item_id}/decision", response_model=Item)
def decide(item_id: int, spec: DecisionCreate, decider: DeciderDep) -> Item:
    """The owner's choice: `keep_build` sets the intent to build, `sell` and `give` to the
    same, `keep_fix` and `not_worth` keep the item, the one to be repaired, the other with
    the note saying why. `keep_fix` also adds the repair steps of the current scenarios to the
    item's notes. The history gets `decided: <choice>: <note>`; the version is bumped when the
    intent changes, a note is given or the notes gain the repair steps, not for the same
    choice said again. With `version` set, a choice made from an older
    version of the item is refused with 409 and nothing is written."""
    return decider.decide(item_id, spec)
