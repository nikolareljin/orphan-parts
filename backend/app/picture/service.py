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

from pydantic import BaseModel, Field

from app.config import Settings
from app.decide.schema import Scenarios
from app.extract.imaging import BadImageError, prepare
from app.inventory.schema import Item
from app.inventory.service import Inventory, NotFoundError
from app.model_api import IncompleteResponseError, ModelApiClient
from app.projects.pack import shown_fields
from app.projects.schema import Project
from app.projects.templates import Templates, UnknownTemplateError

log = logging.getLogger("app.picture")
PICTURE_NAME = re.compile(r"picture-(\d+)\.jpg")
OFF_LINE = "pictures are off on this server (PICTURE_ENABLED)"
USE_MAX = 200
# how many accepted values the prompt carries: enough to say what the item is, not a sheet
PROMPT_VALUES = 8
# a finished project's prompt: what it is, the parts it is built from, one line on it
TITLE_MAX = 120
PARTS_MAX = 6
PART_VALUES = 3
VALUE_MAX = 60
TAIL = "on a plain background, no text, no logos, no people"
# what an item cost or would fetch is the owner's business, never part of a picture
MONEY_WORDS = ("price", "cost", "paid", "msrp", "value", "worth", "resale", "retail")


class PicturesOffError(RuntimeError):
    """``PICTURE_ENABLED`` is not set: no call is made."""


class Picture(BaseModel):
    """One picture kept on the item; the file is at ``/pictures/{n}``."""

    n: int
    use: str = Field(description="what the item was drawn as: a use the owner typed, or itself")
    model: str
    cost_usd: float
    from_fixture: bool
    created_at: str


class PictureList(BaseModel):
    enabled: bool
    pictures: list[Picture]


def _line(text: str, limit: int = USE_MAX) -> str:
    return " ".join(text.split())[:limit]


def prompt_for(item: Item, use: str) -> str:
    """What Muse Image is asked for: the chosen use built from the item as it is known, from
    its type, accepted values, condition and faults; a proposed value is not yet known, and a
    value that identifies the item or its owner (a serial, a MAC, an IMEI) never goes out."""
    what = item.item_type or item.name or "item"
    known = [f"{k} {v}" for k, v in shown_fields(item)][:PROMPT_VALUES]
    about = what if not known else f"{what} ({', '.join(known)})"
    if use and use.lower() != what.lower():
        head = f"a semi-realistic illustration of {use} built from {about}"
    else:
        head = f"a semi-realistic illustration of this {about}, cleaned up and ready to use"
    detail = []
    if item.condition:
        detail.append(f"condition: {_line(item.condition)}")
    if item.faults:
        detail.append(f"known faults: {_line(item.faults)}")
    tail = f"; {'; '.join(detail)}" if detail else ""
    return f"{head}{tail}, {TAIL}"


def part_of(item: Item) -> str:
    """One part of a finished project as the prompt names it: the kind of item and a few of its
    accepted values, never one that identifies it or its owner, never its name, location,
    notes or a price."""
    what = _line(item.item_type, VALUE_MAX) or "item"
    known = [
        _line(f"{k} {v}", VALUE_MAX)
        for k, v in shown_fields(item)
        if not any(word in k.lower() for word in MONEY_WORDS)
    ][:PART_VALUES]
    return what if not known else f"{what} ({', '.join(known)})"


def finished_prompt(title: str, parts: list[str], about: str) -> str:
    """What Muse Image is asked for a finished project: what it is, built from the parts the
    card uses (each once, at most six), and one line on it; every text cut to its bound."""
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
    return f"{head}; {line}, {TAIL}" if line else f"{head}, {TAIL}"


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


def project_prompt(project: Project, items: list[Item], others: Sequence[Named] = ()) -> str:
    """A project as built: its title, the items allocated to it, and what it results in; no
    item's name, even where the model's title or result repeats one (``others``: the rest of
    the inventory's names, which the proposal could read too)."""
    names = named(items, [*others, *((a.item_name, "item") for a in project.allocations)])
    return finished_prompt(
        without_names(project.title, names),
        [part_of(i) for i in items],
        without_names(project.result, names),
    )


def card_prompt(scenarios: Scenarios, card: int, item: Item) -> str:
    """A reuse card as built: its title, the item it is about and the kinds of item it names
    from the rest of the inventory (a kind alone: the card does not say which one), and what
    it does; the item's name, which the scenarios brief carried, is said as its kind."""
    reuse = scenarios.reuse[card]
    names = named([item])
    return finished_prompt(
        without_names(reuse.title, names),
        [part_of(item), *reuse.with_items],
        without_names(reuse.what_it_does, names),
    )


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


class Pictures:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        templates: Templates,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.templates = templates
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

    async def _draw(
        self, folder: Path, prompt: str, drawn_as: str, still_there: Callable[[], object]
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
        )
        with os.fdopen(fd, "wb") as out:
            out.write(pixels)
        # the record makes the picture visible, so it lands whole or not at all
        record = folder / f"picture-{n}.json"
        partial = folder / f".picture-{n}.json.part"
        partial.write_text(picture.model_dump_json(), encoding="utf-8")
        os.replace(partial, record)
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

    async def draw(self, item_id: int, use: str | None) -> Picture:
        """One picture of the item, one call, kept on the item after those it has."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        item = self.inventory.get(item_id)
        drawn_as = self._use(use) or item.item_type or item.name or "item"
        # the item may have been deleted while the picture was drawn: its folder stays gone
        return await self._draw(
            self.folder(item_id),
            prompt_for(item, drawn_as),
            drawn_as,
            lambda: self.inventory.get(item_id),
        )

    async def draw_card(self, scenarios: Scenarios, card: int) -> Picture:
        """How a reuse card's project could look once built: one call, kept with the card."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        item_id = scenarios.item_id
        self._card(scenarios, card)
        item = self.inventory.get(item_id)
        return await self._draw(
            self.card_folder(item_id, scenarios.id, card),
            card_prompt(scenarios, card, item),
            _line(scenarios.reuse[card].title, TITLE_MAX),
            lambda: self.inventory.get(item_id),
        )

    async def draw_project(self, project: Project) -> Picture:
        """How a project could look once built, from the items allocated to it: one call."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        items: list[Item] = []
        for item_id in dict.fromkeys(a.item_id for a in project.allocations):
            try:
                items.append(self.inventory.get(item_id))
            except NotFoundError:
                continue  # an item deleted since is not drawn
        others = [(i.name, i.item_type) for i in self.inventory.list_items()]
        return await self._draw(
            self.project_folder(project.id),
            project_prompt(project, items, others),
            _line(project.title, TITLE_MAX) or "project",
            lambda: None,
        )

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
