from collections.abc import Awaitable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import DeciderDep, PicturesDep, PlannerDep
from app.api.model_errors import as_http
from app.ops.door import live_request
from app.picture import OFF_LINE, Picture, PictureList, Pictures, PicturesOffError

router = APIRouter(prefix="/api/items", tags=["inventory"])
projects_router = APIRouter(prefix="/api/projects", tags=["projects"])


class PictureRequest(BaseModel):
    use: str = Field(
        default="",
        max_length=200,
        description="what to draw the item as: a project template id, a use in your own"
        " words, or empty for the item itself",
    )


async def _drawn(call: Awaitable[Picture]) -> Picture:
    try:
        return await call
    except PicturesOffError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise as_http(exc) from exc


def _on(pictures: Pictures) -> None:
    """``503`` before anything is looked up while the server draws nothing."""
    if not pictures.settings.picture_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=OFF_LINE)


def _jpeg(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{item_id}/picture", response_model=Picture, status_code=status.HTTP_201_CREATED)
async def draw_picture(item_id: int, request: PictureRequest, pictures: PicturesDep) -> Picture:
    """Draw what the item could become with Muse Image: one image per call, made only on this
    request, kept beside the item's photos and never counted as one. Illustrative, not
    evidence. ``503`` while ``PICTURE_ENABLED`` is off."""
    return await _drawn(pictures.draw(item_id, request.use))


@router.get("/{item_id}/pictures", response_model=PictureList)
def item_pictures(item_id: int, pictures: PicturesDep) -> PictureList:
    """The pictures drawn for the item, and whether this server draws any (``enabled``)."""
    return pictures.list(item_id, public_only=not live_request.get())


@router.get("/{item_id}/pictures/{n}", response_class=Response)
def item_picture(item_id: int, n: int, pictures: PicturesDep) -> Response:
    """One picture as JPEG, ``1`` first; ``404`` for a number that was never drawn."""
    return _jpeg(pictures.read(item_id, n, public_only=not live_request.get()))


CARD = "/{item_id}/scenarios/{scenarios_id}/reuse/{card}"


@router.post(f"{CARD}/picture", response_model=Picture, status_code=status.HTTP_201_CREATED)
async def draw_card(
    item_id: int, scenarios_id: int, card: int, pictures: PicturesDep, decider: DeciderDep
) -> Picture:
    """Draw how a reuse card's project could look once built, with Muse Image: one image per
    call, made only on this request, from the card's title and what it does, the item's kind
    and accepted values (never one that identifies it) and the kinds the card names from the
    rest of the inventory. Kept with the card (``card`` counts from 0). Illustrative, not
    evidence. ``503`` while ``PICTURE_ENABLED`` is off."""
    _on(pictures)
    scenarios = decider.scenarios_by_id(item_id, scenarios_id)
    return await _drawn(pictures.draw_card(scenarios, card))


@router.get(f"{CARD}/pictures", response_model=PictureList)
def card_pictures(
    item_id: int, scenarios_id: int, card: int, pictures: PicturesDep, decider: DeciderDep
) -> PictureList:
    """The pictures drawn for a reuse card, and whether this server draws any."""
    return pictures.card_list(decider.scenarios_by_id(item_id, scenarios_id), card)


@router.get(f"{CARD}/pictures/{{n}}", response_class=Response)
def card_picture(
    item_id: int, scenarios_id: int, card: int, n: int, pictures: PicturesDep, decider: DeciderDep
) -> Response:
    """One picture of a reuse card as JPEG, ``1`` first."""
    return _jpeg(pictures.card_read(decider.scenarios_by_id(item_id, scenarios_id), card, n))


@projects_router.post(
    "/{project_id}/picture", response_model=Picture, status_code=status.HTTP_201_CREATED
)
async def draw_project(project_id: int, pictures: PicturesDep, planner: PlannerDep) -> Picture:
    """Draw how the project could look once built, with Muse Image: one image per call, made
    only on this request, from its title, what it results in and the kinds and accepted
    values of the items allocated to it (never one that identifies an item, its location, its
    notes or a price). Kept with the project. Illustrative, not evidence. ``503`` while
    ``PICTURE_ENABLED`` is off."""
    _on(pictures)
    return await _drawn(pictures.draw_project(planner.project(project_id)))


@projects_router.get("/{project_id}/pictures", response_model=PictureList)
def project_pictures(project_id: int, pictures: PicturesDep, planner: PlannerDep) -> PictureList:
    """The pictures drawn for the project, and whether this server draws any."""
    planner.project(project_id)
    return pictures.project_list(project_id)


@projects_router.get("/{project_id}/pictures/{n}", response_class=Response)
def project_picture(
    project_id: int, n: int, pictures: PicturesDep, planner: PlannerDep
) -> Response:
    """One picture of the project as JPEG, ``1`` first."""
    planner.project(project_id)
    return _jpeg(pictures.project_read(project_id, n))
