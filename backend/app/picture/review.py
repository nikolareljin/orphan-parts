"""Command line: python -m app.picture.review [options]

Every drawing checked against the facts it had to show, one Muse Spark call each, and the
wrong ones drawn again with a corrected brief.

  (no option)          load the demo set in fixture mode into a folder of its own (nothing
                       spent, the stack's data untouched), then review every drawing: project
                       pictures and their views, reuse-card pictures, item pictures
  --set FILE           the set to load (default demo/set.yaml)
  --data               review the inventory in DATA_DIR as it stands instead (your own stack's)
  --only SEL,...       only these drawings: project:2, card:monitor_1800fp, item:uno_r3#1 ...
  --max-usd N          stop before a call that could take the run past N USD (default 1.00)
  --dry-run            list the drawings and the facts each must show; no call, no key
  --decide             also check each Decide card set, each item's ideas and each project's
                       allocations against the items' facts (one text call each); report only
  --out DIR            where the report goes (default picture-review/)
  --redraw SEL,...|all-wrong
                       draw these again with the brief proposed in the last report (or
                       --brief / --briefs), then review the new drawing; with the demo set the
                       briefs are written into the set file and only the new drawings are
                       recorded (every other answer replays); with --data a new picture is
                       added after the old ones
  --brief TEXT         the brief for the one drawing --redraw names
  --briefs FILE        a YAML map of drawing id to brief, in place of the report's

Tuning the drawing parameters (backend/app/picture/params.yaml):

  --tune               read the last review (report.json), count its issues by category and
                       subject, and propose edits to the parameters (tune.md, tune.json): fixed
                       rules, and one Muse Spark call to phrase the corrections (none with
                       --dry-run)
  --tune --apply       write the proposal (tune.json) into the parameters, version one up
  --redraw-set         draw the whole demo set again with the parameters as they are: only the
                       drawings whose request changed are bought and recorded (every other
                       answer replays), then every drawing is reviewed (report.json)
  --evaluate           keep what the last review scored for this version of the parameters
                       (eval/pictures/params-v<N>.json), compare it with the version before
                       (compare.md), write the history into --results, and list the drawing
                       recordings the version before used and this one does not
  --prune              with --evaluate: delete those recordings
  --stage WORD         with --evaluate: keep the score as a later stage of the same version
                       (eval/pictures/params-v<N>-<WORD>.json), beside its first score
  --candidates N       best of N: draw each drawing --only names (else each the last review
                       did not find matching) N more times, each with its own brief (the
                       corrected brief, then another framing), review every candidate and keep
                       the best by verdict, confidence and fewer issues; only the winner's brief
                       goes into the set file and only its recording is kept; every candidate
                       is saved under candidates/ in --out
  --eval-dir DIR       where the evaluations are kept (default eval/pictures)
  --results FILE       the page the history table is written into, between its markers

The key is MODEL_API_KEY from the environment, never printed or written.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

import yaml
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings, get_settings
from app.decide.schema import ReuseScenario
from app.decide.service import Decider
from app.demo.schema import DemoSet
from app.extract.imaging import BadImageError, prepare
from app.inventory import Inventory
from app.inventory.schema import Item
from app.model_api import (
    CostLedger,
    ModelApiClient,
    ModelApiError,
    NoRecordingError,
    image_part,
    text_part,
    user_message,
)
from app.model_api.client import IMAGES, output_cap
from app.model_api.fixtures import request_key
from app.model_api.pricing import IMAGE_UNIT_USD, PER_MILLION, token_rates
from app.picture import tune
from app.picture.briefs import SetBrief, apply
from app.picture.params import PARAMS_FILE, DrawingParams
from app.picture.params import load as load_params
from app.picture.service import (
    AS_BUILT_LEFT_OUT,
    MONEY_WORDS,
    Picture,
    Pictures,
    _kept,
    card_prompt,
    prompt_for,
)
from app.projects import Planner
from app.projects.pack import shown_fields
from app.projects.schema import Project
from app.projects.service import fits
from app.projects.templates import Templates, UnknownTemplateError

OP = "picture-review"
DECIDE_OP = "decide-review"
REVIEW_OUTPUT_TOKENS = 1200
DECIDE_OUTPUT_TOKENS = 1500
# what one call reads at most, for the guard: a 768-pixel drawing and its facts; a card set
# with the inventory beside it
REVIEW_INPUT_ALLOWANCE = 6000
DECIDE_INPUT_ALLOWANCE = 9000
REVIEW_PX = 768
THUMB_PX = 512
SHEET_TILE = 320
DEFAULT_MAX_USD = 1.0
# calls under way at once: a review takes most of a minute, a run of forty would take as long
CONCURRENCY = 6
ITEM_VALUES = 12
BRIEF_MAX = 400
# the most candidates one drawing may take in one best-of-N run
MAX_CANDIDATES = 6
# the drawings of the demo set a whole redraw reviews, for its cap
SET_DRAWINGS = 40
# one drawing, at the published rate
IMAGE_USD = IMAGE_UNIT_USD["muse-image"]

Verdict = Literal["matches", "partly", "wrong"]
Category = Literal[
    "scale",
    "missing_part",
    "invented_part",
    "wrong_device",
    "wrong_setting",
    "text",
    "implausible",
]
Kind = Literal["item", "card", "project"]

REVIEW_INSTRUCTIONS = """\
You check one drawing against the facts it had to show. The drawing illustrates a home build \
or a new use for old parts; its style, light and background are free. Judge only what the \
facts settle, by category:
- scale: a part's size against the room and the furniture (an 18 inch monitor is about 46 cm \
across the diagonal, not a television; a credit-card-sized board is not a desktop tower).
- wrong_device: a part drawn as another kind of thing (a monitor as a TV, a laptop as a \
desktop, a sensor module as a phone).
- missing_part: a part the facts list that the finished build must show and the drawing lacks.
- invented_part: a main device the facts do not list. Parts under "still to get" are bought \
for the build and may be drawn; so may the rest of the build its kind of project needs, and \
what the use itself names or plainly needs (a computer for a second screen, a router for a \
network link). A second copy of a listed part is invented.
- wrong_setting: the room or the use differs from the facts.
- text: legible words, logos or brand names (the request asked for none); a clock or a few \
glyphs on a display build are fine.
- implausible: what could not be built or would be unsafe as drawn.
Verdict: matches (nothing misleads), partly (small issues the owner could live with), wrong \
(it misleads about what gets built: another device, the main part at the wrong scale, another \
project). Confidence from 0 to 1.
brief: when the verdict is not matches, one corrected drawing brief of at most 350 \
characters, written as a line added to the image request: the main part's kind and real size \
and proportions, where it sits and how it is used, and what not to draw ("not a TV"). Name \
parts by kind, never by brand or model. Empty when the verdict is matches.
summary: one line on what the drawing shows."""

DECIDE_INSTRUCTIONS = """\
You check recommendations against the facts of the items they rest on. Flag a claim only \
when a fact contradicts it: a part that cannot fit (memory generation or form factor, socket, \
slot, connector, voltage), a wrong size or count, a capability the item lacks, a use that \
needs a part the owner lacks without saying so. Taste, effort and prices are not flags. \
Each flag: where (the card or allocation), the claim, the fact it contradicts, and \
severity (major when following it would fail or damage something, else minor). sound is \
true when there is no flag."""


# --- shapes --------------------------------------------------------------------------------


class Issue(BaseModel):
    category: Category
    detail: str


class ReviewAnswer(BaseModel):
    """Strict output of a review call."""

    verdict: Verdict
    confidence: float
    issues: list[Issue]
    brief: str
    summary: str


class Flag(BaseModel):
    where: str
    claim: str
    fact: str
    severity: Literal["minor", "major"]


class DecideAnswer(BaseModel):
    """Strict output of a recommendation check."""

    sound: bool
    flags: list[Flag]


class Facts(BaseModel):
    """What a drawing had to show, from the app's own records."""

    title: str
    setting: str = ""
    view: str = ""
    parts: list[str] = []
    still_to_get: list[str] = Field(
        default=[], description="open requirements: bought for the build, may be drawn"
    )
    build_needs: list[str] = Field(
        default=[],
        description="what its kind of project needs besides the parts listed: may be drawn",
    )
    asked: str = Field(default="", description="the image request as the app writes it")

    def text(self) -> str:
        lines = [f"Drawing of: {self.title}"]
        if self.setting:
            lines.append(f"What it is and where it is used: {self.setting}")
        if self.view:
            lines.append(f"Shown: {self.view}")
        if self.parts:
            lines.append("Parts it is built from (each a real item):")
            lines += [f"- {p}" for p in self.parts]
        if self.still_to_get:
            lines.append("Still to get (bought for the build; may appear):")
            lines += [f"- {p}" for p in self.still_to_get]
        if self.build_needs:
            lines.append("The rest of the build its kind of project needs (may appear):")
            lines += [f"- {p}" for p in self.build_needs]
        return "\n".join(lines)


