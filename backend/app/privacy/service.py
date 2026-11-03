"""The photo check: one Muse Spark call per photo finds the private details on it (product keys,
MAC addresses, serial numbers, IMEIs, passwords and PINs, QR codes and barcodes) as boxes; the
boxes are checked, padded and kept by the digest of the photo's stored bytes; every copy that
leaves the owner's view is rendered from them with those areas black. A photo that has not
been checked, or whose check failed, is not shared at all unless the owner says so for a
download. The original never changes and stays the owner's."""

import hashlib
import logging
import os
import tempfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import anyio
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.extract.imaging import BadImageError, prepare
from app.model_api import (
    FixtureMissingError,
    ModelApiClient,
    ModelApiError,
    NoRecordingError,
    SpendCapError,
    exact_replay,
    image_part,
    text_part,
    user_message,
)
from app.privacy.render import gridded, redacted
from app.privacy.schema import Area, PhotoCheck, PhotoPrivacy, SensitiveReading
from app.privacy.text import KIND_LABELS, mask_text

log = logging.getLogger("app.privacy")

OP = "find-sensitive"
MAX_OUTPUT_TOKENS = 900
SCALE = 1000  # the model's box coordinates: a 0 to 1000 scale of the width and the height
MAX_AREAS = 24
MIN_SIDE = 3  # on that scale: a box thinner than this is a slip, not an area
# padding around each box, so a box a little off still covers its value: a share of the box's
# shorter side, within a share of the photo's longer side; a long line of text gets a little
# more at its ends, where a box drawn by a model is most often short
PAD_SHARE = 0.3
PAD_MIN_SHARE = 0.008
PAD_MAX_SHARE = 0.03
PAD_ENDS_SHARE = 0.15
WHAT_MAX = 120

INSTRUCTIONS = (
    "You find private details in photos of used items and spare parts, so they can be blacked"
    " out before a photo is shared. Report every area that shows one of these: a software"
    " product key (five groups of five letters and digits, as Windows and Office print it);"
    " a MAC address; a serial number, service tag or express service code with its value; an"
    " IMEI; a password, PIN, Wi-Fi key or network key, printed or handwritten; any QR code; any"
    " barcode, except a retail UPC or EAN code on packaging; anything else that identifies the"
    " owner or unlocks the device (an account number, an email address, a network name printed"
    " beside its key), as other. Model numbers, part numbers, ratings, FCC IDs, dates and"
    " regulatory marks are not private. Each value is its own area, and the area covers all of"
    " the value: every line of it when it wraps onto the next. Give each area its kind, a few"
    " words on what it is without copying the value, and a box around the value (and its own"
    " barcode when one sits under it) as x_min, y_min, x_max, y_max on a 0 to 1000 scale of the"
    " image's width and height, 0,0 being the top left corner. The photo carries a thin magenta"
    " grid every 100 units of that scale, numbered along its edges: read each box off the grid."
    " Never copy a value. When nothing private is visible, return no areas."
)
PROMPT = "Find the private details in this photo."


class NotCheckedError(LookupError):
    """A photo with no finished check is about to leave the owner's view; the message says so."""


def digest_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def place(reading: SensitiveReading, width: int, height: int) -> tuple[list[Area], str]:
    """The model's boxes checked and padded, as fractions of the photo; or the reason the
    answer cannot be placed, in which case nothing is (one area that cannot be placed would
    be one area left showing)."""
    if len(reading.areas) > MAX_AREAS:
        return [], f"more than {MAX_AREAS} areas reported"
    areas: list[Area] = []
    longest = max(width, height)
    for n, found in enumerate(reading.areas, 1):
        x0, x1 = sorted((found.x_min, found.x_max))
        y0, y1 = sorted((found.y_min, found.y_max))
        if x0 < 0 or y0 < 0 or x1 > SCALE or y1 > SCALE:
            return [], f"area {n} lies off the photo"
        if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
            return [], f"area {n} has no size"
        left, right = x0 / SCALE * width, x1 / SCALE * width
        top, bottom = y0 / SCALE * height, y1 / SCALE * height
        pad = PAD_SHARE * min(right - left, bottom - top)
        pad = min(max(pad, PAD_MIN_SHARE * longest), PAD_MAX_SHARE * longest)
        ends = pad + min(PAD_ENDS_SHARE * (right - left), PAD_MAX_SHARE * longest)
        left, top = max(0.0, left - ends), max(0.0, top - pad)
        right, bottom = min(float(width), right + ends), min(float(height), bottom + pad)
        what = mask_text(" ".join(found.what.split()))[:WHAT_MAX]
        areas.append(
            Area(
                id=n,
                kind=found.kind,
                label=KIND_LABELS[found.kind],
                what=what,
                x=round(left / width, 4),
                y=round(top / height, 4),
                w=round((right - left) / width, 4),
                h=round((bottom - top) / height, 4),
            )
        )
    return areas, ""


