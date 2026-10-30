from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import PicturesDep
from app.api.model_errors import as_http
from app.ops.door import live_request
from app.picture import Picture, PictureList, PicturesOffError

router = APIRouter(prefix="/api/items", tags=["inventory"])


class PictureRequest(BaseModel):
    use: str = Field(
        default="",
        max_length=200,
        description="what to draw the item as: a project template id, a use in your own"
        " words, or empty for the item itself",
    )


@router.post("/{item_id}/picture", response_model=Picture, status_code=status.HTTP_201_CREATED)
async def draw_picture(item_id: int, request: PictureRequest, pictures: PicturesDep) -> Picture:
    """Draw what the item could become with Muse Image: one image per call, made only on this
    request, kept beside the item's photos and never counted as one. Illustrative, not
    evidence. ``503`` while ``PICTURE_ENABLED`` is off."""
    try:
        return await pictures.draw(item_id, request.use)
    except PicturesOffError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/{item_id}/pictures", response_model=PictureList)
def item_pictures(item_id: int, pictures: PicturesDep) -> PictureList:
    """The pictures drawn for the item, and whether this server draws any (``enabled``)."""
    return pictures.list(item_id, public_only=not live_request.get())


@router.get("/{item_id}/pictures/{n}", response_class=Response)
def item_picture(item_id: int, n: int, pictures: PicturesDep) -> Response:
    """One picture as JPEG, ``1`` first; ``404`` for a number that was never drawn."""
    data = pictures.read(item_id, n, public_only=not live_request.get())
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
