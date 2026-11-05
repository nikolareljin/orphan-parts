"""The tuning loop: the reviews of the drawings turned into changes to the drawing parameters,
and each version of the parameters measured on the demo set.

* ``aggregate``: the last review's verdicts and issues counted by category, by kind of drawing
  and by subject (the kind of project a drawing is of, or the kind of item), and the requests
  read for what makes drawings go wrong (a brand or a model number said, a condition said).
* ``propose``: edits to ``params.yaml`` from those counts, by fixed rules; the corrections and
  the looks of the kinds of part are phrased by one Muse Spark call from the reviews' own
  issues and briefs (without a key, the shortest proposed brief is kept as it is).
* ``apply``: the proposal written into the file, its ``version`` one up.
* ``evaluation`` / ``compare``: what a version scored on the set, kept as JSON under
  ``eval/pictures/``, and the versions side by side.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.model_api import ModelApiClient, ModelApiError, text_part, user_message
from app.model_api.client import IMAGES, picture_body
from app.model_api.fixtures import request_key
from app.picture.params import DrawingParams, dump, save
from app.picture.params import load as load_params

OP = "picture-tune"
TUNE_OUTPUT_TOKENS = 2500
TUNE_INPUT_ALLOWANCE = 12000
CORRECTION_MAX = 350
TEXT_LIMIT = 400
LOOKS_MAX = 160
# a category seen this often across the set is a rule of the whole set, not of one drawing
TEXT_MIN = 2
LETTERING_FIELDS = ["brand", "model", "part number", "certification", "manufacturer"]
NO_LETTERING = (
    "no lettering, logos, brand names, model numbers or labels on any part, case or screen"
)
# a size said for scale comes back written on the picture ("40 cm", "24\" 16:9")
NO_MEASURES = (
    "the sizes are for scale only: no dimension lines, measurements or size labels written"
    " in the picture"
)
MEASURED = re.compile(r"\d\s*(cm|mm|inch|in\b|\")|\d+:\d+|dimension|measurement", re.I)
FIRST_FACTS = ["size", "diagonal", "aspect", "capacity", "form factor", "count"]
NOT_DRAWN = ["voltage", "current", "wattage"]
CONDITION_FIELDS = ["condition", "fault"]
IN_A_HOME = "finished and in use in a home, no text, no logos, no people"
BUILD = {"scale", "wrong_device", "missing_part", "invented_part", "wrong_setting", "implausible"}
SIZE = {"scale", "wrong_device"}
SETTING = {"wrong_setting", "missing_part"}
VIEW_PRESETS = {
    "from above": (
        "seen straight down from above; every part at its true size against the table or desk"
    ),
    "close-up": "a close-up at arm's length; the parts at their real sizes side by side",
}
# a request that names a brand, a model or a part number invites the model to letter it
LETTERED = re.compile(r"\((?:[^)]*?)\b(brand|model number|part number|certifications?)\b", re.I)
CONDITION_SAID = re.compile(r"\bcondition(?: notes)?\b[: ]", re.I)

TUNE_INSTRUCTIONS = """\
You write corrections for an image model that draws home builds made from old parts. For each \
subject (a kind of project) you get the drawings' issues as a reviewer found them and the \
briefs the reviewer proposed. Write one correction of at most 300 characters that every \
drawing of that subject should carry: the main part's kind with its real size in cm and its \
proportions, where it sits and how it is used, and what never to draw ("not a TV", "no second \
drive"). Name parts by kind, never by brand or model, and never mention lettering (that rule \
is said elsewhere). For each kind of part you get the scale issues it had; write how it looks \
at its real size in at most 120 characters ("a bare circuit board the size of a credit card, \
about 7 x 5 cm"). A kind's line holds for every part of that kind: where its size varies (a \
monitor, a drive, a laptop), give no number and no aspect ratio, since each part's own size is \
said beside it; say what sets it apart from what it gets drawn as instead ("a computer \
monitor, far smaller than a television"). Keep to the facts given; invent no part."""


# --- shapes --------------------------------------------------------------------------------


class SubjectStats(BaseModel):
    subject: str
    drawings: list[str] = []
    verdicts: dict[str, int] = {}
    categories: dict[str, int] = {}
    kinds: list[str] = []
    issues: list[str] = []
    briefs: list[str] = []
    people: list[str] = Field(
        default=[], description="dislikes cast in the app, each with who and the reason"
    )


class Aggregate(BaseModel):
    params_version: int
    report_at: str
    drawings: int
    verdicts: dict[str, int]
    categories: dict[str, int]
    by_kind: dict[str, dict[str, int]]
    subjects: dict[str, SubjectStats]
    lettered_requests: list[str] = Field(
        default=[], description="drawings whose request names a brand, model or part number"
    )
    condition_requests: list[str] = Field(
        default=[], description="drawings whose request says the item's present condition"
    )
    measured_text: list[str] = Field(
        default=[], description="drawings with a size or a dimension written on them"
    )
    size_kinds: dict[str, list[str]] = Field(
        default={}, description="kinds of part in drawings with a scale or device issue"
    )
    view_issues: dict[str, list[str]] = {}
    setting_issues: list[str] = Field(
        default=[], description="items drawn as a use, and reuse cards, with a setting issue"
    )
    disliked: dict[str, list[str]] = Field(
        default={}, description="drawings a person disliked in the app, with the reasons"
    )
    liked: list[str] = Field(
        default=[], description="drawings a person liked and nobody disliked: kept as they are"
    )


class Edit(BaseModel):
    path: str = Field(description="where in params.yaml: facts.left_out, projects.<id>, ...")
    action: Literal["set", "add"]
    value: Any
    why: str
    evidence: list[str] = []


class Proposal(BaseModel):
    at: str
    from_version: int
    to_version: int
    report_at: str
    edits: list[Edit]
    aggregate: Aggregate
    model: str = ""
    cost_usd: float = 0.0
    phrased: bool = Field(default=False, description="corrections phrased by a model call")


class Phrased(BaseModel):
    class Correction(BaseModel):
        subject: str
        text: str

    class Looks(BaseModel):
        kind: str
        text: str

    corrections: list[Correction]
    looks: list[Looks]


# --- aggregate -----------------------------------------------------------------------------


def _count(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def subject_key(review: Any) -> str:
    """Where a drawing's corrections go: its kind of project, else ``kind:<item type>``."""
    subject = getattr(review, "subject", "") or ""
    if subject:
        return subject
    kinds = getattr(review, "kinds", []) or []
    return f"kind:{kinds[0]}" if kinds else f"{review.kind}:{review.id.split('#')[0]}"


