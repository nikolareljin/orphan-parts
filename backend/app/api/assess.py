from fastapi import APIRouter, HTTPException

from app.api.deps import AssessorDep
from app.match import AssessError, Assessment, AssessRequest

router = APIRouter(prefix="/api", tags=["match"])


@router.post("/assess", response_model=Assessment)
def assess(request: AssessRequest, assessor: AssessorDep) -> Assessment:
    """Apply the profile's rules to a need and a candidate: each rule passes, fails or stays
    unknown, the ladder gives one verdict, and every unknown becomes a question. Either side is
    an inventory item or values written in; the profile comes from the request or an item."""
    try:
        return assessor.assess(request)
    except AssessError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
