"""The photos an item is known by, kept beside it so each value can be checked against the
picture: the capture's photos for an item read from the phone, the label photos for an item
saved from the web form. Files under ``DATA_DIR/items/<id>/``, re-encoded like every photo
taken in, at most ``MAX_PHOTOS`` per item."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from app.config import Settings
from app.extract.imaging import prepare
from app.inventory.service import Inventory, NotFoundError

log = logging.getLogger("app.photos")
PHOTO_NAME = re.compile(r"photo-(\d+)\.jpg")


class PhotoError(ValueError):
    """A photo refused: none sent, or more than an item keeps."""


class ItemPhotos:
    def __init__(self, settings: Settings, inventory: Inventory) -> None:
        self.settings = settings
        self.inventory = inventory
        self.root = settings.data_dir / "items"

    def folder(self, item_id: int) -> Path:
        return self.root / str(item_id)

    def _paths(self, item_id: int) -> list[Path]:
        folder = self.folder(item_id)
        if not folder.is_dir():
            return []
        found = []
        for path in folder.iterdir():
            match = PHOTO_NAME.fullmatch(path.name)
            if match and path.is_file():
                found.append((int(match.group(1)), path))
        return [path for _, path in sorted(found)]

    def count(self, item_id: int) -> int:
        """How many photos the item has; 404 for an item that is not there or is hidden."""
        self.inventory.get(item_id)
        return len(self._paths(item_id))

    def add(self, item_id: int, photos: list[bytes], *, prepared: bool = False) -> int:
        """Keep photos on the item, after those it has; returns the new count. ``prepared``
        photos were already re-encoded (a capture's) and are written as they are."""
        self.inventory.get(item_id)
        if not photos:
            raise PhotoError("no photo sent")
        have = len(self._paths(item_id))
        limit = self.settings.max_photos
        if have + len(photos) > limit:
            raise PhotoError(f"an item keeps at most {limit} photos; this one has {have}")
        s = self.settings
        ready = (
            photos
            if prepared
            else [
                prepare(p, max_px=s.image_max_px, max_bytes=s.max_upload_mb * 1024 * 1024)
                for p in photos
            ]
        )
        folder = self.folder(item_id)
        folder.mkdir(parents=True, exist_ok=True)
        n = have
        for data in ready:
            n += 1
            (folder / f"photo-{n}.jpg").write_bytes(data)
        log.info("item photos", extra={"item_id": item_id, "photos": n})
        return n

    def read(self, item_id: int, n: int) -> bytes:
        self.inventory.get(item_id)
        paths = self._paths(item_id)
        if n < 1 or n > len(paths):
            raise NotFoundError(f"item {item_id} has no photo {n}")
        return paths[n - 1].read_bytes()

    def remove(self, item_id: int) -> None:
        """The files go with the item when the owner deletes it; the record stays hidden."""
        folder = self.folder(item_id)
        if folder.is_dir() and folder.parent == self.root:
            shutil.rmtree(folder)
