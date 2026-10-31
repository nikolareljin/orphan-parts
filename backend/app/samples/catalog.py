"""The demo samples: the photos of the demo set, grouped by the item they show, and its
listing texts and voice notes when the set has them. A request names a sample by its id,
never by a path; the server reads the exact file the recordings were made of."""

import logging
import re
import threading
from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image
from pydantic import BaseModel, Field

from app.config import Settings
from app.demo.schema import DemoSet

log = logging.getLogger("app.samples")

SAMPLE_ID = r"^[a-z0-9][a-z0-9-]{0,63}$"
THUMB_PX = 320
# what a visitor sending a file of their own is told; the samples are what the demo reads
VISITOR_UPLOAD_LINE = "Sign in with the access code to read your own photos."
MISSING_LINE = "No recorded answer for this sample yet."
_UNSAFE = re.compile(r"[^a-z0-9]+")


class UnknownSampleError(LookupError):
    """No sample has this id (or it is not of the kind asked for)."""


class SamplePhoto(BaseModel):
    id: str = Field(description="what a request names instead of the file")
    file: str = Field(description="the file name in the demo set")
    item_key: str
    item_name: str


class SampleItem(BaseModel):
    """One thing of the demo set and its photos, in the order the set names them."""

    key: str
    name: str
    item_type: str
    photos: list[SamplePhoto]


class SampleListing(BaseModel):
    """A listing text of the demo set's searches: written examples, labelled as such."""

    id: str
    name: str
    search_key: str
    search_title: str
    asking_price: str
    currency: str


class SampleNote(BaseModel):
    """A voice note of the demo set (WAV)."""

    id: str
    item_key: str
    item_name: str


class SampleCatalog(BaseModel):
    title: str = ""
    items: list[SampleItem] = []
    listings: list[SampleListing] = []
    notes: list[SampleNote] = []


def _id(stem: str, taken: set[str], prefix: str = "") -> str:
    base = (prefix + _UNSAFE.sub("-", stem.lower())).strip("-")[:60] or "sample"
    found, n = base, 1
    while found in taken:
        n += 1
        found = f"{base}-{n}"
    taken.add(found)
    return found


class Samples:
    """The catalog, read once from the demo set; files are read when asked for, so a set
    that is not there (a production image without it) is an empty catalog, not an error."""

    def __init__(self, settings: Settings, path: Path | None = None) -> None:
        self.path = path or settings.demo_set
        self._catalog: SampleCatalog | None = None
        self._files: dict[str, tuple[str, Path]] = {}
        self._thumbs: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def _load(self) -> SampleCatalog:
        with self._lock:
            if self._catalog is not None:
                return self._catalog
            catalog = SampleCatalog()
            files: dict[str, tuple[str, Path]] = {}
            try:
                if self.path.is_file():
                    catalog, files = self._read(self.path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                log.warning("demo set not read for the samples: %s", exc)
                catalog, files = SampleCatalog(), {}
            self._catalog, self._files = catalog, files
            return catalog

    @staticmethod
    def _read(path: Path) -> tuple[SampleCatalog, dict[str, tuple[str, Path]]]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        demo = DemoSet.model_validate(raw)
        demo.check()
        base = path.parent
        taken: set[str] = set()
        files: dict[str, tuple[str, Path]] = {}
        items: list[SampleItem] = []
        notes: list[SampleNote] = []
        for item in demo.items:
            photos: list[SamplePhoto] = []
            for name in item.photos:
                file = base / name
                if not file.is_file():
                    continue
                sid = _id(Path(name).stem, taken)
                files[sid] = ("photo", file)
                photos.append(
                    SamplePhoto(id=sid, file=file.name, item_key=item.key, item_name=item.name)
                )
            if photos:
                items.append(
                    SampleItem(
                        key=item.key, name=item.name, item_type=item.item_type, photos=photos
                    )
                )
            if item.voice_note and (base / item.voice_note).is_file():
                sid = _id(Path(item.voice_note).stem, taken, "note-")
                files[sid] = ("note", base / item.voice_note)
                notes.append(SampleNote(id=sid, item_key=item.key, item_name=item.name))
        listings: list[SampleListing] = []
        for search in demo.searches:
            for n, listing in enumerate(search.listings, 1):
                if not listing.text.startswith("@"):
                    continue
                file = base / listing.text[1:]
                if not file.is_file():
                    continue
                sid = _id(file.stem, taken, "listing-")
                files[sid] = ("listing", file)
                listings.append(
                    SampleListing(
                        id=sid,
                        name=file.stem or f"listing {n}",
                        search_key=search.key,
                        search_title=search.title,
                        asking_price=listing.asking_price,
                        currency=listing.currency,
                    )
                )
        return SampleCatalog(title=demo.title, items=items, listings=listings, notes=notes), files

    # --- what the routes and the reader ask for ---------------------------------

    def catalog(self) -> SampleCatalog:
        return self._load()

    def kind(self, sample_id: str) -> str:
        self._load()
        found = self._files.get(sample_id)
        if found is None:
            raise UnknownSampleError(f"no sample {sample_id}")
        return found[0]

    def file(self, sample_id: str, kind: str | None = None) -> bytes:
        self._load()
        found = self._files.get(sample_id)
        if found is None or (kind is not None and found[0] != kind):
            raise UnknownSampleError(f"no sample {sample_id}")
        return found[1].read_bytes()

    def photo(self, sample_id: str) -> bytes:
        return self.file(sample_id, "photo")

    def thumb(self, sample_id: str) -> bytes:
        """A small JPEG of a sample photo, made once and kept for the process."""
        data = self.photo(sample_id)
        with self._lock:
            kept = self._thumbs.get(sample_id)
        if kept is not None:
            return kept
        with Image.open(BytesIO(data)) as img:
            small = img.convert("RGB")
            small.thumbnail((THUMB_PX, THUMB_PX))
            out = BytesIO()
            small.save(out, "JPEG", quality=80)
        thumb = out.getvalue()
        with self._lock:
            self._thumbs[sample_id] = thumb
        return thumb

    def item_of(self, sample_id: str) -> SampleItem:
        for item in self._load().items:
            if any(p.id == sample_id for p in item.photos):
                return item
        raise UnknownSampleError(f"no sample photo {sample_id}")
