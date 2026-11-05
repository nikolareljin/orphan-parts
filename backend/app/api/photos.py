from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import DevicePhotosDep, ExtractorDep, GateDep, PhotosDep, PrivacyDep
from app.api.model_errors import as_http
from app.api.uploads import read_bounded
from app.extract import Extraction
from app.extract.imaging import BadImageError
from app.inventory import Item, NotFoundError
from app.inventory.parent import PARENT_MODEL, device_model
from app.ops.door import for_visitor, live_request
from app.ops.gate import charge_more, give_back_request, spend_now
from app.photos import ItemPhotos, PhotoError
from app.privacy import AreaChoice, NotCheckedError, PhotoPrivacy, Privacy

router = APIRouter(prefix="/api/items", tags=["inventory"])

PhotosPart = Annotated[list[UploadFile], File(description="Photos of the item, up to MAX_PHOTOS")]


class PhotoCount(BaseModel):
    count: int
    photos: list[PhotoPrivacy] = Field(
        default=[],
        description="each photo's check for private details, 1 first: what is hidden on its"
        " shared copies and whether one may leave the owner's view",
    )


class ParentPhoto(BaseModel):
    """A photo of the device a part came from: kept apart from the part's own photos, read like
    a label, and the model read off it proposed as the item's parent_device_model."""

    item: Item
    model: str = Field(description="the device model read off the photo; empty when none")
    extraction: Extraction


def privacy_of(photos: ItemPhotos, privacy: Privacy, item_id: int) -> list[PhotoPrivacy]:
    return [
        privacy.privacy(n, photos.read(item_id, n)) for n in range(1, photos.count(item_id) + 1)
    ]


@router.get("/{item_id}/photos", response_model=PhotoCount)
def item_photos(item_id: int, photos: PhotosDep, privacy: PrivacyDep) -> PhotoCount:
    """How many photos are kept with the item, each with its check for private details; each
    is at ``/photos/{n}``, 1 first."""
    photos.inventory.get(item_id, public_only=not live_request.get())
    return PhotoCount(count=photos.count(item_id), photos=privacy_of(photos, privacy, item_id))


@router.get("/{item_id}/photos/{n}", response_class=Response)
def item_photo(
    item_id: int,
    n: int,
    photos: PhotosDep,
    privacy: PrivacyDep,
    copy: Annotated[
        Literal["original", "shared"],
        Query(description="the owner's original, or the shared copy with its areas blacked out"),
    ] = "original",
) -> Response:
    """The photo. The owner gets the original unless the shared copy is asked for; the demo
    visitor only ever gets the shared copy, and none of a photo that has not been checked."""
    photos.inventory.get(item_id, public_only=not live_request.get())
    data = photos.read(item_id, n)
    if for_visitor() or copy == "shared":
        try:
            data = privacy.shared_copy(data)
        except NotCheckedError as exc:
            raise HTTPException(status_code=404 if for_visitor() else 409, detail=str(exc)) from exc
    return Response(
        data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},  # private, and the number is reused after a reset
    )


@router.post("/{item_id}/photos", response_model=PhotoCount, status_code=status.HTTP_201_CREATED)
async def add_item_photos(
    item_id: int, uploads: PhotosPart, photos: PhotosDep, privacy: PrivacyDep, gate: GateDep
) -> PhotoCount:
    """Keep the photos an item was read from. Re-encoded on the way in, metadata dropped, and
    each checked for private details (one Muse Spark call a photo, counted as a call that
    spends), so its shared copies go out with them blacked out. Keeping a photo is never
    refused for spend: a check the operator's pause or an allowance refuses, or one that does
    not finish, keeps the photo out of anything shared until it is checked again."""
    limit = photos.settings.max_photos
    if len(uploads) > limit:
        # refused for its count alone, before any part is read into memory
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"an item keeps at most {limit} photos; {len(uploads)} were sent",
        )
    cap = photos.settings.max_upload_mb * 1024 * 1024
    too_big = f"a photo is larger than {photos.settings.max_upload_mb} MB"
    data = [await read_bounded(upload, cap, too_big) for upload in uploads]
    try:
        count = photos.add(item_id, data)
    except PhotoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except BadImageError as exc:
        raise as_http(exc) from exc
    added = [photos.read(item_id, n) for n in range(count - len(data) + 1, count + 1)]
    todo = privacy.waiting(added)
    refused = spend_now(gate, len(todo))
    if refused:
        privacy.not_checked(todo, refused)
    else:
        await privacy.check_all(todo)
    return PhotoCount(count=count, photos=privacy_of(photos, privacy, item_id))


@router.post("/{item_id}/photos/check", response_model=PhotoCount)
async def check_item_photos(
    item_id: int,
    photos: PhotosDep,
    privacy: PrivacyDep,
    gate: GateDep,
    again: Annotated[
        bool, Query(description="check every photo again, not only those without a check")
    ] = False,
) -> PhotoCount:
    """The item's photos checked for private details: those never checked or whose check
    failed, or every one with ``again``. One Muse Spark call a photo checked, each counted."""
    try:
        have = photos.count(item_id)
    except NotFoundError:
        give_back_request(gate)
        raise
    kept = [photos.read(item_id, n) for n in range(1, have + 1)]
    todo = privacy.waiting(kept, again=again)
    if not todo:
        give_back_request(gate)  # nothing to check: no call made
    refused = charge_more(gate, len(todo) - 1)
    if refused is not None:
        why, retry = refused
        headers = {"Retry-After": str(retry)} if retry else None
        raise HTTPException(status_code=429, detail=why, headers=headers)
    await privacy.check_all(todo, again=again)
    return PhotoCount(count=have, photos=privacy_of(photos, privacy, item_id))


@router.patch("/{item_id}/photos/{n}/areas/{area_id}", response_model=PhotoPrivacy)
def choose_area(
    item_id: int, n: int, area_id: int, choice: AreaChoice, photos: PhotosDep, privacy: PrivacyDep
) -> PhotoPrivacy:
    """The owner's choice for one area found on a photo: hidden on every shared copy (the
    default), or shown when it is nothing private after all."""
    data = photos.read(item_id, n)
    try:
        privacy.choose(data, area_id, choice.hidden)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return privacy.privacy(n, data)


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
    empty_or_big = f"the photo is empty or larger than {photos.settings.max_upload_mb} MB"
    try:
        data = await read_bounded(photo, cap, empty_or_big)
    except HTTPException:
        give_back_request(gate)  # refused before any model call
        raise
    if not data:
        give_back_request(gate)
        raise HTTPException(status_code=400, detail=empty_or_big)
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
