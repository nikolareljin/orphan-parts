"""Score one load of the demo set. Nothing here calls a model: the loader has run, the
inventory holds what it read, and the rules say what was right."""

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field

from app.demo.schema import DemoItem, DemoSet, Outcome
from app.extract.fields import FIELD_BY_NAME
from app.extract.service import INSTRUCTIONS, prompt
from app.inventory import Inventory
from app.inventory.parent import PARENT_FIELDS
from app.inventory.schema import Item
from app.inventory.service import current_fields
from app.match import AssessError, Assessor, AssessRequest, Side
from app.match.rules import Reading as RuleReading
from app.match.rules import normal, number, unit_of
from app.projects import Planner

TOLERANCE_PCT = 5.0
FITS = ("EXACT_MATCH", "COMPATIBLE_LIKELY")


class FieldScore(BaseModel):
    field: str
    expected: str
    actual: str = Field(default="", description="the accepted value, with its unit")
    result: str = Field(description="match, mismatch or not_read")


class FitScore(BaseModel):
    against: str
    expected: str
    verdict: str = ""
    summary: str = ""
    right: bool | None = Field(default=None, description="None when the check could not run")


class ItemScore(BaseModel):
    key: str
    name: str
    item_id: int | None = None
    loaded: bool = False
    fields_read: int = Field(default=0, description="values observed from the photos")
    fields_accepted: int = 0
    owner_values: int = 0
    mean_confidence: float | None = None
    expected_fields: list[FieldScore] = []
    fit: FitScore | None = None
    proposals_min: int | None = None
    proposals_in: int = 0


class Summary(BaseModel):
    mode: str
    items: int
    items_loaded: int
    photos: int
    fields_read: int
    matches: int
    expected: int
    fits_right: int
    fits_total: int
    proposals_proposed: int
    proposals_kept: int
    proposals_dropped: int
    dropped_lines: int = Field(description="lines inside kept proposals the inventory did not back")
    stub_answers: int
    cost_usd: float
    skipped: list[str]


class Report(BaseModel):
    title: str
    set_file: str
    summary: Summary
    items: list[ItemScore]


def _shown(value: str, unit: str) -> str:
    return f"{value} {unit}".strip()


def _split(key: str, text: str) -> tuple[float | None, str, str]:
    """A number, a unit and the normalised text of one value, as the rules read them."""
    reading = RuleReading(value=text)
    return number(text), unit_of(reading).lower(), normal(key, text)


def compare(field: str, expected: str, actual: str) -> bool:
    """Numbers within TOLERANCE_PCT with the same unit when both name one; anything else by
    the field's own normaliser, lower case, one space."""
    n_exp, u_exp, t_exp = _split(field, expected)
    n_act, u_act, t_act = _split(field, actual)
    spec = FIELD_BY_NAME.get(field)
    numeric = spec is not None and spec.normalizer in ("volts", "amps", "watts")
    if (numeric or field not in FIELD_BY_NAME) and n_exp is not None and n_act is not None:
        if u_exp and u_act and u_exp != u_act:
            return False
        allowed = abs(n_exp) * TOLERANCE_PCT / 100.0
        return abs(n_act - n_exp) <= allowed
    return t_exp == t_act


def score_fields(item: Item, expected: dict[str, str]) -> list[FieldScore]:
    current = current_fields(item.assertions)
    out: list[FieldScore] = []
    for field, want in expected.items():
        have = current.get(field)
        if have is None or have.review != "accepted":
            out.append(FieldScore(field=field, expected=want, result="not_read"))
            continue
        actual = _shown(have.value, have.unit)
        result = "match" if compare(field, want, actual) else "mismatch"
        out.append(FieldScore(field=field, expected=want, actual=actual, result=result))
    return out


def score_fit(
    assessor: Assessor, item: DemoItem, ids: dict[str, int], values: dict[str, str]
) -> FitScore:
    assert item.expect is not None and item.expect.fit is not None
    fit = item.expect.fit
    out = FitScore(against=fit.against, expected=fit.verdict)
    need_id, cand_id = ids.get(fit.against), ids.get(item.key)
    if need_id is None or cand_id is None:
        out.summary = "one of the two items was not loaded"
        return out
    try:
        found = assessor.assess(
            AssessRequest(
                need=Side(item_id=need_id, values=values), candidate=Side(item_id=cand_id)
            )
        )
    except (AssessError, LookupError) as exc:
        out.summary = str(exc)
        return out
    out.verdict, out.summary = found.verdict, found.summary
    out.right = (found.verdict in FITS) if fit.verdict == "fits" else (found.verdict == "CONFLICT")
    return out


