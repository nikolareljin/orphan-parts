"""Build and reuse: Muse Spark proposes projects from templates and the inventory it is shown
through tools; the rules keep only what the inventory backs; selection commits items, and no
item is committed twice."""

import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.compat import Pairing, set_pairings, shared
from app.compat.rules import best_hosts, memory_need, processor_need
from app.config import Settings
from app.find.schema import SearchCreate, SearchPatch
from app.find.service import Finder
from app.inventory import Inventory, NotFoundError
from app.inventory.parent import PARENT_FIELDS
from app.inventory.schema import Item, ItemPatch
from app.inventory.service import RESERVED_BY_PROJECT
from app.model_api import ModelApiClient, text_part, user_message
from app.ops.door import for_visitor, sandbox
from app.projects import pack as packs
from app.projects.schema import (
    Allocation,
    AllocationSwap,
    Budget,
    Conflict,
    FillRequest,
    OutcomeCreate,
    Pack,
    Preferences,
    Project,
    ProjectList,
    Proposal,
    ProposalSet,
    ProposeRequest,
    Requirement,
    ShareChange,
    Template,
)
from app.projects.templates import Templates

log = logging.getLogger("app.projects")

MAX_OUTPUT_TOKENS = 1600
MAX_STEPS = 4
CHECK_STEPS = 2
# kept beside the answers the demo loader writes: they are not the owner's profile
BY_DEMO = "by_demo"
INSTRUCTIONS = (
    "You propose small, practical projects a person can build from what they already own."
    " First call the tools: the templates are the only projects you may propose, and the"
    " inventory is the only source of items. Fill each requirement with one listed item,"
    " naming it by id and name, with one line of why it fits; leave a requirement missing"
    " rather than inventing an item or stretching one that does not fit. Say the practical"
    " result in one line, the effort, the extra spending you expect in the owner's currency,"
    " and the unknowns a person should check before starting. Respect the owner's preferences"
    " and skills. Plain words, no hype."
)
# with the compatibility rules in the requests: the check the model runs before it answers
CHECK_INSTRUCTIONS = (
    " Parts must physically work together: memory of the generation and form the board or"
    " laptop takes, a processor of the board's socket, a drive of the size and interface its"
    " bay, port or adapter takes. Before answering, call check_allocation with each project's"
    " picks; put another listed item where it refuses one, or leave that requirement missing."
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "list_inventory",
        "description": "Every item the owner has that a build may use, with its fields.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "template_catalog",
        "description": "The projects that may be proposed, with what each one requires.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "item_details",
        "description": "One item in full: condition, faults, tests, accessories and parts.",
        "parameters": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
CHECK_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "check_allocation",
    "description": (
        "Check one project's picks against the compatibility rules: each pick the rules refuse"
        " comes back with the reason (memory generation, socket, drive size or interface, what"
        " an adapter or enclosure takes), and what would fit in its place."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "template": {"type": "string"},
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement": {"type": "string"},
                        "item_id": {"type": "integer"},
                    },
                    "required": ["requirement", "item_id"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["template", "picks"],
        "additionalProperties": False,
    },
    "strict": True,
}
# a requirement's kinds, by the role the compatibility rules give them, and the part that
# fits a host already on the project
NEEDS_BY_ROLE = {"memory": memory_need, "processor": processor_need}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ProjectsError(ValueError):
    """The request cannot be served as given."""


class AllocationConflictError(ProjectsError):
    def __init__(self, conflicts: list[Conflict]) -> None:
        super().__init__("an item is committed to another selected project")
        self.conflicts = conflicts


def item_line(item: Item) -> dict[str, Any]:
    # what the item is; the device a part came from is for its searches, not a build
    fields = {
        k: f"{a.value} {a.unit}".strip() for k, a in item.fields.items() if k not in PARENT_FIELDS
    }
    return {
        "id": item.id,
        "name": item.name,
        "item_type": item.item_type,
        "profile": item.profile,
        "condition": item.condition,
        "intent": item.intent,
        "availability": item.availability,
        "fields": fields,
    }


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