def aggregate(report: Any, params_version: int) -> Aggregate:
    reviews = [r for r in report.reviews if r.verdict in ("matches", "partly", "wrong")]
    subjects: dict[str, SubjectStats] = {}
    by_kind: dict[str, list[str]] = {}
    size_kinds: dict[str, list[str]] = {}
    view_issues: dict[str, list[str]] = {}
    out = Aggregate(
        params_version=params_version,
        report_at=report.at,
        drawings=len(reviews),
        verdicts=_count([r.verdict for r in reviews]),
        categories=_count([i.category for r in reviews for i in r.issues]),
        by_kind={},
        subjects={},
    )
    for r in reviews:
        by_kind.setdefault(r.kind, []).append(r.verdict)
        key = subject_key(r)
        s = subjects.setdefault(key, SubjectStats(subject=key))
        s.drawings.append(r.id)
        s.verdicts = _count([*[k for k, n in s.verdicts.items() for _ in range(n)], r.verdict])
        cats = [i.category for i in r.issues]
        s.categories = _count([*[k for k, n in s.categories.items() for _ in range(n)], *cats])
        for k in getattr(r, "kinds", []) or []:
            if k not in s.kinds:
                s.kinds.append(k)
        s.issues += [f"{i.category}: {i.detail}" for i in r.issues if i.category != "text"]
        people = getattr(r, "people", None)
        if people is not None and people.dislikes:
            # a person flagged it: counted like an issue the reviewer found, ahead of them
            flagged = [f"flagged by a person: {reason}" for reason in people.reasons]
            s.people += flagged
            s.issues = flagged + s.issues
            out.disliked[r.id] = list(people.reasons)
        elif people is not None and people.likes:
            out.liked.append(r.id)
        if r.brief and (r.verdict == "wrong" or BUILD & set(cats)):
            s.briefs.append(r.brief)
        asked = r.facts.asked or ""
        if LETTERED.search(asked):
            out.lettered_requests.append(r.id)
        if CONDITION_SAID.search(asked):
            out.condition_requests.append(r.id)
        if any(i.category == "text" and MEASURED.search(i.detail) for i in r.issues):
            out.measured_text.append(r.id)
        if SIZE & set(cats):
            for k in getattr(r, "kinds", []) or []:
                size_kinds.setdefault(k, []).append(r.id)
        view = r.facts.view
        if view and BUILD & set(cats):
            view_issues.setdefault(view, []).append(r.id)
        if r.kind in ("item", "card") and (SETTING & set(cats) or r.verdict == "wrong"):
            out.setting_issues.append(r.id)
    out.by_kind = {k: _count(v) for k, v in sorted(by_kind.items())}
    out.subjects = dict(sorted(subjects.items()))
    out.size_kinds = dict(sorted(size_kinds.items()))
    out.view_issues = view_issues
    return out