def score(
    demo: DemoSet,
    outcome: Outcome,
    inventory: Inventory,
    assessor: Assessor,
    planner: Planner,
    ids: dict[str, int],
    set_file: str = "",
) -> Report:
    """ids maps the set's item keys to the inventory ids the loader gave them."""
    projects = planner.projects().projects
    allocated: dict[int, int] = {}
    for p in projects:
        for a in p.allocations:
            allocated[a.item_id] = allocated.get(a.item_id, 0) + 1
    items: list[ItemScore] = []
    for spec in demo.items:
        row = ItemScore(key=spec.key, name=spec.name, item_id=ids.get(spec.key))
        if row.item_id is not None:
            item = inventory.get(row.item_id)
            row.loaded = True
            # the item's own values: what is known of the device a part came from is not scored
            own = [a for a in item.assertions if a.field not in PARENT_FIELDS]
            observed = [a for a in own if a.provenance == "observed"]
            row.fields_read = len(observed)
            row.fields_accepted = sum(1 for a in observed if a.review == "accepted")
            row.owner_values = sum(1 for a in own if a.provenance != "observed")
            if observed:
                row.mean_confidence = round(sum(a.confidence for a in observed) / len(observed), 3)
            row.proposals_in = allocated.get(row.item_id, 0)
            if spec.expect is not None:
                row.expected_fields = score_fields(item, spec.expect.fields)
                if spec.expect.fit is not None:
                    row.fit = score_fit(assessor, spec, ids, spec.expect.fit.values)
                row.proposals_min = spec.expect.proposals_min
        elif spec.expect is not None:
            row.expected_fields = [
                FieldScore(field=f, expected=v, result="not_read")
                for f, v in spec.expect.fields.items()
            ]
            if spec.expect.fit is not None:
                row.fit = FitScore(
                    against=spec.expect.fit.against,
                    expected=spec.expect.fit.verdict,
                    summary="the item was not loaded",
                )
            row.proposals_min = spec.expect.proposals_min
        items.append(row)
    expected = sum(len(i.expected_fields) for i in items)
    matches = sum(1 for i in items for f in i.expected_fields if f.result == "match")
    fits = [i.fit for i in items if i.fit is not None]
    summary = Summary(
        mode=outcome.mode,
        items=len(demo.items),
        items_loaded=outcome.items,
        photos=outcome.photos,
        fields_read=sum(i.fields_read for i in items),
        matches=matches,
        expected=expected,
        fits_right=sum(1 for f in fits if f.right),
        fits_total=len(fits),
        proposals_proposed=planner.last_proposed,
        proposals_kept=planner.last_kept,
        proposals_dropped=max(planner.last_proposed - planner.last_kept, 0),
        dropped_lines=sum(len(p.dropped) for p in projects),
        stub_answers=outcome.stub_answers,
        cost_usd=round(outcome.cost_usd, 6),
        skipped=list(outcome.skipped),
    )
    return Report(title=demo.title, set_file=set_file, summary=summary, items=items)


# --- the files -------------------------------------------------------------


def _fit_cell(fit: FitScore | None) -> str:
    if fit is None:
        return ""
    if fit.right is None:
        return f"not run ({fit.summary})"
    word = "right" if fit.right else "wrong"
    return f"{fit.verdict} vs {fit.against}, expected {fit.expected}: {word}"


def _proposals_cell(row: ItemScore) -> str:
    if row.proposals_min is None:
        return str(row.proposals_in) if row.proposals_in else ""
    word = "ok" if row.proposals_in >= row.proposals_min else "short"
    return f"{row.proposals_in} of at least {row.proposals_min}: {word}"


