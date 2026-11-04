"""The review gate: a drawing the owner asks for is checked once by Muse Spark against the
facts it had to show, as ``./dev picture-review`` checks the demo set's. When it shows another
kind of device, or the main part at the wrong size, it is drawn once more with the review's
brief and that drawing is checked too (``PICTURE_CANDIDATES`` above 1: that many corrected
candidates, each with its own framing, while the spend cap leaves room for one more and its
check). All are kept; the best is shown, the others are marked ``hidden``. Each check's
cost is on the picture's record and in the spend ledger.

On with ``PICTURE_REVIEW_GATE=1``; unset, it is on when the calls are live and off in fixture
mode (where a check answers only from a recording). Only the owner's draws go through it: a
demo visitor's drawing is answered from the recordings and never checked or drawn again, and
the demo set's loader never goes through it either (the set's drawings stay one request each).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from PIL import UnidentifiedImageError

from app.decide.schema import Scenarios
from app.extract.imaging import BadImageError
from app.model_api import ModelApiError
from app.ops.door import for_visitor, recorded_request
from app.picture.best import candidate_briefs, score
from app.picture.params import load as load_params
from app.picture.review import (
    IMAGE_USD,
    REVIEW_INPUT_ALLOWANCE,
    REVIEW_OUTPUT_TOKENS,
    Drawing,
    Facts,
    Kind,
    ReviewAnswer,
    card_facts,
    ceiling_usd,
    item_facts,
    project_facts,
    review_one,
    subject_of,
)
from app.picture.service import (
    Picture,
    PictureCheck,
    Pictures,
    card_prompt,
    keep_record,
    prompt_for,
)
from app.projects.schema import Project

log = logging.getLogger("app.picture.gate")
# a drawing is drawn again only when it misleads about what gets built
REDRAW_ON = frozenset({"scale", "wrong_device"})
RANK = {"matches": 2, "partly": 1, "wrong": 0}


def needs_redraw(answer: ReviewAnswer) -> bool:
    """Wrong, or partly with the main part at the wrong size or drawn as another device; and
    the review said how to draw it instead."""
    if not answer.brief.strip():
        return False
    if answer.verdict == "wrong":
        return True
    return answer.verdict == "partly" and any(i.category in REDRAW_ON for i in answer.issues)


def second_is_better(first: PictureCheck | None, second: PictureCheck | None) -> bool:
    """The redraw is shown when its verdict is better, or as good with no more issues: it was
    drawn with the correction."""
    if second is None:
        return False
    if first is None:
        return True
    a = (RANK.get(first.verdict, -1), -len(first.issues))
    b = (RANK.get(second.verdict, -1), -len(second.issues))
    return b >= a


def _issues(picture: Picture) -> int:
    return len(picture.check.issues) if picture.check else 0


def as_check(answer: ReviewAnswer, usd: float, redraw_of: int = 0) -> PictureCheck:
    return PictureCheck(
        verdict=answer.verdict,
        issues=[f"{i.category}: {' '.join(i.detail.split())[:200]}" for i in answer.issues],
        cost_usd=usd,
        redraw_of=redraw_of,
    )


Draw = Callable[[str], Awaitable[Picture]]
FactsOf = Callable[[Picture, str], Facts]


class PictureGate:
    def __init__(self, pictures: Pictures) -> None:
        self.pictures = pictures
        self.settings = pictures.settings
        self.client = pictures.client

    @property
    def on(self) -> bool:
        # a visitor's calls go to the recordings, and so do a code's kept on them: a check
        # there would be a stand-in answer
        return self.settings.picture_gate_on and not for_visitor() and not recorded_request.get()

    async def _check(
        self, folder: Path, kind: Kind, picture: Picture, facts: Facts
    ) -> tuple[ReviewAnswer, float] | None:
        drawing = Drawing(
            id=f"{kind}#{picture.n}",
            kind=kind,
            n=picture.n,
            file=str(folder / f"picture-{picture.n}.jpg"),
            use=picture.use,
            facts=facts,
        )
        try:
            return await review_one(self.client, self.settings, drawing)
        except (ModelApiError, BadImageError, UnidentifiedImageError, OSError, ValueError) as exc:
            log.warning("picture check skipped", extra={"n": picture.n, "error": str(exc)[:200]})
            return None

    def _room(self) -> bool:
        """Whether the spend cap leaves room for one more drawing and its check."""
        ceiling = IMAGE_USD + ceiling_usd(
            self.settings.model_spark, REVIEW_INPUT_ALLOWANCE, REVIEW_OUTPUT_TOKENS
        )
        return self.client.ledger.remaining_usd >= ceiling

    async def _run(
        self, folder: Path, kind: Kind, draw: Draw, facts_of: FactsOf, *, view: bool = False
    ) -> Picture:
        first = await draw("")
        if not self.on:
            return first
        checked = await self._check(folder, kind, first, facts_of(first, ""))
        if checked is None:
            return first
        answer, usd = checked
        first.check = as_check(answer, usd)
        keep_record(folder, first)
        if not needs_redraw(answer):
            return first
        # one corrected drawing, or PICTURE_CANDIDATES of them, each with its own brief
        briefs = candidate_briefs("", answer.brief, self.settings.picture_candidates, view=view)
        drawn: list[tuple[Picture, float]] = []
        for n, brief in enumerate(briefs):
            if n and not self._room():
                log.info("picture candidates stopped at the cap", extra={"drawn": n})
                break
            try:
                second = await draw(brief)
            except (ModelApiError, LookupError) as exc:
                log.warning("picture redraw skipped", extra={"n": first.n, "error": str(exc)[:200]})
                break
            again = await self._check(folder, kind, second, facts_of(second, brief))
            second.check = (
                as_check(again[0], again[1], first.n)
                if again is not None
                else PictureCheck(verdict="not checked", redraw_of=first.n)
            )
            confidence = again[0].confidence if again is not None else 0.0
            drawn.append((second, confidence))
        if not drawn:
            return first
        # the best candidate (verdict, then confidence, then fewer issues; the first drawn on
        # a tie), then that one against the first drawing
        second = max(
            drawn,
            key=lambda pc: score(pc[0].check.verdict if pc[0].check else "", pc[1], _issues(pc[0])),
        )[0]
        shown = second if second_is_better(first.check, second.check) else first
        for pic in [first, *(p for p, _ in drawn)]:
            if pic is not shown:
                pic.hidden = True
                keep_record(folder, pic)
        keep_record(folder, shown)
        log.info(
            "picture gate",
            extra={
                "first": first.check.verdict,
                "candidates": len(drawn),
                "best": second.check.verdict if second.check else "",
                "shown": shown.n,
            },
        )
        return shown

    async def item(self, item_id: int, use: str | None) -> Picture:
        p = self.pictures
        folder = p.folder(item_id)

        def facts_of(pic: Picture, brief: str) -> Facts:
            item = p.inventory.get(item_id)
            params = load_params()
            return item_facts(
                item,
                pic.use,
                prompt_for(item, pic.use, brief),
                subject=subject_of(pic.use, p.templates, params),
                templates=p.templates,
                params=params,
            )

        return await self._run(folder, "item", lambda brief: p.draw(item_id, use, brief), facts_of)

    async def card(self, scenarios: Scenarios, card: int) -> Picture:
        p = self.pictures
        folder = p.card_folder(scenarios.item_id, scenarios.id, card)

        def facts_of(pic: Picture, brief: str) -> Facts:
            item = p.inventory.get(scenarios.item_id)
            reuse = scenarios.reuse[card]
            return card_facts(
                item,
                reuse,
                card_prompt(scenarios, card, item, brief),
                subject=subject_of(reuse.title, p.templates, load_params()),
                templates=p.templates,
            )

        return await self._run(
            folder, "card", lambda brief: p.draw_card(scenarios, card, brief), facts_of
        )

    async def project(self, project: Project, view: str = "") -> Picture:
        p = self.pictures
        folder = p.project_folder(project.id)

        def facts_of(pic: Picture, brief: str) -> Facts:
            return project_facts(
                project, p.allocated(project), view, p.project_prompt(project, view, brief)
            )

        return await self._run(
            folder,
            "project",
            lambda brief: p.draw_project(project, view, brief),
            facts_of,
            view=bool(view.strip()),
        )