class Drawing(BaseModel):
    """One kept picture and where it came from."""

    id: str
    kind: Kind
    n: int
    file: str
    use: str
    item_id: int = 0
    item_key: str = ""
    scenarios_id: int = 0
    card: int = 0
    project_id: int = 0
    template: str = ""
    project_title: str = ""
    view: str = ""
    subject: str = Field(default="", description="its kind of project, a template id")
    kinds: list[str] = Field(default=[], description="the item types of its parts")
    facts: Facts


class Review(BaseModel):
    id: str
    title: str
    kind: Kind
    picture: str = Field(default="", description="the thumbnail, relative to the report")
    subject: str = ""
    kinds: list[str] = []
    facts: Facts
    verdict: Verdict | Literal["error", "not reviewed"] = "not reviewed"
    confidence: float = 0.0
    issues: list[Issue] = []
    brief: str = ""
    summary: str = ""
    cost_usd: float = 0.0
    error: str = ""


class DecideReview(BaseModel):
    id: str
    title: str
    sound: bool | None = None
    flags: list[Flag] = []
    cost_usd: float = 0.0
    error: str = ""


class Redrawn(BaseModel):
    id: str
    brief: str
    before: Review
    after: Review | None = None
    cost_usd: float = 0.0
    error: str = ""


class Report(BaseModel):
    at: str
    source: str
    mode: str
    model: str = ""
    reviews: list[Review] = []
    decide: list[DecideReview] = []
    redrawn: list[Redrawn] = []
    skipped: list[str] = []
    cost_usd: float = 0.0
    load: list[str] = []
    params_version: int = Field(default=0, description="the drawing parameters asked with")

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.reviews:
            out[r.verdict] = out.get(r.verdict, 0) + 1
        return out


# --- facts ---------------------------------------------------------------------------------


def _line(text: str, limit: int = 300) -> str:
    return " ".join(text.split())[:limit]


def describe(item: Item, *, as_built: bool = True) -> str:
    """An item as the reviewer reads it: its kind, the owner's name for it (which often says
    its size) and its accepted values, never one that identifies it or names money; ``as_built``
    leaves out its present condition and the marks printed on it."""
    left_out = MONEY_WORDS + (AS_BUILT_LEFT_OUT if as_built else ())
    values = [
        _line(f"{k} {v}", 80)
        for k, v in shown_fields(item)
        if not any(word in k.lower() for word in left_out)
    ][:ITEM_VALUES]
    head = f"{_line(item.item_type, 80) or 'item'} ({_line(item.name, 120)})"
    return f"{head}: {', '.join(values)}" if values else head


def view_of(picture: Picture, title: str) -> str:
    """The view a project's drawing was asked for: what its record says after the title."""
    use = " ".join(picture.use.split())
    head = " ".join(title.split())
    if use.startswith(head + ", "):
        return use[len(head) + 2 :]
    return ""


def project_facts(project: Project, items: list[Item], view: str, asked: str) -> Facts:
    by_id = {i.id: i for i in items}
    parts = []
    for a in project.allocations:
        item = by_id.get(a.item_id)
        if item is not None:
            params = load_params()
            kind = params.kind(item.item_type)
            shown = kind is not None and kind.built and params.parts_built(project.template)
            built = f"; drawn as built: {kind.built}" if shown and kind is not None else ""
            parts.append(f"{a.requirement}: {describe(item)}{built}")
    return Facts(
        title=_line(project.title),
        setting=_line(project.result),
        view=view,
        parts=parts,
        still_to_get=[_line(r.label, 120) for r in project.requirements if r.state != "pass"],
        asked=asked,
    )


def build_needs(subject: str, items: list[Item], templates: Templates | None) -> list[str]:
    """What a kind of project needs besides the items drawn: its template's requirements none
    of them fills, by label; none when the subject is no template."""
    if templates is None or not subject:
        return []
    try:
        template = templates.get(subject)
    except UnknownTemplateError:
        return []
    return [
        _line(r.label, 120)
        for r in template.requirements
        if not any(fits(r.item_types, i) for i in items)
    ]


def drawn_as_itself(item: Item, use: str) -> bool:
    """The item's own picture (cleaned up), as ``prompt_for`` tells it from a use."""
    what = item.item_type or item.name or "item"
    return not use or use.lower() == what.lower()


def item_facts(
    item: Item,
    use: str,
    asked: str,
    *,
    subject: str = "",
    templates: Templates | None = None,
    params: DrawingParams | None = None,
) -> Facts:
    """An item's picture: the item as built (its present condition and printed marks only when
    the parameters say its own picture shows them), and, drawn as a use, the rest of the build
    its kind of project needs."""
    p = params if params is not None else load_params()
    own = drawn_as_itself(item, use)
    return Facts(
        title=_line(use),
        setting=_line(use),
        parts=[describe(item, as_built=not (own and p.facts.condition))],
        build_needs=[] if own else build_needs(subject, [item], templates),
        asked=asked,
    )


def card_facts(
    item: Item,
    reuse: ReuseScenario,
    asked: str,
    *,
    subject: str = "",
    templates: Templates | None = None,
) -> Facts:
    """A reuse card's picture: the item as built, the other items the card names, its extra
    parts, and the rest of the build its kind of project needs."""
    return Facts(
        title=_line(reuse.title),
        setting=_line(reuse.what_it_does),
        parts=[describe(item)] + [f"another item: {_line(w, 120)}" for w in reuse.with_items],
        still_to_get=[_line(x, 120) for x in reuse.extra_parts],
        build_needs=build_needs(subject, [item], templates),
        asked=asked,
    )


@dataclass
class Services:
    settings: Settings
    inventory: Inventory
    pictures: Pictures
    decider: Decider
    planner: Planner
    keys: dict[int, str] = field(default_factory=dict)
    # the set loaded, when it is the demo set: the corrections its drawings were asked with
    demo: DemoSet | None = None

    def item_brief(self, item_id: int, field_name: str) -> str:
        if self.demo is None:
            return ""
        key = self.keys.get(item_id)
        found = next((i for i in self.demo.items if i.key == key), None)
        return str(getattr(found, field_name, "")) if found is not None else ""

    def project_brief(self, project: Project, view: str) -> str:
        if self.demo is None or self.demo.propose is None:
            return ""
        return self.demo.propose.correction(project.template, project.title, view)


def subject_of(text: str, templates: Templates, params: DrawingParams) -> str:
    """The kind of project a use or a card title means: a template by its label or its id's
    words, else one the parameters name by its words; empty when none."""
    said = " ".join(text.split()).lower()
    if not said:
        return ""
    for tid in templates.ids():
        if said in (tid, templates.get(tid).label.lower()):
            return tid
    for tid, p in params.projects.items():
        if any(word in said for word in p.match):
            return tid
    for tid in templates.ids():
        if tid.replace("_", " ") in said or templates.get(tid).label.lower() in said:
            return tid
    return ""


def _kind(item: Item) -> str:
    return " ".join((item.item_type or "item").split()).lower()


