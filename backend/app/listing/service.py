"""A listing draft in Facebook Marketplace (US) shape: the model writes the prose, picks the
category, the condition, the tags and the photo order from what is confirmed and what the owner
said; the rules add what must be disclosed, set the price, and keep contact details out.
Nothing untested becomes working. The owner pastes the fields on Marketplace and posts."""

import json
import logging
import re
from typing import Any

from app.config import Settings
from app.extract.imaging import prepare
from app.inventory import Inventory
from app.inventory.schema import Item
from app.listing.checklists import Step, checklist, ready
from app.listing.details import SellDetails
from app.listing.marketplace import (
    TAG_MAX,
    TAGS_MAX,
    TITLE_MAX,
    data,
    dollars,
    pick_category,
    pick_condition,
    strip_personal,
    whole_dollars,
)
from app.listing.schema import (
    PLAIN_AMOUNT,
    Draft,
    DraftFact,
    DraftRequest,
    DraftWriting,
    PhotoPick,
    StepChange,
)
from app.model_api import ModelApiClient, image_part, text_part, user_message
from app.photos import ItemPhotos
from app.projects.pack import private_field

log = logging.getLogger("app.listing")

MAX_OUTPUT_TOKENS = 1100
# the photos go to the model smaller than they are kept: enough to rank them, fewer tokens
PHOTO_PX = 768
# at most this many go to the model, in the item's order; the rest follow in the photo order
PHOTOS_SENT = 4
REASON_MAX = 120
# Details of the item the model may rest a line on, beside the confirmed fields.
DETAIL_KEYS = ("name", "item_type", "condition", "faults", "tests_done", "accessories", "pickup")
# The owner's listing details a line may rest on. The lowest price and the reason never appear.
OWNER_KEYS = ("condition_words", "included", "untested", "availability")
# "new" said by the owner, other than "like new"
_SAYS_NEW = re.compile(r"(?<!like )\bnew\b", re.I)
# a claim of a test or a working state; "not tested" and "never tested" are the opposite
_CLAIMS_WORKING = re.compile(
    r"(?<!not )(?<!never )\b(works|working|fully functional|tested|in working order)\b", re.I
)

_SHARED = (
    " Use only the facts given and the owner's words; never add a specification, an accessory"
    " or a test result that is not listed. Do not call anything working or tested unless the"
    " tests say so. Plain words, no hype, no emoji. The title is at most 100 characters and"
    " starts with brand, model and the key specification. Pick the category as exactly one"
    " path from the list given, and the condition as exactly one of the conditions given;"
    " choose New only when the owner says it is new. The description is a few short sentences"
    " on what the item is, its key specifications and its condition in the owner's words;"
    " lines on faults, tests, what is included, data and pickup are added after it, so do not"
    " write a price, a street address, a phone number or an email address. Tags are at most"
    " 20 short search words. Order the photos best first: a clear front view, then the label,"
    " then each fault; every photo once, with a short reason; none when no photo is given."
    " Each fact names the field it rests on, using exactly one of the field keys given."
)
INSTRUCTIONS = {
    "sell": "You write short, honest Facebook Marketplace listings for used items." + _SHARED,
    "give": (
        "You write short, honest Facebook Marketplace listings for items given away for free."
        " Say what the item could still be useful for, in a few plain suggestions, and be"
        " direct about faults and what was not tested." + _SHARED
    ),
}


def claims_working(text: str) -> bool:
    """Whether the text says the item works or was tested, other than to say it was not."""
    return _CLAIMS_WORKING.search(text) is not None


def fact_keys(
    item: Item, known: dict[str, str], request: DraftRequest, details: SellDetails | None = None
) -> list[str]:
    """The keys a fact may rest on: the confirmed fields and the details that are not empty."""
    keys = [k for k in DETAIL_KEYS if k != "pickup" and getattr(item, k, None)]
    if request.pickup or details is not None:
        keys.append("pickup")
    if details is not None:
        said = {
            "condition_words": details.condition_words,
            "included": details.included_text(),
            "untested": details.untested,
            "availability": details.availability,
        }
        keys += [k for k in OWNER_KEYS if said[k]]
        if details.faults and "faults" not in keys:
            keys.append("faults")
    return [*known, *keys]


def _faults(item: Item, details: SellDetails | None) -> str:
    said = [item.faults.strip()]
    if details is not None and details.faults and details.faults != said[0]:
        said.append(details.faults)
    return "; ".join(s for s in said if s)


def _included(item: Item, details: SellDetails | None) -> str:
    said = [item.accessories.strip()]
    if details is not None and details.included_text():
        said.append(details.included_text())
    return "; ".join(s for s in said if s)


