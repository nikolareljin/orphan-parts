"""Deciding what an item becomes: the rules say which projects it fills and gather what the app
already answered (the price, the searches, the history); Muse Spark proposes what else it is
good for and, for this owner, writes three scenarios (keep and fix, reuse, sell or give away);
the owner chooses, and the choice is an event on the item."""

import json
import logging
import re
from typing import Any

from app.config import Settings
from app.decide.schema import (
    CHOICES,
    INTENT_FOR,
    MAX_REUSE,
    MAX_USES,
    Choice,
    Decided,
    Decision,
    DecisionCreate,
    KeepFix,
    OpenSearch,
    ReuseScenario,
    Scenarios,
    ScenariosWriting,
    SellCard,
    TemplateFit,
    Use,
    Uses,
    UsesWriting,
    Worth,
)
from app.find.service import Finder
from app.inventory import Inventory
from app.inventory.schema import TEXT_MAX as NOTES_MAX
from app.inventory.schema import Item
from app.inventory.service import DECIDED, NotFoundError, notes_room
from app.model_api import ModelApiClient, text_part, user_message
from app.projects.pack import private_field
from app.projects.schema import Preferences
from app.projects.service import Planner, fits
from app.projects.skills import skills_line
from app.projects.templates import Templates
from app.value.schema import Strategy
from app.value.service import Valuer

log = logging.getLogger("app.decide")

MAX_OUTPUT_TOKENS = 700
# three cards with their lists: measured at 900 to 1,100 tokens of JSON
SCENARIOS_OUTPUT_TOKENS = 1200
# what the model writes is shown as it is, so it is cut, not trusted
TEXT_MAX = 200
NEEDS_MAX = 6
# how many kinds of item the scenarios brief names from the rest of the inventory
OTHERS_MAX = 40
DETAIL_KEYS = ("condition", "faults", "tests_done", "accessories")
EFFORT_WORDS = {
    "low": "an hour or so of tinkering is fun, no more",
    "medium": "an afternoon of tinkering is fun",
    "high": "a weekend or more of tinkering is fun",
}
NO_PROFILE = (
    "No profile was filled in. Answer for an average person with household tools and no"
    " particular skill, and say so in the first line of each card."
)

INSTRUCTIONS = (
    "You say what a used item is still good for, to a person deciding whether to keep it,"
    " sell it or give it away. Propose at most three uses, the most practical first. Rest"
    " each one on the facts given: the item's confirmed values, its condition, its faults and"
    " what was tested; never assume a part works when the tests do not say so. For each use"
    " say in one line what it would do, list what else it needs that is not in the facts, say"
    " the effort (low, medium or high) for a person with the skills given, and add one note"
    " on what to check first. Respect the person's interests and budget. Plain words, no hype."
)


SCENARIOS_INSTRUCTIONS = (
    "You help one person decide what to do with one used item: keep it and fix it, reuse it"
    " in something, or sell or give it away. Write three cards from the facts given and the"
    " person's profile; never assume a part works when the tests do not say so, and never"
    " invent a fault the record does not hold."
    " keep_fix: the likely problem or problems behind the recorded condition and faults (one"
    " entry 'works as it is' when nothing is wrong), the repair steps written for this person's"
    " level, the difficulty for this person (easy, moderate or hard) with a why that names the"
    " rated skill it rests on, the parts with a rough cost each, the total cost and the time;"
    " when the repair is not worth it for this person, say so with worth_fixing false and the"
    " why. reuse: two or three things to make of it that fit the person's skills and tools,"
    " each naming the other items they own that it would use (with_items; empty when none"
    " applies), the difficulty for this person and why, the extra parts with cost, and the"
    " time. sell: what makes it sellable as it stands, what listing and handing it over takes,"
    " and one note; give no price, the price guidance is a separate step. recommended: one of"
    " keep_fix, reuse, sell or give, with a one-line reason tied to the profile. Plain words,"
    " no hype; each list entry one line."
)


