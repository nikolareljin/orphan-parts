"""Command line: python -m app.textparams.tune [options]

The recommendations of the demo set (each item's Decide cards, its ideas, each project's
allocations) checked against the items' facts, one Muse Spark call each, and the text
parameters (backend/app/textparams/params.yaml) tuned from what the checks flag.

  (no option)          load the demo set in fixture mode into a folder of its own and check
                       every recommendation (report.json, report.md in --out); nothing changed
  --dry-run            list what would be checked; no call, no key
  --tune               propose edits to the text parameters from the last check (tune.md,
                       tune.json): fixed rules, and one Muse Spark call to phrase the
                       corrections (none with --dry-run)
  --tune --apply       write the proposal into the parameters, version one up
  --rerecord           record the demo set again with the parameters as they are: only the
                       Decide cards, the ideas, the proposals and the drawings whose request
                       changed are bought (every other answer must replay), then check every
                       recommendation again
  --evaluate           keep what the last check scored for this version
                       (eval/decide/text-v<N>.json), write the history into --results, and list
                       the recordings the version before used and this one does not
  --prune              with --evaluate: delete those recordings
  --keep N             keep version N, a better one than the last tried: the parameters written
                       back from eval/decide/text-v<N>.json, and the recordings the latest
                       evaluated version used and N does not deleted (both must be evaluated)
  --max-usd N          stop before a call that could take the run past N USD (default 1.00)
  --only KIND,...      check only these: cards, ideas, project, or ids (project:3); a check
                       of some only is never kept as a version's score
  --set FILE           the set (default demo/set.yaml); --out DIR (default picture-review/decide)
  --eval-dir DIR       where the evaluations are kept (default eval/decide)
  --results FILE       the page the history table is written into, between its markers

The key is MODEL_API_KEY from the environment, never printed or written.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.model_api import (
    CostLedger,
    ModelApiClient,
    ModelApiError,
    NoRecordingError,
    text_part,
    user_message,
)
from app.model_api.client import IMAGES
from app.model_api.fixtures import FixtureStore, request_key
from app.picture import review as rv
from app.textparams import (
    LINE_MAX,
    LINES_MAX,
    TEXT_PARAMS_FILE,
    Section,
    TextParams,
    dump,
    load,
)

OP = "decide-tune"
TUNE_OUTPUT_TOKENS = 2000
TUNE_INPUT_ALLOWANCE = 12000
DEFAULT_MAX_USD = 1.0
# what a re-record keeps for the checks after it (about 60 at about 0.008 USD); the checks
# themselves still stop at --max-usd
CHECK_RESERVE_USD = 0.75
# which recommendations each section writes: the id's head as decide_all names it
SECTION_OF: dict[str, Section] = {"cards": "scenarios", "ideas": "uses", "project": "propose"}
# the ops a re-record may buy: the text the parameters change and the drawings made from it
# (a proposal changed changes what a selected project still needs, so its search plans)
TEXT_OPS = frozenset({"scenarios", "uses", "propose", "search-plan"})
# a flag on these says a part does not fit: the brief should lead with the compatibility facts
COMPAT = re.compile(
    r"\b(ddr\d?l?|so-?dimm|dimm|socket|lga\d*|am\d|slot ?1|form factor|m\.2|u\.2|sata|nvme"
    r"|generation|processor|cpu|fits?|incompatible)\b",
    re.I,
)
# a flag on these says a card rests on something the owner does not have
OWNED = re.compile(r"\b(you own|owned|owner has no|no [\w -]+ (is )?owned|not owned|lacks)\b", re.I)
OWN_CONSTRAINT = (
    "A card or a use rests only on items the person owns that fit it; when none fits, it lists"
    " the missing part under extra parts with its cost and never calls it one the person owns"
)
CONDITION_CONSTRAINT = (
    "Read the condition first: a part recorded as missing, bare or unpopulated is not working"
    " as it is, and a use of it says what must be added"
)
CONDITION = re.compile(r"\b(missing|bare|unpopulated|condition|broken|no components)\b", re.I)

TUNE_INSTRUCTIONS = """\
You improve the instructions a home-inventory app gives a text model that writes \
recommendations for used items (Decide cards: keep and fix, reuse, sell; ideas: what an item \
is good for; proposals: which owned items fill a project). A reviewer flagged claims that \
contradict the items' facts. For each section given, write at most four corrections: general \
rules, each one sentence of at most 250 characters, that would have prevented the flagged \
mistakes for any inventory (never name a brand, a model, a person or one specific item; \
name kinds of part and kinds of fact: memory generation, socket, connector, a missing \
processor). Then at most four banned phrases: short phrases the flagged answers used that \
assert something the facts deny (such as "with the processor you own" when no owned \
processor fits). Keep what the current lines already say; do not repeat them."""


