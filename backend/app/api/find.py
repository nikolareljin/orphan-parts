from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.api.deps import FinderDep
from app.api.model_errors import as_http
from app.find import (
    BroughtListing,
    Candidate,
    CandidateCreate,
    FindError,
    ListingsBack,
    PatternResult,
    PatternTest,
    PlanEdit,
    Search,
    SearchCreate,
    SearchPatch,
    SellerQuestions,
)
from app.find.schema import seen_day

router = APIRouter(prefix="/api", tags=["find"])

ScreenshotPart = Annotated[
    UploadFile | None, File(description="A screenshot of the listing, for a screenshot candidate")
]
RequestPart = Annotated[str, Form(description="The candidate, as JSON (CandidateCreate)")]
ScreenshotsPart = Annotated[
    list[UploadFile], File(description="Screenshots of listings, one listing each")
]
SeenPart = Annotated[str, Form(description="The day they were seen, YYYY-MM-DD; today if empty")]
MAX_SCREENSHOTS = 6


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


@router.post("/searches/{search_id}/plan", response_model=Search)
async def plan_search(search_id: int, finder: FinderDep) -> Search:
    """One Muse Spark call: three to six phrasings a seller might have used, each a Marketplace
    search link the owner opens, one match pattern a fitting listing matches and the words
    that rule a listing out. Marketplace has no public search API and its search box takes no
    regular expressions; the pattern is applied here, to the listings brought back."""
    try:
        return await finder.plan(search_id)
    except FindError as exc:
        raise _find_error(exc) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.patch("/searches/{search_id}/plan", response_model=Search)
def edit_plan(search_id: int, edit: PlanEdit, finder: FinderDep) -> Search:
    """The owner's pattern and exclusion words. The pattern is checked before it is kept;
    every listing brought back is scored again by the plan as it now stands."""
    try:
        return finder.edit_plan(search_id, edit)
    except FindError as exc:
        raise _find_error(exc) from exc


@router.post("/find/pattern", response_model=PatternResult)
def test_pattern(spec: PatternTest, finder: FinderDep) -> PatternResult:
    """A pattern tried on a line of text: why it is refused, or how the line scores. Free."""
    return finder.test_pattern(spec)


@router.get("/searches/{search_id}/listings", response_model=list[BroughtListing])
def list_listings(search_id: int, finder: FinderDep) -> list[BroughtListing]:
    """The listings brought back, ranked: fits, maybe, does not fit; cheaper first in each."""
    return finder.listings(search_id)


@router.post(
    "/searches/{search_id}/listings",
    response_model=list[BroughtListing],
    status_code=status.HTTP_201_CREATED,
)
def add_listings(search_id: int, back: ListingsBack, finder: FinderDep) -> list[BroughtListing]:
    """Several pasted listings at once, each scored by the plan's pattern, its exclusion words
    and the price limit. No model call; the answer is the whole ranked list."""
    try:
        return finder.add_listings(search_id, back)
    except FindError as exc:
        raise _find_error(exc) from exc


@router.post(
    "/searches/{search_id}/listings/screenshots",
    response_model=list[BroughtListing],
    status_code=status.HTTP_201_CREATED,
)
async def add_listing_screenshots(
    search_id: int,
    screenshots: ScreenshotsPart,
    finder: FinderDep,
    observed_on: SeenPart = "",
) -> list[BroughtListing]:
    """Screenshots of listings, up to six: each is read into text by the extractor (one call
    each) and scored like a pasted listing."""
    if not screenshots or len(screenshots) > MAX_SCREENSHOTS:
        raise HTTPException(status_code=422, detail=f"one to {MAX_SCREENSHOTS} screenshots")
    try:
        seen = seen_day(observed_on)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"observed_on: {exc}") from exc
    max_mb = finder.settings.max_upload_mb
    shots: list[bytes] = []
    for shot in screenshots:
        if shot.size is not None and shot.size > max_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"a screenshot is larger than {max_mb} MB")
        shots.append(await shot.read())
    try:
        return await finder.add_screenshots(search_id, shots, seen)
    except FindError as exc:
        raise _find_error(exc) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.delete("/searches/{search_id}/listings/{listing_id}", response_model=list[BroughtListing])
def remove_listing(search_id: int, listing_id: int, finder: FinderDep) -> list[BroughtListing]:
    return finder.remove_listing(search_id, listing_id)


@router.post("/searches/{search_id}/listings/{listing_id}/check", response_model=Candidate)
async def check_listing(search_id: int, listing_id: int, finder: FinderDep) -> Candidate:
    """Check fit: Muse Spark reads the listing into fields once and the profile's rules
    assess it; the candidate carries the seller questions. Asked again, it is the same one."""
    try:
        return await finder.check_listing(search_id, listing_id)
    except FindError as exc:
        raise _find_error(exc) from exc
    except Exception as exc:
        raise as_http(exc) from exc


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
