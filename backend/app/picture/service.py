"""A picture of what an item could become, or of how a finished project could look, drawn by
Muse Image when the owner clicks.

Illustrative, never evidence: nothing about the item is read from it, no value rests on it,
and it is labeled as drawn wherever it is shown. An item's pictures are files under
``DATA_DIR/items/<id>/`` beside the photos, named ``picture-<n>.jpg`` with a
``picture-<n>.json`` record, so a picture is never counted as a photo of the item; the folder
goes with the item, as the photos do. A reuse card's pictures sit in a folder of their own
inside the item's (``scenarios-<id>-reuse-<k>/``), so they go with the item too; a project's
under ``DATA_DIR/projects/<id>/``. Every folder is numbered and read the same way.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, field_serializer

from app.config import Settings
from app.decide.schema import Scenarios
from app.extract.imaging import BadImageError, prepare
from app.feedback.steer import Steer, assemble, clean
from app.inventory.schema import Item
from app.inventory.service import Inventory, NotFoundError
from app.model_api import IncompleteResponseError, ModelApiClient
from app.ops.door import for_visitor
from app.picture.params import DrawingParams, name_sizes
from app.picture.params import load as load_params
from app.privacy.text import mask_text
from app.projects.pack import shown_fields
from app.projects.schema import Project
from app.projects.templates import Templates, UnknownTemplateError

log = logging.getLogger("app.picture")
PICTURE_NAME = re.compile(r"picture-(\d+)\.jpg")
OFF_LINE = "pictures are off on this server (PICTURE_ENABLED)"
USE_MAX = 200
# a finished project's prompt: what it is, the parts it is built from, one line on it
TITLE_MAX = 120
PARTS_MAX = 6
PART_VALUES = 3
VALUE_MAX = 60
TAIL = "on a plain background, no text, no logos, no people"
# a project is drawn finished, where it is used; never on a plain background, so the room,
# the wall or the table it belongs to is part of the picture
PROJECT_TAIL = "finished and in use in a home, no text, no logos, no people"
# what a part looks like today (its wear, a label blacked out) or the marks printed on it say
# nothing of the finished build, and drawn they turn into dust, blots and fake labels
AS_BUILT_LEFT_OUT = ("condition", "certification")
# how a finished project is shown, when another view of it is asked for
VIEW_MAX = 120
# a correction said with a drawing (what to show and what not, from a review of an earlier
# drawing); without one the prompt is word for word what it was, so its recording still answers
BRIEF_MAX = 400
# what an item cost or would fetch is the owner's business, never part of a picture
MONEY_WORDS = ("price", "cost", "paid", "msrp", "value", "worth", "resale", "retail")


class PicturesOffError(RuntimeError):
    """``PICTURE_ENABLED`` is not set: no call is made."""


class PictureCheck(BaseModel):
    """What the review gate found of a drawing (``PICTURE_REVIEW_GATE``)."""

    verdict: str = Field(description="matches, partly or wrong")
    issues: list[str] = []
    cost_usd: float = 0.0
    redraw_of: int = Field(default=0, description="the picture this one was drawn again for")


class Picture(BaseModel):
    """One picture kept on the item; the file is at ``/pictures/{n}``."""

    n: int
    use: str = Field(description="what the item was drawn as: a use the owner typed, or itself")
    model: str
    cost_usd: float
    from_fixture: bool
    created_at: str
    check: PictureCheck | None = None
    hidden: bool = Field(
        default=False, description="kept, but a drawing of the same request was judged better"
    )
    brief: str = Field(default="", description="the correction it was drawn with, if any")
    avoided: list[str] = Field(
        default=[], description="what it was drawn avoiding: the reasons of disliked drawings"
    )
    kept: str = Field(default="", description="what it kept: a liked drawing's correction")

    # the owner's own words: a product key or a password typed into them is masked for the
    # demo visitor, as an item's name is
    @field_serializer("use")
    def _shown_use(self, value: str) -> str:
        return mask_text(value) if for_visitor() else value

    # a vote's reason is its author's: the demo visitor reads none of them, nor the brief
    @field_serializer("brief", "kept")
    def _shown_text(self, value: str) -> str:
        return "" if for_visitor() else value

    @field_serializer("avoided")
    def _shown_avoided(self, value: list[str]) -> list[str]:
        return [] if for_visitor() else value


class PictureList(BaseModel):
    enabled: bool
    pictures: list[Picture]


def _line(text: str, limit: int = USE_MAX) -> str:
    return " ".join(text.split())[:limit]


def _params(params: DrawingParams | None) -> DrawingParams:
    return params if params is not None else load_params()


def said(segments: Sequence[str], tail: str) -> str:
    """The request: its segments in order, each once, then its closing words."""
    shown: list[str] = []
    for s in segments:
        if s and s.casefold() not in (x.casefold() for x in shown):
            shown.append(s)
    return f"{'; '.join(shown)}, {tail}" if shown else tail


def with_brief(body: str, brief: str, tail: str) -> str:
    """The prompt's body, the correction (when there is one) and its closing words: without a
    correction the prompt is exactly what it was."""
    return said([body, _line(brief, BRIEF_MAX)], tail)


def facts_of(
    item: Item,
    limit: int,
    params: DrawingParams,
    *,
    as_built: bool = False,
    cut: int | None = VALUE_MAX,
) -> list[str]:
    """An item's facts as a request says them: the sizes its name states (when the parameters
    say so), then its accepted values, those named first by the parameters before the rest,
    never one that identifies it or its owner, names money, or the parameters leave out."""
    rules = params.facts
    left_out = (
        MONEY_WORDS + tuple(rules.left_out) + (tuple(rules.left_out_as_built) if as_built else ())
    )
    values = [(k, v) for k, v in shown_fields(item) if not any(w in k.lower() for w in left_out)]
    if rules.first:
        values.sort(key=lambda kv: 0 if any(w in kv[0].lower() for w in rules.first) else 1)
    sizes = name_sizes(item.name, item.item_type, params)
    stated = [f"{k} {v}" if cut is None else _line(f"{k} {v}", cut) for k, v in values]
    return sizes + stated[:limit]


def _about(what: str, facts: list[str], looks: str) -> str:
    inner = ", ".join(facts)
    if looks:
        inner = f"{inner}; {looks}" if inner else looks
    return f"{what} ({inner})" if inner else what


def prompt_for(
    item: Item,
    use: str,
    brief: str = "",
    params: DrawingParams | None = None,
    steer: Sequence[str] = (),
) -> str:
    """What Muse Image is asked for: the chosen use built from the item as it is known, from
    its type and accepted values (and its condition and faults, when the parameters say so); a
    proposed value is not yet known, and a value that identifies the item or its owner (a
    serial, a MAC, an IMEI) never goes out. Then the correction of the kind of project the use
    names, ``brief`` (a correction from a review), ``steer`` (what people's votes say: what to
    avoid, what to keep), the negatives and the closing rules."""
    p = _params(params)
    what = item.item_type or item.name or "item"
    kind = p.kind(item.item_type)
    about = _about(
        what, facts_of(item, p.facts.item_values, p, cut=None), kind.looks if kind else ""
    )
    own = not use or use.lower() == what.lower()
    if own:
        head = f"a semi-realistic illustration of this {about}, cleaned up and ready to use"
    else:
        head = f"a semi-realistic illustration of {use} built from {about}"
    detail = []
    if p.facts.condition:
        if item.condition:
            detail.append(f"condition: {_line(item.condition)}")
        if item.faults:
            detail.append(f"known faults: {_line(item.faults)}")
    correction = "" if own else p.correction_for(text=use)
    return said(
        [head, *detail, correction, _line(brief, BRIEF_MAX), *steer, *p.negatives],
        p.rules.item if own else p.rules.use,
    )


def part_of(item: Item, *, as_built: bool = False, params: DrawingParams | None = None) -> str:
    """One part of a finished project as the prompt names it: the kind of item and its facts,
    never one that identifies it or its owner, never its name, location, notes or a price;
    ``as_built`` also leaves out what the parameters say a finished build does not show (its
    present condition, the marks printed on it)."""
    p = _params(params)
    what = _line(item.item_type, VALUE_MAX) or "item"
    kind = p.kind(item.item_type)
    facts = facts_of(item, p.facts.part_values, p, as_built=as_built)
    return _about(what, facts, kind.looks if kind else "")


def finished_prompt(
    title: str,
    parts: list[str],
    about: str,
    view: str = "",
    tail: str = TAIL,
    brief: str = "",
    *,
    correction: str = "",
    params: DrawingParams | None = None,
    steer: Sequence[str] = (),
) -> str:
    """What Muse Image is asked for a finished project: what it is, built from the parts the
    card uses (each once, at most six), and one line on it, and how it is shown when a view is
    asked for (in its room, a close-up, with the view's preset); then the correction of its
    kind of project, the brief and the negatives; every text cut to its bound."""
    p = _params(params)
    seen: list[str] = []
    for part in parts:
        text = _line(part, VALUE_MAX * 4)
        if text and text.casefold() not in (s.casefold() for s in seen):
            seen.append(text)
    what = _line(title, TITLE_MAX) or "a reused project"
    head = f"a semi-realistic illustration of {what}"
    if seen:
        head += f" built from {', '.join(seen[:PARTS_MAX])}"
    line = _line(about)
    shown = _line(view, VIEW_MAX)
    if shown:
        line = f"{line}; shown {shown}" if line else f"shown {shown}"
        preset = p.view_preset(shown)
        if preset:
            line = f"{line}; {_line(preset, BRIEF_MAX)}"
    return said(
        [head, line, _line(correction, BRIEF_MAX), _line(brief, BRIEF_MAX), *steer, *p.negatives],
        tail,
    )


# an owner's name for an item and the kind to say instead
Named = tuple[str, str]


def named(items: list[Item], others: Sequence[Named] = ()) -> list[Named]:
    return [(i.name, i.item_type or "item") for i in items] + list(others)


def without_names(text: str, names: list[Named]) -> str:
    """A text the model wrote, with each item's name (the owner's words, which its brief
    carried) said as the kind of item instead, whatever its letter case or spacing."""
    # the longest first, so a name inside another is not left half-said
    for name, kind in sorted(names, key=lambda pair: -len(pair[0].strip())):
        words = name.split()
        if len(" ".join(words)) < 2:
            continue
        pattern = r"\s+".join(re.escape(word) for word in words)
        said = (kind or "item").replace("\\", "\\\\")
        text = re.sub(pattern, said, text, flags=re.IGNORECASE)
    return text


def project_prompt(
    project: Project,
    items: list[Item],
    others: Sequence[Named] = (),
    view: str = "",
    brief: str = "",
    params: DrawingParams | None = None,
    steer: Sequence[str] = (),
) -> str:
    """A project as built, where it is used: its title, the items allocated to it (as built,
    not as they lie in the drawer), and what it results in, shown as ``view`` asks when given;
    no item's name, even where the model's title or result repeats one (``others``: the rest of
    the inventory's names, which the proposal could read too)."""
    p = _params(params)
    names = named(items, [*others, *((a.item_name, "item") for a in project.allocations)])
    return finished_prompt(
        without_names(project.title, names),
        [part_of(i, as_built=True, params=p) for i in items],
        without_names(project.result, names),
        view,
        p.rules.project,
        brief,
        correction=p.correction_for(project.template),
        params=p,
        steer=steer,
    )


def card_prompt(
    scenarios: Scenarios,
    card: int,
    item: Item,
    brief: str = "",
    params: DrawingParams | None = None,
    steer: Sequence[str] = (),
) -> str:
    """A reuse card as built: its title, the item it is about and the kinds of item it names
    from the rest of the inventory (a kind alone: the card does not say which one), and what
    it does; the item's name, which the scenarios brief carried, is said as its kind."""
    p = _params(params)
    reuse = scenarios.reuse[card]
    names = named([item])
    title = without_names(reuse.title, names)
    return finished_prompt(
        title,
        [part_of(item, params=p), *reuse.with_items],
        without_names(reuse.what_it_does, names),
        tail=p.rules.card,
        brief=brief,
        correction=p.correction_for(text=title),
        params=p,
        steer=steer,
    )


def keep_record(folder: Path, picture: Picture) -> None:
    """A picture's record written whole: a reader sees the old one or the new one."""
    record = folder / f"picture-{picture.n}.json"
    partial = folder / f".picture-{picture.n}.json.part"
    partial.write_text(picture.model_dump_json(), encoding="utf-8")
    os.replace(partial, record)


def _numbered(folder: Path) -> list[tuple[int, Path]]:
    if not folder.is_dir():
        return []
    found = []
    for path in folder.iterdir():
        match = PICTURE_NAME.fullmatch(path.name)
        if match and path.is_file():
            found.append((int(match.group(1)), path))
    return sorted(found)


def _reserve(folder: Path) -> tuple[int, int]:
    """The next number, claimed by creating its file exclusively: two draws at once never
    take the same one, and an earlier picture is never written over."""
    n = max((n for n, _ in _numbered(folder)), default=0) + 1
    while True:
        try:
            fd = os.open(folder / f"picture-{n}.jpg", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            n += 1
            continue
        return n, fd


def _kept(folder: Path) -> list[Picture]:
    pictures = []
    for _, path in _numbered(folder):
        record = path.with_suffix(".json")
        if record.is_file():
            pictures.append(Picture.model_validate_json(record.read_text(encoding="utf-8")))
    return pictures


def _read(folder: Path, n: int, what: str) -> bytes:
    for found, path in _numbered(folder):
        # a number still being written has no record yet
        if found == n and path.with_suffix(".json").is_file():
            return path.read_bytes()
    raise NotFoundError(f"{what} has no picture {n}")


class Votes(Protocol):
    """Where people's votes on drawings are read (app.feedback.Feedback)."""

    def drawing_votes(
        self, kind: str, target_id: int, ref_prefix: str = ""
    ) -> list[tuple[str, str, str]]: ...

    def kind_reasons(self, template: str, project_id: int) -> list[str]: ...


class Pictures:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        templates: Templates,
        votes: Votes | None = None,
    ) -> None:
        """``votes``: people's likes and dislikes, read so the next drawing of what they voted
        on avoids what a dislike's reason names; None (the commands, the demo loader, the
        review tools) draws without them."""
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.templates = templates
        self.votes = votes
        self.root = settings.data_dir / "items"
        self.projects_root = settings.data_dir / "projects"

    def folder(self, item_id: int) -> Path:
        return self.root / str(item_id)

    def card_folder(self, item_id: int, scenarios_id: int, card: int) -> Path:
        """A reuse card's pictures, inside the item's folder so they go with the item."""
        return self.folder(item_id) / f"scenarios-{scenarios_id}-reuse-{card}"

    def project_folder(self, project_id: int) -> Path:
        return self.projects_root / str(project_id)

    def _use(self, use: str | None) -> str:
        """A template id names its project; anything else is the owner's own words."""
        text = _line(use or "")
        if not text:
            return ""
        try:
            return self.templates.get(text).label
        except UnknownTemplateError:
            return text

    def _steer(
        self, kind: str, target_id: int, folder: Path, prefix: str = "", template: str = ""
    ) -> Steer:
        """What the caller's own votes on this target's drawings say to the next one: the
        reasons of the dislikes to avoid, a liked drawing's correction to keep, and for a
        project the reasons given on others of its kind. Nothing without votes."""
        if self.votes is None:
            return Steer()
        cast = self.votes.drawing_votes(kind, target_id, prefix)
        own = [reason for _, vote, reason in cast if vote == "dislike"]
        records = {str(p.n): p for p in _kept(folder)}
        liked = [
            records[ref[len(prefix) :]].brief
            for ref, vote, _ in cast
            if vote == "like" and ref[len(prefix) :] in records
        ]
        kind_of = self.votes.kind_reasons(template, target_id) if template else []
        return assemble(own, kind_of, liked)

    async def _draw(
        self,
        folder: Path,
        prompt: str,
        drawn_as: str,
        still_there: Callable[[], object],
        brief: str = "",
        steer: Steer | None = None,
    ) -> Picture:
        """One call, one picture, kept in the folder after those it has. ``still_there``
        raises when what it was drawn for went while it was drawn: nothing is kept then."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        result = await self.client.picture(prompt)
        try:
            pixels = prepare(result.data, max_px=1024, max_bytes=20 * 1024 * 1024)
        except BadImageError as exc:
            raise IncompleteResponseError("the answer carried an invalid image") from exc
        still_there()
        folder.mkdir(parents=True, exist_ok=True)
        n, fd = _reserve(folder)
        picture = Picture(
            n=n,
            use=drawn_as,
            model=result.model,
            cost_usd=result.cost_usd,
            from_fixture=result.from_fixture,
            created_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
            brief=clean(brief, BRIEF_MAX),
            avoided=steer.avoid if steer else [],
            kept=steer.keep if steer else "",
        )
        with os.fdopen(fd, "wb") as out:
            out.write(pixels)
        # the record makes the picture visible, so it lands whole or not at all
        keep_record(folder, picture)
        log.info(
            "picture",
            extra={
                "folder": str(folder.relative_to(self.settings.data_dir)),
                "n": n,
                "fixture": result.from_fixture,
                "usd": result.cost_usd,
            },
        )
        return picture

    async def draw(self, item_id: int, use: str | None, brief: str = "") -> Picture:
        """One picture of the item, one call, kept on the item after those it has; ``brief``
        is a correction said with it (from a review of an earlier drawing)."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        item = self.inventory.get(item_id)
        drawn_as = self._use(use) or item.item_type or item.name or "item"
        folder = self.folder(item_id)
        steer = self._steer("item_picture", item_id, folder)
        # the item may have been deleted while the picture was drawn: its folder stays gone
        return await self._draw(
            folder,
            prompt_for(item, drawn_as, brief, steer=steer.segments()),
            drawn_as,
            lambda: self.inventory.get(item_id),
            brief,
            steer,
        )

    async def draw_card(self, scenarios: Scenarios, card: int, brief: str = "") -> Picture:
        """How a reuse card's project could look once built: one call, kept with the card."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        item_id = scenarios.item_id
        self._card(scenarios, card)
        item = self.inventory.get(item_id)
        folder = self.card_folder(item_id, scenarios.id, card)
        steer = self._steer("card_picture", item_id, folder, f"{scenarios.id}/{card}/")
        return await self._draw(
            folder,
            card_prompt(scenarios, card, item, brief, steer=steer.segments()),
            _line(scenarios.reuse[card].title, TITLE_MAX),
            lambda: self.inventory.get(item_id),
            brief,
            steer,
        )

    async def draw_project(self, project: Project, view: str = "", brief: str = "") -> Picture:
        """How a project could look once built, from the items allocated to it: one call; a
        ``view`` (in its room, a close-up of the parts) asks for another picture of it."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        folder = self.project_folder(project.id)
        steer = self._steer("project_picture", project.id, folder, template=project.template)
        return await self._draw(
            folder,
            self.project_prompt(project, view, brief, steer.segments()),
            _line(
                f"{project.title}, {_line(view, VIEW_MAX)}" if view.strip() else project.title,
                TITLE_MAX + VIEW_MAX,
            )
            or "project",
            lambda: None,
            brief,
            steer,
        )

    def allocated(self, project: Project) -> list[Item]:
        """The items allocated to the project, each once; an item deleted since is left out."""
        items: list[Item] = []
        for item_id in dict.fromkeys(a.item_id for a in project.allocations):
            try:
                items.append(self.inventory.get(item_id))
            except NotFoundError:
                continue
        return items

    def project_prompt(
        self, project: Project, view: str = "", brief: str = "", steer: Sequence[str] = ()
    ) -> str:
        """What a drawing of the project asks for, as ``draw_project`` sends it."""
        others = [(i.name, i.item_type) for i in self.inventory.list_items()]
        return project_prompt(project, self.allocated(project), others, view, brief, steer=steer)

    @staticmethod
    def _card(scenarios: Scenarios, card: int) -> None:
        if not 0 <= card < len(scenarios.reuse):
            raise NotFoundError(f"scenarios {scenarios.id} have no reuse card {card}")

    def list(self, item_id: int, *, public_only: bool = False) -> PictureList:
        self.inventory.get(item_id, public_only=public_only)
        return PictureList(
            enabled=self.settings.picture_enabled, pictures=_kept(self.folder(item_id))
        )

    def read(self, item_id: int, n: int, *, public_only: bool = False) -> bytes:
        self.inventory.get(item_id, public_only=public_only)
        return _read(self.folder(item_id), n, f"item {item_id}")

    def card_list(self, scenarios: Scenarios, card: int) -> PictureList:
        self._card(scenarios, card)
        folder = self.card_folder(scenarios.item_id, scenarios.id, card)
        return PictureList(enabled=self.settings.picture_enabled, pictures=_kept(folder))

    def card_read(self, scenarios: Scenarios, card: int, n: int) -> bytes:
        self._card(scenarios, card)
        folder = self.card_folder(scenarios.item_id, scenarios.id, card)
        return _read(folder, n, f"reuse card {card}")

    def project_list(self, project_id: int) -> PictureList:
        return PictureList(
            enabled=self.settings.picture_enabled, pictures=_kept(self.project_folder(project_id))
        )

    def project_read(self, project_id: int, n: int) -> bytes:
        return _read(self.project_folder(project_id), n, f"project {project_id}")