def note_for(check: PhotoCheck | None) -> str:
    """The line the app shows under a photo: what is hidden, and why it is not shared when it
    is not."""
    if check is None or check.status == "unchecked":
        return "Not checked for private details yet; kept out of anything shared until it is."
    if check.status == "failed":
        why = f" ({check.reason})" if check.reason else ""
        return f"The check for private details did not finish{why}; kept out of anything shared."
    if check.status == "clear" or not check.areas:
        return "Checked: nothing private found."
    hidden = [a for a in check.areas if a.hidden]
    shown = [a for a in check.areas if not a.hidden]

    def kinds(areas: list[Area]) -> str:
        return ", ".join(dict.fromkeys(a.label for a in areas))

    parts = []
    if hidden:
        plural = "area" if len(hidden) == 1 else "areas"
        parts.append(f"{len(hidden)} {plural} hidden: {kinds(hidden)}")
    if shown:
        parts.append(f"{len(shown)} shown by the owner: {kinds(shown)}")
    return "; ".join(parts) + "."


class Privacy:
    def __init__(self, settings: Settings, client: ModelApiClient) -> None:
        self.settings = settings
        self.client = client
        self.root = settings.data_dir / "privacy"
        # a demo-set sample's digest as the loader keeps it (the file re-encoded as an upload
        # is), by sample id: the files do not change while the process runs
        self._sample_digests: dict[str, str] = {}

    def _path(self, digest: str) -> Path:
        return self.root / f"{digest}.json"

    def kept(self, data: bytes) -> PhotoCheck | None:
        """The check kept for these very bytes, or None."""
        path = self._path(digest_of(data))
        if not path.is_file():
            return None
        try:
            return PhotoCheck.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("a photo check could not be read", extra={"path": path.name})
            return None

    def _save(self, check: PhotoCheck) -> PhotoCheck:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(check.digest)
        # a part of its own: an owner's choice (on a worker thread) and a check (on the loop)
        # may save the same photo's check at once
        fd, part = tempfile.mkstemp(dir=self.root, prefix=f"{check.digest}.", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(check.model_dump_json(indent=2) + "\n")
            os.replace(part, path)
        except BaseException:
            Path(part).unlink(missing_ok=True)
            raise
        return check

    @staticmethod
    def _finished(check: PhotoCheck | None) -> bool:
        return check is not None and check.status in ("clear", "found")

    def waiting(self, photos: list[bytes], *, again: bool = False) -> list[bytes]:
        """The photos a check would run on, each once: those without a finished check, or
        every one when asked again."""
        out: dict[str, bytes] = {}
        for data in photos:
            if again or not self._finished(self.kept(data)):
                out.setdefault(digest_of(data), data)
        return list(out.values())

    def not_checked(self, photos: list[bytes], reason: str) -> None:
        """Photos whose check was refused before any call (the operator's pause, an
        allowance), kept as failed checks with the reason, so the line under each says why it
        is not shared; a finished check of the same photo stands."""
        for data in photos:
            if not self._finished(self.kept(data)):
                self._save(PhotoCheck(digest=digest_of(data), status="failed", reason=reason))

    async def check(self, data: bytes, *, again: bool = False) -> PhotoCheck:
        """The photo checked once (kept, and answered from what is kept after), or again when
        asked. A failure is kept as a failed check and returned, never raised, so the photo
        stays where it is and is simply not shared; only a missing recording of a demo-set
        photo is raised, for the loader to list."""
        kept = self.kept(data)
        if kept is not None and kept.status in ("clear", "found") and not again:
            return kept
        digest = digest_of(data)
        try:
            width, height, sent = await anyio.to_thread.run_sync(_measured, data)
        except ValueError as exc:
            if kept is not None and kept.status in ("clear", "found"):
                return kept
            return self._save(PhotoCheck(digest=digest, status="failed", reason=str(exc)))
        # only a recording of this very photo answers in fixture mode, never an operation's
        # stub: a stub's "nothing private" would share a photo nobody checked
        loader = exact_replay.get()
        token = exact_replay.set(True)
        try:
            result = await self.client.respond_structured(
                SensitiveReading,
                model=self.settings.model_spark,
                input=[user_message(text_part(PROMPT), image_part(sent, "image/jpeg"))],
                instructions=INSTRUCTIONS,
                effort="low",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                op=OP,
            )
        except NoRecordingError as exc:
            if loader:
                raise  # the demo loader lists the photos its set has no recording of
            return self._failed(kept, digest, exc)
        except (ModelApiError, ValueError) as exc:
            return self._failed(kept, digest, exc)
        finally:
            exact_replay.reset(token)
        areas, problem = place(result.parsed, width, height)
        if problem and kept is not None and kept.status in ("clear", "found"):
            log.info("photo check not placed", extra={"digest": digest, "reason": problem})
            return kept
        response = result.response
        check = PhotoCheck(
            digest=digest,
            status="failed" if problem else ("found" if areas else "clear"),
            areas=areas,
            reason=problem,
            model=response.model,
            from_fixture=response.from_fixture,
            cost_usd=response.cost_usd,
            checked_at=_now(),
        )
        if kept is not None and again:
            # a check run again keeps the owner's choice for an area of the same kind in the
            # same place
            check.areas = [_keep_choice(a, kept.areas) for a in check.areas]
        log.info(
            "photo checked",
            extra={"digest": digest, "status": check.status, "areas": len(areas)},
        )
        return self._save(check)

    def _failed(self, kept: PhotoCheck | None, digest: str, exc: Exception) -> PhotoCheck:
        log.info("photo check failed", extra={"digest": digest, "error": str(exc)[:200]})
        if kept is not None and kept.status in ("clear", "found"):
            return kept  # a check run again that fails leaves the finished one standing
        return self._save(
            PhotoCheck(digest=digest, status="failed", reason=_short(exc), checked_at=_now())
        )

    async def check_all(self, photos: list[bytes], *, again: bool = False) -> list[PhotoCheck]:
        """Each photo checked, at the same time, and the same photo once; in the order
        given."""
        unique = {digest_of(d): d for d in photos}
        if len(unique) < len(photos):
            checked = await self.check_all(list(unique.values()), again=again)
            done = dict(zip(unique, checked, strict=True))
            return [done[digest_of(d)] for d in photos]
        out: list[PhotoCheck | None] = [None] * len(photos)

        async def one(n: int, data: bytes) -> None:
            out[n] = await self.check(data, again=again)

        async with anyio.create_task_group() as group:
            for n, data in enumerate(photos):
                group.start_soon(one, n, data)
        return [c for c in out if c is not None]

    def choose(self, data: bytes, area_id: int, hidden: bool) -> PhotoCheck:
        """The owner's choice for one area: shown on shared copies, or hidden again."""
        check = self.kept(data)
        if check is None or not any(a.id == area_id for a in check.areas):
            raise LookupError(f"no area {area_id} on this photo")
        for area in check.areas:
            if area.id == area_id:
                area.hidden = hidden
        return self._save(check)

    def shared_copy(self, data: bytes, *, unchecked: bool = False) -> bytes:
        """The copy that may leave the owner's view: the hidden areas black, no metadata. A
        photo without a finished check raises NotCheckedError, unless ``unchecked`` says the
        owner chose to share it as it is."""
        check = self.kept(data)
        if check is None or check.status not in ("clear", "found"):
            if not unchecked:
                raise NotCheckedError(note_for(check))
            return redacted(data, [])
        return redacted(data, check.areas)

    def shared_or_none(self, data: bytes) -> bytes | None:
        try:
            return self.shared_copy(data)
        except NotCheckedError:
            return None

    def sample_areas(self, sample_id: str, data: bytes) -> list[Area]:
        """The hidden areas of a demo-set photo, from the check the loader kept for the same
        photo on its item; none when the set was not loaded here. The set's photos are masked
        by hand before they are committed: these areas go on top of that."""
        digest = self._sample_digests.get(sample_id)
        if digest is None:
            s = self.settings
            try:
                stored = prepare(data, max_px=s.image_max_px, max_bytes=s.max_upload_mb << 20)
            except BadImageError:
                return []
            digest = self._sample_digests[sample_id] = digest_of(stored)
        path = self._path(digest)
        if not path.is_file():
            return []
        try:
            check = PhotoCheck.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [a for a in check.areas if a.hidden]

    def privacy(self, n: int, data: bytes) -> PhotoPrivacy:
        check = self.kept(data)
        return PhotoPrivacy(
            n=n,
            status=check.status if check is not None else "unchecked",
            areas=check.areas if check is not None else [],
            note=note_for(check),
            shared=check is not None and check.status in ("clear", "found"),
            reason=check.reason if check is not None else "",
        )


def _measured(data: bytes) -> tuple[int, int, bytes]:
    """The photo's size and the copy the model reads: the photo with its grid drawn on."""
    try:
        with Image.open(BytesIO(data)) as img:
            rgb = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("the photo could not be opened") from exc
    return rgb.width, rgb.height, gridded(rgb)


def _short(exc: Exception) -> str:
    """Why a check failed, as the owner reads it under the photo."""
    if isinstance(exc, FixtureMissingError):
        return "no recorded answer for this photo; a key checks it live"
    if isinstance(exc, SpendCapError):
        return "the spend cap is reached"
    text = " ".join(str(exc).split())
    return text[:160]


def _keep_choice(area: Area, before: list[Area]) -> Area:
    for old in before:
        if (
            old.kind == area.kind
            and abs(old.x - area.x) < 0.05
            and abs(old.y - area.y) < 0.05
            and not old.hidden
        ):
            return area.model_copy(update={"hidden": False})
    return area


__all__ = [
    "OP",
    "NotCheckedError",
    "Privacy",
    "digest_of",
    "note_for",
    "place",
]
