from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import PlannerDep
from app.api.model_errors import as_http
from app.projects import (
    AllocationConflictError,
    FillRequest,
    Preferences,
    Project,
    ProjectList,
    ProjectsError,
    ProposeRequest,
    SelectRequest,
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
    return planner.shortlist(project_id)


@router.post("/projects/{project_id}/select", response_model=Project)
def select(project_id: int, request: SelectRequest, planner: PlannerDep) -> Project:
    """Commit the project's items. 409 with the conflicts when an item is committed to another
    selected project; `take: true` moves it here and opens the requirement there."""
    try:
        return planner.select(project_id, take=request.take)
    except AllocationConflictError as exc:
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": str(exc),
                "conflicts": [c.model_dump() for c in exc.conflicts],
            },
        )


@router.post("/projects/{project_id}/abandon", response_model=Project)
def abandon(project_id: int, planner: PlannerDep) -> Project:
    return planner.abandon(project_id)


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
