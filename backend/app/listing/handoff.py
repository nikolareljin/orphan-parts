"""Around the draft: the details the owner adds before it, the photos zipped in the draft's
order, and what happened on Marketplace after the owner posted it. A sale is also a recorded
sale for price guidance; a sale or a give-away marks the item gone."""

import logging
from typing import Any

from app.inventory import Inventory
from app.listing.details import (
    Given,
    Listed,
    MarketplaceEvent,
    MarketplaceStatus,
    SellDetails,
    SellDetailsRecord,
    Sold,
)
from app.listing.marketplace import dollars, photo_zip
from app.listing.service import Lister
from app.photos import ItemPhotos

log = logging.getLogger("app.listing")

# the outcomes a new one may follow: none yet, or listed
OPEN = frozenset({"", "listed"})


class Handoff:
    def __init__(self, inventory: Inventory, photos: ItemPhotos, lister: Lister) -> None:
        self.inventory = inventory
        self.photos = photos
        self.lister = lister

    def details(self, item_id: int) -> SellDetailsRecord | None:
        row = self.inventory.sell_details(item_id)
        return None if row is None else self._record(row)

    def save_details(self, item_id: int, details: SellDetails) -> SellDetailsRecord:
        return self._record(self.inventory.add_sell_details(item_id, details.model_dump_json()))

    def zip(self, draft_id: int) -> tuple[int, bytes]:
        """The draft's photos in its order; a photo removed since is skipped."""
        draft = self.lister.get(draft_id)
        have = self.photos.count(draft.item_id)
        chosen = [
            (p.photo, self.photos.read(draft.item_id, p.photo))
            for p in draft.photos
            if p.photo <= have
        ]
        return draft.item_id, photo_zip(chosen)

    def status(self, item_id: int) -> MarketplaceStatus:
        events = [self._event(r) for r in self.inventory.marketplace_events(item_id)]
        return MarketplaceStatus(
            item_id=item_id, state=events[-1].kind if events else "", events=events
        )

    def listed(self, item_id: int, spec: Listed) -> MarketplaceStatus:
        # listed again is a new price or a new listing; nothing follows a sale or a gift
        self.inventory.add_marketplace_event(
            item_id,
            "listed",
            on=spec.on,
            price=spec.price,
            url=spec.url,
            change=f"listed on Facebook Marketplace at {dollars(spec.price)} on {spec.on}",
            after=OPEN,
        )
        return self.status(item_id)

    def sold(self, item_id: int, spec: Sold) -> MarketplaceStatus:
        # the final price counts as a reported sale beside the guidance, never mixed into it;
        # the event, the report and the item marked gone are one write
        self.inventory.add_marketplace_event(
            item_id,
            "sold",
            on=spec.on,
            price=spec.price,
            url="",
            change=f"sold on Facebook Marketplace for {dollars(spec.price)} on {spec.on}",
            after=OPEN,
            report=True,
            gone=True,
        )
        return self.status(item_id)

    def given(self, item_id: int, spec: Given) -> MarketplaceStatus:
        self.inventory.add_marketplace_event(
            item_id,
            "given",
            on=spec.on,
            price=0,
            url="",
            change=f"given away through Facebook Marketplace on {spec.on}",
            after=OPEN,
            gone=True,
        )
        return self.status(item_id)

    def _record(self, row: Any) -> SellDetailsRecord:
        return SellDetailsRecord(
            item_id=int(row["item_id"]),
            version=int(row["version"]),
            details=SellDetails.model_validate_json(row["content"]),
            at=row["at"],
        )

    def _event(self, row: Any) -> MarketplaceEvent:
        return MarketplaceEvent(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            kind=row["kind"],
            on=row["on_date"],
            price=row["price"],
            url=row["url"],
            at=row["at"],
        )
