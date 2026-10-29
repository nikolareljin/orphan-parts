"""A listing draft: the model writes the prose from what is confirmed, the rules add what must
be disclosed, and nothing untested becomes working."""

import json
import logging
import re
from typing import Any

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import Item
from app.listing.checklists import Step, checklist, ready
from app.listing.schema import Draft, DraftFact, DraftRequest, DraftWriting, StepChange
from app.model_api import ModelApiClient, text_part, user_message

log = logging.getLogger("app.listing")

MAX_OUTPUT_TOKENS = 700
# Details of the item the model may rest a line on, beside the confirmed fields.
DETAIL_KEYS = ("name", "item_type", "condition", "faults", "tests_done", "accessories", "pickup")
# a claim of a test or a working state; "not tested" and "never tested" are the opposite
_CLAIMS_WORKING = re.compile(
    r"(?<!not )(?<!never )\b(works|working|fully functional|tested|in working order)\b", re.I
)

INSTRUCTIONS = {
    "sell": (
        "You write short, honest Marketplace listings for used items. Use only the facts given;"
        " never add a specification, an accessory or a test result that is not listed. Do not"
        " call anything working or tested unless the tests say so. Plain words, no hype, no"
        " emoji. The title is at most 80 characters and starts with what the item is. Each fact"
        " names the field it rests on, using exactly one of the field keys given."
    ),
    "give": (
        "You write short, honest free-item notices for things given away. Use only the facts"
        " given; never add a specification, an accessory or a test result that is not listed."
        " Say what the item could still be useful for, in a few plain suggestions, and be"
        " direct about faults and what was not tested. No hype, no emoji. The title is at most"
        " 80 characters. Each fact names the field it rests on, using exactly one of the field"
        " keys given."
    ),
}


def claims_working(text: str) -> bool:
    """Whether the text says the item works or was tested, other than to say it was not."""
    return _CLAIMS_WORKING.search(text) is not None


def fact_keys(item: Item, known: dict[str, str], request: DraftRequest) -> list[str]:
    """The keys a fact may rest on: the confirmed fields and the details that are not empty."""
    details = [k for k in DETAIL_KEYS if k != "pickup" and getattr(item, k, None)]
    if request.pickup:
        details.append("pickup")
    return [*known, *details]


def brief(item: Item, known: dict[str, str], request: DraftRequest) -> str:
    """What the model is told: confirmed values and the owner's details, nothing else."""
    lines = [f"Mode: {request.mode}", f"name: {item.name}", f"item_type: {item.item_type}"]
    for key in ("condition", "faults", "tests_done", "accessories"):
        lines.append(f"{key}: {getattr(item, key) or '(not given)'}")
    lines.append(f"pickup: {request.pickup or '(not given)'}")
    if request.mode == "sell":
        lines.append(f"asking price: {request.asking_price or '(the owner sets it)'}")
    lines.append("Confirmed fields (key: value):")
    lines.extend(f"- {k}: {v}" for k, v in known.items())
    if not known:
        lines.append("- (none confirmed yet)")
    lines.append("Field keys a fact may name: " + ", ".join(fact_keys(item, known, request)))
    return "\n".join(lines)


def disclosures(item: Item, request: DraftRequest) -> list[str]:
    """What the rules append to every draft, whatever the model wrote."""
    out = [f"Known faults: {item.faults}" if item.faults else "No faults known to the owner."]
    out.append(f"Tested: {item.tests_done}" if item.tests_done else "Not tested; sold as is.")
    if request.mode == "give" and not item.tests_done:
        out[-1] = "Not tested."
    out.append(f"Included: {item.accessories}" if item.accessories else "Nothing else included.")
    if request.mode == "give":
        out.append("Free to collect." + (f" Pickup: {request.pickup}" if request.pickup else ""))
    else:
        out.append(
            f"Price: {request.asking_price}" if request.asking_price else "Price: to be set."
        )
        if request.pickup:
            out.append(f"Pickup: {request.pickup}")
    return out


class Lister:
    def __init__(self, settings: Settings, client: ModelApiClient, inventory: Inventory) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory

    async def draft(self, item_id: int, request: DraftRequest) -> Draft:
        item = self.inventory.get(item_id)
        known = {
            k: (f"{a.value} {a.unit}".strip())
            for k, a in item.fields.items()
            if a.review == "accepted"
        }
        to_confirm = sorted(k for k, a in item.fields.items() if a.review == "proposed")
        result = await self.client.respond_structured(
            DraftWriting,
            model=self.settings.model_spark,
            input=[user_message(text_part(brief(item, known, request)))],
            instructions=INSTRUCTIONS[request.mode],
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            op=f"draft-{request.mode}",
        )
        writing = result.parsed
        warnings: list[str] = []
        allowed = set(fact_keys(item, known, request))
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
        title = writing.title.strip()[:80]
        if request.mode == "give" and not title.lower().startswith("free"):
            title = f"Free: {title}"[:80]
        description = writing.description.strip() + "\n\n" + "\n".join(disclosures(item, request))
        content: dict[str, Any] = {
            "title": title,
            "description": description,
            "facts": [f.model_dump() for f in facts],
            "uses": [u.strip() for u in writing.uses if u.strip()]
            if request.mode == "give"
            else [],
            "keywords": [k.strip() for k in writing.keywords if k.strip()][:12],
            "warnings": warnings,
            "to_confirm": to_confirm,
            "pickup": request.pickup,
            "asking_price": request.asking_price if request.mode == "sell" else "",
            "holds_data": request.holds_data,
            "model": result.response.model,
            "from_fixture": result.response.from_fixture,
            "cost_usd": result.response.cost_usd,
        }
        steps = checklist(request.mode, request.holds_data)
        row = self.inventory.add_draft(
            item_id, request.mode, json.dumps(content), json.dumps([s.model_dump() for s in steps])
        )
        log.info(
            "drafted",
            extra={
                "item_id": item_id,
                "mode": request.mode,
                "facts": len(facts),
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