class Sentences(BaseModel):
    section: Section
    corrections: list[str]
    banned: list[str]


class Phrased(BaseModel):
    """Strict output of the phrasing call."""

    sections: list[Sentences]


class Edit(BaseModel):
    section: Section
    field: Literal["facts_first", "constraints", "corrections", "banned"]
    value: bool | list[str]
    why: str


class Proposal(BaseModel):
    at: str
    from_version: int
    to_version: int
    report_at: str
    edits: list[Edit]
    model: str = ""
    cost_usd: float = 0.0


class Report(BaseModel):
    at: str
    source: str
    mode: str
    model: str = ""
    params_version: int = 0
    decide: list[rv.DecideReview] = []
    skipped: list[str] = []
    load: list[str] = []
    cost_usd: float = 0.0
    used: dict[str, list[str]] = Field(
        default={}, description="the recordings the set's replay answered from, by endpoint"
    )
    only: list[str] = Field(default=[], description="the kinds of check run, when not all")


class Scored(BaseModel):
    id: str
    section: str
    flags: int
    major: int
    claims: list[str] = []


class Evaluation(BaseModel):
    params_version: int
    at: str
    report_at: str
    reviewer: str
    checked: int
    flagged: int
    flags: int
    major: int
    by_section: dict[str, dict[str, int]]
    review_usd: float
    scored: list[Scored]
    used: dict[str, list[str]]
    params: dict[str, Any]


# --- the replay, with the recordings it used ---------------------------------------------------


