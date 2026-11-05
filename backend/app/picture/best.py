"""Best of N: a drawing drawn several times, each with its own brief, each reviewed, and the best
kept.

Muse Image draws a different picture for every request, and one request can miss where the next
lands. ``./dev picture-review --candidates N`` draws each chosen drawing of the demo set N more
times, each candidate a request of its own (the corrected brief, then the same brief with a
different framing or a narrower scene), reviews every candidate against the drawing's facts and
keeps the best by verdict, then confidence, then fewer issues; the drawing as it stands keeps
its place on a tie. Only the winner's brief is written into ``demo/set.yaml`` and only its
recording joins ``backend/tests/fixtures/api``; every candidate is kept under
``picture-review/candidates/`` for the report and never in the repository.

The owner's own clicks can do the same with ``PICTURE_CANDIDATES`` (the review gate draws that
many corrected candidates instead of one when the first drawing misleads; ``gate.py``).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from pydantic import BaseModel

from app.config import Settings
from app.model_api import CostLedger, ModelApiClient, ModelApiError
from app.model_api.client import IMAGES
from app.model_api.fixtures import FixtureStore
from app.picture import review as rv
from app.picture.briefs import apply
from app.picture.params import load as load_params
from app.picture.review import Drawing, Options, Report, Review, Services
from app.picture.service import Pictures, card_prompt, prompt_for
from app.picture.tune import recording_of

BRIEF_MAX = 400
RANK = {"matches": 2, "partly": 1, "wrong": 0}

# what changes from one candidate to the next: a drawing with no view of its own gets another
# framing; a view (a close-up, from above) keeps its framing and gets a narrower scene
FRAMINGS = (
    "",
    "seen at eye level from across the room, every part at its true size against the furniture",
    "a three-quarter view from slightly above, the main part centered and its real size clear",
    "a calm daylight scene with only the parts listed and the furniture they stand on",
    "a closer view of the main part in place, the room around it still in sight",
    "a plain, uncluttered home setting, nothing on the walls or the table but the build",
)
SCENES = (
    "",
    "only the parts listed, nothing extra on the table, every part at its true size",
    "soft daylight, a clean uncluttered composition, the parts side by side at real scale",
    "the main part fills the middle of the picture, the smaller parts in front of it",
    "fewer objects: the build alone on a plain table or wall",
    "every cable short and tidy, no second copy of any part",
)


def compose(base: str, variant: str, limit: int = BRIEF_MAX) -> str:
    """A candidate's brief: the correction, cut to leave room for the variant, then the
    variant."""
    base = " ".join(base.split())
    variant = " ".join(variant.split())
    if not variant:
        return base[:limit]
    room = limit - len(variant) - 2
    if room <= 0 or not base:
        return variant[:limit]
    return f"{base[:room].rstrip(' ;,.')}; {variant}"


def candidate_briefs(current: str, proposed: str, n: int, *, view: bool) -> list[str]:
    """``n`` briefs, each different from the one the drawing was asked with and from each
    other: the review's corrected brief when there is one (else the current brief), alone and
    then with each variant in turn."""
    base = proposed.strip() or current.strip()
    pool = SCENES if view else FRAMINGS
    out: list[str] = []
    for variant in pool:
        text = compose(base, variant)
        if text and text != current.strip() and text not in out:
            out.append(text)
        if len(out) >= n:
            break
    return out


def score(verdict: str, confidence: float, issues: int) -> tuple[int, float, int]:
    """Better verdict first, then a surer review, then fewer issues."""
    return (RANK.get(verdict, -1), round(confidence, 2), -issues)


def review_score(r: Review | None) -> tuple[int, float, int]:
    if r is None:
        return (-1, 0.0, 0)
    return score(r.verdict, r.confidence, len(r.issues))


def pick(incumbent: Review | None, candidates: list[Review]) -> int | None:
    """The index of the best candidate, or None when the drawing as it stands is as good."""
    best, at = review_score(incumbent), None
    for n, c in enumerate(candidates):
        s = review_score(c)
        if s > best:
            best, at = s, n
    return at


class Candidate(BaseModel):
    brief: str
    review: Review | None = None
    file: str = ""
    error: str = ""


class Outcome(BaseModel):
    id: str
    title: str
    before: Review | None = None
    candidates: list[Candidate] = []
    winner: int | None = None


@dataclass
class Run:
    outcomes: list[Outcome] = field(default_factory=list)
    load: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    cost_usd: float = 0.0


def targets(drawings: list[Drawing], last: Report | None, only: list[str]) -> list[Drawing]:
    """The drawings ``--only`` names (``disliked`` and ``liked`` by the votes the last review
    kept), else every drawing the last review did not find matching and no person liked."""
    reviews = last.reviews if last else []
    if only:
        return rv.pick(drawings, only, {r.id: r.people for r in reviews})
    shown = {r.id: r for r in reviews}
    return [
        d
        for d in drawings
        if d.id in shown
        and shown[d.id].verdict in ("partly", "wrong")
        and not shown[d.id].people.liked
    ]


def current_brief(sv: Services, d: Drawing) -> str:
    if d.kind == "item":
        return sv.item_brief(d.item_id, "picture_brief")
    if d.kind == "card":
        return sv.item_brief(d.item_id, "reuse_picture_brief") if d.card == 0 else ""
    project = sv.planner.project(d.project_id)
    return sv.project_brief(project, d.view)


def markdown(run: Run, n: int) -> str:
    def said(r: Review | None) -> str:
        if r is None:
            return "-"
        return f"{r.verdict} ({r.confidence:.2f}, {len(r.issues)} issue(s))"

    better = sum(1 for o in run.outcomes if o.winner is not None)
    lines = [
        f"# Best of {n}",
        "",
        f"{len(run.outcomes)} drawing(s), {n} candidate(s) each; a candidate replaced the drawing"
        f" in {better}. Spent {run.cost_usd:.4f} USD.",
        "",
        "| drawing | before | best candidate | kept |",
        "|---|---|---|---|",
    ]
    for o in run.outcomes:
        reviewed = [c.review for c in o.candidates if c.review is not None]
        top = max(reviewed, key=review_score, default=None)
        kept = f"candidate {o.winner + 1}" if o.winner is not None else "as it was"
        lines.append(f"| `{o.id}` | {said(o.before)} | {said(top)} | {kept} |")
    lines.append("")
    for o in run.outcomes:
        lines += [f"## `{o.id}` {o.title}", "", f"Before: {said(o.before)}", ""]
        for k, c in enumerate(o.candidates, 1):
            mark = " **kept**" if o.winner == k - 1 else ""
            lines.append(f"{k}. {said(c.review)}{mark}: {c.brief}")
            if c.review is not None and c.review.issues:
                lines += [f"   - {i.category}: {i.detail}" for i in c.review.issues]
            if c.error:
                lines.append(f"   - error: {c.error}")
        lines.append("")
    if run.load or run.skipped:
        lines += ["## Notes", ""] + [f"- {s}" for s in run.load + run.skipped] + [""]
    return "\n".join(lines).rstrip() + "\n"


async def run_candidates(settings: Settings, opts: Options) -> Run:
    """Draw ``opts.candidates`` candidates of each target, review them, keep the best."""
    n = opts.candidates
    last_path = opts.out / "report.json"
    last = (
        Report.model_validate_json(last_path.read_text(encoding="utf-8"))
        if last_path.is_file()
        else None
    )
    if last is not None and "dry run" in last.mode:
        last = None
    params = load_params()
    if last is not None and last.params_version and last.params_version != params.version:
        raise ValueError(
            f"the last review is of parameters version {last.params_version}, the file is at"
            f" {params.version}: run ./dev picture-review --redraw-set first"
        )
    before = {r.id: r for r in (last.reviews if last else [])}
    work = Path(tempfile.mkdtemp(prefix="picture-candidates-"))
    run = Run()
    budget = rv.Budget(opts.max_usd)
    review_ceiling = rv.ceiling_usd(
        settings.model_spark, rv.REVIEW_INPUT_ALLOWANCE, rv.REVIEW_OUTPUT_TOKENS
    )
    try:
        data = work / "data"
        replay = rv._scratch(settings, data, fake_api=True, record_fixtures=False)
        sv, _ = await rv.load_set(replay, opts.set_file)
        drawings = rv.collect(sv)
        chosen = targets(drawings, last, opts.only)
        if not chosen:
            raise ValueError("no drawing to draw again: name them with --only")
        # what each target is drawn with: its own candidates, in turn, so a cap cuts the last
        # candidates of every drawing rather than every candidate of the last drawings
        plans: list[tuple[Drawing, list[str]]] = []
        for d in chosen:
            if d.kind == "card" and d.card != 0:
                run.skipped.append(f"{d.id}: the set draws the first reuse card alone")
                continue
            if d.kind == "item" and not rv.first_of_item(drawings, d):
                run.skipped.append(f"{d.id}: the set gives a brief to an item's first drawing")
                continue
            r = before.get(d.id)
            proposed = r.brief if r is not None and r.verdict != "matches" else ""
            briefs = candidate_briefs(current_brief(sv, d), proposed, n, view=bool(d.view))
            plans.append((d, briefs))
        per_draw = rv.IMAGE_USD + review_ceiling
        allowed = int((opts.max_usd + 1e-9) // per_draw)
        queue: list[tuple[Drawing, str]] = []
        for k in range(n):
            for d, briefs in plans:
                if k < len(briefs):
                    queue.append((d, briefs[k]))
        if len(queue) > allowed:
            run.skipped += [
                f"{d.id}: candidate not drawn, over --max-usd" for d, _ in queue[allowed:]
            ]
            queue = queue[:allowed]
        record = settings.model_copy(
            update={
                "data_dir": data,
                "fake_api": False,
                "record_fixtures": True,
                "picture_enabled": True,
                "fixtures_dir": work / "fixtures",
            }
        )
        cap = rv.drawings_cap(max(opts.max_usd - review_ceiling * len(queue), 0.0))
        client = ModelApiClient(record, CostLedger(cap))
        pictures = Pictures(record, client, sv.inventory, sv.pictures.templates)
        drawn: list[tuple[Drawing, str, int | None, str, str]] = []

        async def draw(d: Drawing, brief: str) -> tuple[Drawing, str, int | None, str, str]:
            """One candidate, and the request it was drawn with (its recording's key)."""
            try:
                if d.kind == "item":
                    item = sv.inventory.get(d.item_id)
                    asked = prompt_for(item, pictures._use(d.use) or d.use, brief)
                    pic = await pictures.draw(d.item_id, d.use, brief)
                elif d.kind == "card":
                    cards = sv.decider.scenarios_by_id(d.item_id, d.scenarios_id)
                    item = sv.inventory.get(d.item_id)
                    asked = card_prompt(cards, d.card, item, brief)
                    pic = await pictures.draw_card(cards, d.card, brief)
                else:
                    project = sv.planner.project(d.project_id)
                    asked = pictures.project_prompt(project, d.view, brief)
                    pic = await pictures.draw_project(project, d.view, brief)
            except (ModelApiError, LookupError, ValueError) as exc:
                return d, brief, None, str(exc)[:300], ""
            return d, brief, pic.n, "", asked

        try:
            drawn = await rv._each([partial(draw, d, b) for d, b in queue])
        finally:
            await client.aclose()
        budget.add(client.ledger.total_usd)
        fresh = {x.id: x for x in rv.collect(sv)}
        new: list[Drawing] = []
        found: dict[str, list[tuple[str, Drawing | None, str]]] = {}
        for d, brief, number, error, asked in drawn:
            x = fresh.get(f"{d.id.split('#')[0]}#{number}") if number is not None else None
            if x is not None:
                # the facts say what this candidate was asked with, not the set's brief
                x = x.model_copy(update={"facts": x.facts.model_copy(update={"asked": asked})})
            found.setdefault(d.id, []).append((brief, x, error or ("" if x else "not drawn")))
            if x is not None:
                new.append(x)
        # each run's thumbnails and copies under names of their own
        stamp = "-c" + datetime.now(tz=UTC).strftime("%m%d%H%M%S")
        reviewer = rv.reviewer(rv._scratch(settings, work / "review"), opts.max_usd)
        try:
            reviews = await rv.review_all(
                reviewer, settings, new, opts.out, budget, suffix=stamp, skipped=run.skipped
            )
        finally:
            await reviewer.aclose()
        by_file = {x.file: r for x, r in zip(new, reviews, strict=True)}
        winners: dict[str, tuple[str, Review, Drawing]] = {}
        keep = opts.out / "candidates"
        for d, _ in plans:
            outcome = Outcome(id=d.id, title=rv.title_of(d), before=before.get(d.id))
            entries = found.get(d.id, [])
            for k, (brief, x, error) in enumerate(entries, 1):
                c = Candidate(brief=brief, error=error)
                if x is not None:
                    c.review = by_file.get(x.file)
                    if c.review is not None and c.review.verdict not in (
                        "matches",
                        "partly",
                        "wrong",
                    ):
                        c.review = None
                    target = keep / rv._safe(d.id) / f"{stamp.strip('-')}-{k}.jpg"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(x.file, target)
                    c.file = str(target)
                outcome.candidates.append(c)
            at = pick(outcome.before, [c.review for c in outcome.candidates])  # type: ignore[misc]
            if at is not None:
                outcome.winner = at
                won = outcome.candidates[at]
                x = entries[at][1]
                assert won.review is not None and x is not None
                winners[d.id] = (won.brief, won.review, x)
            run.outcomes.append(outcome)
        if winners:
            store = FixtureStore(work / "fixtures")
            target_dir = settings.fixtures_dir
            for won_id, (_brief, _r, x) in list(winners.items()):
                key = recording_of(settings.model_image, x.facts.asked)
                src = store.path_for(IMAGES, key)
                if not src.is_file():
                    run.skipped.append(f"{won_id}: the winner's recording was not found; kept")
                    del winners[won_id]
                    continue
                dst = FixtureStore(target_dir).path_for(IMAGES, key)
                dst.parent.mkdir(parents=True, exist_ok=True)
                for path in [src, *sorted(src.parent.glob(f"{key}-*"))]:
                    shutil.copyfile(path, dst.parent / path.name)
            text = opts.set_file.read_text(encoding="utf-8")
            olds = {d.id: d for d in drawings}
            written = apply(
                text,
                rv.set_briefs(list(olds.values()), {k: v[0] for k, v in winners.items()}),
            )
            opts.set_file.write_text(written, encoding="utf-8")
        for o in run.outcomes:
            if o.id not in winners:
                o.winner = None
        check = rv._scratch(settings, work / "after", fake_api=True, record_fixtures=False)
        sv_after, notes = await rv.load_set(check, opts.set_file)
        run.load += [f"replay: {x}" for x in notes]
        if last is not None:
            for won_id, (_, r, _x) in winners.items():
                kept = r.model_copy(update={"id": won_id})
                last.reviews = [kept if old.id == won_id else old for old in last.reviews]
            last.cost_usd = round(last.cost_usd + budget.spent, 6)
            rv.write(last, opts.out)
        rv.contact_sheet(
            [
                (f"{o.id} {o.before.verdict}", opts.out / o.before.picture)
                for o in run.outcomes
                if o.winner is not None
                and o.before is not None
                and (opts.out / o.before.picture).is_file()
            ],
            opts.out / "best-before.jpg",
        )
        rv.contact_sheet(
            [
                (f"{o.id} {winners[o.id][1].verdict}", opts.out / winners[o.id][1].picture)
                for o in run.outcomes
                if o.id in winners
            ],
            opts.out / "best-after.jpg",
        )
        del sv_after
        run.cost_usd = budget.spent
        (opts.out / "candidates.md").write_text(markdown(run, n), encoding="utf-8")
        return run
    finally:
        shutil.rmtree(work, ignore_errors=True)
