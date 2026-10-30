from fastapi import APIRouter, status

from app.api.deps import DeciderDep
from app.api.model_errors import as_http
from app.decide import Decision, DecisionCreate, Uses
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


@router.get("/items/{item_id}/decide", response_model=Decision)
def decision_view(item_id: int, decider: DeciderDep) -> Decision:
    """One view to decide from: the item and how many values are accepted, the latest price
    guidance with the strategy to start from, the latest uses, the open searches from this
    item with their candidate counts, the templates it fills, its intent, the selected
    projects that count on it (`committed_to`) and the last decision. Nothing is asked of a
    model."""
    return decider.decision(item_id)


@router.post("/items/{item_id}/decision", response_model=Item)
def decide(item_id: int, spec: DecisionCreate, decider: DeciderDep) -> Item:
    """The owner's choice: `keep_build` sets the intent to build, `sell` and `give` to the
    same, `not_worth` keeps the item with the note. The history gets
    `decided: <choice>: <note>`; the version is bumped when the intent changes or a note is
    given, not for the same choice said again."""
    return decider.decide(item_id, spec)