# --- propose -------------------------------------------------------------------------------


def _missing(values: list[str], have: list[str]) -> list[str]:
    return [v for v in values if v not in have]


def needs_correction(s: SubjectStats) -> bool:
    if s.subject.startswith(("kind:", "item:", "card:")):
        return False
    return s.verdicts.get("wrong", 0) > 0 or bool(BUILD & set(s.categories)) or bool(s.people)


def rule_edits(agg: Aggregate, params: DrawingParams) -> list[Edit]:
    """The edits that follow from the counts alone, by fixed rules."""
    edits: list[Edit] = []
    f = params.facts
    text = agg.categories.get("text", 0)
    if text >= TEXT_MIN:
        fields = _missing(LETTERING_FIELDS, f.left_out)
        if fields:
            edits.append(
                Edit(
                    path="facts.left_out",
                    action="add",
                    value=fields,
                    why=f"{text} issue(s) of legible text or logos; {len(agg.lettered_requests)}"
                    " request(s) name a brand, a model or a part number, which the drawing"
                    " then letters",
                    evidence=agg.lettered_requests[:12],
                )
            )
        if not any("lettering" in n.lower() for n in params.negatives):
            edits.append(
                Edit(
                    path="negatives",
                    action="add",
                    value=[NO_LETTERING],
                    why=f"{text} issue(s) of legible text or logos although every request"
                    " closes with 'no text, no logos': said once more, plainly, before it",
                )
            )
    if agg.measured_text and not any("dimension" in n.lower() for n in params.negatives):
        edits.append(
            Edit(
                path="negatives",
                action="add",
                value=[NO_MEASURES],
                why=f"{len(agg.measured_text)} drawing(s) carry a size written on them: the"
                " sizes said for scale came back as labels",
                evidence=agg.measured_text,
            )
        )
    if agg.condition_requests and (f.condition or _missing(CONDITION_FIELDS, f.left_out)):
        if f.condition:
            edits.append(
                Edit(
                    path="facts.condition",
                    action="set",
                    value=False,
                    why="an item drawn as a use is drawn finished; its present condition"
                    " (dust, a wrap, a blacked-out label) turns into blots and wraps",
                    evidence=agg.condition_requests[:12],
                )
            )
        fields = _missing(CONDITION_FIELDS, f.left_out)
        if fields:
            edits.append(
                Edit(
                    path="facts.left_out",
                    action="add",
                    value=fields,
                    why=f"{len(agg.condition_requests)} request(s) carry condition notes as a"
                    " value of a part",
                    evidence=agg.condition_requests[:12],
                )
            )
    size_issues = sum(agg.categories.get(c, 0) for c in SIZE)
    if size_issues or any(s.verdicts.get("wrong") for s in agg.subjects.values()):
        if not f.from_name:
            edits.append(
                Edit(
                    path="facts.from_name",
                    action="set",
                    value=True,
                    why="the sizes (18 inch, 2.5 inch, 480 GB) are in the item's name, never"
                    " in a request: say them, and nothing else of the name",
                    evidence=sorted({i for ids in agg.size_kinds.values() for i in ids})[:12],
                )
            )
        first = _missing(FIRST_FACTS, f.first)
        if first:
            edits.append(
                Edit(
                    path="facts.first",
                    action="add",
                    value=first,
                    why="facts that set a part's size go before the rest, not in alphabetical"
                    " order behind its brand",
                )
            )
        left = _missing(NOT_DRAWN, f.left_out)
        if left:
            edits.append(
                Edit(
                    path="facts.left_out",
                    action="add",
                    value=left,
                    why="a voltage or a current cannot be drawn; it takes the place of a fact"
                    " that can",
                )
            )
        if f.part_values < 6:
            edits.append(
                Edit(
                    path="facts.part_values",
                    action="set",
                    value=6,
                    why="a part carried at most three values, so its size was cut",
                )
            )
    for kind in agg.size_kinds:
        if ("monitor" in kind or "display" in kind) and (
            params.kind(kind) is None or "screen" not in params.kind(kind).size  # type: ignore[union-attr]
        ):
            edits.append(
                Edit(
                    path=f"kinds.{kind}.size",
                    action="set",
                    value="screen size",
                    why="a screen's size is its diagonal; said in cm too",
                    evidence=agg.size_kinds[kind],
                )
            )
    for view, ids in agg.view_issues.items():
        for words, preset in VIEW_PRESETS.items():
            if words in view.lower() and words not in params.views:
                edits.append(
                    Edit(
                        path=f"views.{words}",
                        action="set",
                        value=preset,
                        why=f"the views {words!r} had build issues: scale is easiest to lose there",
                        evidence=ids,
                    )
                )
    if agg.setting_issues:
        for kind in ("use", "card"):
            if "plain background" in getattr(params.rules, kind):
                edits.append(
                    Edit(
                        path=f"rules.{kind}",
                        action="set",
                        value=IN_A_HOME,
                        why="a use or a reuse card is a build in its place; 'on a plain"
                        " background' took the room away and with it the scale",
                        evidence=agg.setting_issues,
                    )
                )
    return edits