def scenarios_brief(
    item: Item,
    known: dict[str, str],
    prefs: Preferences,
    *,
    profiled: bool,
    others: list[str],
) -> str:
    """What the scenarios call is told: the item's confirmed values and details, the owner's
    profile (rated skills, tools, effort, whether they open devices, budget) and the kinds of
    item they own besides. Nothing else: not the location, the notes, a photo, a price or a
    search; the same rule as the uses brief."""
    lines = [f"name: {item.name}", f"item_type: {item.item_type}"]
    for key in DETAIL_KEYS:
        lines.append(f"{key}: {getattr(item, key) or '(not given)'}")
    lines.append(f"intent so far: {item.intent}")
    lines.append("Confirmed fields (key: value):")
    lines.extend(f"- {k}: {v}" for k, v in known.items())
    if not known:
        lines.append("- (none confirmed yet)")
    lines.append("Profile:")
    if profiled:
        rated = skills_line(prefs.skills) or "(none rated)"
        lines.append(f"- skills (rated none, some, confident or pro): {rated}")
        lines.append(f"- tools: {prefs.tools or '(not given)'}")
        lines.append(f"- effort: {EFFORT_WORDS[prefs.effort]}")
        lines.append(f"- opens devices up: {'yes' if prefs.opens_devices else 'no'}")
        budget = f"{prefs.budget:g} {prefs.currency}" if prefs.budget is not None else "(not given)"
        lines.append(f"- budget for parts: {budget}")
    else:
        lines.append(f"- {NO_PROFILE}")
    lines.append("Other items the person owns (kind, how many):")
    lines.extend(f"- {o}" for o in others)
    if not others:
        lines.append("- (nothing else listed)")
    return "\n".join(lines)


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
    lines.append(f"skills: {skills_line(prefs.skills) or '(not given)'}")
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


MORE = "… (more in the scenarios)"


def plan_heading(version: int) -> str:
    """How a repair plan from the scenarios of this version starts in the notes."""
    return f"Repair plan (scenarios v{version},"


def repair_plan(scenarios: Scenarios, room: int = NOTES_MAX) -> str:
    """The keep and fix card as a few lines for the item's notes: the steps, the parts, the
    cost and the time, in at most ``room`` characters. When it does not fit, whole steps are
    left out from the end and the plan ends with a line saying the rest is in the scenarios;
    empty when the card says it is not worth fixing, has no steps, or not even its heading
    fits."""
    card = scenarios.keep_fix
    if not card.worth_fixing or not card.steps:
        return ""
    head = f"{plan_heading(scenarios.version)} {card.difficulty}):"
    tail = [f"Parts: {'; '.join(card.parts)}"] if card.parts else []
    tail.append(f"Cost: {card.cost}. Time: {card.time}.")
    steps = [f"{n}. {step}" for n, step in enumerate(card.steps, start=1)]
    whole = "\n".join([head, *steps, *tail])
    if len(whole) <= room:
        return whole
    for kept in range(len(steps) - 1, -1, -1):
        cut = "\n".join([head, *steps[:kept], *tail, MORE])
        if len(cut) <= room:
            return cut
    bare = f"{head}\n{MORE}"
    return bare if len(bare) <= room else ""


# what the model wrote for the cards is shown as it is, so each text is cut to its bound and
# each list to its length, blank entries dropped


def _line(text: str) -> str:
    return text.strip()[:TEXT_MAX]


def _lines(texts: list[str]) -> list[str]:
    return [t.strip()[:TEXT_MAX] for t in texts if t.strip()][:NEEDS_MAX]


def _cut_keep_fix(card: KeepFix) -> KeepFix:
    return KeepFix(
        worth_fixing=card.worth_fixing,
        problems=_lines(card.problems),
        steps=_lines(card.steps),
        difficulty=card.difficulty,
        why=_line(card.why),
        parts=_lines(card.parts),
        cost=_line(card.cost),
        time=_line(card.time),
    )


# the brief lists the other items as "kind (count)", and a card may copy the count with it:
# "(1)", "(x1)", "( 2 )", with a trailing full stop or comma
_COUNT = re.compile(r"\s*\(\s*x?\s*\d+\s*\)\s*[.,;]?\s*$", re.I)


def kind_named(text: str) -> str:
    """The kind an entry of a card's with_items names, without a count copied from the brief."""
    return _COUNT.sub("", text.strip()).strip()


def owned_items(texts: list[str], kinds: list[str]) -> list[str]:
    """A card's with_items as the kinds the owner has: each entry without its count, matched
    to an owned kind whatever its letter case, each kind once; an entry that names nothing the
    owner has is dropped."""
    by_key = {kind.casefold(): kind for kind in kinds}
    found: list[str] = []
    for text in texts:
        kind = by_key.get(kind_named(text).casefold())
        if kind is not None and kind not in found:
            found.append(kind)
    return found


def _cut_reuse(card: ReuseScenario) -> ReuseScenario:
    return ReuseScenario(
        title=_line(card.title),
        what_it_does=_line(card.what_it_does),
        with_items=_lines(card.with_items),
        difficulty=card.difficulty,
        why=_line(card.why),
        extra_parts=_lines(card.extra_parts),
        cost=_line(card.cost),
        time=_line(card.time),
    )


