"""A picture of what an item could become, drawn by Muse Image when the owner clicks.

Illustrative, never evidence: nothing about the item is read from it, no value rests on it,
and it is labeled as drawn wherever it is shown. Files under ``DATA_DIR/items/<id>/`` beside
the photos, named ``picture-<n>.jpg`` with a ``picture-<n>.json`` record, so a picture is
never counted as a photo of the item; the folder goes with the item, as the photos do.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.config import Settings
from app.extract.imaging import BadImageError, prepare
from app.inventory.schema import Item
from app.inventory.service import Inventory, NotFoundError
from app.model_api import IncompleteResponseError, ModelApiClient
from app.projects.pack import shown_fields
from app.projects.templates import Templates, UnknownTemplateError

log = logging.getLogger("app.picture")
PICTURE_NAME = re.compile(r"picture-(\d+)\.jpg")
OFF_LINE = "pictures are off on this server (PICTURE_ENABLED)"
USE_MAX = 200
# how many accepted values the prompt carries: enough to say what the item is, not a sheet
PROMPT_VALUES = 8


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
    return f"{head}{tail}, on a plain background, no text, no logos, no people"


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

    def folder(self, item_id: int) -> Path:
        return self.root / str(item_id)

    def _paths(self, item_id: int) -> list[tuple[int, Path]]:
        folder = self.folder(item_id)
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            match = PICTURE_NAME.fullmatch(path.name)
            if match and path.is_file():
                found.append((int(match.group(1)), path))
        return sorted(found)

    def _use(self, use: str | None) -> str:
        """A template id names its project; anything else is the owner's own words."""
        text = _line(use or "")
        if not text:
            return ""
        try:
            return self.templates.get(text).label
        except UnknownTemplateError:
            return text

    async def draw(self, item_id: int, use: str | None) -> Picture:
        """One picture, one call, kept on the item after those it has."""
        if not self.settings.picture_enabled:
            raise PicturesOffError(OFF_LINE)
        item = self.inventory.get(item_id)
        drawn_as = self._use(use) or item.item_type or item.name or "item"
        result = await self.client.picture(prompt_for(item, drawn_as))
        try:
            pixels = prepare(result.data, max_px=1024, max_bytes=20 * 1024 * 1024)
        except BadImageError as exc:
            raise IncompleteResponseError("the answer carried an invalid image") from exc
        # the item may have been deleted while the picture was drawn: its folder stays gone
        self.inventory.get(item_id)
        folder = self.folder(item_id)
        folder.mkdir(parents=True, exist_ok=True)
        n, fd = self._reserve(item_id)
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
            "item picture",
            extra={
                "item_id": item_id,
                "n": n,
                "fixture": result.from_fixture,
                "usd": result.cost_usd,
            },
        )
        return picture

    def _reserve(self, item_id: int) -> tuple[int, int]:
        """The next number, claimed by creating its file exclusively: two draws at once never
        take the same one, and an earlier picture is never written over."""
        folder = self.folder(item_id)
        n = max((n for n, _ in self._paths(item_id)), default=0) + 1
        while True:
            try:
                fd = os.open(
                    folder / f"picture-{n}.jpg", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
            except FileExistsError:
                n += 1
                continue
            return n, fd

    def list(self, item_id: int, *, public_only: bool = False) -> PictureList:
        self.inventory.get(item_id, public_only=public_only)
        pictures = []
        for _, path in self._paths(item_id):
            record = path.with_suffix(".json")
            if record.is_file():
                pictures.append(Picture.model_validate_json(record.read_text(encoding="utf-8")))
        return PictureList(enabled=self.settings.picture_enabled, pictures=pictures)

    def read(self, item_id: int, n: int, *, public_only: bool = False) -> bytes:
        self.inventory.get(item_id, public_only=public_only)
        for found, path in self._paths(item_id):
            # a number still being written has no record yet
            if found == n and path.with_suffix(".json").is_file():
                return path.read_bytes()
        raise NotFoundError(f"item {item_id} has no picture {n}")