def _pickup(request: DraftRequest, details: SellDetails | None) -> str:
    if request.pickup:
        return request.pickup
    return details.handover_line(request.mode) if details is not None else ""


def brief(
    item: Item,
    known: dict[str, str],
    request: DraftRequest,
    details: SellDetails | None = None,
    photos: int = 0,
) -> str:
    """What the model is told: confirmed values and the owner's details, nothing else. The
    lowest acceptable price, the reason for selling and the asking price stay out: the rules
    set the price, and the rest is the owner's own."""
    lines = [
        f"Mode: {request.mode}",
        "Marketplace: Facebook Marketplace, United States",
        f"name: {item.name}",
        f"item_type: {item.item_type}",
        f"condition: {item.condition or '(not given)'}",
        f"faults: {_faults(item, details) or '(not given)'}",
        f"tests_done: {item.tests_done or '(not given)'}",
        f"accessories: {_included(item, details) or '(not given)'}",
        f"pickup: {_pickup(request, details) or '(not given)'}",
    ]
    if details is not None:
        lines += [
            f"condition_words (the owner's words): {details.condition_words or '(not given)'}",
            f"untested: {details.untested or '(not given)'}",
            f"availability: {details.availability or '(not given)'}",
        ]
    lines.append("Confirmed fields (key: value):")
    lines.extend(f"- {k}: {v}" for k, v in known.items())
    if not known:
        lines.append("- (none confirmed yet)")
    lines.append(
        f"Photos: {photos}, numbered 1 to {photos} in the order attached"
        if photos
        else "Photos: none"
    )
    lines.append("Categories (one path): " + "; ".join(c.path for c in data().categories))
    lines.append("Conditions (one): " + "; ".join(data().conditions))
    lines.append(
        "Field keys a fact may name: " + ", ".join(fact_keys(item, known, request, details))
    )
    return "\n".join(lines)


def disclosures(item: Item, request: DraftRequest, details: SellDetails | None = None) -> list[str]:
    """What the rules append to every draft, whatever the model wrote. No price: Marketplace
    has a field for it."""
    faults = _faults(item, details)
    out = [f"Known faults: {faults}" if faults else "No faults known to the owner."]
    if item.tests_done:
        out.append(f"Tested: {item.tests_done}")
    else:
        out.append("Not tested." if request.mode == "give" else "Not tested; sold as is.")
    if details is not None and details.untested:
        out.append(f"Not tested: {details.untested}")
    included = _included(item, details)
    out.append(f"Included: {included}" if included else "Nothing else included.")
    state = details.data if details is not None else "none"
    if state == "wiped":
        out.append("Data: signed out of every account and wiped.")
    elif state == "not_wiped" or (request.holds_data and state == "none"):
        out.append("Data: not wiped yet.")
    pickup = _pickup(request, details)
    if request.mode == "give":
        if details is not None and not request.pickup:
            out.append(f"Free. {pickup}")
        else:
            out.append("Free to collect." + (f" Pickup: {pickup}" if pickup else ""))
    elif pickup:
        out.append(pickup if details is not None and not request.pickup else f"Pickup: {pickup}")
    if details is not None and details.availability:
        out.append(f"Available: {details.availability}")
    return out


def _amount(text: str) -> float | None:
    # the request checked it is one plain amount ("$1,200.50"); the rest is its digits
    if not PLAIN_AMOUNT.fullmatch(text.strip()):
        return None
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def private_values(item: Item) -> list[str]:
    """What an item holds that identifies it or its owner (a serial, a MAC address, an IMEI),
    accepted or not: never shown in a listing, even when the model reads it off a photo."""
    return sorted(
        {
            a.value.strip()
            for a in item.assertions
            if private_field(a.field) and len(a.value.strip()) >= 4
        },
        key=len,
        reverse=True,
    )


def strip_values(text: str, values: list[str]) -> str:
    """The text with each private value taken out, letter case aside."""
    for value in values:
        text = re.sub(re.escape(value), "[removed]", text, flags=re.I)
    return text


