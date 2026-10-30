"""The build pack: one Markdown document per project, written by the rules from what the
inventory holds on the day, with a digest of its inputs so a change marks it stale. Serial
numbers, locations and notes never go in."""

import hashlib
import json
import re
from datetime import UTC, datetime

from app.find.schema import Candidate, Search
from app.inventory.schema import Item
from app.projects.schema import Budget, Preferences, Project

PRIVATE_FIELDS = ("serial", "imei", "mac_address", "account", "password", "location")


def shown_fields(item: Item) -> list[tuple[str, str]]:
    """The accepted values of an item, without anything that identifies it or its owner."""
    out: list[tuple[str, str]] = []
    for key in sorted(item.fields):
        if any(p in key for p in PRIVATE_FIELDS):
            continue
        assertion = item.fields[key]
        if assertion.review != "accepted":
            continue
        out.append((key.replace("_", " "), f"{assertion.value} {assertion.unit}".strip()))
    return out


def money(amount: float) -> str:
    """A sum as people write it: no exponent, at most two decimals, no trailing zeros."""
    return f"{amount:.2f}".rstrip("0").rstrip(".") or "0"


def digest_for(
    project: Project,
    items: list[Item],
    prefs: Preferences,
    budget: Budget,
    searches: dict[int, tuple[Search, list[Candidate]]],
) -> str:
    """What the pack rests on: the project as it stands, each item at its version, the budget
    and what the other selected projects take of it, the tools, the candidates of its searches."""
    parts = {
        "project": project.version,
        "requirements": [(r.key, r.state, r.item_id, r.search_id) for r in project.requirements],
        "allocations": [(a.item_id, a.requirement, a.committed) for a in project.allocations],
        "items": sorted((i.id, i.version) for i in items),
        "budget": (prefs.budget, prefs.currency, budget.committed_spend, budget.remaining),
        "tools": prefs.tools,
        "candidates": sorted(
            (sid, c.id, c.state, c.asking_price)
            for sid, (_search, candidates) in searches.items()
            for c in candidates
        ),
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def render(
    project: Project,
    items: list[Item],
    prefs: Preferences,
    budget: Budget,
    searches: dict[int, tuple[Search, list[Candidate]]],
    version: int,
    digest: str,
) -> str:
    day = datetime.now(UTC).date().isoformat()
    by_id = {i.id: i for i in items}
    lines: list[str] = [
        f"# {project.title}",
        "",
        f"Build pack version {version}, written {day}, inputs {digest}. The items are as recorded",
        "on that day; a change to any of them, to the project or to the budget marks this pack",
        "stale, and a new one is written from what stands then.",
        "",
        "## Goal",
        "",
        project.result,
        "",
        f"Effort: {project.effort}. Skills: {', '.join(project.skills) or 'none in particular'}.",
        "",
        "## From the inventory",
        "",
    ]
    if not project.allocations:
        lines.append("No item is on this project.")
    for a in project.allocations:
        item = by_id.get(a.item_id)
        state = "committed" if a.committed else "exploratory"
        lines.append(
            f"- **{a.item_name}** as {a.requirement.replace('_', ' ')} ({state}). {a.why}".rstrip()
        )
        if item is None:
            continue
        if item.condition:
            lines.append(f"  - condition: {item.condition}")
        if item.faults:
            lines.append(f"  - faults: {item.faults}")
        if item.tests_done:
            lines.append(f"  - tested: {item.tests_done}")
        if item.accessories:
            lines.append(f"  - with: {item.accessories}")
        for key, value in shown_fields(item):
            lines.append(f"  - {key}: {value}")
    lines += ["", "## Still needed", ""]
    open_reqs = [r for r in project.requirements if r.state != "pass"]
    if not open_reqs:
        lines.append("Nothing: every requirement is filled from the inventory.")
    for r in open_reqs:
        need = "blocks the build" if r.blocking else "optional"
        line = f"- {r.label} ({need})"
        if r.search_id is not None and r.search_id in searches:
            search, candidates = searches[r.search_id]
            documented = [c for c in candidates if c.state == "documented"]
            line += f". Search: {search.title}"
            if search.max_price is not None:
                line += f", top price {money(search.max_price)} {search.currency}"
            line += f"; {len(candidates)} candidate(s), {len(documented)} documented"
            for c in documented:
                seen = f" seen {c.observed_on}" if c.observed_on else ""
                price = f", {c.asking_price} {c.currency}" if c.asking_price else ""
                line += f"\n  - {c.title or 'listing'}{price}{seen}"
        lines.append(line)
    lines += [
        "",
        "## Costs",
        "",
        f"Expected spending for this project: {money(project.spend_estimate)}"
        f" {project.currency}, as estimated on {project.created_at[:10]}.",
    ]
    if budget.budget is not None:
        lines.append(
            f"Across the selected projects: {money(budget.committed_spend)} of"
            f" {money(budget.budget)} {budget.currency}, {money(budget.remaining or 0)} left."
        )
    if prefs.tools:
        lines += ["", "## Tools", "", prefs.tools]
    lines += ["", "## Steps", ""]
    if not project.steps:
        lines.append("No steps are written for this template.")
    for n, step in enumerate(project.steps, 1):
        tick = "x" if n - 1 < len(project.progress) and project.progress[n - 1] else " "
        lines.append(f"{n}. [{tick}] {step}")
    if project.safety:
        lines += ["", "## Safety", ""] + [f"- {s}" for s in project.safety]
    lines += ["", "## Check before starting", ""]
    if not project.unknowns:
        lines.append("Nothing recorded as unknown.")
    lines += [f"- {u}" for u in project.unknowns]
    if project.sources:
        lines += ["", "## Guidance", ""] + [f"- {s}" for s in project.sources]
    lines += [
        "",
        "## Limitations",
        "",
        "- A dimension that matches is not a compatibility claim on its own; the seat, the latch"
        " and the power side count too.",
        "- A documented candidate is a listing that reads as fitting, not a part in hand.",
        "- Values marked exploratory are not reserved for this build.",
        "- Nothing here was checked by a person unless the outcome record says so.",
        "",
    ]
    if project.outcome is not None:
        o = project.outcome
        lines += [
            "## Outcome",
            "",
            f"Tested {o.tested_on}: {'working' if o.working else 'not working'}.",
            "",
            f"Configuration: {o.configuration}",
            "",
            f"Test: {o.test}",
            "",
            f"Limitations: {o.limitations or 'none recorded'}",
            "",
        ]
    return "\n".join(lines)


def without_names(text: str, items: list[Item]) -> str:
    """The item's kind where its name was: the title and the result were written from the
    names, and the names are the owner's."""
    for item in sorted(items, key=lambda i: -len(i.name)):
        if len(item.name) < 3:
            continue
        text = re.sub(re.escape(item.name), item.item_type or "an item", text, flags=re.I)
    return text


def share_text(project: Project, items: list[Item]) -> str:
    """The outcome for other people: what was built, from what kinds of things, how it was
    tested and what it cannot do. No item names, ids, values, places or prices."""
    if project.outcome is None:
        raise ValueError("no outcome recorded")
    kinds = sorted({(i.item_type or "item").lower() for i in items})
    o = project.outcome
    lines = [
        without_names(project.title, items),
        "",
        f"Built from: {', '.join(kinds) or 'items on hand'}.",
        f"Result: {without_names(project.result, items)}",
        f"Set up: {o.configuration}",
        f"Tested {o.tested_on}: {o.test} ({'working' if o.working else 'not working'})",
    ]
    if o.limitations:
        lines.append(f"Limits: {o.limitations}")
    return "\n".join(lines)
