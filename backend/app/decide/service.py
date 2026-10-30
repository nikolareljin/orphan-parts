"""Deciding what an item becomes: the rules say which projects it fills and gather what the app
already answered (the price, the searches, the history); Muse Spark proposes what else it is
good for; the owner chooses, and the choice is an event on the item."""

import json
import logging
from typing import Any

from app.config import Settings
from app.decide.schema import (
    CHOICES,
    INTENT_FOR,
    MAX_USES,
    Choice,
    Decided,
    Decision,
    DecisionCreate,
    OpenSearch,
    TemplateFit,
    Use,
    Uses,
    UsesWriting,
    Worth,
)
from app.find.service import Finder
from app.inventory import Inventory
from app.inventory.schema import Item
from app.model_api import ModelApiClient, text_part, user_message
from app.projects.pack import private_field
from app.projects.schema import Preferences
from app.projects.service import Planner, fits
from app.projects.templates import Templates
from app.value.schema import Strategy
from app.value.service import Valuer

log = logging.getLogger("app.decide")

MAX_OUTPUT_TOKENS = 700
# what the model writes is shown as it is, so it is cut, not trusted
TEXT_MAX = 200
NEEDS_MAX = 6
DETAIL_KEYS = ("condition", "faults", "tests_done", "accessories")
DECIDED = "decided: "

INSTRUCTIONS = (
    "You say what a used item is still good for, to a person deciding whether to keep it,"
    " sell it or give it away. Propose at most three uses, the most practical first. Rest"
    " each one on the facts given: the item's confirmed values, its condition, its faults and"
    " what was tested; never assume a part works when the tests do not say so. For each use"
    " say in one line what it would do, list what else it needs that is not in the facts, say"
    " the effort (low, medium or high) for a person with the skills given, and add one note"
    " on what to check first. Respect the person's interests and budget. Plain words, no hype."
)


def brief(item: Item, known: dict[str, str], prefs: Preferences, fills: list[TemplateFit]) -> str:
    """What the model is told: confirmed values, the item's condition, faults, tests and
    accessories, the owner's preferences, and the projects the rules already found it fills.
    Nothing else: not the location, the notes, a photo or a search."""
    lines = [f"name: {item.name}", f"item_type: {item.item_type}"]
    for key in DETAIL_KEYS:
        lines.append(f"{key}: {getattr(item, key) or '(not given)'}")
    lines.append("Confirmed fields (key: value):")
    lines.extend(f"- {k}: {v}" for k, v in known.items())
    if not known:
        lines.append("- (none confirmed yet)")
    lines.append(f"interests: {prefs.interests or '(not given)'}")
    lines.append(f"skills: {', '.join(prefs.skills) or '(not given)'}")
    budget = f"{prefs.budget:g} {prefs.currency}" if prefs.budget is not None else "(not given)"
    lines.append(f"budget for extra parts: {budget}")
    lines.append("Projects in the catalog this item already fills a part of:")
    lines.extend(f"- {t.label} ({', '.join(t.fills)})" for t in fills)
    if not fills:
        lines.append("- (none)")
    return "\n".join(lines)


def known_fields(item: Item) -> dict[str, str]:
    """The accepted values the brief may carry: nothing that identifies the item or its owner
    (a serial, an address, an account), by the same rule the build brief keeps."""
    return {
        k: f"{a.value} {a.unit}".strip()
        for k, a in item.fields.items()
        if a.review == "accepted" and not private_field(k)
    }


def templates_for(item: Item, templates: Templates) -> list[TemplateFit]:
    """The templates with a requirement this item can fill, by the rules: the requirement names
    kinds of item and the item's type is one of them. A requirement open to anything does not
    count; it says nothing about this item."""
    out: list[TemplateFit] = []
    for template_id in templates.ids():
        template = templates.get(template_id)
        keys = [r.key for r in template.requirements if r.item_types and fits(r.item_types, item)]
        if keys:
            out.append(TemplateFit(id=template.id, label=template.label, fills=keys))
    return out


def suggested(strategies: list[Strategy]) -> Strategy | None:
    """The strategy to start from: typical when it has a figure, else the first that does."""
    typical = next((s for s in strategies if s.name == "typical" and s.price is not None), None)
    if typical is not None:
        return typical
    return next((s for s in strategies if s.price is not None), None)


def parse_decided(change: str) -> tuple[Choice, str] | None:
    """The choice and the note out of a ``decided: <choice>: <note>`` event line."""
    if not change.startswith(DECIDED):
        return None
    choice, _, note = change[len(DECIDED) :].partition(": ")
    for known in CHOICES:
        if choice == known:
            return known, note
    return None


def decided_line(spec: DecisionCreate) -> str:
    return f"{DECIDED}{spec.choice}: {spec.note}" if spec.note else f"{DECIDED}{spec.choice}"