def collect(sv: Services) -> list[Drawing]:
    """Every kept drawing: each item's, each reuse card's, each project's, in that order."""
    found: list[Drawing] = []
    params = load_params()
    templates = sv.pictures.templates
    items = sv.inventory.list_items()
    for summary in items:
        item = sv.inventory.get(summary.id)
        name = sv.keys.get(item.id, str(item.id))
        for pic in _kept(sv.pictures.folder(item.id)):
            found.append(
                Drawing(
                    id=f"item:{name}#{pic.n}",
                    kind="item",
                    n=pic.n,
                    file=str(sv.pictures.folder(item.id) / f"picture-{pic.n}.jpg"),
                    use=pic.use,
                    item_id=item.id,
                    item_key=sv.keys.get(item.id, ""),
                    subject=subject_of(pic.use, templates, params),
                    kinds=[_kind(item)],
                    facts=item_facts(
                        item,
                        pic.use,
                        prompt_for(item, pic.use, sv.item_brief(item.id, "picture_brief")),
                        subject=subject_of(pic.use, templates, params),
                        templates=templates,
                        params=params,
                    ),
                )
            )
        for scenarios in sv.decider.all_scenarios(item.id):
            for card, reuse in enumerate(scenarios.reuse):
                folder = sv.pictures.card_folder(item.id, scenarios.id, card)
                suffix = "" if card == 0 else f".{card}"
                for pic in _kept(folder):
                    found.append(
                        Drawing(
                            id=f"card:{name}{suffix}#{pic.n}",
                            kind="card",
                            n=pic.n,
                            file=str(folder / f"picture-{pic.n}.jpg"),
                            use=pic.use,
                            item_id=item.id,
                            item_key=sv.keys.get(item.id, ""),
                            scenarios_id=scenarios.id,
                            card=card,
                            subject=subject_of(reuse.title, templates, params),
                            kinds=[_kind(item)],
                            facts=card_facts(
                                item,
                                reuse,
                                card_prompt(
                                    scenarios,
                                    card,
                                    item,
                                    sv.item_brief(item.id, "reuse_picture_brief")
                                    if card == 0
                                    else "",
                                ),
                                subject=subject_of(reuse.title, templates, params),
                                templates=templates,
                            ),
                        )
                    )
    for project in sorted(sv.planner.projects().projects, key=lambda p: p.id):
        folder = sv.pictures.project_folder(project.id)
        allocated = sv.pictures.allocated(project)
        for pic in _kept(folder):
            view = view_of(pic, project.title)
            found.append(
                Drawing(
                    id=f"project:{project.id}#{pic.n}",
                    kind="project",
                    n=pic.n,
                    file=str(folder / f"picture-{pic.n}.jpg"),
                    use=pic.use,
                    project_id=project.id,
                    template=project.template,
                    project_title=project.title,
                    view=view,
                    subject=project.template,
                    kinds=list(dict.fromkeys(_kind(i) for i in allocated)),
                    facts=project_facts(
                        project,
                        allocated,
                        view,
                        sv.pictures.project_prompt(project, view, sv.project_brief(project, view)),
                    ),
                )
            )
    return found


def selected(drawing_id: str, selectors: Iterable[str]) -> bool:
    """``project:2`` picks every drawing of project 2, ``project:2#1`` the first alone,
    ``project`` (a kind alone) every project drawing."""
    kind = drawing_id.split(":", 1)[0]
    return any(drawing_id == s or drawing_id.startswith(s + "#") or s == kind for s in selectors)


# --- calls ---------------------------------------------------------------------------------


def ceiling_usd(model: str, input_tokens: int, answer_tokens: int) -> float:
    """The most one call can cost: its input allowance and every output token it may write."""
    _, inp, out = token_rates(model)
    return (input_tokens * inp + output_cap(answer_tokens, "low") * out) / PER_MILLION


class Budget:
    """The run's own cap: a call is made only when even its most costly answer fits, counting
    what the calls still under way could cost."""

    def __init__(self, max_usd: float) -> None:
        self.max_usd = max_usd
        self.spent = 0.0
        self.held = 0.0

    def allows(self, ceiling: float) -> bool:
        return self.spent + self.held + ceiling <= self.max_usd + 1e-9

    def reserve(self, ceiling: float) -> bool:
        if not self.allows(ceiling):
            return False
        self.held += ceiling
        return True

    def settle(self, ceiling: float, usd: float) -> None:
        self.held = max(self.held - ceiling, 0.0)
        self.add(usd)

    def add(self, usd: float) -> None:
        self.spent = round(self.spent + usd, 6)


async def _each[T](jobs: list[Callable[[], Awaitable[T]]], limit: int = CONCURRENCY) -> list[T]:
    """The jobs run a few at a time, their results in the order given."""
    gate = asyncio.Semaphore(limit)

    async def one(job: Callable[[], Awaitable[T]]) -> T:
        async with gate:
            return await job()

    return list(await asyncio.gather(*(one(j) for j in jobs)))


async def review_one(
    client: ModelApiClient, settings: Settings, drawing: Drawing, title: str = ""
) -> tuple[ReviewAnswer, float]:
    data = Path(drawing.file).read_bytes()
    small = prepare(data, max_px=REVIEW_PX, max_bytes=20 * 1024 * 1024)
    result = await client.respond_structured(
        ReviewAnswer,
        model=settings.model_spark,
        input=[user_message(text_part(drawing.facts.text()), image_part(small))],
        instructions=REVIEW_INSTRUCTIONS,
        effort="low",
        max_output_tokens=REVIEW_OUTPUT_TOKENS,
        op=OP,
    )
    answer = result.parsed
    answer.brief = _line(answer.brief, BRIEF_MAX) if answer.verdict != "matches" else ""
    answer.confidence = min(max(answer.confidence, 0.0), 1.0)
    return answer, result.response.cost_usd


