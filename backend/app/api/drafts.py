from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.deps import HandoffDep, ListerDep
from app.api.model_errors import as_http
from app.listing import (
    Draft,
    DraftRequest,
    Given,
    Listed,
    MarketplaceStatus,
    SellDetails,
    SellDetailsRecord,
    Sold,
    StepChange,
)
from app.listing.marketplace import MarketplaceData, data

router = APIRouter(prefix="/api", tags=["listing"])


@router.post("/items/{item_id}/drafts", response_model=Draft, status_code=201)
async def write_draft(item_id: int, request: DraftRequest, lister: ListerDep) -> Draft:
    """Write a Facebook Marketplace (US) draft for sale or free pickup from what is confirmed
    about the item, the saved listing details and its photos. One Muse Spark call writes the
    title, description, tags, category, condition and photo order; the rules validate the
    category and condition against the data file, set the price (the asking price, else the
    typical figure of the latest price guidance, named; 0 for a give-away), add the disclosures
    (faults, what was tested, what is included, data, pickup), take out contact details and drop
    any line that rests on nothing confirmed. Nothing is posted: the owner pastes the fields on
    Marketplace's create page."""
    try:
        return await lister.draft(item_id, request)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/items/{item_id}/drafts", response_model=list[Draft])
def list_drafts(item_id: int, lister: ListerDep) -> list[Draft]:
    """Every draft written for the item, newest last, each saying whether the item changed
    since."""
    return lister.drafts(item_id)


@router.get("/drafts/{draft_id}", response_model=Draft)
def get_draft(draft_id: int, lister: ListerDep) -> Draft:
    return lister.get(draft_id)


@router.post("/drafts/{draft_id}/checklist", response_model=Draft)
def set_step(draft_id: int, change: StepChange, lister: ListerDep) -> Draft:
    """Tick or untick one step of the draft's checklist."""
    try:
        return lister.set_step(draft_id, change)
    except LookupError as exc:
        if "no step" in str(exc):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise


@router.get("/marketplace/us", response_model=MarketplaceData)
def marketplace_us() -> MarketplaceData:
    """The Marketplace (US) categories and conditions a draft may name, from the data file."""
    return data()


@router.get("/items/{item_id}/sell-details", response_model=SellDetailsRecord | None)
def get_sell_details(item_id: int, handoff: HandoffDep) -> SellDetailsRecord | None:
    """The latest listing details the owner saved, or null before the first save."""
    return handoff.details(item_id)


@router.put("/items/{item_id}/sell-details", response_model=SellDetailsRecord)
def save_sell_details(item_id: int, details: SellDetails, handoff: HandoffDep) -> SellDetailsRecord:
    """Save what the owner adds before a draft, as a new version. The lowest price and the
    reason for selling are kept for the owner and never reach the model or the listing; the
    area is a city, ZIP or neighborhood, and free text with a street address, an email or a
    phone number is refused."""
    return handoff.save_details(item_id, details)


@router.get("/drafts/{draft_id}/photos.zip", response_class=Response)
def draft_photos(draft_id: int, handoff: HandoffDep) -> Response:
    """The item's photos in the draft's order, as stored (re-encoded, metadata dropped)."""
    item_id, archive = handoff.zip(draft_id)
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="item-{item_id}-photos.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/items/{item_id}/marketplace", response_model=MarketplaceStatus)
def marketplace_status(item_id: int, handoff: HandoffDep) -> MarketplaceStatus:
    """What happened on Marketplace after the owner posted: listed, sold, given."""
    return handoff.status(item_id)


@router.post("/items/{item_id}/marketplace/listed", response_model=MarketplaceStatus)
def mark_listed(item_id: int, spec: Listed, handoff: HandoffDep) -> MarketplaceStatus:
    """The owner posted it: the date, the price, and the listing's address when pasted."""
    return handoff.listed(item_id, spec)


@router.post("/items/{item_id}/marketplace/sold", response_model=MarketplaceStatus)
def mark_sold(item_id: int, spec: Sold, handoff: HandoffDep) -> MarketplaceStatus:
    """Sold: the final price is also recorded as a sale for price guidance; the item is gone."""
    return handoff.sold(item_id, spec)


@router.post("/items/{item_id}/marketplace/given", response_model=MarketplaceStatus)
def mark_given(item_id: int, spec: Given, handoff: HandoffDep) -> MarketplaceStatus:
    """Given away: the item is gone."""
    return handoff.given(item_id, spec)
