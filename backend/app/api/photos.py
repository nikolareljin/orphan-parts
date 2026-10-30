from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import PhotosDep
from app.api.model_errors import as_http
from app.extract.imaging import BadImageError
from app.photos import PhotoError

router = APIRouter(prefix="/api/items", tags=["inventory"])

PhotosPart = Annotated[list[UploadFile], File(description="Photos of the item, up to MAX_PHOTOS")]


class PhotoCount(BaseModel):
    count: int


@router.get("/{item_id}/photos", response_model=PhotoCount)
def item_photos(item_id: int, photos: PhotosDep) -> PhotoCount:
    """How many photos are kept with the item; each is at ``/photos/{n}``, 1 first."""
    return PhotoCount(count=photos.count(item_id))


@router.get("/{item_id}/photos/{n}", response_class=Response)
def item_photo(item_id: int, n: int, photos: PhotosDep) -> Response:
    return Response(
        photos.read(item_id, n),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},  # private, and the number is reused after a reset
    )


@router.post("/{item_id}/photos", response_model=PhotoCount, status_code=status.HTTP_201_CREATED)
async def add_item_photos(item_id: int, uploads: PhotosPart, photos: PhotosDep) -> PhotoCount:
    """Keep the photos an item was read from. Re-encoded on the way in, metadata dropped."""
    limit = photos.settings.max_photos
    if len(uploads) > limit:
        # before a byte is read: a send over the ceiling is refused for its count alone
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"an item keeps at most {limit} photos; {len(uploads)} were sent",
        )
    cap = photos.settings.max_upload_mb * 1024 * 1024
    data = []
    for upload in uploads:
        # one byte past the cap says the part is too large, whatever the client declared
        part = await upload.read(cap + 1)
        if len(part) > cap:
            raise HTTPException(
                status_code=400,
                detail=f"a photo is larger than {photos.settings.max_upload_mb} MB",
            )
        data.append(part)
    try:
        return PhotoCount(count=photos.add(item_id, data))
    except PhotoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except BadImageError as exc:
        raise as_http(exc) from exc