def thumbnail(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        img = opened.convert("RGB")
    img.thumbnail((THUMB_PX, THUMB_PX))
    img.save(target, "JPEG", quality=85)


def _safe(drawing_id: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", drawing_id.lower()).strip("-")


def title_of(d: Drawing) -> str:
    if d.kind == "project":
        return _line(d.project_title + (f" ({d.view})" if d.view else ""), 200)
    return d.facts.title


async def review_all(
    client: ModelApiClient,
    settings: Settings,
    drawings: list[Drawing],
    out: Path,
    budget: Budget,
    *,
    suffix: str = "",
    skipped: list[str],
) -> list[Review]:
    ceiling = ceiling_usd(settings.model_spark, REVIEW_INPUT_ALLOWANCE, REVIEW_OUTPUT_TOKENS)

    async def job(d: Drawing) -> Review:
        thumb = Path("pictures") / f"{_safe(d.id)}{suffix}.jpg"
        thumbnail(Path(d.file), out / thumb)
        review = Review(
            id=d.id,
            title=title_of(d),
            kind=d.kind,
            picture=str(thumb),
            subject=d.subject,
            kinds=d.kinds,
            facts=d.facts,
        )
        if not budget.reserve(ceiling):
            skipped.append(f"{d.id}: not reviewed, the next call could pass --max-usd")
            return review
        try:
            answer, usd = await review_one(client, settings, d)
        except (ModelApiError, BadImageError, OSError, ValueError) as exc:
            budget.settle(ceiling, 0.0)
            review.verdict = "error"
            review.error = str(exc)[:300]
            print(f"{d.id}: error {review.error}", file=sys.stderr, flush=True)
            return review
        budget.settle(ceiling, usd)
        review.verdict = answer.verdict
        review.confidence = answer.confidence
        review.issues = answer.issues
        review.brief = answer.brief
        review.summary = _line(answer.summary)
        review.cost_usd = usd
        print(f"{d.id}: {answer.verdict} ({usd:.4f} USD) {review.title}", flush=True)
        return review

    return await _each([partial(job, d) for d in drawings])


# --- recommendations -----------------------------------------------------------------------


def inventory_lines(items: list[Item], skip: int = 0) -> list[str]:
    return [f"- {describe(i, as_built=False)}" for i in items if i.id != skip]


async def decide_all(
    client: ModelApiClient,
    sv: Services,
    budget: Budget,
    skipped: list[str],
    only: Iterable[str] = (),
) -> list[DecideReview]:
    """Each item's latest Decide cards and each project's allocations, checked against the
    items' facts: one text call each, reported only; ``only`` keeps the checks of these kinds
    (``cards``, ``ideas``, ``project``) or ids."""
    items = [sv.inventory.get(s.id) for s in sv.inventory.list_items()]
    by_id = {i.id: i for i in items}
    ceiling = ceiling_usd(sv.settings.model_spark, DECIDE_INPUT_ALLOWANCE, DECIDE_OUTPUT_TOKENS)
    jobs: list[tuple[str, str, str]] = []
    for item in items:
        cards = sv.decider.latest_scenarios(item.id)
        if cards is None:
            continue
        name = sv.keys.get(item.id, str(item.id))
        reuse = "\n".join(
            f"- reuse card {n}: {r.title}: {r.what_it_does}; with {', '.join(r.with_items) or '-'};"
            f" extra parts {', '.join(r.extra_parts) or '-'}"
            for n, r in enumerate(cards.reuse)
        )
        text = "\n".join(
            [
                f"The item: {describe(item, as_built=False)}",
                f"Its condition: {_line(item.condition) or '-'};"
                f" faults: {_line(item.faults) or '-'}",
                "",
                f"Recommended: {cards.recommended} ({_line(cards.reason)})",
                f"- keep and fix: problems {'; '.join(cards.keep_fix.problems) or '-'};"
                f" steps {'; '.join(cards.keep_fix.steps) or '-'};"
                f" parts {'; '.join(cards.keep_fix.parts) or '-'}",
                reuse,
                f"- sell: {'; '.join(cards.sell.selling_points) or '-'}",
                "",
                "The owner's other items:",
                *inventory_lines(items, item.id),
            ]
        )
        jobs.append((f"cards:{name}", f"Decide cards of {item.name}", text))
    for item in items:
        ideas = sv.decider.latest_uses(item.id)
        if ideas is None or not ideas.uses:
            continue
        name = sv.keys.get(item.id, str(item.id))
        text = "\n".join(
            [
                f"The item: {describe(item, as_built=False)}",
                f"Its condition: {_line(item.condition) or '-'};"
                f" faults: {_line(item.faults) or '-'}",
                "",
                "What it is good for:",
                *(
                    f"- idea {n}: {u.title}: {u.what_it_does}; needs {', '.join(u.needs) or '-'};"
                    f" effort {u.effort}; note {u.note or '-'}"
                    for n, u in enumerate(ideas.uses)
                ),
                "",
                "The owner's other items:",
                *inventory_lines(items, item.id),
            ]
        )
        jobs.append((f"ideas:{name}", f"Ideas for {item.name}", text))
    for project in sorted(sv.planner.projects().projects, key=lambda p: p.id):
        parts = [
            f"- {a.requirement}: {describe(by_id[a.item_id])}; why: {_line(a.why, 200)}"
            for a in project.allocations
            if a.item_id in by_id
        ]
        open_ = [r.label for r in project.requirements if r.state != "pass"]
        text = "\n".join(
            [
                f"Project: {project.title}",
                f"What it results in: {_line(project.result)}",
                "Allocated items:",
                *parts,
                f"Still to get: {', '.join(open_) or '-'}",
                f"Unknowns: {'; '.join(project.unknowns) or '-'}",
            ]
        )
        jobs.append((f"project:{project.id}", project.title, text))

    async def check(job_id: str, title: str, text: str) -> DecideReview:
        review = DecideReview(id=job_id, title=_line(title, 200))
        if not budget.reserve(ceiling):
            skipped.append(f"{job_id}: not checked, the next call could pass --max-usd")
            return review
        try:
            result = await client.respond_structured(
                DecideAnswer,
                model=sv.settings.model_spark,
                input=[user_message(text_part(text))],
                instructions=DECIDE_INSTRUCTIONS,
                effort="low",
                max_output_tokens=DECIDE_OUTPUT_TOKENS,
                op=DECIDE_OP,
            )
        except (ModelApiError, ValueError) as exc:
            budget.settle(ceiling, 0.0)
            review.error = str(exc)[:300]
            return review
        budget.settle(ceiling, result.response.cost_usd)
        review.sound = result.parsed.sound and not result.parsed.flags
        review.flags = result.parsed.flags
        review.cost_usd = result.response.cost_usd
        said = "sound" if review.sound else f"{len(review.flags)} flag(s)"
        print(f"{job_id}: {said}", flush=True)
        return review

    kinds = set(only)
    if kinds:
        jobs = [j for j in jobs if j[0] in kinds or j[0].split(":", 1)[0] in kinds]
    return await _each([partial(check, *job) for job in jobs])


# --- the report ----------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def _review_md(r: Review, heading: str = "##") -> list[str]:
    lines = [f"{heading} `{r.id}` {r.title}", ""]
    if r.picture:
        lines += [f"![{r.id}]({r.picture})", ""]
    lines.append(
        f"**Verdict: {r.verdict}**"
        + (f" (confidence {r.confidence:.2f}, {r.cost_usd:.4f} USD)" if r.summary else "")
    )
    if r.summary:
        lines += ["", f"What it shows: {r.summary}"]
    if r.error:
        lines += ["", f"Error: {r.error}"]
    lines += ["", "Facts it had to show:", "", "```text", r.facts.text(), "```"]
    if r.facts.asked:
        lines += ["", "Asked of Muse Image:", "", f"> {r.facts.asked}"]
    if r.issues:
        lines += ["", "Issues:", ""] + [f"- **{i.category}**: {i.detail}" for i in r.issues]
    if r.brief:
        lines += ["", "Proposed brief:", "", f"> {r.brief}"]
    return [*lines, ""]


def markdown(report: Report) -> str:
    counts = report.counts()
    said = ", ".join(f"{counts[k]} {k}" for k in sorted(counts)) or "none"
    lines = [
        "# Picture review",
        "",
        f"{report.at}, {report.source} ({report.mode}); reviewed by {report.model or '-'}.",
        "",
        f"{len(report.reviews)} drawing(s): {said}. Spent {report.cost_usd:.4f} USD.",
        "",
    ]
    if report.redrawn:
        lines += ["## Redrawn", "", "| drawing | before | after | brief |", "|---|---|---|---|"]
        for rd in report.redrawn:
            after = rd.after.verdict if rd.after else f"error: {_cell(rd.error)}"
            lines.append(f"| `{rd.id}` | {rd.before.verdict} | {after} | {_cell(rd.brief)} |")
        lines.append("")
        for rd in report.redrawn:
            lines += [f"### `{rd.id}`", "", f"Brief: {rd.brief}", ""]
            lines += _review_md(rd.before, "#### Before:")
            if rd.after is not None:
                lines += _review_md(rd.after, "#### After:")
    if report.reviews:
        lines += [
            "## Summary",
            "",
            "| drawing | what | verdict | first issue |",
            "|---|---|---|---|",
        ]
        for r in report.reviews:
            first = f"{r.issues[0].category}: {r.issues[0].detail}" if r.issues else ""
            lines.append(f"| `{r.id}` | {_cell(r.title)} | {r.verdict} | {_cell(first)[:160]} |")
        lines.append("")
    if report.decide:
        flagged = [d for d in report.decide if d.flags]
        lines += [
            "## Recommendations",
            "",
            f"{len(report.decide)} checked, {len(flagged)} with flags.",
            "",
        ]
        for d in flagged:
            lines += [f"### `{d.id}` {d.title}", ""]
            lines += [f"- **{f.severity}** {f.where}: {f.claim} (but {f.fact})" for f in d.flags]
            lines.append("")
        errors = [d for d in report.decide if d.error]
        lines += [f"- `{d.id}`: {d.error}" for d in errors]
    if report.reviews and not report.redrawn:
        lines += ["## Drawings", ""]
        for r in report.reviews:
            lines += _review_md(r, "###")
    if report.skipped or report.load:
        lines += ["## Notes", ""] + [f"- {s}" for s in report.load + report.skipped] + [""]
    return "\n".join(lines).rstrip() + "\n"


def write(report: Report, out: Path, name: str = "report") -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    md = out / f"{name}.md"
    js = out / f"{name}.json"
    md.write_text(markdown(report), encoding="utf-8")
    js.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return [md, js]


def contact_sheet(tiles: list[tuple[str, Path]], target: Path) -> None:
    """The drawings side by side, each labeled with its id and verdict."""
    if not tiles:
        return
    cols = min(len(tiles), 4)
    rows = (len(tiles) + cols - 1) // cols
    label = 28
    sheet = Image.new("RGB", (cols * SHEET_TILE, rows * (SHEET_TILE + label)), "white")
    draw = ImageDraw.Draw(sheet)
    for n, (text, path) in enumerate(tiles):
        x, y = (n % cols) * SHEET_TILE, (n // cols) * (SHEET_TILE + label)
        with Image.open(path) as opened:
            img = opened.convert("RGB")
        img.thumbnail((SHEET_TILE - 8, SHEET_TILE - 8))
        sheet.paste(img, (x + 4, y + label))
        draw.text((x + 6, y + 8), text[:48], fill="black")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, "JPEG", quality=85)


# --- the runs ------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "demo" / "set.yaml").is_file():
            return parent
    return Path.cwd()


def default_set() -> Path:
    for root in (Path.cwd(), Path.cwd().parent, _repo_root(), Path("/")):
        candidate = root / "demo" / "set.yaml"
        if candidate.is_file():
            return candidate
    return Path("demo/set.yaml")


def default_out() -> Path:
    root = _repo_root()
    return root / "picture-review" if (root / "demo").is_dir() else Path("picture-review")


class PicturesOnlyClient(ModelApiClient):
    """Record mode for drawings alone: any other request answers only from its recording, so
    a redraw run buys the new drawings and nothing else."""

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        op: str,
        files: dict[str, Any] | None = None,
        key: dict[str, Any] | None = None,
        attempts: int | None = None,
    ) -> tuple[dict[str, Any], bool, int, float]:
        if endpoint != IMAGES:
            keyed = body if key is None else key
            kept = self.fixtures.find(endpoint, keyed, op)
            if kept is None or kept.key != request_key(endpoint, keyed) or kept.status >= 400:
                raise NoRecordingError(endpoint, request_key(endpoint, keyed), op)
        return await super()._post(endpoint, body, op, files=files, key=key, attempts=attempts)


async def load_set(
    settings: Settings, set_file: Path, client: ModelApiClient | None = None
) -> tuple[Services, list[str]]:
    """The set loaded into ``settings.data_dir`` (fresh), in the client's mode."""
    from app.demo.__main__ import build_loader
    from app.demo.service import load_set as read_set

    demo = read_set(set_file)
    loader, used = build_loader(settings, client)
    try:
        outcome = await loader.run(demo, set_file.parent)
    finally:
        await used.aclose()
    keys = {v: k for k, v in loader.ids.items()}
    notes = [
        f"set load ({outcome.mode}): {outcome.pictures} picture(s),"
        f" {len(outcome.unrecorded)} not recorded, {outcome.stub_answers} stand-in answer(s),"
        f" {len(outcome.skipped)} skipped, {outcome.cost_usd:.4f} USD"
    ]
    notes += [f"not recorded: {u}" for u in outcome.unrecorded]
    notes += [f"skipped: {s}" for s in outcome.skipped]
    assert loader.pictures is not None
    sv = Services(
        settings, loader.inventory, loader.pictures, loader.decider, loader.planner, keys, demo
    )
    return sv, notes


def open_data(settings: Settings) -> Services:
    """The inventory in ``settings.data_dir`` as it stands; nothing is loaded."""
    from app.demo.__main__ import build_loader

    loader, _ = build_loader(settings)
    assert loader.pictures is not None
    return Services(settings, loader.inventory, loader.pictures, loader.decider, loader.planner)


def _scratch(settings: Settings, data_dir: Path, **update: Any) -> Settings:
    return settings.model_copy(update={"data_dir": data_dir, **update})


def reviewer(settings: Settings, max_usd: float) -> ModelApiClient:
    """The client the reviews go through: live with a key (or replaying in fixture mode), its
    ledger in memory with the run's cap."""
    return ModelApiClient(
        settings.model_copy(update={"record_fixtures": False}), CostLedger(max_usd)
    )


def set_briefs(drawings: list[Drawing], briefs: dict[str, str]) -> list[SetBrief]:
    """Where each brief goes in the set file."""
    by_template: dict[str, int] = {}
    for d in drawings:
        if d.kind == "project" and d.n == min(
            x.n for x in drawings if x.project_id == d.project_id and x.kind == "project"
        ):
            by_template[d.template] = by_template.get(d.template, 0) + 1
    out: list[SetBrief] = []
    for d in drawings:
        brief = briefs.get(d.id)
        if not brief:
            continue
        if d.kind == "item":
            out.append(SetBrief(brief, item=d.item_key, field="picture_brief"))
        elif d.kind == "card":
            if d.card != 0:
                raise ValueError(f"{d.id}: the set draws the first reuse card alone")
            out.append(SetBrief(brief, item=d.item_key, field="reuse_picture_brief"))
        else:
            name = d.template if by_template.get(d.template) == 1 else d.project_title
            key = f"{name} / {d.view}" if d.view else name
            out.append(SetBrief(brief, correction=key))
    return out


def chosen_briefs(
    report: Report | None, selectors: list[str], brief: str, briefs_file: Path | None
) -> dict[str, str]:
    """The brief for each drawing to redraw: --brief for the one named, else the briefs file,
    else what the last review proposed."""
    given: dict[str, str] = {}
    if briefs_file is not None:
        loaded = yaml.safe_load(briefs_file.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{briefs_file}: a map of drawing id to brief")
        given = {str(k): _line(str(v), BRIEF_MAX) for k, v in loaded.items() if str(v).strip()}
    reviews = report.reviews if report is not None else []
    if selectors == ["all-wrong"]:
        selectors = [r.id for r in reviews if r.verdict == "wrong"]
    out: dict[str, str] = {}
    for r in reviews:
        if selected(r.id, selectors):
            out[r.id] = given.get(r.id) or r.brief
    for sel in selectors:
        if sel in given:
            out[sel] = given[sel]
    if brief:
        if len(selectors) != 1 or len(out) > 1:
            raise ValueError("--brief goes with one drawing")
        out = {next(iter(out), selectors[0]): _line(brief, BRIEF_MAX)}
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise ValueError(f"no brief for {', '.join(missing)}: give --brief or --briefs")
    return out


@dataclass
class Options:
    set_file: Path
    out: Path
    data: bool = False
    only: list[str] = field(default_factory=list)
    max_usd: float = DEFAULT_MAX_USD
    dry_run: bool = False
    decide: bool = False
    redraw: list[str] = field(default_factory=list)
    brief: str = ""
    briefs: Path | None = None
    tune: bool = False
    apply: bool = False
    redraw_set: bool = False
    evaluate: bool = False
    prune: bool = False
    eval_dir: Path | None = None
    results: Path | None = None
    stage: str = ""
    candidates: int = 0


async def run_review(settings: Settings, opts: Options) -> Report:
    work = Path(tempfile.mkdtemp(prefix="picture-review-"))
    try:
        if opts.data:
            sv = open_data(settings)
            report = Report(at=_now(), source=str(settings.data_dir), mode="data")
        else:
            replay = _scratch(settings, work / "data", fake_api=True, record_fixtures=False)
            sv, notes = await load_set(replay, opts.set_file)
            report = Report(at=_now(), source=str(opts.set_file), mode="demo set", load=notes)
        drawings = [d for d in collect(sv) if not opts.only or selected(d.id, opts.only)]
        report.model = settings.model_spark
        report.params_version = load_params().version
        if opts.dry_run:
            report.mode += ", dry run"
            report.model = ""
            for d in drawings:
                thumb = Path("pictures") / f"{_safe(d.id)}.jpg"
                thumbnail(Path(d.file), opts.out / thumb)
                report.reviews.append(
                    Review(
                        id=d.id,
                        title=title_of(d),
                        kind=d.kind,
                        picture=str(thumb),
                        subject=d.subject,
                        kinds=d.kinds,
                        facts=d.facts,
                    )
                )
                print(f"{d.id}: {title_of(d)}")
            return report
        budget = Budget(opts.max_usd)
        client = reviewer(_scratch(settings, work / "review"), opts.max_usd)
        try:
            report.reviews = await review_all(
                client, settings, drawings, opts.out, budget, skipped=report.skipped
            )
            if opts.decide:
                report.decide = await decide_all(client, sv, budget, report.skipped)
        finally:
            await client.aclose()
        report.cost_usd = budget.spent
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def run_redraw(settings: Settings, opts: Options) -> Report:
    last_path = opts.out / "report.json"
    last = (
        Report.model_validate_json(last_path.read_text(encoding="utf-8"))
        if last_path.is_file()
        else None
    )
    briefs = chosen_briefs(last, opts.redraw, opts.brief, opts.briefs)
    secret = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
    if secret and any(secret in b for b in briefs.values()):
        # a brief goes into the set file and the request: never the key pasted into one
        raise ValueError("a brief holds MODEL_API_KEY; nothing was written or drawn")
    before = {r.id: r for r in (last.reviews if last else [])}
    work = Path(tempfile.mkdtemp(prefix="picture-redraw-"))
    report = Report(
        at=_now(),
        source=str(settings.data_dir if opts.data else opts.set_file),
        mode="redraw",
        model=settings.model_spark,
    )
    budget = Budget(opts.max_usd)
    try:
        # the old drawings, kept for the before side even without a last report
        if opts.data:
            sv = open_data(settings)
        else:
            replay = _scratch(settings, work / "before", fake_api=True, record_fixtures=False)
            sv, _ = await load_set(replay, opts.set_file)
        old = {d.id: d for d in collect(sv)}
        unknown = [k for k in briefs if k not in old]
        if unknown:
            raise ValueError(f"no drawing {', '.join(unknown)} (ids as the report gives them)")
        for k in briefs:
            # the last review's thumbnail is the drawing it reviewed; kept as it is
            if k not in before or not (opts.out / before[k].picture).is_file():
                thumb = Path("pictures") / f"{_safe(k)}-{_digest(Path(old[k].file))}.jpg"
                thumbnail(Path(old[k].file), opts.out / thumb)
                before[k] = Review(
                    id=k,
                    title=title_of(old[k]),
                    kind=old[k].kind,
                    picture=str(thumb),
                    subject=old[k].subject,
                    kinds=old[k].kinds,
                    facts=old[k].facts,
                )
        new: dict[str, Drawing] = {}
        if opts.data:
            new = await _redraw_data(settings, sv, old, briefs, budget, report)
        else:
            new = await _redraw_set(settings, opts, old, briefs, budget, report, work)
        client = reviewer(_scratch(settings, work / "review"), opts.max_usd)
        try:
            for k, brief in briefs.items():
                entry = Redrawn(id=k, brief=brief, before=before[k])
                d = new.get(k)
                if d is None:
                    entry.error = entry.error or "not drawn"
                    report.redrawn.append(entry)
                    continue
                after = await review_all(
                    client,
                    settings,
                    [d],
                    opts.out,
                    budget,
                    suffix=f"-{_digest(Path(d.file))}",
                    skipped=report.skipped,
                )
                entry.after = after[0]
                report.redrawn.append(entry)
                report.reviews.append(after[0])
        finally:
            await client.aclose()
        contact_sheet(
            [
                (f"{r.id} {r.before.verdict}", opts.out / r.before.picture)
                for r in report.redrawn
                if r.before.picture and (opts.out / r.before.picture).is_file()
            ],
            opts.out / "before.jpg",
        )
        contact_sheet(
            [
                (f"{r.id} {r.after.verdict}", opts.out / r.after.picture)
                for r in report.redrawn
                if r.after is not None and r.after.picture
            ],
            opts.out / "after.jpg",
        )
        report.cost_usd = budget.spent
        if last is not None:
            # the review stands for the drawings as they are now: the next redraw starts there
            fresh = {r.id: r for r in report.reviews}
            last.reviews = [fresh.get(r.id, r) for r in last.reviews]
            last.cost_usd = round(last.cost_usd + report.cost_usd, 6)
            write(last, opts.out)
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def drawings_cap(left_usd: float) -> float:
    """The record run's ledger cap: the ledger refuses a call only once its total has reached
    the cap, so the cap allows whole drawings alone, never one that would pass ``left_usd``."""
    whole = int((left_usd + 1e-9) / IMAGE_USD)
    return max(whole * IMAGE_USD - 1e-9, 0.0)


async def _redraw_set(
    settings: Settings,
    opts: Options,
    old: dict[str, Drawing],
    briefs: dict[str, str],
    budget: Budget,
    report: Report,
    work: Path,
) -> dict[str, Drawing]:
    """The briefs written into the set; one record run in which only drawings are bought (every
    other answer replays its recording); then the set replayed, as the demo will be."""
    text = opts.set_file.read_text(encoding="utf-8")
    written = apply(text, set_briefs(list(old.values()), briefs))
    opts.set_file.write_text(written, encoding="utf-8")
    print(f"wrote {len(briefs)} brief(s) into {opts.set_file}")
    # the most the drawings may take: what the run has left after a review of each
    review_ceiling = ceiling_usd(settings.model_spark, REVIEW_INPUT_ALLOWANCE, REVIEW_OUTPUT_TOKENS)
    left = max(opts.max_usd - budget.spent - review_ceiling * len(briefs), 0.0)
    cap = drawings_cap(left)
    record = _scratch(
        settings, work / "record", fake_api=False, record_fixtures=True, picture_enabled=True
    )
    client = PicturesOnlyClient(record, CostLedger(cap))
    _, notes = await load_set(record, opts.set_file, client)
    drawn = client.ledger.total_usd
    budget.add(drawn)
    report.load += [f"record run: {n}" for n in notes]
    replay = _scratch(settings, work / "after", fake_api=True, record_fixtures=False)
    sv, notes = await load_set(replay, opts.set_file)
    report.load += [f"replay: {n}" for n in notes]
    return {d.id: d for d in collect(sv) if d.id in briefs}


async def _redraw_data(
    settings: Settings,
    sv: Services,
    old: dict[str, Drawing],
    briefs: dict[str, str],
    budget: Budget,
    report: Report,
) -> dict[str, Drawing]:
    """A new drawing after the old ones, in the inventory as it stands."""
    live = settings.model_copy(update={"picture_enabled": True, "record_fixtures": False})
    client = ModelApiClient(live, CostLedger(settings.spend_cap_usd, settings.spend_ledger_path))
    pictures = Pictures(live, client, sv.inventory, sv.pictures.templates)
    image_ceiling = IMAGE_USD
    out: dict[str, Drawing] = {}
    try:
        for k, brief in briefs.items():
            d = old[k]
            if not budget.allows(image_ceiling):
                report.skipped.append(f"{k}: not drawn, it could pass --max-usd")
                continue
            try:
                if d.kind == "item":
                    pic = await pictures.draw(d.item_id, d.use, brief)
                elif d.kind == "card":
                    cards = sv.decider.scenarios_by_id(d.item_id, d.scenarios_id)
                    pic = await pictures.draw_card(cards, d.card, brief)
                else:
                    project = sv.planner.project(d.project_id)
                    pic = await pictures.draw_project(project, d.view, brief)
            except (ModelApiError, LookupError, ValueError) as exc:
                report.skipped.append(f"{k}: {exc}")
                continue
            budget.add(pic.cost_usd)
            fresh = {x.id: x for x in collect(sv)}
            new_id = f"{k.split('#')[0]}#{pic.n}"
            if new_id in fresh:
                out[k] = fresh[new_id]
    finally:
        await client.aclose()
    return out


# --- tuning -------------------------------------------------------------------------------


def last_review(out: Path) -> Report:
    path = out / "report.json"
    if not path.is_file():
        raise ValueError(f"no review at {path}: run ./dev picture-review first")
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    if "dry run" in report.mode or not any(
        r.verdict in ("matches", "partly", "wrong") for r in report.reviews
    ):
        raise ValueError(f"{path} reviews nothing: run ./dev picture-review first")
    return report


async def with_subjects(settings: Settings, opts: Options, report: Report) -> Report:
    """A review written before drawings carried their subject: the set replayed (nothing
    spent) and each drawing's subject and kinds of part filled in by its id."""
    if all(r.subject or r.kinds for r in report.reviews):
        return report
    work = Path(tempfile.mkdtemp(prefix="picture-subjects-"))
    try:
        replay = _scratch(settings, work / "data", fake_api=True, record_fixtures=False)
        sv, _ = await load_set(replay, opts.set_file)
        by_id = {d.id: d for d in collect(sv)}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for r in report.reviews:
        d = by_id.get(r.id)
        if d is not None and not (r.subject or r.kinds):
            r.subject, r.kinds = d.subject, d.kinds
    return report


def approved_corrections(set_file: Path) -> dict[str, str]:
    """The corrections the demo set keeps for its projects, by template id or title."""
    from app.demo.service import load_set as read_set

    if not set_file.is_file():
        return {}
    demo = read_set(set_file)
    if demo.propose is None:
        return {}
    return {str(k): str(v) for k, v in demo.propose.corrections.items() if str(v).strip()}


def _same_version(report: Report, params: DrawingParams) -> None:
    if report.params_version and report.params_version != params.version:
        raise ValueError(
            f"the last review is of parameters version {report.params_version}, the file is"
            f" at {params.version}: run ./dev picture-review --redraw-set first"
        )


async def run_tune(settings: Settings, opts: Options) -> tune.Proposal:
    """Edits to the parameters from the last review: the rules, then the corrections phrased
    by one call (none in a dry run or in fixture mode)."""
    report = last_review(opts.out)
    params = load_params()
    _same_version(report, params)
    report = await with_subjects(settings, opts, report)
    agg = tune.aggregate(report, params.version)
    templates = Templates()
    labels = {tid: templates.get(tid).label for tid in templates.ids()}
    edits = tune.rule_edits(agg, params)
    phrased, usd = None, 0.0
    approved = approved_corrections(opts.set_file)
    text = tune.phrase_input(agg, params, labels, approved)
    live = settings.model_api_mode != "fixture" and not opts.dry_run
    if live and text:
        ceiling = ceiling_usd(
            settings.model_spark, tune.TUNE_INPUT_ALLOWANCE, tune.TUNE_OUTPUT_TOKENS
        )
        if ceiling > opts.max_usd:
            raise ValueError(f"the phrasing call could cost {ceiling:.4f} USD, over --max-usd")
        work = Path(tempfile.mkdtemp(prefix="picture-tune-"))
        client = reviewer(_scratch(settings, work), opts.max_usd)
        try:
            phrased, usd = await tune.phrase(client, settings.model_spark, text)
        finally:
            await client.aclose()
            shutil.rmtree(work, ignore_errors=True)
    corrections = tune.correction_edits(agg, params, phrased, labels)
    taken = {e.path.split(".", 1)[1] for e in corrections if e.path.startswith("projects.")}
    edits += corrections + tune.promoted_edits(agg, params, approved, labels, taken)
    proposal = tune.Proposal(
        at=_now(),
        from_version=params.version,
        to_version=params.version + 1,
        report_at=report.at,
        edits=edits,
        aggregate=agg,
        model=settings.model_spark if phrased else "",
        cost_usd=usd,
        phrased=phrased is not None,
    )
    opts.out.mkdir(parents=True, exist_ok=True)
    (opts.out / "tune.json").write_text(tune.dumps(proposal), encoding="utf-8")
    (opts.out / "tune.md").write_text(tune.proposal_markdown(proposal, params), encoding="utf-8")
    return proposal


def set_size(out: Path) -> int:
    """How many drawings the reviews after a whole redraw are kept for: as many as the last
    review had, else a set's worth."""
    path = out / "report.json"
    try:
        found = len(Report.model_validate_json(path.read_text(encoding="utf-8")).reviews)
    except (OSError, ValueError):
        found = 0
    return found or SET_DRAWINGS


async def run_redraw_set(settings: Settings, opts: Options) -> Report:
    """Every drawing of the set with the parameters as they are: one record run in which only
    drawings are bought (a drawing whose request is unchanged replays its recording), the set
    replayed, every drawing reviewed."""
    params = load_params()
    work = Path(tempfile.mkdtemp(prefix="picture-redraw-set-"))
    budget = Budget(opts.max_usd)
    report = Report(
        at=_now(),
        source=str(opts.set_file),
        mode=f"demo set, drawn with parameters version {params.version}",
        model=settings.model_spark,
        params_version=params.version,
    )
    try:
        record = _scratch(
            settings, work / "record", fake_api=False, record_fixtures=True, picture_enabled=True
        )
        # the drawings take what the reviews of a set this size leave: whole drawings alone
        review_ceiling = ceiling_usd(
            settings.model_spark, REVIEW_INPUT_ALLOWANCE, REVIEW_OUTPUT_TOKENS
        )
        cap = drawings_cap(max(opts.max_usd - review_ceiling * set_size(opts.out), 0.0))
        client = PicturesOnlyClient(record, CostLedger(cap))
        _, notes = await load_set(record, opts.set_file, client)
        budget.add(client.ledger.total_usd)
        report.load += [f"record run: {n}" for n in notes]
        replay = _scratch(settings, work / "after", fake_api=True, record_fixtures=False)
        sv, notes = await load_set(replay, opts.set_file)
        report.load += [f"replay: {n}" for n in notes]
        drawings = [d for d in collect(sv) if not opts.only or selected(d.id, opts.only)]
        review_client = reviewer(_scratch(settings, work / "review"), opts.max_usd)
        try:
            report.reviews = await review_all(
                review_client, settings, drawings, opts.out, budget, skipped=report.skipped
            )
        finally:
            await review_client.aclose()
        report.cost_usd = budget.spent
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def run_evaluate(settings: Settings, opts: Options) -> tuple[tune.Evaluation, list[str]]:
    """What the last review scored, kept for its version of the parameters, compared with the
    version before; the recordings that version used and this one does not (deleted with
    --prune)."""
    report = last_review(opts.out)
    params = load_params()
    _same_version(report, params)
    report = await with_subjects(settings, opts, report)
    folder = opts.eval_dir or default_eval_dir()
    folder.mkdir(parents=True, exist_ok=True)
    ev = tune.evaluation(report, params, settings.model_image, opts.stage)
    tune.eval_path(folder, params.version, opts.stage).write_text(tune.dumps(ev), encoding="utf-8")
    evals = tune.history(folder)
    at = next(
        n
        for n, e in enumerate(evals)
        if (e.params_version, e.stage) == (ev.params_version, ev.stage)
    )
    earlier = evals[:at]
    lines = ["# Drawing parameters, version by version", "", tune.table(evals), ""]
    notes: list[str] = []
    if earlier:
        moved = tune.changes(earlier[-1], ev)
        if moved:
            lines += [f"Moved since {tune.label(earlier[-1])}:", ""]
            lines += [f"- {m}" for m in moved] + [""]
        unused = tune.unused_recordings(earlier[-1], ev)
        if unused and opts.prune:
            removed = tune.prune(settings.fixtures_dir, unused)
            notes.append(f"removed {len(removed)} file(s) of {len(unused)} unused recording(s)")
        elif unused:
            notes.append(
                f"{len(unused)} recording(s) of {tune.label(earlier[-1])} unused"
                " now (--prune deletes them): " + ", ".join(unused)
            )
    (opts.out / "compare.md").write_text("\n".join(lines), encoding="utf-8")
    contact_sheet(
        [
            (f"{r.id} {r.verdict}", opts.out / r.picture)
            for r in report.reviews
            if r.picture and (opts.out / r.picture).is_file()
        ],
        opts.out / f"sheet-v{params.version}.jpg",
    )
    if opts.results is not None:
        if tune.write_history(opts.results, evals):
            notes.append(f"wrote the history into {opts.results}")
        else:
            notes.append(f"{opts.results} has no history markers; nothing written there")
    return ev, notes


def default_eval_dir() -> Path:
    return _repo_root() / "eval" / "pictures"


# --- command line --------------------------------------------------------------------------


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def parse(argv: list[str]) -> Options | str:
    opts = Options(set_file=default_set(), out=default_out())
    args = list(argv)
    while args:
        arg = args.pop(0)
        needs = arg in (
            "--set",
            "--out",
            "--only",
            "--max-usd",
            "--redraw",
            "--brief",
            "--briefs",
            "--eval-dir",
            "--results",
            "--stage",
            "--candidates",
        )
        if needs and not args:
            return f"{arg} needs a value"
        if arg == "--set":
            opts.set_file = Path(args.pop(0))
        elif arg == "--out":
            opts.out = Path(args.pop(0))
        elif arg == "--only":
            opts.only = _split(args.pop(0))
        elif arg == "--max-usd":
            try:
                opts.max_usd = float(args.pop(0))
            except ValueError:
                return "--max-usd needs a number"
            if opts.max_usd < 0:
                return "--max-usd must not be negative"
        elif arg == "--redraw":
            opts.redraw = _split(args.pop(0))
        elif arg == "--brief":
            opts.brief = args.pop(0)
        elif arg == "--briefs":
            opts.briefs = Path(args.pop(0))
        elif arg == "--eval-dir":
            opts.eval_dir = Path(args.pop(0))
        elif arg == "--results":
            opts.results = Path(args.pop(0))
        elif arg == "--stage":
            opts.stage = args.pop(0).strip().lower()
            if not tune.STAGE.fullmatch(opts.stage):
                return "--stage is a short word: letters, digits and dashes"
        elif arg == "--candidates":
            try:
                opts.candidates = int(args.pop(0))
            except ValueError:
                return "--candidates needs a whole number"
            if not 1 <= opts.candidates <= MAX_CANDIDATES:
                return f"--candidates is 1 to {MAX_CANDIDATES}"
        elif arg == "--tune":
            opts.tune = True
        elif arg == "--apply":
            opts.apply = True
        elif arg == "--redraw-set":
            opts.redraw_set = True
        elif arg == "--evaluate":
            opts.evaluate = True
        elif arg == "--prune":
            opts.prune = True
        elif arg == "--data":
            opts.data = True
        elif arg == "--dry-run":
            opts.dry_run = True
        elif arg == "--decide":
            opts.decide = True
        elif arg in ("-h", "--help"):
            return "help"
        else:
            # only an option's name is said back, never a value (a key pasted by mistake)
            shown = arg.split("=", 1)[0] if arg.startswith("-") else "(a value)"
            return f"unknown argument {shown[:40]}"
    if (opts.brief or opts.briefs) and not opts.redraw:
        return "--brief and --briefs go with --redraw"
    if opts.redraw and opts.dry_run:
        return "--redraw draws; it has no dry run (review with --dry-run first)"
    modes = [opts.tune, opts.redraw_set, opts.evaluate, bool(opts.redraw), bool(opts.candidates)]
    if sum(modes) > 1:
        return "--tune, --redraw-set, --evaluate, --redraw and --candidates go one at a time"
    if opts.stage and not opts.evaluate:
        return "--stage goes with --evaluate"
    if opts.candidates and (opts.data or opts.dry_run):
        return "--candidates draws on the demo set; it has no dry run and no --data"
    if opts.apply and not opts.tune:
        return "--apply goes with --tune"
    if opts.prune and not opts.evaluate:
        return "--prune goes with --evaluate"
    if (opts.redraw_set or opts.tune or opts.evaluate) and opts.data:
        return "the tuning works on the demo set, not --data"
    if opts.redraw_set and opts.dry_run:
        return "--redraw-set draws; it has no dry run"
    return opts


def refused(exc: ValueError) -> str:
    """Why the settings were refused, without the values they were given: a validation error
    prints its input, and the key is part of it."""
    if isinstance(exc, ValidationError):
        return "; ".join(str(e["msg"]) for e in exc.errors(include_url=False, include_input=False))
    return str(exc)


def main(argv: list[str] | None = None) -> int:
    parsed = parse(list(sys.argv[1:] if argv is None else argv))
    if parsed == "help":
        print(__doc__)
        return 0
    if isinstance(parsed, str):
        print(f"picture-review: {parsed}", file=sys.stderr)
        return 2
    opts = parsed
    try:
        settings = get_settings()
    except ValueError as exc:
        if not (opts.dry_run or opts.evaluate or (opts.tune and opts.apply)):
            print(f"picture-review: the settings are refused: {refused(exc)}", file=sys.stderr)
            print(
                "picture-review: a review needs MODEL_API_KEY; --dry-run needs none",
                file=sys.stderr,
            )
            return 1
        try:
            settings = Settings(OPL_FAKE_API=True)
        except ValueError as again:
            # a validation error prints its input; the reasons alone
            print(f"picture-review: the settings are refused: {refused(again)}", file=sys.stderr)
            return 1
    if not opts.data and not opts.set_file.is_file():
        print(f"picture-review: no set at {opts.set_file}", file=sys.stderr)
        return 1
    if opts.tune and opts.apply:
        try:
            new = tune.apply_proposal(opts.out / "tune.json")
        except (ValueError, OSError) as exc:
            print(f"picture-review: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {PARAMS_FILE.name}: version {new.version}")
        print("next: ./dev picture-review --redraw-set, then --evaluate")
        return 0
    if opts.evaluate:
        try:
            ev, notes = asyncio.run(run_evaluate(settings, opts))
        except (ValueError, OSError) as exc:
            print(f"picture-review: {exc}", file=sys.stderr)
            return 1
        said = ", ".join(f"{ev.verdicts.get(v, 0)} {v}" for v in tune.VERDICTS)
        print(f"parameters version {ev.params_version}: {ev.drawings} drawing(s), {said}")
        for line in notes:
            print(line)
        print(f"wrote {opts.out / 'compare.md'}")
        return 0
    if opts.tune:
        try:
            proposal = asyncio.run(run_tune(settings, opts))
        except (ValueError, OSError) as exc:
            print(f"picture-review: {exc}", file=sys.stderr)
            return 1
        print(
            f"{len(proposal.edits)} edit(s) proposed, version {proposal.from_version} to"
            f" {proposal.to_version}; {proposal.cost_usd:.4f} USD"
        )
        print(f"wrote {opts.out / 'tune.md'} and {opts.out / 'tune.json'}")
        return 0
    if opts.redraw_set and settings.model_api_mode == "fixture":
        print(
            "picture-review: --redraw-set draws and records; it needs MODEL_API_KEY and"
            " OPL_FAKE_API off",
            file=sys.stderr,
        )
        return 1
    if opts.redraw and settings.model_api_mode == "fixture" and not opts.data:
        print(
            "picture-review: --redraw draws and records; it needs MODEL_API_KEY and"
            " OPL_FAKE_API off",
            file=sys.stderr,
        )
        return 1
    if opts.candidates:
        if settings.model_api_mode == "fixture":
            print(
                "picture-review: --candidates draws and records; it needs MODEL_API_KEY and"
                " OPL_FAKE_API off",
                file=sys.stderr,
            )
            return 1
        from app.picture.best import run_candidates

        try:
            run = asyncio.run(run_candidates(settings, opts))
        except (ValueError, KeyError, OSError) as exc:
            print(f"picture-review: {exc}", file=sys.stderr)
            return 1
        for line in run.load:
            print(line)
        for line in run.skipped:
            print(f"skipped: {line}")
        better = [o for o in run.outcomes if o.winner is not None]
        for o in run.outcomes:
            got = [c.review.verdict if c.review else "error" for c in o.candidates]
            was = o.before.verdict if o.before else "-"
            kept = f"candidate {o.winner + 1}" if o.winner is not None else "as it was"
            print(f"{o.id}: {was}; candidates {', '.join(got)}; kept {kept}")
        print(f"wrote {opts.out / 'candidates.md'}")
        print(
            f"{len(run.outcomes)} drawing(s), {len(better)} replaced by a better candidate;"
            f" {run.cost_usd:.4f} USD"
        )
        return 0
    try:
        if opts.redraw_set:
            report = asyncio.run(run_redraw_set(settings, opts))
            paths = write(report, opts.out)
        elif opts.redraw:
            report = asyncio.run(run_redraw(settings, opts))
            paths = write(report, opts.out, "redraw")
        else:
            report = asyncio.run(run_review(settings, opts))
            paths = write(report, opts.out)
    except (ValueError, KeyError, OSError) as exc:
        print(f"picture-review: {exc}", file=sys.stderr)
        return 1
    for line in report.load:
        print(line)
    for line in report.skipped:
        print(f"skipped: {line}")
    for path in paths:
        print(f"wrote {path}")
    counts = report.counts()
    said = ", ".join(f"{counts[k]} {k}" for k in sorted(counts)) or "nothing reviewed"
    print(f"{len(report.reviews)} drawing(s): {said}; {report.cost_usd:.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