class UsedStore(FixtureStore):
    """A fixture store that remembers every recording it answered from by its exact key."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.used: dict[str, set[str]] = {}

    def find(self, endpoint: str, body: dict[str, Any], op: str):  # type: ignore[no-untyped-def]
        found = super().find(endpoint, body, op)
        key = request_key(endpoint, body)
        if found is not None and found.key == key:
            self.used.setdefault(endpoint.strip("/").replace("/", "-"), set()).add(key)
        return found


Used = dict[str, list[str]]


async def replay(
    settings: Settings, set_file: Path, work: Path
) -> tuple[rv.Services, list[str], Used]:
    """The set loaded in fixture mode into ``work``, with the recordings it answered from."""
    fixture = rv._scratch(settings, work, fake_api=True, record_fixtures=False)
    store = UsedStore(settings.fixtures_dir)
    # a replay spends nothing; the cap only keeps the ledger from warning on each answer
    client = ModelApiClient(fixture, CostLedger(1.0), store)
    sv, notes = await rv.load_set(fixture, set_file, client)
    return sv, notes, {k: sorted(v) for k, v in sorted(store.used.items())}


def text_op(op: str) -> bool:
    """An op the text parameters change: one of ``TEXT_OPS``, or a step of its tool loop
    (``propose-2``)."""
    head, _, step = op.rpartition("-")
    return op in TEXT_OPS or (head in TEXT_OPS and step.isdigit())


class TextOnlyClient(ModelApiClient):
    """Record mode for the text the parameters change and the drawings made from it: any other
    request answers only from its recording."""

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        op: str,
        files: dict[str, Any] | None = None,
        key: dict[str, Any] | None = None,
        attempts: int | None = None,
    ) -> tuple[dict[str, Any], bool, int, float]:
        if endpoint != IMAGES and not text_op(op):
            keyed = body if key is None else key
            kept = self.fixtures.find(endpoint, keyed, op)
            if kept is None or kept.key != request_key(endpoint, keyed) or kept.status >= 400:
                raise NoRecordingError(endpoint, request_key(endpoint, keyed), op)
        return await super()._post(endpoint, body, op, files=files, key=key, attempts=attempts)


# --- checks --------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def section_of(check_id: str) -> str:
    return SECTION_OF.get(check_id.split(":", 1)[0], "")


async def check(settings: Settings, sv: rv.Services, report: Report, max_usd: float) -> None:
    budget = rv.Budget(max_usd)
    work = Path(tempfile.mkdtemp(prefix="decide-check-"))
    client = rv.reviewer(rv._scratch(settings, work), max_usd)
    try:
        report.decide = await rv.decide_all(client, sv, budget, report.skipped, report.only)
    finally:
        await client.aclose()
        shutil.rmtree(work, ignore_errors=True)
    report.cost_usd = round(report.cost_usd + budget.spent, 6)


@dataclass
class Options:
    set_file: Path
    out: Path
    max_usd: float = DEFAULT_MAX_USD
    dry_run: bool = False
    tune: bool = False
    apply: bool = False
    rerecord: bool = False
    evaluate: bool = False
    prune: bool = False
    eval_dir: Path | None = None
    results: Path | None = None
    keep: int = 0
    only: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


async def run_review(settings: Settings, opts: Options) -> Report:
    work = Path(tempfile.mkdtemp(prefix="decide-review-"))
    try:
        sv, notes, used = await replay(settings, opts.set_file, work / "data")
        report = Report(
            at=_now(),
            source=str(opts.set_file),
            mode="demo set",
            model=settings.model_spark,
            params_version=load().version,
            load=notes,
            used=used,
            only=opts.only,
        )
        if opts.dry_run:
            report.mode += ", dry run"
            report.model = ""
            return report
        await check(settings, sv, report, opts.max_usd)
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def run_rerecord(settings: Settings, opts: Options) -> Report:
    """One record run in which only the text the parameters change, and the drawings made from
    it, are bought; the set replayed; every recommendation checked."""
    params = load()
    work = Path(tempfile.mkdtemp(prefix="decide-rerecord-"))
    try:
        record = rv._scratch(
            settings, work / "record", fake_api=False, record_fixtures=True, picture_enabled=True
        )
        # the record run takes what the checks leave: about sixty of them at about a cent each
        cap = max(opts.max_usd - CHECK_RESERVE_USD, 0.0)
        client = TextOnlyClient(record, CostLedger(cap))
        _, notes = await rv.load_set(record, opts.set_file, client)
        spent = client.ledger.total_usd
        sv, after, used = await replay(settings, opts.set_file, work / "after")
        report = Report(
            at=_now(),
            source=str(opts.set_file),
            mode=f"demo set, recorded with text parameters version {params.version}",
            model=settings.model_spark,
            params_version=params.version,
            load=[f"record run: {n}" for n in notes] + [f"replay: {n}" for n in after],
            used=used,
            cost_usd=spent,
            only=opts.only,
        )
        await check(settings, sv, report, max(opts.max_usd - spent, 0.0))
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- the report ----------------------------------------------------------------------------


def markdown(report: Report) -> str:
    flagged = [d for d in report.decide if d.flags]
    lines = [
        "# Recommendation check",
        "",
        f"{report.at}, {report.source} ({report.mode}); checked by {report.model or '-'};"
        f" text parameters version {report.params_version}.",
        "",
        f"{len(report.decide)} checked, {len(flagged)} with flags,"
        f" {sum(len(d.flags) for d in report.decide)} flag(s). Spent {report.cost_usd:.4f} USD.",
        "",
    ]
    for d in flagged:
        lines += [f"## `{d.id}` {d.title}", ""]
        lines += [f"- **{f.severity}** {f.where}: {f.claim} (but {f.fact})" for f in d.flags]
        lines.append("")
    errors = [d for d in report.decide if d.error]
    lines += [f"- `{d.id}`: {d.error}" for d in errors]
    if report.load or report.skipped:
        lines += ["## Notes", ""] + [f"- {s}" for s in report.load + report.skipped]
    return "\n".join(lines).rstrip() + "\n"


def write(report: Report, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    md, js = out / "report.md", out / "report.json"
    md.write_text(markdown(report), encoding="utf-8")
    js.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return [md, js]


def last_report(out: Path) -> Report:
    path = out / "report.json"
    if not path.is_file():
        raise ValueError(f"no check at {path}: run ./dev decide-review first")
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    if "dry run" in report.mode or not report.decide:
        raise ValueError(f"{path} checks nothing: run ./dev decide-review first")
    return report


# --- tuning ---------------------------------------------------------------------------------


def flags_by_section(report: Report) -> dict[str, list[rv.Flag]]:
    out: dict[str, list[rv.Flag]] = {}
    for d in report.decide:
        sec = section_of(d.id)
        if sec:
            out.setdefault(sec, []).extend(d.flags)
    return out


def rule_edits(report: Report, params: TextParams) -> list[Edit]:
    """What the rules propose without a call: the compatibility facts first where a flag says a
    part does not fit, the owned-items rule where a card rests on what the owner lacks, the
    condition rule where a card ignores a recorded state."""
    edits: list[Edit] = []
    for sec, flags in flags_by_section(report).items():
        section = params.section(sec)  # type: ignore[arg-type]
        said = " ".join(f"{f.claim} {f.fact}" for f in flags)
        fit = [f for f in flags if COMPAT.search(f"{f.claim} {f.fact}")]
        if fit and not section.facts_first:
            edits.append(
                Edit(
                    section=sec,
                    field="facts_first",
                    value=True,
                    why=f"{len(fit)} flag(s) on a part that does not fit",
                )
            )
        lines: list[str] = []
        if OWNED.search(said) and OWN_CONSTRAINT not in section.constraints and sec != "propose":
            lines.append(OWN_CONSTRAINT)
        if CONDITION.search(said) and CONDITION_CONSTRAINT not in section.constraints:
            lines.append(CONDITION_CONSTRAINT)
        if lines:
            edits.append(
                Edit(
                    section=sec,
                    field="constraints",
                    value=lines,
                    why="flags on what the owner lacks or on a recorded condition",
                )
            )
    return edits


def phrase_input(report: Report, params: TextParams) -> str:
    lines: list[str] = []
    for sec, flags in flags_by_section(report).items():
        if not flags:
            continue
        section = params.section(sec)  # type: ignore[arg-type]
        current = section.constraints + section.corrections
        lines += [
            f"Section: {sec}",
            "Current lines: " + (" | ".join(current) or "-"),
            "Banned already: " + (" | ".join(section.banned) or "-"),
            "Flags:",
            *[f"- {f.severity}: claim {f.claim} / fact {f.fact}" for f in flags[:24]],
            "",
        ]
    return "\n".join(lines).strip()


async def phrase(client: ModelApiClient, model: str, text: str) -> tuple[Phrased | None, float]:
    if not text:
        return None, 0.0
    try:
        result = await client.respond_structured(
            Phrased,
            model=model,
            input=[user_message(text_part(text))],
            instructions=TUNE_INSTRUCTIONS,
            effort="low",
            max_output_tokens=TUNE_OUTPUT_TOKENS,
            op=OP,
        )
    except (ModelApiError, ValueError) as exc:
        print(f"decide-review: the phrasing call failed: {exc}", file=sys.stderr)
        return None, 0.0
    return result.parsed, result.response.cost_usd


def _short(values: list[str], limit: int) -> list[str]:
    out = []
    for v in values:
        line = " ".join(v.split())
        if 3 <= len(line) <= limit:
            out.append(line)
    return out


def phrased_edits(phrased: Phrased | None, report: Report) -> list[Edit]:
    if phrased is None:
        return []
    flagged = flags_by_section(report)
    edits: list[Edit] = []
    for s in phrased.sections:
        if not flagged.get(s.section):
            continue
        n = len(flagged[s.section])
        corrections = _short(s.corrections, 250)[:4]
        banned = _short(s.banned, 60)[:4]
        if corrections:
            edits.append(
                Edit(
                    section=s.section,
                    field="corrections",
                    value=corrections,
                    why=f"phrased from {n} flag(s)",
                )
            )
        if banned:
            edits.append(
                Edit(section=s.section, field="banned", value=banned, why=f"used in {n} flag(s)")
            )
    return edits


def apply_edits(params: TextParams, edits: list[Edit], version: int = 0) -> TextParams:
    data = params.model_dump(mode="json")
    for e in edits:
        sec = data[e.section]
        if e.field == "facts_first":
            sec["facts_first"] = bool(e.value)
            continue
        have = list(sec[e.field])
        for line in e.value if isinstance(e.value, list) else []:
            line = " ".join(str(line).split())[:LINE_MAX]
            if line and line not in have:
                have.append(line)
        sec[e.field] = have[-LINES_MAX:]
    data["version"] = max(version, params.version + 1)
    return TextParams.model_validate(data)


def next_version(params: TextParams, folder: Path) -> int:
    """One above the file and above every version evaluated: a version tried and not kept
    (``--keep``) keeps its number and its evaluation."""
    tried = [e.params_version for e in history(folder)] if folder.is_dir() else []
    return max([params.version, *tried]) + 1


def proposal_markdown(p: Proposal) -> str:
    lines = [
        f"# Text parameters: version {p.from_version} to {p.to_version}",
        "",
        f"From the check of {p.report_at}; {len(p.edits)} edit(s);"
        f" phrased by {p.model or 'no call'} for {p.cost_usd:.4f} USD.",
        "",
        "| section | field | value | why |",
        "|---|---|---|---|",
    ]
    for e in p.edits:
        value = e.value if isinstance(e.value, bool) else " / ".join(e.value)
        lines.append(f"| {e.section} | {e.field} | {rv._cell(str(value))} | {rv._cell(e.why)} |")
    return "\n".join(lines) + "\n"


async def run_tune(settings: Settings, opts: Options) -> Proposal:
    report = last_report(opts.out)
    params = load()
    if report.params_version and report.params_version != params.version:
        raise ValueError(
            f"the last check is of text parameters version {report.params_version}, the file is"
            f" at {params.version}: run ./dev decide-review --rerecord first"
        )
    edits = rule_edits(report, params)
    phrased, usd = None, 0.0
    text = phrase_input(report, params)
    if settings.model_api_mode != "fixture" and not opts.dry_run and text:
        ceiling = rv.ceiling_usd(settings.model_spark, TUNE_INPUT_ALLOWANCE, TUNE_OUTPUT_TOKENS)
        if ceiling > opts.max_usd:
            raise ValueError(f"the phrasing call could cost {ceiling:.4f} USD, over --max-usd")
        work = Path(tempfile.mkdtemp(prefix="decide-tune-"))
        client = rv.reviewer(rv._scratch(settings, work), opts.max_usd)
        try:
            phrased, usd = await phrase(client, settings.model_spark, text)
        finally:
            await client.aclose()
            shutil.rmtree(work, ignore_errors=True)
    edits += phrased_edits(phrased, report)
    proposal = Proposal(
        at=_now(),
        from_version=params.version,
        to_version=next_version(params, opts.eval_dir or rv._repo_root() / "eval" / "decide"),
        report_at=report.at,
        edits=edits,
        model=settings.model_spark if phrased else "",
        cost_usd=usd,
    )
    opts.out.mkdir(parents=True, exist_ok=True)
    (opts.out / "tune.json").write_text(proposal.model_dump_json(indent=2) + "\n", "utf-8")
    (opts.out / "tune.md").write_text(proposal_markdown(proposal), encoding="utf-8")
    return proposal


def apply_proposal(path: Path, params_file: Path | None = None) -> TextParams:
    proposal = Proposal.model_validate_json(path.read_text(encoding="utf-8"))
    params = load(params_file)
    if proposal.from_version != params.version:
        raise ValueError(
            f"the proposal is for version {proposal.from_version}, the file is at {params.version}"
        )
    new = apply_edits(params, proposal.edits, proposal.to_version)
    dump(new, params_file)
    return new


# --- evaluation -----------------------------------------------------------------------------


START = "<!-- text-history:start -->"
END = "<!-- text-history:end -->"


def evaluation(report: Report, params: TextParams) -> Evaluation:
    by_section: dict[str, dict[str, int]] = {}
    scored: list[Scored] = []
    for d in report.decide:
        sec = section_of(d.id) or "other"
        s = by_section.setdefault(sec, {"checked": 0, "flagged": 0, "flags": 0})
        s["checked"] += 1
        s["flagged"] += 1 if d.flags else 0
        s["flags"] += len(d.flags)
        scored.append(
            Scored(
                id=d.id,
                section=sec,
                flags=len(d.flags),
                major=sum(1 for f in d.flags if f.severity == "major"),
                claims=[" ".join(f.claim.split())[:160] for f in d.flags],
            )
        )
    return Evaluation(
        params_version=params.version,
        at=_now(),
        report_at=report.at,
        reviewer=report.model,
        checked=len(report.decide),
        flagged=sum(1 for d in report.decide if d.flags),
        flags=sum(len(d.flags) for d in report.decide),
        major=sum(1 for d in report.decide for f in d.flags if f.severity == "major"),
        by_section=by_section,
        review_usd=round(report.cost_usd, 4),
        scored=scored,
        used=report.used,
        params=params.model_dump(mode="json"),
    )


def eval_path(folder: Path, version: int) -> Path:
    return folder / f"text-v{version}.json"


def history(folder: Path) -> list[Evaluation]:
    found = [
        Evaluation.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("text-v*.json"))
    ]
    return sorted(found, key=lambda e: e.params_version)


def table(evals: list[Evaluation]) -> str:
    head = "| | " + " | ".join(f"text v{e.params_version}" for e in evals) + " |"
    lines = [head, "|---|" + "---|" * len(evals)]
    lines.append("| checked | " + " | ".join(str(e.checked) for e in evals) + " |")
    lines.append("| with flags | " + " | ".join(str(e.flagged) for e in evals) + " |")
    lines.append("| flags | " + " | ".join(str(e.flags) for e in evals) + " |")
    lines.append("| major | " + " | ".join(str(e.major) for e in evals) + " |")
    for sec in ("cards", "ideas", "projects"):
        key = {"cards": "scenarios", "ideas": "uses", "projects": "propose"}[sec]
        counts = [e.by_section.get(key, {}) for e in evals]
        row = " | ".join(f"{c.get('flagged', 0)}/{c.get('checked', 0)}" for c in counts)
        lines.append(f"| {sec} with flags | {row} |")
    lines.append(
        "| spent on the run, USD | " + " | ".join(f"{e.review_usd:.2f}" for e in evals) + " |"
    )
    return "\n".join(lines)


def write_history(page: Path, evals: list[Evaluation]) -> bool:
    if not page.is_file():
        return False
    text = page.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    block = "\n".join(
        [
            START,
            "",
            "*Written by `./dev decide-review --evaluate` from `eval/decide/`.*",
            "",
            table(evals),
            "",
            END,
        ]
    )
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    page.write_text(head + block + tail, encoding="utf-8")
    return True


def unused(old: Evaluation, new: Evaluation) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for endpoint, keys in old.used.items():
        now = set(new.used.get(endpoint, []))
        gone = sorted(k for k in keys if k not in now)
        if gone:
            out[endpoint] = gone
    return out


def prune(fixtures: Path, gone: dict[str, list[str]]) -> list[Path]:
    removed: list[Path] = []
    for endpoint, keys in gone.items():
        folder = fixtures / endpoint
        for key in keys:
            if not re.fullmatch(r"[0-9a-f]{24}", key):
                continue
            for path in [folder / f"{key}.json", *sorted(folder.glob(f"{key}-*"))]:
                if path.is_file():
                    path.unlink()
                    removed.append(path)
    return removed


def run_keep(settings: Settings, opts: Options) -> tuple[TextParams, list[Path]]:
    """Version ``opts.keep`` back in the file (its own number), and the recordings only the
    versions tried after it used deleted."""
    folder = opts.eval_dir or rv._repo_root() / "eval" / "decide"
    evals = {e.params_version: e for e in history(folder)}
    kept = evals.get(opts.keep)
    if kept is None:
        raise ValueError(f"no evaluation of text parameters version {opts.keep} in {folder}")
    latest = evals[max(evals)]
    if latest.params_version == opts.keep:
        raise ValueError(f"version {opts.keep} is the latest evaluated; nothing to undo")
    params = TextParams.model_validate(kept.params)
    gone: dict[str, list[str]] = {}
    for e in evals.values():
        if e.params_version > opts.keep:
            for endpoint, keys in unused(e, kept).items():
                gone[endpoint] = sorted(set(gone.get(endpoint, [])) | set(keys))
    removed = prune(settings.fixtures_dir, gone)
    dump(params)
    return params, removed


def run_evaluate(settings: Settings, opts: Options) -> tuple[Evaluation, list[str]]:
    report = last_report(opts.out)
    if report.only:
        raise ValueError(
            f"the last check ran {', '.join(report.only)} only; a version is scored on every"
            " check: run ./dev decide-review without --only"
        )
    params = load()
    if report.params_version and report.params_version != params.version:
        raise ValueError(
            f"the last check is of text parameters version {report.params_version}, the file is"
            f" at {params.version}: run ./dev decide-review --rerecord first"
        )
    folder = opts.eval_dir or rv._repo_root() / "eval" / "decide"
    folder.mkdir(parents=True, exist_ok=True)
    ev = evaluation(report, params)
    eval_path(folder, params.version).write_text(ev.model_dump_json(indent=2) + "\n", "utf-8")
    evals = history(folder)
    notes: list[str] = []
    earlier = [e for e in evals if e.params_version < params.version]
    if earlier:
        gone = unused(earlier[-1], ev)
        count = sum(len(v) for v in gone.values())
        if gone and opts.prune:
            removed = prune(settings.fixtures_dir, gone)
            notes.append(f"removed {len(removed)} file(s) of {count} unused recording(s)")
        elif gone:
            notes.append(
                f"{count} recording(s) of text v{earlier[-1].params_version} unused now"
                " (--prune deletes them)"
            )
    if opts.results is not None:
        if write_history(opts.results, evals):
            notes.append(f"wrote the history into {opts.results}")
        else:
            notes.append(f"{opts.results} has no text-history markers; nothing written there")
    return ev, notes


# --- command line --------------------------------------------------------------------------


def parse(argv: list[str]) -> Options | str:
    opts = Options(set_file=rv.default_set(), out=rv.default_out() / "decide")
    args = list(argv)
    while args:
        arg = args.pop(0)
        if (
            arg in ("--set", "--out", "--max-usd", "--eval-dir", "--results", "--keep", "--only")
            and not args
        ):
            return f"{arg} needs a value"
        if arg == "--set":
            opts.set_file = Path(args.pop(0))
        elif arg == "--out":
            opts.out = Path(args.pop(0))
        elif arg == "--eval-dir":
            opts.eval_dir = Path(args.pop(0))
        elif arg == "--results":
            opts.results = Path(args.pop(0))
        elif arg == "--max-usd":
            try:
                opts.max_usd = float(args.pop(0))
            except ValueError:
                return "--max-usd needs a number"
            if opts.max_usd < 0:
                return "--max-usd must not be negative"
        elif arg == "--only":
            opts.only = [v.strip() for v in args.pop(0).split(",") if v.strip()]
            if any(v.split(":", 1)[0] not in SECTION_OF for v in opts.only):
                return "--only takes cards, ideas, project or their ids (project:3)"
        elif arg == "--keep":
            try:
                opts.keep = int(args.pop(0))
            except ValueError:
                return "--keep needs a version number"
        elif arg == "--dry-run":
            opts.dry_run = True
        elif arg == "--tune":
            opts.tune = True
        elif arg == "--apply":
            opts.apply = True
        elif arg == "--rerecord":
            opts.rerecord = True
        elif arg == "--evaluate":
            opts.evaluate = True
        elif arg == "--prune":
            opts.prune = True
        elif arg in ("-h", "--help"):
            return "help"
        else:
            shown = arg.split("=", 1)[0] if arg.startswith("-") else "(a value)"
            return f"unknown argument {shown[:40]}"
    if sum([opts.tune, opts.rerecord, opts.evaluate, bool(opts.keep)]) > 1:
        return "--tune, --rerecord, --evaluate and --keep go one at a time"
    if opts.apply and not opts.tune:
        return "--apply goes with --tune"
    if opts.prune and not opts.evaluate:
        return "--prune goes with --evaluate"
    if opts.rerecord and opts.dry_run:
        return "--rerecord records; it has no dry run"
    return opts


def main(argv: list[str] | None = None) -> int:
    parsed = parse(list(sys.argv[1:] if argv is None else argv))
    if parsed == "help":
        print(__doc__)
        return 0
    if isinstance(parsed, str):
        print(f"decide-review: {parsed}", file=sys.stderr)
        return 2
    opts = parsed
    try:
        settings = get_settings()
    except ValueError as exc:
        if not (opts.dry_run or opts.evaluate or (opts.tune and opts.apply)):
            print(f"decide-review: the settings are refused: {rv.refused(exc)}", file=sys.stderr)
            return 1
        try:
            settings = Settings(OPL_FAKE_API=True)
        except ValueError as again:
            # a validation error prints its input; the reasons alone
            print(f"decide-review: the settings are refused: {rv.refused(again)}", file=sys.stderr)
            return 1
    if not opts.set_file.is_file():
        print(f"decide-review: no set at {opts.set_file}", file=sys.stderr)
        return 1
    try:
        if opts.tune and opts.apply:
            new = apply_proposal(opts.out / "tune.json")
            print(f"wrote {TEXT_PARAMS_FILE.name}: version {new.version}")
            print("next: ./dev decide-review --rerecord, then --evaluate")
            return 0
        if opts.keep:
            kept, removed = run_keep(settings, opts)
            print(f"wrote {TEXT_PARAMS_FILE.name}: version {kept.version} kept")
            print(f"removed {len(removed)} file(s) of the recordings only later versions used")
            return 0
        if opts.evaluate:
            ev, notes = run_evaluate(settings, opts)
            print(
                f"text parameters version {ev.params_version}: {ev.checked} checked,"
                f" {ev.flagged} with flags, {ev.flags} flag(s), {ev.major} major"
            )
            for line in notes:
                print(line)
            return 0
        if opts.tune:
            proposal = asyncio.run(run_tune(settings, opts))
            print(
                f"{len(proposal.edits)} edit(s) proposed, version {proposal.from_version} to"
                f" {proposal.to_version}; {proposal.cost_usd:.4f} USD"
            )
            print(f"wrote {opts.out / 'tune.md'} and {opts.out / 'tune.json'}")
            return 0
        if opts.rerecord:
            if settings.model_api_mode == "fixture":
                print(
                    "decide-review: --rerecord records; it needs MODEL_API_KEY and"
                    " OPL_FAKE_API off",
                    file=sys.stderr,
                )
                return 1
            report = asyncio.run(run_rerecord(settings, opts))
        else:
            report = asyncio.run(run_review(settings, opts))
    except (ValueError, KeyError, OSError) as exc:
        print(f"decide-review: {exc}", file=sys.stderr)
        return 1
    for line in report.load:
        print(line)
    for line in report.skipped:
        print(f"skipped: {line}")
    for path in write(report, opts.out):
        print(f"wrote {path}")
    flagged = sum(1 for d in report.decide if d.flags)
    print(
        f"{len(report.decide)} checked, {flagged} with flags,"
        f" {sum(len(d.flags) for d in report.decide)} flag(s); {report.cost_usd:.4f} USD"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