def phrase_input(
    agg: Aggregate,
    params: DrawingParams,
    labels: dict[str, str],
    approved: dict[str, str] | None = None,
) -> str:
    lines = []
    for s in agg.subjects.values():
        if not needs_correction(s):
            continue
        have = params.projects.get(s.subject)
        current = have.correction if have and have.correction else (approved or {}).get(s.subject)
        lines += [
            f"Subject: {s.subject} ({labels.get(s.subject, s.subject)})",
            f"Parts by kind: {', '.join(s.kinds) or '-'}",
            f"Current correction (keep what still holds): {current or '-'}",
            "Issues:",
            *[f"- {i}" for i in s.issues[:10]],
            "Proposed briefs:",
            *[f"- {b}" for b in s.briefs[:6]],
            "",
        ]
    for kind, ids in agg.size_kinds.items():
        details = [
            i
            for s in agg.subjects.values()
            for i in s.issues
            if any(d in s.drawings for d in ids) and i.split(":")[0] in SIZE
        ]
        lines += [f"Kind of part: {kind}", *[f"- {d}" for d in details[:6]], ""]
    return "\n".join(lines).strip()


def promoted_edits(
    agg: Aggregate,
    params: DrawingParams,
    approved: dict[str, str],
    labels: dict[str, str],
    taken: set[str],
) -> list[Edit]:
    """A correction the owner approved in the demo set for a kind of project (not for one
    view of it) becomes that kind's correction in the parameters, so every drawing of it
    carries it, the owner's own included; unless the reviews call for a new one."""
    edits = []
    for key, brief in approved.items():
        if " / " in key or key not in labels or key in taken:
            continue
        have = params.projects.get(key)
        text = " ".join(brief.split())[:TEXT_LIMIT]
        if have is not None and have.correction == text:
            continue
        stats = agg.subjects.get(key)
        edits.append(
            Edit(
                path=f"projects.{key}",
                action="set",
                value={"match": _match(key, labels, have), "correction": text},
                why="approved in the demo set for this kind of project (propose.corrections);"
                " now every drawing of it carries it, not only the demo's",
                evidence=stats.drawings if stats else [],
            )
        )
    return edits


