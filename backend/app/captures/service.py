"""Captures from the phone: stored as sent (photos re-encoded to pixels, the clip and the note
as they are), processed on request into an item with the reading, the transcript and the
owner's line, kept until the owner deletes them."""

import json
import logging
import shutil
import threading
from pathlib import Path
from typing import Any

from app.captures.schema import Capture, CaptureCreate
from app.config import Settings
from app.extract import Extractor
from app.extract.imaging import BadImageError, prepare
from app.inventory import Inventory
from app.inventory.schema import ItemCreate, ItemPatch
from app.inventory.service import NotFoundError
from app.listing import BadAudioError, VoiceNotes, wav_seconds
from app.model_api import ModelApiError
from app.photos import ItemPhotos, PhotoError
from app.segment import Segmenter

log = logging.getLogger("app.captures")

# The brands an MP4 or 3GP file announces after ``ftyp``: what the phone's camera writes and
# a browser plays. HEIC photos, M4A audio and MOV files carry ``ftyp`` too and are not clips.
MP4_BRANDS = frozenset(
    {
        b"isom",
        b"iso2",
        b"iso4",
        b"iso5",
        b"iso6",
        b"mp41",
        b"mp42",
        b"avc1",
        b"M4V ",
        b"3gp4",
        b"3gp5",
        b"3gp6",
        b"3gp7",
        b"3ge6",
        b"3gg6",
        b"3gr6",
        b"3gs6",
        b"3g2a",
    }
)


class CaptureError(ValueError):
    """The bundle cannot be kept as given."""


def looks_like_video(data: bytes) -> bool:
    """An MP4 or 3GP container: the ``ftyp`` box within the first bytes, with a video brand."""
    return len(data) > 12 and data[4:8] == b"ftyp" and data[8:12] in MP4_BRANDS


