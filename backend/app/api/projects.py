from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response

from app.api.deps import PlannerDep
from app.api.model_errors import as_http
from app.projects import (
    AllocationConflictError,
    FillRequest,
    OutcomeCreate,
    Pack,
    Preferences,
    ProgressChange,
    Project,
    ProjectList,
    ProjectsError,
    ProposeRequest,
    SelectRequest,
    ShareChange,
    ShareText,
    TemplateSummary,
)

router = APIRouter(prefix="/api", tags=["projects"])


def _error(exc: ProjectsError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.get("/preferences", response_model=Preferences)
def get_preferences(planner: PlannerDep) -> Preferences:
    return planner.preferences()


@router.put("/preferences", response_model=Preferences)
def put_preferences(prefs: Preferences, planner: PlannerDep) -> Preferences:
    """What you want from a build: interests, effort, skills, tools, whether you open devices,
    the budget and currency, the radius, used or new. Read by every proposal."""
    return planner.set_preferences(prefs)


@router.get("/templates", response_model=list[TemplateSummary])
def templates(planner: PlannerDep) -> list[TemplateSummary]:
    """The projects that may be proposed, kept as data, with what each requires."""
    return planner.templates.summaries()


@router.post("/projects/propose", response_model=list[Project], status_code=201)
async def propose(request: ProposeRequest, planner: PlannerDep) -> list[Project]:
    """Muse Spark reads the inventory and the templates through tools and proposes projects;
    only a proposal every allocation of which names a usable item that fits is kept. Each
    becomes a project in the proposed state with exploratory allocations."""
    try:
        return await planner.propose(request)
    except ProjectsError as exc:
        raise _error(exc) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/projects", response_model=ProjectList)
def list_projects(planner: PlannerDep) -> ProjectList:
    """Every project, newest first, and what the selected set spends against the budget."""
    return planner.projects()


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: int, planner: PlannerDep) -> Project:
    return planner.project(project_id)


@router.post("/projects/{project_id}/shortlist", response_model=Project)
def shortlist(project_id: int, planner: PlannerDep) -> Project:
    """Keep the proposal in mind; a selected project put back here releases its items."""
    try:
        return planner.shortlist(project_id)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/select", response_model=Project)
def select(project_id: int, request: SelectRequest, planner: PlannerDep) -> Project:
    """Commit the project's items. 409 with the conflicts when an item is committed to another
    selected project; `take: true` moves it here and opens the requirement there."""
    try:
        return planner.select(project_id, take=request.take)
    except ProjectsError as exc:
        if not isinstance(exc, AllocationConflictError):
            raise _error(exc) from exc
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "conflicts": [c.model_dump() for c in exc.conflicts],
            },
        )


@router.post("/projects/{project_id}/abandon", response_model=Project)
def abandon(project_id: int, planner: PlannerDep) -> Project:
    """Give the project up from any state but done; its items are released."""
    try:
        return planner.abandon(project_id)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/advance/{to}", response_model=Project)
def advance(project_id: int, to: str, planner: PlannerDep) -> Project:
    """A selected project moves to building, then done."""
    try:
        return planner.advance(project_id, to)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/requirements/{key}/search", response_model=Project)
def search_for(project_id: int, key: str, planner: PlannerDep) -> Project:
    """A missing requirement becomes a search request, with the budget left as its ceiling."""
    try:
        return planner.search_for(project_id, key)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/requirements/{key}/fill", response_model=Project)
def fill(project_id: int, key: str, request: FillRequest, planner: PlannerDep) -> Project:
    """An item of yours for a requirement the proposal left open; it must be usable and of a
    kind the requirement takes. A search open for it is marked found."""
    try:
        return planner.fill(project_id, key, request)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/pack", response_model=Pack, status_code=201)
def write_pack(project_id: int, planner: PlannerDep) -> Pack:
    """The build pack from what stands now, written by the rules: goal, the items with their
    accepted values (never a serial, a location or a note), what is still needed with its
    search, costs with dates, steps with progress, safety, unknowns, guidance, limitations and
    the outcome; versioned, with a digest of its inputs."""
    try:
        return planner.write_pack(project_id)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/packs", response_model=list[Pack])
def packs(project_id: int, planner: PlannerDep) -> list[Pack]:
    """Every pack written for the project, each `stale` when its inputs changed since."""
    return planner.packs_of(project_id)


@router.get("/packs/{pack_id}.md", response_class=Response)
def pack_markdown(pack_id: int, planner: PlannerDep) -> Response:
    """The pack as a Markdown file to keep."""
    found = planner.pack(pack_id)
    name = f"build-pack-{found.project_id}-v{found.version}.md"
    return Response(
        found.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/packs/{pack_id}", response_model=Pack)
def pack(pack_id: int, planner: PlannerDep) -> Pack:
    return planner.pack(pack_id)


@router.post("/projects/{project_id}/progress", response_model=Project)
def progress(project_id: int, change: ProgressChange, planner: PlannerDep) -> Project:
    """Tick or untick one step of a selected or building project."""
    try:
        return planner.set_progress(project_id, change.step, change.done)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/outcome", response_model=Project)
def outcome(project_id: int, record: OutcomeCreate, planner: PlannerDep) -> Project:
    """What was built and how it was tested, in your words; a working result marks the project
    done, a failed test keeps it building with the record kept."""
    try:
        return planner.record_outcome(project_id, record)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/outcome/share", response_model=Project)
def share(project_id: int, change: ShareChange, planner: PlannerDep) -> Project:
    """Whether the outcome may be shown to others; off by default."""
    try:
        return planner.set_share(project_id, change)
    except ProjectsError as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/outcome/share", response_model=ShareText)
def share_text(project_id: int, planner: PlannerDep) -> ShareText:
    """The outcome for other people, once shared: the kinds of items, the result, the set-up,
    the test and the limits; no names, ids, values, places or prices."""
    try:
        return ShareText(text=planner.share_text(project_id))
    except ProjectsError as exc:
        raise _error(exc) from exc
