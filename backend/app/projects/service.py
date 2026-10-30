"""Build and reuse: Muse Spark proposes projects from templates and the inventory it is shown
through tools; the rules keep only what the inventory backs; selection commits items, and no
item is committed twice."""

import json
import logging
from typing import Any

from app.config import Settings
from app.find.schema import SearchCreate, SearchPatch
from app.find.service import Finder
from app.inventory import Inventory
from app.inventory.schema import Item, ItemPatch
from app.model_api import ModelApiClient, text_part, user_message
from app.projects.schema import (
    Allocation,
    Budget,
    Conflict,
    FillRequest,
    Preferences,
    Project,
    ProjectList,
    Proposal,
    ProposalSet,
    ProposeRequest,
    Requirement,
    Template,
)
from app.projects.templates import Templates

log = logging.getLogger("app.projects")

MAX_OUTPUT_TOKENS = 1600
MAX_STEPS = 4
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


class ProjectsError(ValueError):
    """The request cannot be served as given."""


class AllocationConflictError(ProjectsError):
    def __init__(self, conflicts: list[Conflict]) -> None:
        super().__init__("an item is committed to another selected project")
        self.conflicts = conflicts


def item_line(item: Item) -> dict[str, Any]:
    fields = {k: f"{a.value} {a.unit}".strip() for k, a in item.fields.items()}
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


def fits(requirement_types: list[str], item: Item) -> bool:
    """Whether an item can fill a requirement: its type names one of the kinds asked for. The
    name is the owner's label and does not count; a toaster called "old laptop" is a toaster."""
    if not requirement_types:
        return True
    kind = item.item_type.lower()
    return any(t.lower() in kind for t in requirement_types)


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

    # --- preferences --------------------------------------------------------

    def preferences(self) -> Preferences:
        row = self.inventory.preferences()
        return Preferences(**json.loads(row["content"])) if row else Preferences()

    def set_preferences(self, prefs: Preferences) -> Preferences:
        row = self.inventory.set_preferences(prefs.model_dump_json())
        return Preferences(**json.loads(row["content"]))

    # --- the tools the model may call --------------------------------------

    def usable(self) -> list[Item]:
        """Items a build may count on: not gone, and not meant for sale or giving away."""
        out: list[Item] = []
        for summary in self.inventory.list_items():
            if summary.availability == "gone" or summary.intent in ("sell", "give"):
                continue
            out.append(self.inventory.get(summary.id))
        return out

    def tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "list_inventory":
            return json.dumps([item_line(i) for i in self.usable()])
        if name == "template_catalog":
            return json.dumps([t.model_dump() for t in self.templates.summaries()])
        if name == "item_details":
            try:
                item = self.inventory.get(int(args.get("item_id", 0)))
            except (LookupError, ValueError):
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
            tools=TOOLS,
            handle=self.tool,
            instructions=INSTRUCTIONS,
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_steps=MAX_STEPS,
            op="propose",
        )
        by_id = {i.id: i for i in usable}
        by_name: dict[str, Item] = {}
        for item in usable:
            by_name.setdefault(item.name.strip().lower(), item)
        projects: list[Project] = []
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
            project = self.realise(template, proposal, by_id, by_name, prefs, response.response)
            if project is None:
                continue
            seen.add(proposal.template)
            projects.append(project)
        log.info(
            "proposed",
            extra={
                "proposed": len(response.parsed.proposals),
                "kept": len(projects),
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
    ) -> Project | None:
        """A proposal becomes a project only where the inventory backs it: every allocation
        names a usable item that fits the requirement; nothing else is shown."""
        req_by_key = {r.key: r for r in template.requirements}
        allocations: list[tuple[int, str, str, str]] = []
        dropped: list[str] = []
        taken: set[int] = set()
        for a in proposal.allocations:
            req = req_by_key.get(a.requirement)
            item = by_id.get(a.item_id) or by_name.get(a.item_name.strip().lower())
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
        row = self.inventory.add_project(
            template.id,
            proposal.title.strip()[:200] or template.label,
            json.dumps(content),
            [(item_id, key, why) for item_id, _name, key, why in allocations],
        )
        return self.project_of(row)

    # --- projects ---------------------------------------------------------------

    def projects(self) -> ProjectList:
        rows = self.inventory.projects()
        projects = [self.project_of(r) for r in rows]
        prefs = self.preferences()
        selected = [p for p in projects if p.status in ("selected", "building")]
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

    def project(self, project_id: int) -> Project:
        return self.project_of(self.inventory.project(project_id))

    def shortlist(self, project_id: int) -> Project:
        return self.set_status(project_id, "shortlisted", commit=False)

    def select(self, project_id: int, *, take: bool = False) -> Project:
        """Commit the project's items. An item committed to another selected project is a
        conflict, answered with the other project, unless the owner says to take it."""
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
        return self.set_status(project_id, "abandoned", commit=False)

    def advance(self, project_id: int, status: str) -> Project:
        if status not in ("building", "done"):
            raise ProjectsError("a project advances to building or done")
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
        committed = str(row["status"]) in ("selected", "building")
        self.inventory.add_allocation(
            project_id, item.id, key, request.why.strip() or "put here by you", committed
        )
        req["item_id"], req["state"] = item.id, "pass"
        if req["search_id"] is not None:
            self.finder.update(int(req["search_id"]), SearchPatch(status="found"))
        updated = self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        if committed:
            self.reserve(item.id)
        return self.project_of(updated)

    def set_status(self, project_id: int, status: str, *, commit: bool) -> Project:
        row = self.inventory.project(project_id)
        updated = self.inventory.update_project(project_id, status, row["content"])
        self.inventory.set_committed(project_id, commit)
        # the status is written first: an item is reserved by what a selected project holds
        for a in self.inventory.allocations(project_id):
            self.reserve(int(a["item_id"]))
        return self.project_of(updated)

    def reserve(self, item_id: int) -> None:
        """An item is reserved while any selected project counts on it, available otherwise."""
        wanted = "reserved" if self.inventory.committed_elsewhere(item_id, 0) else "available"
        item = self.inventory.get(item_id)
        if item.availability != "gone" and item.availability != wanted:
            self.inventory.update(item_id, ItemPatch(availability=wanted))

    def search_for(self, project_id: int, key: str) -> Project:
        """A missing requirement becomes a search request, with the budget left as its ceiling."""
        row = self.inventory.project(project_id)
        content = json.loads(row["content"])
        req = next((r for r in content["requirements"] if r["key"] == key), None)
        if req is None:
            raise ProjectsError(f"no requirement {key!r}")
        if req["state"] == "pass":
            raise ProjectsError(f"{key} is filled from the inventory")
        if req["search_id"] is not None:
            raise ProjectsError(f"a search is open for {key} already")
        budget = self.projects().budget
        search = self.finder.create(
            SearchCreate(
                profile=req["profile"] or "generic_item",
                title=f"{req['label']} for {row['title']}",
                max_price=budget.remaining if budget.remaining and budget.remaining > 0 else None,
                currency=budget.currency,
                budget_left=budget.remaining if budget.remaining and budget.remaining > 0 else None,
            )
        )
        req["search_id"] = search.id
        return self.project_of(
            self.inventory.update_project(project_id, str(row["status"]), json.dumps(content))
        )

    def project_of(self, row: Any) -> Project:
        content = json.loads(row["content"])
        allocations = [
            Allocation(
                item_id=int(a["item_id"]),
                item_name=a["item_name"],
                requirement=a["requirement"],
                committed=bool(a["committed"]),
                why=a["why"],
            )
            for a in self.inventory.allocations(int(row["id"]))
        ]
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
            **content,
        )