def _match(subject: str, labels: dict[str, str], have: Any) -> list[str]:
    if have is not None and have.match:
        return list(have.match)
    label = labels.get(subject, "").lower()
    return [w for w in dict.fromkeys((label, subject.replace("_", " "))) if w]


def correction_edits(
    agg: Aggregate, params: DrawingParams, phrased: Phrased | None, labels: dict[str, str]
) -> list[Edit]:
    """A correction for each kind of project with build issues, and the looks of each kind of
    part drawn at the wrong size; phrased by the call, else the shortest brief as it is."""
    edits: list[Edit] = []
    said = {c.subject: c.text for c in (phrased.corrections if phrased else [])}
    looks = {c.kind: c.text for c in (phrased.looks if phrased else [])}
    for s in agg.subjects.values():
        if not needs_correction(s):
            continue
        text = said.get(s.subject) or (min(s.briefs, key=len) if s.briefs else "")
        text = " ".join(text.split())[:CORRECTION_MAX]
        if not text:
            continue
        have = params.projects.get(s.subject)
        value: dict[str, Any] = {"match": _match(s.subject, labels, have), "correction": text}
        cats = ", ".join(f"{k} {n}" for k, n in s.categories.items() if k != "text") or "-"
        edits.append(
            Edit(
                path=f"projects.{s.subject}",
                action="set",
                value=value,
                why=f"{len(s.drawings)} drawing(s), {s.verdicts.get('wrong', 0)} wrong;"
                f" issues: {cats}"
                + (f"; {len(s.people)} disliked by a person" if s.people else ""),
                evidence=s.drawings,
            )
        )
    for kind, ids in agg.size_kinds.items():
        text = " ".join(looks.get(kind, "").split())[:LOOKS_MAX]
        if not text:
            continue
        edits.append(
            Edit(
                path=f"kinds.{kind}.looks",
                action="set",
                value=text,
                why="drawn at the wrong size or as another device",
                evidence=ids,
            )
        )
    return edits


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
    except (ModelApiError, ValueError):
        return None, 0.0
    return result.parsed, result.response.cost_usd


def apply_edits(params: DrawingParams, edits: list[Edit]) -> DrawingParams:
    """The parameters with each edit made, ``version`` one up; validated as the file is."""
    data = params.model_dump(mode="json")
    for e in edits:
        keys = e.path.split(".", 2)
        if keys[0] in ("kinds", "projects", "views") and len(keys) >= 2:
            section = data.setdefault(keys[0], {})
            if keys[0] == "views":
                section[keys[1]] = e.value
                continue
            entry = section.setdefault(keys[1], {})
            if len(keys) == 3:
                entry[keys[2]] = e.value
            elif isinstance(e.value, dict):
                entry.update(e.value)
            continue
        target: Any = data
        for k in keys[:-1]:
            target = target[k]
        last = keys[-1]
        if e.action == "add":
            have = list(target.get(last) or [])
            target[last] = have + [v for v in e.value if v not in have]
        else:
            target[last] = e.value
    data["version"] = params.version + 1
    return DrawingParams.model_validate(data)


def diff(old: DrawingParams, new: DrawingParams) -> str:
    return "".join(
        difflib.unified_diff(
            dump(old).splitlines(keepends=True),
            dump(new).splitlines(keepends=True),
            fromfile=f"params.yaml (version {old.version})",
            tofile=f"params.yaml (version {new.version})",
        )
    )


