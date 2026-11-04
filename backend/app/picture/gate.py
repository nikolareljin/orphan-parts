"""The review gate: a drawing the owner asks for is checked once by Muse Spark against the
facts it had to show, as ``./dev picture-review`` checks the demo set's. When it shows another
kind of device, or the main part at the wrong size, it is drawn once more with the review's
brief and that drawing is checked too. Both are kept; the better one is shown, the other is
marked ``hidden``. Each check's cost is on the picture's record and in the spend ledger.

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
from app.ops.door import for_visitor
from app.picture.review import (
    Drawing,
    Facts,
    Kind,
    ReviewAnswer,
    describe,
    project_facts,
    review_one,
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
        # a visitor's calls go to the recordings: a check there would be a stand-in answer
        return self.settings.picture_gate_on and not for_visitor()

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

    async def _run(self, folder: Path, kind: Kind, draw: Draw, facts_of: FactsOf) -> Picture:
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
        try:
            second = await draw(answer.brief)
        except (ModelApiError, LookupError) as exc:
            log.warning("picture redraw skipped", extra={"n": first.n, "error": str(exc)[:200]})
            return first
        again = await self._check(folder, kind, second, facts_of(second, answer.brief))
        second.check = (
            as_check(again[0], again[1], first.n)
            if again is not None
            else PictureCheck(verdict="not checked", redraw_of=first.n)
        )
        shown, kept = (
            (second, first)
            if second_is_better(first.check, second.check)
            else (
                first,
                second,
            )
        )
        kept.hidden = True
        keep_record(folder, kept)
        keep_record(folder, shown)
        log.info(
            "picture gate",
            extra={
                "first": first.check.verdict,
                "second": second.check.verdict,
                "shown": shown.n,
            },
        )
        return shown

    async def item(self, item_id: int, use: str | None) -> Picture:
        p = self.pictures
        folder = p.folder(item_id)

        def facts_of(pic: Picture, brief: str) -> Facts:
            item = p.inventory.get(item_id)
            return Facts(
                title=pic.use,
                setting=pic.use,
                parts=[describe(item, as_built=False)],
                asked=prompt_for(item, pic.use, brief),
            )

        return await self._run(folder, "item", lambda brief: p.draw(item_id, use, brief), facts_of)

    async def card(self, scenarios: Scenarios, card: int) -> Picture:
        p = self.pictures
        folder = p.card_folder(scenarios.item_id, scenarios.id, card)

        def facts_of(pic: Picture, brief: str) -> Facts:
            item = p.inventory.get(scenarios.item_id)
            reuse = scenarios.reuse[card]
            return Facts(
                title=reuse.title,
                setting=reuse.what_it_does,
                parts=[describe(item)] + [f"another item: {w}" for w in reuse.with_items],
                still_to_get=list(reuse.extra_parts),
                asked=card_prompt(scenarios, card, item, brief),
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
            folder, "project", lambda brief: p.draw_project(project, view, brief), facts_of
        )