def markdown(report: Report) -> str:
    s = report.summary
    lines = [
        f"# Evaluation: {report.title}",
        "",
        f"Set `{report.set_file}`, mode `{s.mode}`.",
        "",
        "| | |",
        "|---|---|",
        f"| Items | {s.items_loaded} of {s.items} loaded, {s.photos} photo(s) read |",
        f"| Fields read | {s.fields_read} |",
        f"| Expected values matched | {s.matches} of {s.expected} |",
        f"| Fit verdicts right | {s.fits_right} of {s.fits_total} |",
        f"| Proposals | {s.proposals_proposed} written, {s.proposals_kept} kept,"
        f" {s.proposals_dropped} dropped; {s.dropped_lines} line(s) dropped inside kept ones |",
        f"| Stub answers | {s.stub_answers} |",
        f"| Spend | {s.cost_usd:.4f} USD |",
        "",
        "## Items",
        "",
        "| Item | Fields read | Accepted | Owner values | Mean confidence | Expected values |"
        " Fit | Proposals |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in report.items:
        if not row.loaded:
            lines.append(f"| {row.key} | not loaded | | | | | | |")
            continue
        conf = "" if row.mean_confidence is None else f"{row.mean_confidence:.2f}"
        exp = ", ".join(
            f"{f.field} {f.result}" + (f" ({f.actual!r})" if f.result == "mismatch" else "")
            for f in row.expected_fields
        )
        lines.append(
            f"| {row.key} | {row.fields_read} | {row.fields_accepted} | {row.owner_values} |"
            f" {conf} | {exp} | {_fit_cell(row.fit)} | {_proposals_cell(row)} |"
        )
    if s.skipped:
        lines += ["", "## Skipped", ""] + [f"- {x}" for x in s.skipped]
    if s.stub_answers:
        lines += [
            "",
            f"{s.stub_answers} answer(s) came from an operation's stub, not a recording of this"
            " set: the numbers above describe the stubs. Record the set first.",
        ]
    return "\n".join(lines) + "\n"


def charts(report: Report, folder: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    folder.mkdir(parents=True, exist_ok=True)
    blue, orange, aqua = "#2a78d6", "#eb6834", "#1baf7a"
    out: list[Path] = []

    keys = [i.key for i in report.items]
    read = [i.fields_read for i in report.items]
    matched = [sum(1 for f in i.expected_fields if f.result == "match") for i in report.items]
    fig, ax = plt.subplots(figsize=(9, 4))
    xs = range(len(keys))
    ax.bar([x - 0.2 for x in xs], read, 0.38, color=blue, label="fields read")
    ax.bar([x + 0.2 for x in xs], matched, 0.38, color=orange, label="expected values matched")
    ax.set_xticks(list(xs), keys, rotation=30, ha="right")
    ax.set_ylabel("count")
    ax.set_ylim(bottom=0, top=max([*read, *matched, 1]) * 1.15)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Fields per item")
    ax.legend(frameon=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = folder / "fields.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    out.append(path)

    s = report.summary
    fig, ax = plt.subplots(figsize=(5, 4))
    names = ["written", "kept", "dropped"]
    values = [s.proposals_proposed, s.proposals_kept, s.proposals_dropped]
    ax.bar(names, values, 0.6, color=[blue, aqua, orange])
    ax.set_ylabel("proposals")
    ax.set_ylim(bottom=0, top=max([*values, 1]) * 1.15)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Proposals: what the model wrote, what the rules kept")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = folder / "proposals.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    out.append(path)
    return out


def write_report(report: Report, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [out_dir / "report.json", out_dir / "report.md"]
    written[0].write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    written[1].write_text(markdown(report), encoding="utf-8")
    return written + charts(report, out_dir / "charts")


# --- the training export ---------------------------------------------------


def training_lines(inventory: Inventory, items: Iterable[Item] | None = None) -> list[str]:
    """One chat-format line per item with accepted observed values: the instruction the app
    sends, the photo reference and the fields asked, the accepted values as the answer."""
    rows = items if items is not None else [inventory.get(i.id) for i in inventory.list_items()]
    out: list[str] = []
    for item in rows:
        accepted = {
            k: {"value": a.value, "unit": a.unit}
            for k, a in current_fields(item.assertions).items()
            if a.provenance == "observed" and a.review == "accepted"
        }
        if not accepted:
            continue
        record = {
            "messages": [
                {"role": "system", "content": INSTRUCTIONS},
                {
                    "role": "user",
                    "content": f"[photos of item {item.id}: GET /api/items/{item.id}/photos]\n"
                    + prompt(),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"item_type": item.item_type, "fields": accepted}, ensure_ascii=False
                    ),
                },
            ],
            "item_id": item.id,
        }
        out.append(json.dumps(record, ensure_ascii=False))
    return out


# --- two reports side by side ----------------------------------------------

COMPARED = (
    "items_loaded",
    "fields_read",
    "matches",
    "fits_right",
    "proposals_kept",
    "proposals_dropped",
    "dropped_lines",
    "stub_answers",
    "cost_usd",
)


def diff(a: Report, b: Report) -> list[str]:
    lines = [f"{'':24} {'a':>10} {'b':>10} {'change':>10}"]
    for key in COMPARED:
        x, y = getattr(a.summary, key), getattr(b.summary, key)
        change = y - x
        shown = f"{change:+.4f}" if isinstance(change, float) else f"{change:+d}"
        lines.append(f"{key:24} {x:>10} {y:>10} {shown:>10}")
    by_key = {i.key: i for i in b.items}
    for row in a.items:
        other = by_key.get(row.key)
        if other is None:
            lines.append(f"{row.key}: only in a")
            continue
        before = {f.field: f.result for f in row.expected_fields}
        after = {f.field: f.result for f in other.expected_fields}
        for field in sorted(set(before) | set(after)):
            if before.get(field) != after.get(field):
                lines.append(
                    f"{row.key}.{field}: {before.get(field, '-')} -> {after.get(field, '-')}"
                )
        if (row.fit is None) != (other.fit is None) or (
            row.fit is not None and other.fit is not None and row.fit.right != other.fit.right
        ):
            lines.append(f"{row.key} fit: {_fit_cell(row.fit)} -> {_fit_cell(other.fit)}")
    for key in by_key:
        if key not in {i.key for i in a.items}:
            lines.append(f"{key}: only in b")
    return lines