# A word a kind may end in without being another thing: "vacuum cleaner" is a vacuum, "laptop
# computer" a laptop, "speaker system" speakers. A "tv stand" or a "laptop charger" is not, and
# neither is a "module": a "camera module" is a part of a phone, not a camera, and a "switch
# module" no network switch, so a template that takes a module names it ("relay module").
GENERIC_HEADS = frozenset(
    {"cleaner", "computer", "device", "unit", "set", "system", "machine", "player", "kit", "pc"}
)


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2].endswith(("s", "x", "ch", "sh")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def fits(requirement_types: list[str], item: Item) -> bool:
    """Whether an item can fill a requirement: its type ends in one of the kinds asked for, as
    whole words, one or many ("hdmi cables" are a cable, "crevice tool" a tool or a crevice
    tool), or in the kind followed by a generic head ("vacuum cleaner", "laptop computer").
    "Headphones" are not a phone, a "tv stand" is not a tv, a "laptop charger" not a laptop.
    The name is the owner's label and does not count; a toaster called "old laptop" is a
    toaster."""
    if not requirement_types:
        return True
    kind = [_singular(w) for w in _words(item.item_type)]
    if kind and kind[-1] in GENERIC_HEADS and len(kind) > 1:
        kind = kind[:-1]
    for wanted in requirement_types:
        words = [_singular(w) for w in _words(wanted)]
        if words and kind[-len(words) :] == words:
            return True
    return False


@dataclass
class Refusal:
    """A pick the compatibility rules refuse: the requirement, the item, why, and the part
    that would fit the rest of the build."""

    key: str
    item: Item
    reason: str
    need: str


@dataclass
class Realised:
    """A proposal the inventory backs, ready to be written: nothing is inserted until every
    proposal of the call is known, so each project carries its share of the call's cost."""

    template: Template
    title: str
    content: dict[str, Any]
    allocations: list[tuple[int, str, str]]


class Planner:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        templates: Templates,
        finder: Finder,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.templates = templates
        self.finder = finder
        # one change to the projects at a time: a selection checks the other projects' holds
        # and then commits, and two selections of one item must not both pass the check
        self._lock = threading.RLock()
        # the last proposal call: what the model wrote and what the rules kept of it
        self.last_proposed = 0
        self.last_kept = 0
        self.rules = shared()

    # --- preferences --------------------------------------------------------

    def preferences(self) -> Preferences:
        """The owner's answers. A judge's code gets them as the profile shows them to the demo
        visitor: the skills, interests and tools, never the budget or the radius, so neither
        reaches a proposal, a pack, a search ceiling or a card made for the judge."""
        row = self.inventory.preferences()
        if row is None:
            return Preferences()
        content = json.loads(row["content"])
        content.pop(BY_DEMO, None)
        if sandbox():
            content.pop("budget", None)
            content.pop("radius_km", None)
        return Preferences(**content)

    def has_preferences(self) -> bool:
        """Whether the owner has filled the form once; the defaults stand for nobody, and
        neither do the answers the demo loader wrote."""
        row = self.inventory.preferences()
        return row is not None and not json.loads(row["content"]).get(BY_DEMO, False)

    def set_preferences(self, prefs: Preferences, *, by_demo: bool = False) -> Preferences:
        """Keeps the answers; ``by_demo`` marks the ones the demo loader writes, until the owner
        saves the form."""
        content = prefs.model_dump(mode="json")
        if by_demo:
            content[BY_DEMO] = True
        self.inventory.set_preferences(json.dumps(content))
        return self.preferences()

    # --- the tools the model may call --------------------------------------

    def usable(self, *, public_only: bool = False) -> list[Item]:
        """Items a build may count on: not gone, and not meant for sale or giving away."""
        out: list[Item] = []
        for summary in self.inventory.list_items(public_only=public_only):
            if summary.availability == "gone" or summary.intent in ("sell", "give"):
                continue
            # a judge's code builds from the demo set and its own; the owner from the owner's
            # own, never from what a judge added
            if summary.owner_code is not None and summary.owner_code != sandbox():
                continue
            out.append(self.inventory.get(summary.id))
        return out

    def tools(self) -> list[dict[str, Any]]:
        return [*TOOLS, CHECK_TOOL] if self.settings.compat_prompts else TOOLS

    def tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "list_inventory":
            if not self.settings.compat_prompts:
                return json.dumps([item_line(i) for i in self.usable()])
            lines = []
            for item in self.usable():
                line = item_line(item)
                reading = self.rules.read(item)
                if reading.attrs:
                    line["compatibility"] = reading.attrs
                lines.append(line)
            return json.dumps(lines)
        if name == "check_allocation" and self.settings.compat_prompts:
            return json.dumps(self.check_picks(args))
        if name == "template_catalog":
            return json.dumps([t.model_dump() for t in self.templates.summaries()])
        if name == "item_details":
            try:
                item = self.inventory.get(int(args.get("item_id", 0)))
            except (LookupError, ValueError, TypeError):
                return json.dumps({"error": "no such item"})
            line = item_line(item)
            line.update(
                {
                    "faults": item.faults,
                    "tests_done": item.tests_done,
                    "accessories": item.accessories,
                    "components": item.components,
                }
            )
            return json.dumps(line)
        return json.dumps({"error": f"no tool named {name}"})

    # --- proposals ------------------------------------------------------------

    async def propose(self, request: ProposeRequest) -> list[Project]:
        prefs = self.preferences()
        usable = self.usable()
        if not usable:
            raise ProjectsError("nothing in the inventory a build may use")
        brief = [
            f"Propose at most {request.count} projects.",
            f"Preferences: {prefs.model_dump_json()}",
        ]
        if request.note:
            brief.append(f"This time: {request.note}")
        response = await self.client.respond_with_tools(
            ProposalSet,
            model=self.settings.model_spark,
            input=[user_message(text_part("\n".join(brief)))],
            tools=self.tools(),
            handle=self.tool,
            instructions=INSTRUCTIONS
            + (CHECK_INSTRUCTIONS if self.settings.compat_prompts else ""),
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            # the check is one or two more steps: the picks, then the picks fixed
            max_steps=MAX_STEPS + (CHECK_STEPS if self.settings.compat_prompts else 0),
            op="propose",
        )
        self.last_proposed = len(response.parsed.proposals)
        by_id = {i.id: i for i in usable}
        by_name: dict[str, Item] = {}
        for item in usable:
            by_name.setdefault(item.name.strip().lower(), item)
        realised: list[Realised] = []
        seen: set[str] = set()
        for proposal in response.parsed.proposals[: request.count]:
            if proposal.template in seen:
                continue
            try:
                template = self.templates.get(proposal.template)
            except LookupError:
                log.info(
                    "proposal dropped: unknown template", extra={"template": proposal.template}
                )
                continue
            ready = self.realise(template, proposal, by_id, by_name, prefs, response.response)
            if ready is None:
                continue
            seen.add(proposal.template)
            realised.append(ready)
        # the call's cost (every step of the loop) is shared by the projects it produced
        share = round(response.response.cost_usd / len(realised), 6) if realised else 0.0
        projects: list[Project] = []
        for ready in realised:
            ready.content["cost_usd"] = share
            row = self.inventory.add_project(
                ready.template.id, ready.title, json.dumps(ready.content), ready.allocations
            )
            projects.append(self.project_of(row))
        self.last_kept = len(projects)
        log.info(
            "proposed",
            extra={
                "proposed": self.last_proposed,
                "kept": self.last_kept,
                "usd": response.response.cost_usd,
            },
        )
        return projects

    def realise(
        self,
        template: Template,
        proposal: Proposal,
        by_id: dict[int, Item],
        by_name: dict[str, Item],
        prefs: Preferences,
        response: Any,
    ) -> Realised | None:
        """A proposal becomes a project only where the inventory backs it: every allocation
        names a usable item that fits the requirement; nothing else is shown."""
        req_by_key = {r.key: r for r in template.requirements}
        allocations: list[tuple[int, str, str, str]] = []
        dropped: list[str] = []
        taken: set[int] = set()
        for a in proposal.allocations:
            req = req_by_key.get(a.requirement)
            # an id names one item; the name is only for a proposal that gave no id, so an id
            # the inventory cannot use is never re-pointed at another item of the same name
            by_name_only = by_name.get(a.item_name.strip().lower())
            item = by_id.get(a.item_id) if a.item_id else by_name_only
            if req is None or item is None:
                dropped.append(
                    f"{a.requirement}: {a.item_name or a.item_id} is not in the inventory"
                )
                continue
            if item.id in taken or not fits(req.item_types, item):
                dropped.append(f"{a.requirement}: {item.name} does not fill it")
                continue
            taken.add(item.id)
            allocations.append((item.id, item.name, req.key, a.why.strip()[:200]))
        # what does not physically work with the rest goes, said why, and its requirement is
        # open again with the part that would fit
        picks = [(key, by_id[item_id]) for item_id, _name, key, _why in allocations]
        _kept, refusals, _pairings = self.screen(template, picks)
        refused = {(r.key, r.item.id): r for r in refusals}
        allocations = [a for a in allocations if (a[2], a[0]) not in refused]
        notes: dict[str, Refusal] = {}
        for r in refusals:
            dropped.append(f"{r.key}: {r.item.name} incompatible: {r.reason}")
            notes.setdefault(r.key, r)
        if not allocations:
            log.info(
                "proposal dropped: nothing in the inventory backs it",
                extra={"template": template.id},
            )
            return None
        filled = {a[2] for a in allocations}
        requirements = [
            {
                "key": r.key,
                "label": r.label,
                "kind": r.kind,
                "blocking": r.blocking,
                "state": "pass" if r.key in filled else "unknown",
                "item_id": next((a[0] for a in allocations if a[2] == r.key), None),
                "search_id": None,
                "profile": r.profile,
                **(
                    {
                        "incompatible": f"incompatible: {notes[r.key].reason}",
                        "need": notes[r.key].need,
                    }
                    if r.key in notes and r.key not in filled
                    else {}
                ),
            }
            for r in template.requirements
        ]
        content: dict[str, Any] = {
            "result": proposal.result.strip()[:400] or template.result,
            "requirements": requirements,
            "effort": proposal.effort,
            "skills": template.skills,
            "spend_estimate": max(0.0, min(float(proposal.spend_estimate), 10_000_000.0)),
            "currency": prefs.currency,
            "unknowns": [u.strip()[:300] for u in proposal.unknowns if u.strip()][:10],
            "sources": template.sources,
            "steps": template.steps,
            "safety": template.safety,
            "dropped": dropped,
            "model": response.model,
            "from_fixture": response.from_fixture,
            "cost_usd": response.cost_usd,
        }
        return Realised(
            template,
            proposal.title.strip()[:200] or template.label,
            content,
            [(item_id, key, why) for item_id, _name, key, why in allocations],
        )

    # --- compatibility ------------------------------------------------------------

    def screen(
        self, template: Template, picks: list[tuple[str, Item]]
    ) -> tuple[list[tuple[str, Item]], list[Refusal], list[Pairing]]:
        """The picks the compatibility rules keep, the ones they refuse and why, and the
        pairings of those kept. The blocking requirements go first, in the template's order,
        so the laptop stays and the stick that does not fit it goes."""
        order = {r.key: (not r.blocking, n) for n, r in enumerate(template.requirements)}
        ranked = sorted(range(len(picks)), key=lambda i: order.get(picks[i][0], (True, 999)))
        readings = {item.id: self.rules.read(item) for _key, item in picks}
        kept: list[int] = []
        refusals: list[Refusal] = []
        for i in ranked:
            key, item = picks[i]
            candidate = readings[item.id]
            with_it = [readings[picks[j][1].id] for j in kept] + [candidate]
            fails = [
                (part, host, result)
                for part, host, result in best_hosts(with_it)
                if result.state == "fail" and candidate.id in (part.id, host.id)
            ]
            if not fails:
                kept.append(i)
                continue
            part, host, result = fails[0]
            other = host if part.id == candidate.id else part
            need = (
                result.need_part or result.need_host
                if part.id == candidate.id
                else result.need_host or result.need_part
            )
            refusals.append(Refusal(key, item, f"{result.reason} ({other.name})", need))
        kept_picks = [picks[i] for i in sorted(kept)]
        pairings = set_pairings([readings[item.id] for _key, item in kept_picks], [])
        return kept_picks, refusals, pairings

    def check_picks(self, args: dict[str, Any]) -> dict[str, Any]:
        """The check_allocation tool: one project's picks through the rules a proposal is kept
        by, kinds and compatibility, with what else of the inventory would fit a refused one."""
        try:
            template = self.templates.get(str(args.get("template", "")))
        except LookupError:
            return {"error": "no such template; call template_catalog"}
        usable = {i.id: i for i in self.usable()}
        req_by_key = {r.key: r for r in template.requirements}
        refused: list[dict[str, Any]] = []
        picks: list[tuple[str, Item]] = []
        raw = args.get("picks")
        for pick in raw if isinstance(raw, list) else []:
            if not isinstance(pick, dict):
                continue
            key, item_id = str(pick.get("requirement", "")), pick.get("item_id")
            req = req_by_key.get(key)
            item = usable.get(item_id) if isinstance(item_id, int) else None
            if req is None or item is None:
                why = "no such requirement" if req is None else "not an item a build may use"
                refused.append({"requirement": key, "item_id": item_id, "reason": why})
            elif not fits(req.item_types, item):
                refused.append(
                    {"requirement": key, "item_id": item.id, "reason": "not a kind that fills it"}
                )
            else:
                picks.append((key, item))
        kept, refusals, pairings = self.screen(template, picks)
        taken = {item.id for _key, item in kept}
        for r in refusals:
            req = req_by_key[r.key]
            instead = [
                {"item_id": i.id, "name": i.name}
                for i in usable.values()
                if i.id not in taken
                and i.id != r.item.id
                and fits(req.item_types, i)
                and not self.screen(template, [*kept, (r.key, i)])[1]
            ][:3]
            refused.append(
                {
                    "requirement": r.key,
                    "item_id": r.item.id,
                    "reason": f"incompatible: {r.reason}",
                    "fits_instead": instead,
                    "needs": r.need,
                }
            )
        return {
            "template": template.id,
            "kept": [{"requirement": key, "item_id": item.id} for key, item in kept],
            "refused": refused,
            "pairings": [
                {"state": p.state, "part": p.part, "host": p.host, "reason": p.reason}
                for p in pairings
            ],
        }

    def compatibility(self, items: list[Item]) -> list[Pairing]:
        """The pairings of a project's items, with what fixes a failure from what else the
        owner may build with (for the demo visitor, what is public)."""
        readings = [self.rules.read(i) for i in items]
        found = set_pairings(readings, [])
        if any(p.state == "fail" for p in found) or any(
            r.role in ("adapter", "enclosure") for r in readings
        ):
            owned = [self.rules.read(i) for i in self.usable(public_only=for_visitor())]
            found = set_pairings(readings, owned)
        return found

    def needs(self, requirements: list[dict[str, Any]], template: str, items: list[Item]) -> None:
        """An open requirement says the part that fits what the project holds: the memory a
        laptop on it takes, a processor of its board's socket."""
        try:
            kinds = {r.key: r.item_types for r in self.templates.get(template).requirements}
        except LookupError:
            return
        readings = [self.rules.read(i) for i in items]
        for req in requirements:
            if req["state"] == "pass" or req.get("need"):
                continue
            roles = {self.rules.role_of(k) for k in kinds.get(req["key"], [])}
            for role, need_of in NEEDS_BY_ROLE.items():
                if role not in roles:
                    continue
                key = "memory_type" if role == "memory" else "socket"
                host = next(
                    (
                        r
                        for r in readings
                        if r.role in ("board", "laptop")
                        and r.get(key)
                        and (role == "memory" or r.role == "board")
                    ),
                    None,
                )
                if host is not None:
                    req["need"] = need_of(host)

    def instead(
        self, requirements: list[dict[str, Any]], template: str, project_id: int, items: list[Item]
    ) -> None:
        """For an open requirement the rules know the part for, an item of yours that fills
        it and passes with everything on the project: the DDR3L stick in the drawer, not the
        DDR4 one the proposal named."""
        open_reqs = [
            r
            for r in requirements
            if r["state"] != "pass" and (r.get("need") or r.get("incompatible"))
        ]
        if not open_reqs:
            return
        try:
            kinds = {r.key: r.item_types for r in self.templates.get(template).requirements}
        except LookupError:
            return
        held = [self.rules.read(i) for i in items]
        on = {i.id for i in items}
        usable = [i for i in self.usable(public_only=for_visitor()) if i.id not in on]
        for req in open_reqs:
            for item in usable:
                if not fits(kinds.get(req["key"], []), item):
                    continue
                if self.inventory.committed_elsewhere(item.id, project_id):
                    continue
                candidate = self.rules.read(item)
                mine = [
                    result.state
                    for part, host, result in best_hosts([*held, candidate])
                    if candidate.id in (part.id, host.id)
                ]
                if mine and all(state == "pass" for state in mine):
                    req["instead_id"], req["instead"] = item.id, item.name
                    break

    # --- projects ---------------------------------------------------------------

    def projects(self, *, public_only: bool = False) -> ProjectList:
        """Every project; for the demo visitor, only those built on public items alone."""
        rows = self.inventory.projects()
        projects = [self.project_of(r) for r in rows]
        # what the budget counts is the asker's own selection: the owner's, never a judge's,
        # and a judge's own alone
        own = {int(r["id"]) for r in rows if r["owner_code"] == (sandbox() or None)}
        if public_only:
            projects = [p for p in projects if self.shown(p)]
        prefs = self.preferences()
        selected = [
            p for p in projects if p.status in ("selected", "building", "done") and p.id in own
        ]
        spend = round(sum(p.spend_estimate for p in selected), 2)
        return ProjectList(
            projects=projects,
            budget=Budget(
                budget=prefs.budget,
                currency=prefs.currency,
                committed_spend=spend,
                remaining=None if prefs.budget is None else round(prefs.budget - spend, 2),
                selected=len(selected),
            ),
        )

    def project(self, project_id: int, *, public_only: bool = False) -> Project:
        """The project; one the demo visitor may not see is not there at all for them."""
        found = self.project_of(self.inventory.project(project_id))
        if public_only and not self.shown(found):
            raise NotFoundError(f"no project {project_id}")
        return found

    def shown(self, project: Project) -> bool:
        """Whether the demo visitor may see the project: every item on it is marked public."""
        if not project.allocations:
            return False
        for allocation in project.allocations:
            try:
                self.inventory.get(allocation.item_id, public_only=True)
            except NotFoundError:
                return False
        return True

    def shortlist(self, project_id: int) -> Project:
        with self._lock:
            self.expect_status(project_id, "proposed", "shortlisted", "selected")
            return self.set_status(project_id, "shortlisted", commit=False)

    def select(self, project_id: int, *, take: bool = False) -> Project:
        """Commit the project's items. An item committed to another selected project is a
        conflict, answered with the other project, unless the owner says to take it."""
        with self._lock:
            return self._select(project_id, take=take)

    def expect_status(self, project_id: int, *allowed: str) -> None:
        """A project moves one way: proposed, shortlisted, selected, building, done; abandoned
        from anywhere but done."""
        status = str(self.inventory.project(project_id)["status"])
        if status not in allowed:
            article = "an" if status[0] in "aeiou" else "a"
            raise ProjectsError(f"{article} {status} project cannot be changed this way")

    def _select(self, project_id: int, *, take: bool) -> Project:
        self.expect_status(project_id, "proposed", "shortlisted", "selected")
        project = self.project(project_id)
        conflicts: list[Conflict] = []
        for a in project.allocations:
            for other in self.inventory.committed_elsewhere(a.item_id, project_id):
                conflicts.append(
                    Conflict(
                        item_id=a.item_id,
                        item_name=a.item_name,
                        project_id=int(other["project_id"]),
                        project_title=other["title"],
                    )
                )
        if conflicts and not take:
            raise AllocationConflictError(conflicts)
        for c in conflicts:
            # a build under way keeps its items: every blocking requirement passed before it
            # started, and taking one would leave it in a state it cannot be in
            other_status = str(self.inventory.project(c.project_id)["status"])
            if other_status == "building":
                raise ProjectsError(
                    f"{c.item_name} is being built into {c.project_title!r};"
                    " finish or abandon that first"
                )
            if other_status == "done":
                raise ProjectsError(
                    f"{c.item_name} is part of {c.project_title!r}, which is done; it stays there"
                )
        for c in conflicts:
            self.inventory.release_allocation(c.project_id, c.item_id)
            self.mark_missing(c.project_id, c.item_id)
        return self.set_status(project_id, "selected", commit=True)

    def mark_missing(self, project_id: int, item_id: int) -> None:
        """A project that lost an item to another: the requirement is open again."""
        row = self.inventory.project(project_id)
        content = json.loads(row["content"])
        for req in content["requirements"]:
            if req["item_id"] == item_id:
                req["item_id"], req["state"] = None, "unknown"
        self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))

    def abandon(self, project_id: int) -> Project:
        with self._lock:
            self.expect_status(project_id, "proposed", "shortlisted", "selected", "building")
            return self.set_status(project_id, "abandoned", commit=False)

    def advance(self, project_id: int, status: str) -> Project:
        if status not in ("building", "done"):
            raise ProjectsError("a project advances to building or done")
        with self._lock:
            return self._advance(project_id, status)

    def _advance(self, project_id: int, status: str) -> Project:
        project = self.project(project_id)
        if project.status not in ("selected", "building"):
            raise ProjectsError("only a selected project is built")
        open_keys = [r.key for r in project.requirements if r.blocking and r.state != "pass"]
        if open_keys:
            raise ProjectsError(f"still needed before building: {', '.join(open_keys)}")
        return self.set_status(project_id, status, commit=True)

    def fill(self, project_id: int, key: str, request: FillRequest) -> Project:
        """An item of the owner's for a requirement the proposal left open. It must be usable
        and of a kind the requirement takes; a search open for the requirement is marked found."""
        with self._lock:
            return self._fill(project_id, key, request)

    def _fill(self, project_id: int, key: str, request: FillRequest) -> Project:
        row = self.inventory.project(project_id)
        if row["status"] in ("done", "abandoned"):
            raise ProjectsError("the project is over")
        content = json.loads(row["content"])
        req = next((r for r in content["requirements"] if r["key"] == key), None)
        if req is None:
            raise ProjectsError(f"no requirement {key!r}")
        if req["state"] == "pass":
            raise ProjectsError(f"{key} is filled already")
        item = next((i for i in self.usable() if i.id == request.item_id), None)
        if item is None:
            raise ProjectsError("the item is not one a build may use")
        if any(int(a["item_id"]) == item.id for a in self.inventory.allocations(project_id)):
            raise ProjectsError(f"{item.name} is on this project already")
        template = self.templates.get(str(row["template"]))
        kinds = next((r.item_types for r in template.requirements if r.key == key), [])
        if not fits(kinds, item):
            raise ProjectsError(f"{item.name} is not a kind that fills {key}")
        if self.inventory.committed_elsewhere(item.id, project_id):
            raise ProjectsError(f"{item.name} is committed to another selected project")
        self.expect_fit(project_id, item)
        committed = str(row["status"]) in ("selected", "building")
        self.inventory.add_allocation(
            project_id, item.id, key, request.why.strip() or "put here by you", committed
        )
        req["item_id"], req["state"] = item.id, "pass"
        req.pop("incompatible", None)
        req.pop("need", None)
        if req["search_id"] is not None:
            self.finder.update(int(req["search_id"]), SearchPatch(status="found"))
        updated = self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        if committed:
            self.reserve(item.id)
        return self.project_of(updated)

    def expect_fit(self, project_id: int, item: Item, *, without: int = 0) -> None:
        """The item works with what the project holds (all but ``without``), or the refusal
        says why: a DDR4 stick for a DDR3 laptop is not put on it by hand either."""
        held = [
            self.rules.read(self.inventory.get(int(a["item_id"])))
            for a in self.inventory.allocations(project_id)
            if int(a["item_id"]) != without
        ]
        candidate = self.rules.read(item)
        for part, host, result in best_hosts([*held, candidate]):
            if result.state == "fail" and candidate.id in (part.id, host.id):
                other = host if part.id == candidate.id else part
                raise ProjectsError(
                    f"{item.name} does not fit this build: {result.reason} ({other.name})"
                )

    # --- an allocation changed by hand ----------------------------------------------

    def swap(self, project_id: int, item_id: int, request: AllocationSwap) -> Project:
        """Another item of yours in place of one on the project, for the same requirement: it
        must be usable, of a kind the requirement takes, free and compatible with the rest."""
        with self._lock:
            return self._swap(project_id, item_id, request)

    def _swap(self, project_id: int, item_id: int, request: AllocationSwap) -> Project:
        row = self.inventory.project(project_id)
        if row["status"] in ("done", "abandoned"):
            raise ProjectsError("the project is over")
        held = {int(a["item_id"]): a for a in self.inventory.allocations(project_id)}
        if item_id not in held:
            raise NotFoundError(f"item {item_id} is not on project {project_id}")
        if request.item_id == item_id:
            raise ProjectsError("that item is on the project already")
        if request.item_id in held:
            raise ProjectsError("that item is on this project already")
        key = str(held[item_id]["requirement"])
        item = next((i for i in self.usable() if i.id == request.item_id), None)
        if item is None:
            raise ProjectsError("the item is not one a build may use")
        template = self.templates.get(str(row["template"]))
        kinds = next((r.item_types for r in template.requirements if r.key == key), [])
        if not fits(kinds, item):
            raise ProjectsError(f"{item.name} is not a kind that fills {key}")
        if self.inventory.committed_elsewhere(item.id, project_id):
            raise ProjectsError(f"{item.name} is committed to another selected project")
        self.expect_fit(project_id, item, without=item_id)
        committed = bool(held[item_id]["committed"])
        self.inventory.release_allocation(project_id, item_id)
        self.inventory.add_allocation(
            project_id, item.id, key, request.why.strip() or "put here by you", committed
        )
        content = json.loads(row["content"])
        for req in content["requirements"]:
            if req["key"] == key:
                req["item_id"], req["state"] = item.id, "pass"
                req.pop("incompatible", None)
                req.pop("need", None)
        updated = self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        if committed:
            self.reserve(item_id)
            self.reserve(item.id)
        return self.project_of(updated)

    def remove(self, project_id: int, item_id: int) -> Project:
        """An item taken off the project: its requirement is open again and, when the project
        held it, the item is free for another. A build under way keeps what it blocks on."""
        with self._lock:
            return self._remove(project_id, item_id)

    def _remove(self, project_id: int, item_id: int) -> Project:
        row = self.inventory.project(project_id)
        if row["status"] in ("done", "abandoned"):
            raise ProjectsError("the project is over")
        held = {int(a["item_id"]): a for a in self.inventory.allocations(project_id)}
        if item_id not in held:
            raise NotFoundError(f"item {item_id} is not on project {project_id}")
        key = str(held[item_id]["requirement"])
        template = self.templates.get(str(row["template"]))
        blocking = next((r.blocking for r in template.requirements if r.key == key), False)
        if row["status"] == "building" and blocking:
            raise ProjectsError(f"{key} blocks the build under way; swap the item instead")
        self.inventory.release_allocation(project_id, item_id)
        self.mark_missing(project_id, item_id)
        if held[item_id]["committed"]:
            self.reserve(item_id)
        return self.project(project_id)

    def set_status(self, project_id: int, status: str, *, commit: bool) -> Project:
        with self._lock:
            row = self.inventory.project(project_id)
            was_committed = str(row["status"]) in ("selected", "building", "done")
            updated = self.inventory.update_project(project_id, status, row["content"])
            self.inventory.set_committed(project_id, commit)
            # the status is written first: an item is reserved by what a selected project
            # holds. Availability is touched only when a commitment begins or ends; a proposal
            # shortlisted or abandoned leaves what the owner set alone.
            if commit or was_committed:
                for a in self.inventory.allocations(project_id):
                    self.reserve(int(a["item_id"]))
            return self.project_of(updated)

    def reserve(self, item_id: int) -> None:
        """An item is reserved while a selected, building or done project counts on it."""
        if not self.inventory.writable(item_id):
            return  # a judge's project holds the demo set's items without reserving them
        wanted = "reserved" if self.inventory.committed_elsewhere(item_id, 0) else "available"
        item = self.inventory.get(item_id)
        if item.availability != "gone" and item.availability != wanted:
            # kept apart from an edit: the cards and drafts written before stay current
            self.inventory.update(
                item_id, ItemPatch(availability=wanted), change=RESERVED_BY_PROJECT + wanted
            )

    def search_for(self, project_id: int, key: str) -> Project:
        """A missing requirement becomes a search request, with the budget left as its ceiling."""
        with self._lock:
            return self._search_for(project_id, key)

    def _search_for(self, project_id: int, key: str) -> Project:
        row = self.inventory.project(project_id)
        if row["status"] in ("done", "abandoned"):
            raise ProjectsError("the project is over")
        content = json.loads(row["content"])
        req = next((r for r in content["requirements"] if r["key"] == key), None)
        if req is None:
            raise ProjectsError(f"no requirement {key!r}")
        if req["state"] == "pass":
            raise ProjectsError(f"{key} is filled from the inventory")
        if req["search_id"] is not None:
            raise ProjectsError(f"a search is open for {key} already")
        budget = self.projects().budget
        # the budget left is the ceiling; a budget spent is a ceiling of nothing, not none
        left = None if budget.remaining is None else max(0.0, budget.remaining)
        # with the rules in the requests, the search names the part that fits the build
        need = ""
        if self.settings.compat_prompts:
            need = req.get("need") or ""
            if not need:
                held = [
                    self.inventory.get(int(a["item_id"]))
                    for a in self.inventory.allocations(project_id)
                ]
                probe = [dict(r) for r in content["requirements"]]
                self.needs(probe, str(row["template"]), held)
                need = next((r.get("need", "") for r in probe if r["key"] == key), "")
        what = need[:1].upper() + need[1:] if need else req["label"]
        search = self.finder.create(
            SearchCreate(
                profile=req["profile"] or "generic_item",
                title=f"{what} for {row['title']}"[:200],
                max_price=left,
                currency=budget.currency,
                budget_left=left,
            )
        )
        req["search_id"] = search.id
        return self.project_of(
            self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        )

    # --- the build pack, progress and the outcome ------------------------------

    def items_on(self, project: Project) -> list[Item]:
        out: list[Item] = []
        for a in project.allocations:
            try:
                out.append(self.inventory.get(a.item_id))
            except LookupError:
                continue
        return out

    def searches_of(self, project: Project) -> dict[int, Any]:
        searches: dict[int, Any] = {}
        for r in project.requirements:
            if r.search_id is None:
                continue
            try:
                searches[r.search_id] = (
                    self.finder.search(r.search_id),
                    self.finder.candidates(r.search_id),
                )
            except LookupError:
                continue
        return searches

    def digest(self, project: Project) -> str:
        return packs.digest_for(
            project,
            self.items_on(project),
            self.preferences(),
            self.projects().budget,
            self.searches_of(project),
        )

    def write_pack(self, project_id: int) -> Pack:
        """The pack from what stands now: the rules write it, nothing is asked of a model."""
        with self._lock:
            project = self.project(project_id)
            if project.status in ("proposed", "shortlisted", "abandoned"):
                raise ProjectsError("a build pack is written for a selected project")
            items = self.items_on(project)
            prefs = self.preferences()
            budget = self.projects().budget
            searches = self.searches_of(project)
            digest = packs.digest_for(project, items, prefs, budget, searches)
            version = len(self.inventory.packs(project_id)) + 1
            markdown = packs.render(project, items, prefs, budget, searches, version, digest)
            return self.pack_of(self.inventory.add_pack(project_id, digest, markdown), digest)

    def packs_of(self, project_id: int, *, public_only: bool = False) -> list[Pack]:
        current = self.digest(self.project(project_id, public_only=public_only))
        return [self.pack_of(r, current) for r in self.inventory.packs(project_id)]

    def pack(self, pack_id: int, *, public_only: bool = False) -> Pack:
        row = self.inventory.pack(pack_id)
        try:
            project = self.project(int(row["project_id"]), public_only=public_only)
        except NotFoundError:
            raise NotFoundError(f"no pack {pack_id}") from None
        return self.pack_of(row, self.digest(project))

    def pack_of(self, row: Any, current: str) -> Pack:
        return Pack(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            version=int(row["version"]),
            digest=row["digest"],
            stale=row["digest"] != current,
            markdown=row["markdown"],
            created_at=row["created_at"],
        )

    def set_progress(self, project_id: int, step: int, done: bool) -> Project:
        with self._lock:
            return self._set_progress(project_id, step, done)

    def _set_progress(self, project_id: int, step: int, done: bool) -> Project:
        row = self.inventory.project(project_id)
        if row["status"] not in ("selected", "building"):
            raise ProjectsError("progress is kept on a selected or building project")
        content = json.loads(row["content"])
        steps = content.get("steps", [])
        if step >= len(steps):
            raise ProjectsError(f"no step {step}")
        progress = list(content.get("progress", [])) + [False] * len(steps)
        progress = progress[: len(steps)]
        progress[step] = done
        content["progress"] = progress
        return self.project_of(
            self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        )

    def record_outcome(self, project_id: int, outcome: OutcomeCreate) -> Project:
        """The owner's record of what was built and how it was tested. A working result marks
        the project done; a failed test keeps it building, with the record kept."""
        with self._lock:
            return self._record_outcome(project_id, outcome)

    def _record_outcome(self, project_id: int, outcome: OutcomeCreate) -> Project:
        # read as a project first: an item deleted since is noticed and its requirement opened
        project = self.project(project_id)
        if project.status != "building":
            raise ProjectsError("an outcome is recorded on a project being built")
        if outcome.working:
            # done means built: the same bar as advancing, so the two routes agree
            open_keys = [r.key for r in project.requirements if r.blocking and r.state != "pass"]
            if open_keys:
                raise ProjectsError(f"still needed before done: {', '.join(open_keys)}")
        row = self.inventory.project(project_id)
        content = json.loads(row["content"])
        # a new record is a new text: sharing is off until the owner says so for this one
        content["outcome"] = {**outcome.model_dump(), "recorded_at": now_iso(), "shared": False}
        status = "done" if outcome.working else "building"
        self.inventory.update_project(project_id, status, json.dumps(content))
        if status == "done":
            return self.set_status(project_id, status, commit=True)
        return self.project(project_id)

    def set_share(self, project_id: int, change: ShareChange) -> Project:
        with self._lock:
            return self._set_share(project_id, change)

    def _set_share(self, project_id: int, change: ShareChange) -> Project:
        row = self.inventory.project(project_id)
        content = json.loads(row["content"])
        if not content.get("outcome"):
            raise ProjectsError("no outcome recorded")
        content["outcome"]["shared"] = change.shared
        return self.project_of(
            self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        )

    def share_text(self, project_id: int) -> str:
        project = self.project(project_id)
        if project.outcome is None or not project.outcome.shared:
            raise ProjectsError("the outcome is not shared")
        # every item the owner has is a name to keep out, not only those still on the project
        known = [(s.name, s.item_type) for s in self.inventory.list_items()]
        return packs.share_text(project, self.items_on(project), known)

    def _readable(self, item_id: int) -> bool:
        try:
            self.inventory.get(item_id)
        except LookupError:
            return False
        return True

    def project_of(self, row: Any) -> Project:
        content = json.loads(row["content"])
        content.setdefault("progress", [])
        content.setdefault("outcome", None)
        rows = self.inventory.allocations(int(row["id"]))
        judge = sandbox()
        if judge:
            # an item a judge's code may not read (the owner made it private since) is not on
            # the project for it, its name included
            rows = [a for a in rows if self._readable(int(a["item_id"]))]
        # an item deleted from the inventory drops out of the allocations (the join skips it);
        # the requirement it filled is open again, written back so the next read agrees (a
        # judge's read of the owner's project changes nothing: it is opened in the answer only)
        held = {int(a["item_id"]) for a in rows}
        lost = [r for r in content["requirements"] if r["item_id"] and r["item_id"] not in held]
        if lost:
            for r in lost:
                r["item_id"], r["state"] = None, "unknown"
            if not judge or row["owner_code"] == judge:
                row = self.inventory.update_project(
                    int(row["id"]), str(row["status"]), json.dumps(content)
                )
                content = json.loads(row["content"])
        allocations = [
            Allocation(
                item_id=int(a["item_id"]),
                item_name=a["item_name"],
                requirement=a["requirement"],
                committed=bool(a["committed"]),
                why=a["why"],
            )
            for a in rows
        ]
        # the rules read the items as they are now: a value accepted since changes the answer
        items: list[Item] = []
        for a in rows:
            try:
                items.append(self.inventory.get(int(a["item_id"])))
            except LookupError:
                continue
        self.needs(content["requirements"], str(row["template"]), items)
        self.instead(content["requirements"], str(row["template"]), int(row["id"]), items)
        content.pop("compatibility", None)
        return Project(
            id=int(row["id"]),
            template=row["template"],
            title=row["title"],
            status=row["status"],
            version=int(row["version"]),
            requirements=[Requirement(**r) for r in content.pop("requirements")],
            allocations=allocations,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            compatibility=self.compatibility(items),
            **content,
        )