class Decider:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        templates: Templates,
        planner: Planner,
        valuer: Valuer,
        finder: Finder,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.templates = templates
        self.planner = planner
        self.valuer = valuer
        self.finder = finder

    # --- what it is good for ----------------------------------------------------

    async def uses(self, item_id: int) -> Uses:
        item = self.inventory.get(item_id)
        known = known_fields(item)
        fills = templates_for(item, self.templates)
        result = await self.client.respond_structured(
            UsesWriting,
            model=self.settings.model_spark,
            input=[user_message(text_part(brief(item, known, self.planner.preferences(), fills)))],
            instructions=INSTRUCTIONS,
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            op="uses",
        )
        kept: list[Use] = []
        for use in result.parsed.uses:
            title = use.title.strip()[:TEXT_MAX]
            if not title:
                continue
            kept.append(
                Use(
                    title=title,
                    what_it_does=use.what_it_does.strip()[:TEXT_MAX],
                    needs=[n.strip()[:TEXT_MAX] for n in use.needs if n.strip()][:NEEDS_MAX],
                    effort=use.effort,
                    note=use.note.strip()[:TEXT_MAX],
                )
            )
            if len(kept) == MAX_USES:
                break
        content: dict[str, Any] = {
            "templates": [t.model_dump() for t in fills],
            "uses": [u.model_dump() for u in kept],
            "model": result.response.model,
            "from_fixture": result.response.from_fixture,
            "cost_usd": result.response.cost_usd,
        }
        row = self.inventory.add_uses(item_id, json.dumps(content))
        log.info(
            "uses",
            extra={
                "item_id": item_id,
                "uses": len(kept),
                "templates": len(fills),
                "usd": result.response.cost_usd,
            },
        )
        return self.uses_of(row)

    def latest_uses(self, item_id: int) -> Uses | None:
        rows = self.inventory.uses(item_id)
        return self.uses_of(rows[-1]) if rows else None

    def uses_of(self, row: Any) -> Uses:
        content = json.loads(row["content"])
        return Uses(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            version=int(row["version"]),
            item_version=int(row["item_version"]),
            stale=int(row["item_version"]) != int(row["current_item_version"]),
            at=row["created_at"],
            **content,
        )

    # --- the view ----------------------------------------------------------------------

    def worth(self, item_id: int) -> Worth | None:
        guidances = self.valuer.guidances(item_id)
        if not guidances:
            return None
        latest = guidances[-1]
        typical = next((q.typical for q in latest.quantities if q.kind == "asking"), None)
        if typical is None:
            typical = next((q.typical for q in latest.quantities if q.kind == "estimate"), None)
        return Worth(
            id=latest.id,
            version=latest.version,
            currency=latest.currency,
            typical=typical,
            strategy=suggested(latest.strategies),
            weak=latest.weak,
            stale=latest.stale,
            at=latest.at,
        )

    def searches_from(self, item_id: int) -> list[OpenSearch]:
        return [
            OpenSearch(
                id=s.id,
                title=s.title,
                status=s.status,
                candidates=s.candidates,
                handoff_url=s.handoff_url,
            )
            for s in self.finder.searches()
            if s.need_item_id == item_id and s.status == "open"
        ]

    def last(self, item_id: int) -> Decided | None:
        for event in reversed(self.inventory.events(item_id)):
            found = parse_decided(event.change)
            if found is not None:
                choice, note = found
                return Decided(choice=choice, note=note, at=event.at, version=event.version)
        return None

    def committed_to(self, item_id: int) -> list[str]:
        """The titles of the selected, building or done projects that count on the item: a
        sale or a gift breaks that build, so the view says it before the choice."""
        # an item can fill more than one requirement of a project: each title once, in order
        titles = (str(r["title"]) for r in self.inventory.committed_elsewhere(item_id, 0))
        return list(dict.fromkeys(titles))

    def decision(self, item_id: int) -> Decision:
        item = self.inventory.get(item_id)
        return Decision(
            item=item,
            accepted_fields=sum(1 for a in item.fields.values() if a.review == "accepted"),
            worth=self.worth(item_id),
            uses=self.latest_uses(item_id),
            searches=self.searches_from(item_id),
            templates=templates_for(item, self.templates),
            intent=item.intent,
            committed_to=self.committed_to(item_id),
            last=self.last(item_id),
        )

    # --- the choice ------------------------------------------------------------------------

    def decide(self, item_id: int, spec: DecisionCreate) -> Item:
        item = self.inventory.decide(
            item_id,
            INTENT_FOR[spec.choice],
            decided_line(spec),
            said=bool(spec.note),
            version=spec.version,
        )
        log.info("decided", extra={"item_id": item_id, "choice": spec.choice})
        return item
