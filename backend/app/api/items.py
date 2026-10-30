from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import InventoryDep, PhotosDep, ProfilesDep
from app.inventory import (
    ComponentCreate,
    Event,
    FieldCreate,
    Item,
    ItemCreate,
    ItemPatch,
    ItemSummary,
    NotFoundError,
    ReviewChange,
    VersionConflictError,
)
from app.profiles import Profiles, UnknownProfileError

router = APIRouter(prefix="/api/items", tags=["inventory"])


def not_found(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)


def version_conflict(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_409_CONFLICT)


Handler = Callable[[Request, Exception], Response]
error_handlers: dict[type[Exception], Handler] = {
    NotFoundError: not_found,
    VersionConflictError: version_conflict,
}


def _known_profile(profile: str | None, profiles: Profiles) -> None:
    """An item's profile is one that ships, or none."""
    if not profile:
        return
    try:
        profiles.get(profile)
    except UnknownProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(spec: ItemCreate, inventory: InventoryDep, profiles: ProfilesDep) -> Item:
    """Save an item privately, from a label reading or by hand. Nothing is published."""
    _known_profile(spec.profile, profiles)
    return inventory.create(spec)


@router.get("", response_model=list[ItemSummary])
def list_items(inventory: InventoryDep) -> list[ItemSummary]:
    """Every item that is not deleted, newest first. Location and notes stay off the list."""
    return inventory.list_items()


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: int, inventory: InventoryDep) -> Item:
    return inventory.get(item_id)


@router.patch("/{item_id}", response_model=Item)
def update_item(
    item_id: int, patch: ItemPatch, inventory: InventoryDep, profiles: ProfilesDep
) -> Item:
    """Edit the item in place. With ``version`` set, a stale write is refused with 409."""
    _known_profile(patch.profile, profiles)
    return inventory.update(item_id, patch)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, inventory: InventoryDep, photos: PhotosDep) -> None:
    """Hide the item; its photos are removed, its record and history stay."""
    inventory.delete(item_id)
    photos.remove(item_id)


@router.post("/{item_id}/fields", response_model=Item)
def add_field(item_id: int, spec: FieldCreate, inventory: InventoryDep) -> Item:
    """State a value yourself. The observed one stays beside it."""
    return inventory.add_field(item_id, spec)


@router.post("/{item_id}/assertions/{assertion_id}/review", response_model=Item)
def review_assertion(
    item_id: int, assertion_id: int, change: ReviewChange, inventory: InventoryDep
) -> Item:
    """Accept or reject one observed value."""
    return inventory.review(item_id, assertion_id, change.review)


@router.post("/{item_id}/components", response_model=Item, status_code=status.HTTP_201_CREATED)
def add_component(item_id: int, spec: ComponentCreate, inventory: InventoryDep) -> Item:
    """Separate a part into its own record; the whole device notes what left."""
    return inventory.add_component(item_id, spec)


@router.get("/{item_id}/events", response_model=list[Event])
def item_events(item_id: int, inventory: InventoryDep) -> list[Event]:
    return inventory.events(item_id)