class Captures:
    def __init__(
        self,
        settings: Settings,
        inventory: Inventory,
        extractor: Extractor,
        segmenter: Segmenter,
        voice: VoiceNotes,
        photos: ItemPhotos,
    ) -> None:
        self.settings = settings
        self.inventory = inventory
        self.extractor = extractor
        self.segmenter = segmenter
        self.voice = voice
        self.photos = photos
        self.root = settings.data_dir / "captures"
        self._busy: set[int] = set()  # captures being read right now, one read each
        # the check of the busy set and the step after it are one: a delete and a read of the
        # same capture cannot both pass
        self._guard = threading.Lock()

    def folder(self, capture_id: int) -> Path:
        return self.root / str(capture_id)

    # --- intake ---------------------------------------------------------------

    def create(
        self,
        spec: CaptureCreate,
        photos: list[bytes],
        clip: bytes | None,
        audio: bytes | None,
    ) -> Capture:
        s = self.settings
        if not photos and clip is None and audio is None and not spec.note.strip():
            raise CaptureError("an empty capture: send a photo, a clip, a note or a line")
        if len(photos) > s.max_photos:
            raise CaptureError(f"at most {s.max_photos} photos per capture")
        prepared: list[bytes] = []
        for n, data in enumerate(photos, 1):
            try:
                prepared.append(
                    prepare(data, max_px=s.image_max_px, max_bytes=s.max_upload_mb * 1024 * 1024)
                )
            except BadImageError as exc:
                raise CaptureError(f"photo {n}: {exc}") from exc
        if clip is not None:
            if len(clip) > s.max_clip_mb * 1024 * 1024:
                raise CaptureError(f"the clip is larger than {s.max_clip_mb} MB")
            if not looks_like_video(clip):
                raise CaptureError("the clip is not an MP4 or 3GP file")
        seconds = 0.0
        if audio is not None:
            try:
                seconds = wav_seconds(audio)
            except BadAudioError as exc:
                raise CaptureError(f"the note: {exc}") from exc
            if seconds > s.voice_max_seconds:
                raise CaptureError(f"the note is longer than {s.voice_max_seconds} s")
        content: dict[str, Any] = {
            "note": spec.note.strip(),
            "name": spec.name.strip(),
            "find_label": spec.find_label,
            "photos": len(prepared),
            "clip": clip is not None,
            "clip_bytes": len(clip) if clip is not None else 0,
            "audio": audio is not None,
            "audio_seconds": round(seconds, 1),
            "item_id": None,
            "error": "",
            "model": "",
            "cost_usd": 0.0,
        }
        kept = len(self.inventory.captures())
        if kept >= self.settings.max_captures:
            raise CaptureError(
                f"the inbox holds at most {self.settings.max_captures} captures; delete some first"
            )
        row = self.inventory.add_capture(json.dumps(content))
        folder = self.folder(int(row["id"]))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for n, data in enumerate(prepared, 1):
                (folder / f"photo-{n}.jpg").write_bytes(data)
            if clip is not None:
                (folder / "clip.mp4").write_bytes(clip)
            if audio is not None:
                (folder / "note.wav").write_bytes(audio)
        except OSError:
            # no row without its files: the capture is taken back and the caller hears why
            shutil.rmtree(folder, ignore_errors=True)
            self.inventory.delete_capture(int(row["id"]))
            raise
        log.info(
            "capture",
            extra={"capture_id": int(row["id"]), "photos": len(prepared), "clip": clip is not None},
        )
        return self.capture_of(row)

    def captures(self, *, public_only: bool = False) -> list[Capture]:
        return [self.capture_of(r) for r in self.inventory.captures(public_only=public_only)]

    def capture(self, capture_id: int, *, public_only: bool = False) -> Capture:
        return self.capture_of(self.inventory.capture(capture_id, public_only=public_only))

    def set_public(self, capture_id: int, public: bool) -> Capture:
        return self.capture_of(self.inventory.set_capture_public(capture_id, public))

    def photo(self, capture_id: int, n: int, *, public_only: bool = False) -> bytes:
        found = self.capture(capture_id, public_only=public_only)
        if n < 1 or n > found.photos:
            raise NotFoundError(f"capture {capture_id} has no photo {n}")
        return (self.folder(capture_id) / f"photo-{n}.jpg").read_bytes()

    def media(self, capture_id: int, name: str) -> bytes:
        found = self.capture(capture_id)
        if name == "clip.mp4" and not found.clip:
            raise NotFoundError(f"capture {capture_id} has no clip")
        if name == "note.wav" and not found.audio:
            raise NotFoundError(f"capture {capture_id} has no note")
        return (self.folder(capture_id) / name).read_bytes()

    def media_path(self, capture_id: int, name: str) -> Path:
        """Where a clip or a note is, for a route that streams it (and takes a byte range)."""
        found = self.capture(capture_id)
        if name == "clip.mp4" and not found.clip:
            raise NotFoundError(f"capture {capture_id} has no clip")
        if name == "note.wav" and not found.audio:
            raise NotFoundError(f"capture {capture_id} has no note")
        return self.folder(capture_id) / name

    def delete(self, capture_id: int) -> None:
        """The files go and the row is hidden; an item made from it stays."""
        with self._guard:
            self.inventory.capture(capture_id)
            if capture_id in self._busy:
                raise CaptureError("being read right now; delete it once that is done")
            self.inventory.delete_capture(capture_id)
        folder = self.folder(capture_id)
        if folder.is_dir() and folder.parent == self.root:
            shutil.rmtree(folder)

    # --- processing -------------------------------------------------------------

    async def process(self, capture_id: int) -> Capture:
        """The photos read (the label found first when asked), the item created with the
        reading, the note transcribed onto it, the line kept as its notes. A failure is
        recorded on the capture and raised; the media stays for another try."""
        with self._guard:
            row = self.inventory.capture(capture_id)
            content = json.loads(row["content"])
            if content["item_id"] is not None:
                raise CaptureError("already processed; the item is there")
            if capture_id in self._busy:
                raise CaptureError("being read right now; the item will be there in a moment")
            self._busy.add(capture_id)
        try:
            return await self._process(capture_id, content)
        finally:
            self._busy.discard(capture_id)

    async def _process(self, capture_id: int, content: dict[str, Any]) -> Capture:
        folder = self.folder(capture_id)
        photos = [
            (folder / f"photo-{n}.jpg").read_bytes()
            for n in range(1, int(content["photos"]) + 1)
            if (folder / f"photo-{n}.jpg").is_file()
        ]
        model, cost = "", 0.0
        try:
            missing = int(content["photos"]) - len(photos)
            if missing:
                raise CaptureError(f"{missing} photo(s) missing on disk; send the capture again")
            spec = ItemCreate(name=content["name"] or "", notes=content["note"])
            if photos:
                crops: list[bytes] = []
                if content["find_label"]:
                    crops, cost = await self.label_crops(photos[0])
                reading = await self.extractor.extract(photos, crops)
                model, cost = reading.model, cost + reading.cost_usd
                spec = spec.model_copy(
                    update={
                        "extraction": reading,
                        "item_type": reading.item_type or "item",
                        "name": spec.name or (reading.item_type or "").capitalize() or "Capture",
                    }
                )
            else:
                # the line stays in the notes, never in the name: a name is shown wherever
                # the item is, to the demo visitor too once the item is public
                spec = spec.model_copy(update={"item_type": "item", "name": spec.name or "Capture"})
            item = self.inventory.create(spec)
            if photos:
                # the item keeps the pictures it was read from, so the capture can go later;
                # a copy that fails is said in the log and never undoes the read
                try:
                    self.photos.add(item.id, photos, prepared=True)
                except (OSError, PhotoError) as exc:
                    log.warning(
                        "item photos not kept", extra={"item_id": item.id, "error": str(exc)}
                    )
        except (ModelApiError, BadImageError, ValueError) as exc:
            content["error"] = str(exc)[:500]
            self.inventory.update_capture(capture_id, "failed", json.dumps(content))
            raise
        # the item is linked first: a recording that cannot be kept is said on the capture,
        # the item stays, and the reading is not paid for twice
        content.update(
            {"item_id": item.id, "error": "", "model": model, "cost_usd": round(cost, 6)}
        )
        self.inventory.update_capture(capture_id, "processed", json.dumps(content))
        try:
            if content["audio"] and (folder / "note.wav").is_file():
                note = await self.voice.note(item.id, (folder / "note.wav").read_bytes())
                cost += note.cost_usd
                model = model or note.model
            if content["clip"]:
                line = f"a clip of {content['clip_bytes'] // 1024} KB came with the capture"
                self.inventory.update(
                    item.id,
                    ItemPatch(notes=(content["note"] + "\n" + line).strip()),
                )
        except (ModelApiError, BadAudioError, ValueError) as exc:
            content["error"] = f"the item is there; the note was not kept: {exc}"[:500]
        content.update({"model": model, "cost_usd": round(cost, 6)})
        updated = self.inventory.update_capture(capture_id, "processed", json.dumps(content))
        log.info("capture processed", extra={"capture_id": capture_id, "item_id": item.id})
        return self.capture_of(updated)

    async def label_crops(self, photo: bytes) -> tuple[list[bytes], float]:
        """The label crop from the first photo, as the web form sends it, and what finding it
        cost; none when the label is not found or segmentation fails, and the photos are
        read whole."""
        try:
            result = await self.segmenter.segment(photo, ["label"])
        except (ModelApiError, BadImageError, ValueError) as exc:
            log.info("label not found first", extra={"reason": str(exc)[:200]})
            return [], 0.0
        crops: list[bytes] = []
        for region in result.regions:
            if region.concept == "label" and region.crop.startswith("data:"):
                crops.append(_data_url_bytes(region.crop))
        return crops[:1], result.cost_usd

    def capture_of(self, row: Any) -> Capture:
        content = json.loads(row["content"])
        return Capture(
            id=int(row["id"]),
            status=row["status"],
            created_at=row["created_at"],
            processed_at=row["processed_at"] or "",
            public=bool(row["public"]),
            **content,
        )


def _data_url_bytes(url: str) -> bytes:
    import base64

    comma = url.index(",")
    return base64.b64decode(url[comma + 1 :])
