"""Load the demo set through the same services the API uses. In record mode (a key and
``OPL_RECORD_FIXTURES=1``) every model answer is written as a fixture; in fixture mode the same
run replays them. Photos are given to the services as they would be uploaded, so the exact
match on the request digest holds for the files in the set."""

import logging
import shutil
from pathlib import Path

import yaml

from app.config import Settings
from app.demo.schema import DemoItem, DemoSet, Outcome
from app.extract import Extractor
from app.extract.imaging import BadImageError, prepare
from app.find import Finder
from app.find.schema import CandidateCreate, SearchCreate
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.listing import Lister, VoiceNotes
from app.listing.schema import DraftRequest
from app.model_api import ModelApiClient, ModelApiError
from app.projects import Planner, ProposeRequest
from app.value import Valuer
from app.value.schema import PriceRequest

log = logging.getLogger("app.demo")

SCRUB_MAX_PX = 1600
SCRUB_MAX_BYTES = 40 * 1024 * 1024
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
NOTE_SUFFIXES = {".wav"}


def load_set(path: Path) -> DemoSet:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    found = DemoSet.model_validate(raw)
    found.check()
    return found


def scrub(raw_dir: Path, out_dir: Path, notes_dir: Path | None = None) -> list[str]:
    """Raw photos re-encoded without any metadata, long side at most SCRUB_MAX_PX, as JPEGs
    under out_dir; WAV notes copied as they are into notes_dir (out_dir when none is given);
    anything else left behind with a note. The raw directory is never written to."""
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = notes_dir or out_dir
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    for src in sorted(p for p in raw_dir.iterdir() if p.is_file()):
        suffix = src.suffix.lower()
        if suffix in PHOTO_SUFFIXES:
            try:
                data = prepare(src.read_bytes(), max_px=SCRUB_MAX_PX, max_bytes=SCRUB_MAX_BYTES)
            except BadImageError as exc:
                notes.append(f"{src.name}: {exc}")
                continue
            (out_dir / f"{src.stem}.jpg").write_bytes(data)
            notes.append(f"{src.name} -> {src.stem}.jpg ({len(data) // 1024} KB, no metadata)")
        elif suffix in NOTE_SUFFIXES:
            shutil.copyfile(src, notes_dir / src.name)
            notes.append(f"{src.name} -> {notes_dir.name}/{src.name} (copied)")
        else:
            notes.append(f"{src.name}: not a photo or a WAV note; left out")
    return notes