def proposal_markdown(p: Proposal, old: DrawingParams) -> str:
    new = apply_edits(old, p.edits)
    a = p.aggregate
    verdicts = ", ".join(f"{n} {k}" for k, n in a.verdicts.items())
    cats = ", ".join(f"{k} {n}" for k, n in sorted(a.categories.items(), key=lambda x: -x[1]))
    lines = [
        f"# Drawing parameters: version {p.from_version} to {p.to_version}",
        "",
        f"From the review of {a.report_at}: {a.drawings} drawing(s), {verdicts}.",
        f"Issues by category: {cats or 'none'}.",
        "",
        f"{len(p.edits)} edit(s)"
        + (f"; corrections phrased by {p.model} ({p.cost_usd:.4f} USD)" if p.phrased else "")
        + ". Apply with `./dev picture-review --tune --apply`; edit or drop an edit in"
        " `picture-review/tune.json` first if the owner wants it otherwise.",
        "",
        "| # | where | why | drawings |",
        "|---|---|---|---|",
    ]
    for n, e in enumerate(p.edits, 1):
        ev = ", ".join(f"`{x}`" for x in e.evidence[:4]) + (" ..." if len(e.evidence) > 4 else "")
        lines.append(f"| {n} | `{e.path}` | {e.why.replace('|', '/')} | {ev} |")
    lines += [
        "",
        "## By subject",
        "",
        "| subject | drawings | verdicts | issues |",
        "|---|---|---|---|",
    ]
    for s in a.subjects.values():
        v = ", ".join(f"{n} {k}" for k, n in s.verdicts.items())
        c = ", ".join(f"{k} {n}" for k, n in s.categories.items()) or "-"
        lines.append(f"| `{s.subject}` | {len(s.drawings)} | {v} | {c} |")
    if a.disliked or a.liked:
        lines += ["", "## People's votes", ""]
        lines += [f"- `{d}` disliked: {'; '.join(r)}" for d, r in a.disliked.items()]
        lines += [f"- `{d}` liked: kept as it is" for d in a.liked]
    lines += ["", "## The change", "", "```diff", diff(old, new).rstrip(), "```", ""]
    return "\n".join(lines)


# --- evaluation ----------------------------------------------------------------------------


class Scored(BaseModel):
    id: str
    subject: str = ""
    verdict: str
    categories: list[str] = []
    recording: str = Field(default="", description="the digest of the drawing's recording")


class Evaluation(BaseModel):
    params_version: int
    stage: str = Field(
        default="",
        description="a later score of the same version: the reviewer's facts changed, or the"
        " best of several candidates kept",
    )
    at: str
    report_at: str
    reviewer: str
    image_model: str
    drawings: int
    verdicts: dict[str, int]
    categories: dict[str, int]
    by_kind: dict[str, dict[str, int]]
    review_usd: float = Field(description="what the run spent: its drawings and its reviews")
    scored: list[Scored]
    params: dict[str, Any]


def recording_of(image_model: str, asked: str) -> str:
    return request_key(IMAGES, picture_body(image_model, asked)) if asked else ""


def evaluation(report: Any, params: DrawingParams, image_model: str, stage: str = "") -> Evaluation:
    agg = aggregate(report, params.version)
    return Evaluation(
        params_version=params.version,
        stage=stage,
        at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        report_at=report.at,
        reviewer=report.model,
        image_model=image_model,
        drawings=agg.drawings,
        verdicts=agg.verdicts,
        categories=agg.categories,
        by_kind=agg.by_kind,
        review_usd=round(report.cost_usd, 4),
        scored=[
            Scored(
                id=r.id,
                subject=subject_key(r),
                verdict=r.verdict,
                categories=sorted({i.category for i in r.issues}),
                recording=recording_of(image_model, r.facts.asked),
            )
            for r in report.reviews
        ],
        params=params.model_dump(mode="json"),
    )


STAGE = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")


def eval_path(folder: Path, version: int, stage: str = "") -> Path:
    return folder / (f"params-v{version}-{stage}.json" if stage else f"params-v{version}.json")


def history(folder: Path) -> list[Evaluation]:
    """Every evaluation kept, by version, a version's later stages after its first score."""
    found = []
    for path in sorted(folder.glob("params-v*.json")):
        found.append(Evaluation.model_validate_json(path.read_text(encoding="utf-8")))
    return sorted(found, key=lambda e: (e.params_version, bool(e.stage), e.at))