def price_for(
    request: DraftRequest, details: SellDetails | None, guidance: dict[str, Any] | None
) -> tuple[str, str]:
    """The price to type on Marketplace, in whole dollars, and where it comes from: free for a
    give-away; the owner's asking price; else the typical figure of the latest price guidance,
    named. A sale is never priced at 0, which Marketplace shows as free."""
    if request.mode == "give":
        return "0", "free"
    asked = _amount(request.asking_price) if request.asking_price else None
    if asked is None and details is not None:
        asked = details.asking_price
    if asked:
        whole = whole_dollars(asked)
        if whole >= 1:
            if whole != asked:
                return str(whole), f"your asking price, {dollars(asked)} rounded to whole dollars"
            return str(whole), "your asking price"
    if guidance is not None and guidance["content"].get("currency") == "USD":
        typical = next(
            (s for s in guidance["content"].get("strategies", []) if s["name"] == "typical"), None
        )
        figure = whole_dollars(float(typical.get("price") or 0)) if typical is not None else 0
        if figure >= 1:
            weak = " (weak evidence)" if guidance["content"].get("weak") else ""
            return (
                str(figure),
                f"suggested: the typical figure of price guidance v{guidance['version']},"
                f" ${figure}{weak}; set your own",
            )
    return "", "no asking price and no price guidance; set the price on Marketplace"