def _cut_sell(card: SellCard) -> SellCard:
    return SellCard(
        selling_points=_lines(card.selling_points), effort=_line(card.effort), note=_line(card.note)
    )


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
        row = self.inventory.add_uses(item_id, json.dumps(content), item_version=item.version)
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

    # --- what to do with it, for this owner ---------------------------------------

    def _kinds(self, item_id: int) -> list[tuple[str, int]]:
        """The kinds of item the owner has besides this one, with how many of each, the most
        of a kind first; what is gone is not counted."""
        counts: dict[str, int] = {}
        for summary in self.inventory.list_items():
            if summary.id == item_id or summary.availability == "gone":
                continue
            counts[summary.item_type] = counts.get(summary.item_type, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    def others(self, item_id: int) -> list[str]:
        """The other kinds as the brief names them, "kind (count)"; capped, so a large
        inventory does not become the brief."""
        return [f"{kind} ({n})" for kind, n in self._kinds(item_id)[:OTHERS_MAX]]

    async def scenarios(self, item_id: int) -> Scenarios:
        item = self.inventory.get(item_id)
        known = known_fields(item)
        profiled = self.planner.has_preferences()
        text = scenarios_brief(
            item,
            known,
            self.planner.preferences(),
            profiled=profiled,
            others=self.others(item_id),
        )
        result = await self.client.respond_structured(
            ScenariosWriting,
            model=self.settings.model_spark,
            input=[user_message(text_part(text))],
            instructions=SCENARIOS_INSTRUCTIONS,
            effort="low",
            max_output_tokens=SCENARIOS_OUTPUT_TOKENS,
            op="scenarios",
        )
        written = result.parsed
        content: dict[str, Any] = {
            "profiled": profiled,
            "keep_fix": _cut_keep_fix(written.keep_fix).model_dump(),
            "reuse": [_cut_reuse(r).model_dump() for r in written.reuse if r.title.strip()][
                :MAX_REUSE
            ],
            "sell": _cut_sell(written.sell).model_dump(),
            "recommended": written.recommended,
            "reason": _line(written.reason),
            "model": result.response.model,
            "from_fixture": result.response.from_fixture,
            "cost_usd": result.response.cost_usd,
        }
        row = self.inventory.add_scenarios(item_id, json.dumps(content), item_version=item.version)
        log.info(
            "scenarios",
            extra={
                "item_id": item_id,
                "recommended": written.recommended,
                "profiled": profiled,
                "usd": result.response.cost_usd,
            },
        )
        return self.scenarios_of(row)

    def latest_scenarios(self, item_id: int) -> Scenarios | None:
        rows = self.inventory.scenarios(item_id)
        return self.scenarios_of(rows[-1]) if rows else None

    def scenarios_by_id(self, item_id: int, scenarios_id: int) -> Scenarios:
        """One set of cards written for the item, by its id; 404 for one written for another."""
        for row in self.inventory.scenarios(item_id):
            if int(row["id"]) == scenarios_id:
                return self.scenarios_of(row)
        raise NotFoundError(f"item {item_id} has no scenarios {scenarios_id}")

    def scenarios_of(self, row: Any) -> Scenarios:
        """The cards as kept, with each reuse card's with_items read as the kinds the owner has
        now: the stored row stays as the model wrote it."""
        content = json.loads(row["content"])
        kinds = [kind for kind, _ in self._kinds(int(row["item_id"]))]
        content["reuse"] = [
            {**card, "with_items": owned_items(card["with_items"], kinds)}
            for card in content["reuse"]
        ]
        return Scenarios(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            version=int(row["version"]),
            item_version=int(row["item_version"]),
            stale=bool(row["changed_since"]),
            steps_in_notes=plan_heading(int(row["version"])) in str(row["current_notes"]),
            at=row["created_at"],
            **content,
        )

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
            scenarios=self.latest_scenarios(item_id),
            searches=self.searches_from(item_id),
            templates=templates_for(item, self.templates),
            intent=item.intent,
            committed_to=self.committed_to(item_id),
            last=self.last(item_id),
        )

    # --- the choice ------------------------------------------------------------------------

    def decide(self, item_id: int, spec: DecisionCreate) -> Item:
        """The choice, kept as an event. Keep and fix also writes the repair steps of the
        latest scenarios into the item's notes, where the owner reads and edits them, when the
        item has not changed since they were written."""
        plan = ""
        plan_item_version: int | None = None
        if spec.choice == "keep_fix":
            latest = self.latest_scenarios(item_id)
            if latest is not None:
                # written only while the item is still at the version the cards were written
                # from: the inventory checks it in the transaction that writes the notes
                room = notes_room(self.inventory.get(item_id).notes)
                plan = repair_plan(latest, room)
                plan_item_version = latest.item_version
        item = self.inventory.decide(
            item_id,
            INTENT_FOR[spec.choice],
            decided_line(spec),
            said=bool(spec.note),
            version=spec.version,
            notes_add=plan,
            plan_item_version=plan_item_version,
        )
        log.info("decided", extra={"item_id": item_id, "choice": spec.choice})
        return item
