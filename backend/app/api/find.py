from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import FinderDep
from app.api.model_errors import as_http
from app.find import (
    Candidate,
    CandidateCreate,
    FindError,
    Search,
    SearchCreate,
    SearchPatch,
    SellerQuestions,
)

router = APIRouter(prefix="/api", tags=["find"])

ScreenshotPart = Annotated[
    UploadFile | None, File(description="A screenshot of the listing, for a screenshot candidate")
]
RequestPart = Annotated[str, Form(description="The candidate, as JSON (CandidateCreate)")]


def _find_error(exc: FindError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/searches", response_model=Search, status_code=status.HTTP_201_CREATED)
def create_search(spec: SearchCreate, finder: FinderDep) -> Search:
    """What is needed, as another item's requirements or values written in under a profile,
    with the radius, the top price and the budget left. The answer carries the Marketplace
    search to run by hand; nothing is searched, fetched or posted by the service."""
    try:
        return finder.create(spec)
    except FindError as exc:
        raise _find_error(exc) from exc


@router.get("/searches", response_model=list[Search])
def list_searches(finder: FinderDep) -> list[Search]:
    return finder.searches()


@router.get("/searches/{search_id}", response_model=Search)
def get_search(search_id: int, finder: FinderDep) -> Search:
    return finder.search(search_id)


@router.patch("/searches/{search_id}", response_model=Search)
def update_search(search_id: int, patch: SearchPatch, finder: FinderDep) -> Search:
    """Close a search, mark it found, or change its notes."""
    return finder.update(search_id, patch)


@router.post(
    "/searches/{search_id}/candidates",
    response_model=Candidate,
    status_code=status.HTTP_201_CREATED,
)
async def add_candidate(
    search_id: int,
    request: RequestPart,
    finder: FinderDep,
    screenshot: ScreenshotPart = None,
) -> Candidate:
    """A listing brought back: its text, a screenshot or values typed in, with the day it was
    seen. Muse Spark reads the text into fields, the extractor reads a screenshot, typed values
    are the owner's word; then the profile's rules assess it and the ladder names its state."""
    try:
        spec = CandidateCreate.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", "request", *e["loc"]], "msg": e["msg"]} for e in exc.errors()],
        ) from exc
    data: bytes | None = None
    if screenshot is not None:
        max_mb = finder.settings.max_upload_mb
        if screenshot.size is not None and screenshot.size > max_mb * 1024 * 1024:
            raise HTTPException(
                status_code=400, detail=f"the screenshot is larger than {max_mb} MB"
            )
        data = await screenshot.read()
    try:
        return await finder.add_candidate(search_id, spec, data)
    except FindError as exc:
        raise _find_error(exc) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/searches/{search_id}/candidates", response_model=list[Candidate])
def list_candidates(search_id: int, finder: FinderDep) -> list[Candidate]:
    return finder.candidates(search_id)


@router.get("/candidates/{candidate_id}", response_model=Candidate)
def get_candidate(candidate_id: int, finder: FinderDep) -> Candidate:
    return finder.candidate(candidate_id)


@router.post("/candidates/{candidate_id}/recheck", response_model=Candidate)
def recheck_candidate(candidate_id: int, finder: FinderDep) -> Candidate:
    """The same listing against the need as it stands now; the observation date stays."""
    try:
        return finder.recheck(candidate_id)
    except FindError as exc:
        raise _find_error(exc) from exc


@router.post("/candidates/{candidate_id}/withdraw", response_model=Candidate)
def withdraw_candidate(candidate_id: int, finder: FinderDep) -> Candidate:
    return finder.withdraw(candidate_id)


@router.get("/candidates/{candidate_id}/questions", response_model=SellerQuestions)
def seller_questions(candidate_id: int, finder: FinderDep) -> SellerQuestions:
    """The rules' questions for this candidate as a message the owner can send to the seller."""
    return finder.questions(candidate_id)