class Lister:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        photos: ItemPhotos | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.photos = photos or ItemPhotos(settings, inventory)

    def details(self, item_id: int) -> tuple[SellDetails | None, int | None]:
        row = self.inventory.sell_details(item_id)
        if row is None:
            return None, None
        return SellDetails.model_validate_json(row["content"]), int(row["version"])

    def _guidance(self, item_id: int) -> dict[str, Any] | None:
        rows = self.inventory.guidances(item_id)
        if not rows:
            return None
        return {"version": int(rows[-1]["version"]), "content": json.loads(rows[-1]["content"])}

    def _photo_parts(self, item_id: int) -> list[dict[str, Any]]:
        s = self.settings
        parts: list[dict[str, Any]] = []
        for n in range(1, min(self.photos.count(item_id), PHOTOS_SENT) + 1):
            small = prepare(
                self.photos.read(item_id, n),
                max_px=PHOTO_PX,
                max_bytes=s.max_upload_mb * 1024 * 1024,
            )
            parts += [text_part(f"Photo {n}"), image_part(small)]
        return parts

    async def draft(self, item_id: int, request: DraftRequest) -> Draft:
        item = self.inventory.get(item_id)
        details, details_version = self.details(item_id)
        # nothing that identifies the item or its owner (a serial, a MAC address, an IMEI, an
        # account) reaches the model, by the rule the other briefs keep
        known = {
            k: (f"{a.value} {a.unit}".strip())
            for k, a in item.fields.items()
            if a.review == "accepted" and not private_field(k)
        }
        to_confirm = sorted(
            k for k, a in item.fields.items() if a.review == "proposed" and not private_field(k)
        )
        secrets = private_values(item)
        photo_parts = self._photo_parts(item_id)
        count = len(photo_parts) // 2
        result = await self.client.respond_structured(
            DraftWriting,
            model=self.settings.model_spark,
            input=[
                user_message(text_part(brief(item, known, request, details, count)), *photo_parts)
            ],
            instructions=INSTRUCTIONS[request.mode],
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            op=f"draft-{request.mode}",
        )
        writing = result.parsed
        warnings: list[str] = []
        allowed = set(fact_keys(item, known, request, details))
        facts: list[DraftFact] = []
        for fact in writing.facts:
            if fact.field in allowed and fact.text.strip():
                facts.append(DraftFact(text=fact.text.strip(), field=fact.field))
            else:
                warnings.append(f"left out a line that rested on nothing confirmed: {fact.text!r}")
        if not item.tests_done and claims_working(writing.title + "\n" + writing.description):
            warnings.append(
                "the text claims a test or a working state that is not recorded; record what"
                " was tested under Details, or edit the text before posting"
            )
        if to_confirm:
            warnings.append(
                "observed values still to confirm were left out: " + ", ".join(to_confirm)
            )
        if details is None:
            warnings.append(
                "no listing details saved yet: condition, what is included, pickup area and"
                " price come from Listing details"
            )

        title, removed = strip_personal(strip_values(" ".join(writing.title.split()), secrets))
        if request.mode == "give" and not title.lower().startswith("free"):
            title = f"Free: {title}"
        title = title[:TITLE_MAX].rstrip()
        holds_data = request.holds_data or (details is not None and details.data != "none")
        text, more = strip_personal(strip_values(writing.description.strip(), secrets))
        removed += more
        description = text + "\n\n" + "\n".join(disclosures(item, request, details))
        if removed:
            warnings.append(
                "took out " + ", ".join(sorted(set(removed))) + "; buyers write through Marketplace"
            )
        written = writing.title + "\n" + writing.description
        if strip_values(written, secrets) != written:
            warnings.append(
                "took out a serial number, MAC address or IMEI the item holds; cover it on the"
                " label photo too"
            )

        category = pick_category(writing.category)
        if request.mode == "give":
            free = data().free_category
            if category and category != free:
                warnings.append(
                    f"listed under {free}; if Marketplace asks for a category too, {category} fits"
                )
            category = free
        elif not category:
            warnings.append(
                f"the draft named a category that is not in the Marketplace list"
                f" ({writing.category.strip()[:60]!r}); pick one on the create page"
            )
        seen = {c.path: c.seen for c in data().categories}
        if category and not seen.get(category, False):
            warnings.append(
                f"{category} could not be confirmed on Marketplace's category pages; check it"
                " in the picker"
            )

        condition = pick_condition(writing.condition)
        said = " ".join([item.condition, details.condition_words if details else ""])
        if condition == "New" and (not _SAYS_NEW.search(said) or _faults(item, details)):
            condition = "Used - Like New"
            warnings.append("the draft said New; the owner did not, so it is Used - Like New")
        if not condition:
            warnings.append("the draft named no Marketplace condition; pick one on the create page")

        tags: list[str] = []
        for tag in writing.tags:
            tag = " ".join(tag.split()).strip("#")[:TAG_MAX]
            if (
                tag
                and not strip_personal(tag)[1]
                and strip_values(tag, secrets) == tag
                and tag.casefold() not in map(str.casefold, tags)
            ):
                tags.append(tag)
        tags = tags[:TAGS_MAX]

        photos: list[PhotoPick] = []
        for pick in writing.photo_order:
            if 1 <= pick.photo <= count and pick.photo not in {p.photo for p in photos}:
                reason = " ".join(pick.reason.split())[:REASON_MAX] or "placed by the draft"
                photos.append(PhotoPick(photo=pick.photo, reason=reason))
        for n in range(1, count + 1):
            if n not in {p.photo for p in photos}:
                photos.append(PhotoPick(photo=n, reason="not placed by the draft; kept after"))
        for n in range(count + 1, self.photos.count(item_id) + 1):
            photos.append(PhotoPick(photo=n, reason=f"after the first {PHOTOS_SENT}; not read"))
        if count == 0:
            warnings.append(
                "the item has no photos yet: add the front, the label and every fault first"
            )

        price, price_basis = price_for(request, details, self._guidance(item_id))
        content: dict[str, Any] = {
            "title": title,
            "price": price,
            "price_basis": price_basis,
            "category": category,
            "condition": condition,
            "description": description,
            "facts": [f.model_dump() for f in facts],
            "uses": [u.strip() for u in writing.uses if u.strip()]
            if request.mode == "give"
            else [],
            "tags": tags,
            "photos": [p.model_dump() for p in photos],
            "details_version": details_version,
            "warnings": warnings,
            "to_confirm": to_confirm,
            "pickup": _pickup(request, details),
            "asking_price": price
            if request.mode == "sell" and price_basis.startswith("your")
            else "",
            "holds_data": holds_data,
            "model": result.response.model,
            "from_fixture": result.response.from_fixture,
            "cost_usd": result.response.cost_usd,
        }
        steps = checklist(request.mode, holds_data)
        row = self.inventory.add_draft(
            item_id, request.mode, json.dumps(content), json.dumps([s.model_dump() for s in steps])
        )
        log.info(
            "drafted",
            extra={
                "item_id": item_id,
                "mode": request.mode,
                "facts": len(facts),
                "photos": count,
                "warnings": len(warnings),
                "usd": result.response.cost_usd,
            },
        )
        return self.assemble(row)

    def drafts(self, item_id: int) -> list[Draft]:
        return [self.assemble(r) for r in self.inventory.drafts(item_id)]

    def get(self, draft_id: int) -> Draft:
        return self.assemble(self.inventory.draft(draft_id))

    def set_step(self, draft_id: int, change: StepChange) -> Draft:
        row = self.inventory.draft(draft_id)
        steps = [Step.model_validate(s) for s in json.loads(row["checklist"])]
        if change.key not in {s.key for s in steps}:
            raise LookupError(f"draft {draft_id} has no step {change.key!r}")
        for s in steps:
            if s.key == change.key:
                s.done = change.done
        return self.assemble(
            self.inventory.set_checklist(draft_id, json.dumps([s.model_dump() for s in steps]))
        )

    def assemble(self, row: Any) -> Draft:
        content = json.loads(row["content"])
        # drafts written before the Marketplace fields called the tags keywords
        if "keywords" in content:
            content.setdefault("tags", content.pop("keywords"))
        steps = [Step.model_validate(s) for s in json.loads(row["checklist"])]
        return Draft(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            mode=row["mode"],
            version=int(row["version"]),
            item_version=int(row["item_version"]),
            stale=int(row["item_version"]) != int(row["current_item_version"]),
            checklist=steps,
            ready=ready(steps),
            handoff_url=self.settings.marketplace_create_url,
            at=row["at"],
            **content,
        )