def label(e: Evaluation) -> str:
    return f"params v{e.params_version}" + (f" {e.stage}" if e.stage else "")


VERDICTS = ("matches", "partly", "wrong")
CATEGORIES = (
    "text",
    "scale",
    "wrong_device",
    "missing_part",
    "invented_part",
    "wrong_setting",
    "implausible",
)


def table(evals: list[Evaluation]) -> str:
    """The versions side by side: verdicts, then issues by category."""
    head = "| | " + " | ".join(label(e) for e in evals) + " |"
    lines = [head, "|---|" + "---|" * len(evals)]
    lines.append("| drawings | " + " | ".join(str(e.drawings) for e in evals) + " |")
    for v in VERDICTS:
        lines.append(f"| {v} | " + " | ".join(str(e.verdicts.get(v, 0)) for e in evals) + " |")
    for c in CATEGORIES:
        if any(e.categories.get(c) for e in evals):
            row = " | ".join(str(e.categories.get(c, 0)) for e in evals)
            lines.append(f"| issues: {c} | {row} |")
    lines.append(
        "| spent on the run, USD | " + " | ".join(f"{e.review_usd:.2f}" for e in evals) + " |"
    )
    return "\n".join(lines)


def changes(old: Evaluation, new: Evaluation) -> list[str]:
    """Each drawing whose verdict moved, better first."""
    rank = {"matches": 2, "partly": 1, "wrong": 0}
    was = {s.id: s for s in old.scored}
    moved = []
    for s in new.scored:
        before = was.get(s.id)
        if before is None or before.verdict == s.verdict:
            continue
        up = rank.get(s.verdict, -1) - rank.get(before.verdict, -1)
        moved.append((-up, s.id, f"`{s.id}`: {before.verdict} to {s.verdict}"))
    return [m[2] for m in sorted(moved)]


START = "<!-- params-history:start -->"
END = "<!-- params-history:end -->"


def history_block(evals: list[Evaluation]) -> str:
    lines = [
        START,
        "",
        "*Written by `./dev picture-review --evaluate` from `eval/pictures/`.*",
        "",
        table(evals),
        "",
    ]
    if len(evals) >= 2:
        moved = changes(evals[-2], evals[-1])
        if moved:
            lines += [
                f"Moved from {label(evals[-2])} to {label(evals[-1])}:",
                "",
                *[f"- {m}" for m in moved],
                "",
            ]
    lines.append(END)
    return "\n".join(lines)


def write_history(page: Path, evals: list[Evaluation]) -> bool:
    """The history table written between its markers in the results page; ``False`` when the
    page has no markers (nothing is written)."""
    if not page.is_file():
        return False
    text = page.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    page.write_text(head + history_block(evals) + tail, encoding="utf-8")
    return True


def unused_recordings(old: Evaluation, new: Evaluation) -> list[str]:
    now = {s.recording for s in new.scored if s.recording}
    return sorted({s.recording for s in old.scored if s.recording and s.recording not in now})


def prune(fixtures: Path, digests: list[str]) -> list[Path]:
    """The drawing recordings no version still uses: each ``.json`` and its image files."""
    folder = fixtures / IMAGES.strip("/").replace("/", "-")
    removed = []
    for d in digests:
        if not re.fullmatch(r"[0-9a-f]{24}", d):
            continue
        for path in [folder / f"{d}.json", *sorted(folder.glob(f"{d}-*"))]:
            if path.is_file():
                path.unlink()
                removed.append(path)
    return removed


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def read_proposal(path: Path) -> Proposal:
    return Proposal.model_validate_json(path.read_text(encoding="utf-8"))


def apply_proposal(path: Path, params_file: Path | None = None) -> DrawingParams:
    proposal = read_proposal(path)
    params = load_params(params_file)
    if params.version != proposal.from_version:
        raise ValueError(
            f"the proposal is for version {proposal.from_version}, the file is at"
            f" {params.version}: run --tune again"
        )
    new = apply_edits(params, proposal.edits)
    save(new, params_file)
    return new


def dumps(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