class Loader:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        extractor: Extractor,
        lister: Lister,
        voice: VoiceNotes,
        valuer: Valuer,
        finder: Finder,
        planner: Planner,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.extractor = extractor
        self.lister = lister
        self.voice = voice
        self.valuer = valuer
        self.finder = finder
        self.planner = planner

    async def run(self, demo: DemoSet, base: Path) -> Outcome:
        out = Outcome(mode=self.settings.model_api_mode)
        self.currency, self.country = demo.currency, demo.country
        ids: dict[str, int] = {}
        for item in demo.items:
            item_id = await self.load_item(item, base, out)
            if item_id is not None:
                ids[item.key] = item_id
        for search in demo.searches:
            need_id = ids.get(search.need) if search.need else None
            if search.need and need_id is None:
                out.skipped.append(f"search {search.key}: its item {search.need} was not loaded")
                continue
            try:
                created = self.finder.create(
                    SearchCreate(
                        need_item_id=need_id,
                        profile=search.profile if need_id is None else "",
                        title=search.title,
                        spec=search.spec,
                        max_price=search.max_price,
                        currency=search.currency,
                    )
                )
            except ValueError as exc:
                out.skipped.append(f"search {search.key}: {exc}")
                continue
            out.searches += 1
            for n, listing in enumerate(search.listings, 1):
                text = listing.text
                if text.startswith("@"):
                    file = base / text[1:]
                    if not file.is_file():
                        out.skipped.append(f"search {search.key} listing {n}: {file.name} missing")
                        continue
                    text = file.read_text(encoding="utf-8")
                try:
                    candidate = await self.finder.add_candidate(
                        created.id,
                        CandidateCreate(
                            text=text,
                            observed_on=listing.observed_on,
                            asking_price=listing.asking_price,
                            currency=listing.currency,
                            location=listing.location,
                        ),
                    )
                except (ValueError, ModelApiError) as exc:
                    out.skipped.append(f"search {search.key} listing {n}: {exc}")
                    continue
                out.candidates += 1
                out.cost_usd += candidate.cost_usd
        if demo.propose is not None:
            self.planner.set_preferences(demo.propose.preferences)
            try:
                projects = await self.planner.propose(
                    ProposeRequest(count=demo.propose.count, note=demo.propose.note)
                )
            except (ValueError, ModelApiError) as exc:
                out.skipped.append(f"proposals: {exc}")
            else:
                out.projects += len(projects)
                out.cost_usd += sum(p.cost_usd for p in projects)
        log.info("demo set loaded", extra={"mode": out.mode, "items": out.items})
        return out

    async def load_item(self, item: DemoItem, base: Path, out: Outcome) -> int | None:
        photos: list[bytes] = []
        for name in item.photos:
            file = base / name
            if not file.is_file():
                out.skipped.append(f"{item.key}: photo {name} missing")
                continue
            photos.append(file.read_bytes())
        try:
            spec = ItemCreate(
                name=item.name,
                item_type=item.item_type,
                profile=item.profile,
                condition=item.condition,
                faults=item.faults,
                tests_done=item.tests_done,
                accessories=item.accessories,
                intent=item.intent,
                availability=item.availability,
            )
        except ValueError as exc:
            out.skipped.append(f"{item.key}: {exc}")
            return None
        if photos:
            try:
                reading = await self.extractor.extract(photos)
            except (BadImageError, ModelApiError) as exc:
                out.skipped.append(f"{item.key}: the photos could not be read: {exc}")
            else:
                spec = spec.model_copy(update={"extraction": reading})
                if not spec.item_type:
                    spec = spec.model_copy(update={"item_type": reading.item_type})
                out.photos += len(photos)
                out.cost_usd += reading.cost_usd
        if not spec.item_type:
            spec = spec.model_copy(update={"item_type": "item"})
        created = self.inventory.create(spec)
        out.items += 1
        if item.accept_all:
            for assertion in created.assertions:
                if assertion.review == "proposed":
                    self.inventory.review(created.id, assertion.id, "accepted")
        for field, value in item.fields.items():
            try:
                self.inventory.add_field(created.id, FieldCreate(field=field, value=value))
            except ValueError as exc:
                out.skipped.append(f"{item.key}: field {field}: {exc}")
        if item.voice_note:
            file = base / item.voice_note
            if not file.is_file():
                out.skipped.append(f"{item.key}: voice note {item.voice_note} missing")
            else:
                try:
                    note = await self.voice.note(created.id, file.read_bytes())
                except (ValueError, ModelApiError) as exc:
                    out.skipped.append(f"{item.key}: voice note: {exc}")
                else:
                    out.voice_notes += 1
                    out.cost_usd += note.cost_usd
        if item.draft is not None:
            try:
                draft = await self.lister.draft(
                    created.id,
                    DraftRequest(
                        mode=item.draft, holds_data=item.holds_data, asking_price=item.asking_price
                    ),
                )
            except (ValueError, ModelApiError) as exc:
                out.skipped.append(f"{item.key}: draft: {exc}")
            else:
                out.drafts += 1
                out.cost_usd += draft.cost_usd
        if item.price:
            try:
                guidance = await self.valuer.guide(
                    created.id, PriceRequest(currency=self.currency, country=self.country)
                )
            except (ValueError, ModelApiError) as exc:
                out.skipped.append(f"{item.key}: price guidance: {exc}")
            else:
                out.guidances += 1
                out.cost_usd += guidance.cost_usd
        return created.id

    # the set's currency and country, read once per run
    currency: str = "USD"
    country: str = ""


def reset(settings: Settings) -> list[str]:
    """Start over: the inventory file goes, and the captures' media with it (their rows were in
    the file); the spend ledger stays (the cap is cumulative)."""
    gone: list[str] = []
    db = settings.inventory_db_path
    for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm"), Path(f"{db}-journal")):
        if path.is_file():
            path.unlink()
            gone.append(path.name)
    captures = settings.data_dir / "captures"
    if captures.is_dir():
        shutil.rmtree(captures)
        gone.append("captures/")
    return gone
