from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import DevicePhotosDep, ExtractorDep, GateDep, PhotosDep
from app.api.model_errors import as_http
from app.extract import Extraction
from app.extract.imaging import BadImageError
from app.inventory import Item, NotFoundError
from app.inventory.parent import PARENT_MODEL, device_model
from app.ops.door import live_request
from app.ops.gate import give_back_request
from app.photos import PhotoError

router = APIRouter(prefix="/api/items", tags=["inventory"])

PhotosPart = Annotated[list[UploadFile], File(description="Photos of the item, up to MAX_PHOTOS")]


class PhotoCount(BaseModel):
    count: int


class ParentPhoto(BaseModel):
    """A photo of the device a part came from: kept apart from the part's own photos, read like
    a label, and the model read off it proposed as the item's parent_device_model."""

    item: Item
    model: str = Field(description="the device model read off the photo; empty when none")
    extraction: Extraction


@router.get("/{item_id}/photos", response_model=PhotoCount)
def item_photos(item_id: int, photos: PhotosDep) -> PhotoCount:
    """How many photos are kept with the item; each is at ``/photos/{n}``, 1 first."""
    photos.inventory.get(item_id, public_only=not live_request.get())
    return PhotoCount(count=photos.count(item_id))


@router.get("/{item_id}/photos/{n}", response_class=Response)
def item_photo(item_id: int, n: int, photos: PhotosDep) -> Response:
    photos.inventory.get(item_id, public_only=not live_request.get())
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
        # refused for its count alone, before any part is read into memory
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


@router.post("/{item_id}/parent-photo", response_model=ParentPhoto, status_code=201)
async def add_parent_photo(
    item_id: int,
    photo: Annotated[UploadFile, File(description="A photo of the device the part came from")],
    photos: DevicePhotosDep,
    extractor: ExtractorDep,
    gate: GateDep,
) -> ParentPhoto:
    """The device a part came from, by a photo of it (the label under its base is best): one
    label reading (one Muse Spark call), the photo kept with the item's device photos (apart
    from the part's own: never in a draft, the photo zip or the visitor's view), and the model
    read off it proposed as ``parent_device_model``, sourced ``photo``, for the owner to accept."""
    cap = photos.settings.max_upload_mb * 1024 * 1024
    try:
        have = photos.count(item_id)
    except NotFoundError:
        give_back_request(gate)  # refused before any model call
        raise
    if have >= photos.settings.max_photos:
        give_back_request(gate)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"an item keeps at most {photos.settings.max_photos} photos of the device;"
            f" this one has {have}",
        )
    data = await photo.read(cap + 1)
    if not data or len(data) > cap:
        give_back_request(gate)
        raise HTTPException(
            status_code=400,
            detail=f"the photo is empty or larger than {photos.settings.max_upload_mb} MB",
        )
    try:
        reading = await extractor.extract([data])
    except Exception as exc:
        raise as_http(exc) from exc
    try:
        photos.add(item_id, [data])
    except PhotoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except BadImageError as exc:
        raise as_http(exc) from exc
    model, confidence, raw = device_model(reading)
    inventory = photos.inventory
    item = (
        inventory.add_observation(
            item_id, PARENT_MODEL, model, confidence=confidence, source="photo", raw=raw
        )
        if model
        # the photo is kept all the same: a new version, so the dialog reads them again
        else inventory.note(item_id, "a photo of the device kept; no model read off it")
    )
    return ParentPhoto(item=item, model=model, extraction=reading)


@router.get("/{item_id}/device-photos", response_model=PhotoCount)
def device_photos(item_id: int, photos: DevicePhotosDep) -> PhotoCount:
    """How many photos of the device the part came from are kept; the owner's alone."""
    return PhotoCount(count=photos.count(item_id))


@router.get("/{item_id}/device-photos/{n}", response_class=Response)
def device_photo(item_id: int, n: int, photos: DevicePhotosDep) -> Response:
    return Response(
        photos.read(item_id, n), media_type="image/jpeg", headers={"Cache-Control": "no-store"}
    )
