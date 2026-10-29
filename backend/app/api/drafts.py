from fastapi import APIRouter, HTTPException

from app.api.deps import ListerDep
from app.api.model_errors import as_http
from app.listing import Draft, DraftRequest, StepChange

router = APIRouter(prefix="/api", tags=["listing"])


@router.post("/items/{item_id}/drafts", response_model=Draft, status_code=201)
async def write_draft(item_id: int, request: DraftRequest, lister: ListerDep) -> Draft:
    """Write a listing draft for sale or free pickup from what is confirmed about the item.
    Muse Spark writes the prose; the rules add the disclosures (faults, what was tested, what is
    included, price or free, pickup) and drop any line that rests on nothing confirmed. The
    draft comes with its preparation checklist, and the data-removal steps when the item holds
    data."""
    try:
        return await lister.draft(item_id, request)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/items/{item_id}/drafts", response_model=list[Draft])
def list_drafts(item_id: int, lister: ListerDep) -> list[Draft]:
    """Every draft written for the item, newest last, each saying whether the item changed
    since."""
    return lister.drafts(item_id)


@router.get("/drafts/{draft_id}", response_model=Draft)
def get_draft(draft_id: int, lister: ListerDep) -> Draft:
    return lister.get(draft_id)


@router.post("/drafts/{draft_id}/checklist", response_model=Draft)
def set_step(draft_id: int, change: StepChange, lister: ListerDep) -> Draft:
    """Tick or untick one step of the draft's checklist."""
    try:
        return lister.set_step(draft_id, change)
    except LookupError as exc:
        if "no step" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise
