"""Load the demo set through the same services the API uses. In record mode (a key and
``OPL_RECORD_FIXTURES=1``) every model answer is written as a fixture; in fixture mode the same
run replays them. Photos are given to the services as they would be uploaded, so the exact
match on the request digest holds for the files in the set."""

import logging
import shutil
import wave
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import TypeVar

import yaml

from app.config import Settings
from app.decide import DecisionCreate
from app.decide.service import Decider
from app.demo.schema import DemoItem, DemoMeasurement, DemoSet, Outcome
from app.extract import Extractor
from app.extract.imaging import BadImageError, dimensions, prepare
from app.find import Finder
from app.find.schema import CandidateCreate, SearchCreate
from app.inventory import Inventory
from app.inventory.parent import PARENT_DEVICE, PARENT_MODEL, device_model
from app.inventory.schema import FieldCreate, ItemCreate
from app.listing import Lister, VoiceNotes
from app.listing.schema import DraftRequest
from app.measure import Measurer, MeasureRequest
from app.measure.schema import ImageSize
from app.model_api import ModelApiClient, ModelApiError, NoRecordingError, exact_replay
from app.photos import DevicePhotos, ItemPhotos, PhotoError
from app.picture import Pictures, PicturesOffError
from app.privacy import Privacy
from app.profiles import Profiles
from app.projects import Planner, ProposeRequest
from app.value import Valuer
from app.value.schema import PriceRequest

log = logging.getLogger("app.demo")

T = TypeVar("T")

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
    under out_dir; WAV notes rewritten as the sound alone (the header and the frames; a
    recorder's or an editor's own chunks dropped) into notes_dir (out_dir when none is given);
    anything else left behind with a note. Two sources that would land on one name get
    numbered. The raw directory is never written to."""
    out_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = notes_dir or out_dir
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    written: set[Path] = set()

    def free(folder: Path, stem: str, suffix: str) -> Path:
        target = folder / f"{stem}{suffix}"
        n = 1
        while target in written:
            n += 1
            target = folder / f"{stem}-{n}{suffix}"
        written.add(target)
        return target

    for src in sorted(p for p in raw_dir.iterdir() if p.is_file()):
        suffix = src.suffix.lower()
        if suffix in PHOTO_SUFFIXES:
            try:
                data = prepare(src.read_bytes(), max_px=SCRUB_MAX_PX, max_bytes=SCRUB_MAX_BYTES)
            except BadImageError as exc:
                notes.append(f"{src.name}: {exc}")
                continue
            target = free(out_dir, src.stem, ".jpg")
            target.write_bytes(data)
            notes.append(f"{src.name} -> {target.name} ({len(data) // 1024} KB, no metadata)")
        elif suffix in NOTE_SUFFIXES:
            target = free(notes_dir, src.stem, ".wav")
            try:
                with wave.open(str(src), "rb") as sound:
                    params = sound.getparams()
                    frames = sound.readframes(sound.getnframes())
                with wave.open(str(target), "wb") as clean:
                    clean.setparams(params)
                    clean.writeframes(frames)
            except (wave.Error, EOFError, OSError) as exc:
                written.discard(target)
                notes.append(f"{src.name}: not a WAV file that reads: {exc}")
                continue
            notes.append(f"{src.name} -> {notes_dir.name}/{target.name} (the sound alone)")
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
        pictures: Pictures | None = None,
        privacy: Privacy | None = None,
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
        self.pictures = pictures
        self.privacy = privacy
        # the set's photos stay with the items they were read from, as a capture's do
        self.photos = ItemPhotos(settings, inventory)
        # a part's photos of the device it came from, kept apart from its own
        self.device_photos = DevicePhotos(settings, inventory)
        # geometry only: a measurement calls no model, so it is the same in every mode
        self.measurer = Measurer(settings, Profiles())
        # the Decide cards, the ideas and the decision, as the owner's buttons ask for them
        self.decider = Decider(
            settings, client, inventory, planner.templates, planner, valuer, finder
        )

    async def run(self, demo: DemoSet, base: Path) -> Outcome:
        out = Outcome(mode=self.settings.model_api_mode)
        self.currency, self.country = demo.currency, demo.country
        stubs_before = self.client.fixture_fallbacks
        # the profile's answers first, so every step that reads them (the ideas, the cards, the
        # proposals below) reads the same ones; marked as the loader's, the cards still say they
        # are written for an average person until the owner saves the form
        if demo.propose is not None:
            self.planner.set_preferences(demo.propose.preferences, by_demo=True)
        # the set's keys to the ids the inventory gave, kept for whoever scores the run
        self.ids = ids = {}
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
                        profile=search.profile,
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
                    try:
                        text = file.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError) as exc:
                        out.skipped.append(f"search {search.key} listing {n}: {file.name}: {exc}")
                        continue
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
            if search.web:
                await self.search_web(search.key, created.id, out)
            if search.plan:
                planned = await self.exactly(
                    f"search {search.key}: the search plan",
                    partial(self.finder.plan, created.id),
                    out,
                )
                if planned is not None and planned.plan is not None:
                    out.plans += 1
                    out.cost_usd += planned.plan.cost_usd
        if demo.propose is not None:
            try:
                self.planner.set_preferences(demo.propose.preferences, by_demo=True)
                projects = await self.planner.propose(
                    ProposeRequest(count=demo.propose.count, note=demo.propose.note)
                )
            except (ValueError, ModelApiError) as exc:
                out.skipped.append(f"proposals: {exc}")
            else:
                out.projects += len(projects)
                out.cost_usd += sum(p.cost_usd for p in projects)
                if demo.propose.pictures and self.pictures is not None:
                    pictures = self.pictures
                    for project in projects:
                        drawn = await self.exactly(
                            f"project {project.title}: picture",
                            partial(pictures.draw_project, project),
                            out,
                        )
                        if drawn is not None:
                            out.pictures += 1
                            out.cost_usd += drawn.cost_usd
        self.record_decisions(demo, out)
        out.stub_answers = self.client.fixture_fallbacks - stubs_before
        log.info(
            "demo set loaded",
            extra={"mode": out.mode, "items": out.items, "stub_answers": out.stub_answers},
        )
        return out

    async def load_item(self, item: DemoItem, base: Path, out: Outcome) -> int | None:
        photos: list[bytes] = []
        for name in item.photos:
            file = base / name
            if not file.is_file():
                out.skipped.append(f"{item.key}: photo {name} missing")
                continue
            try:
                photos.append(file.read_bytes())
            except OSError as exc:
                out.skipped.append(f"{item.key}: photo {name}: {exc}")
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
        try:
            created = self.inventory.create(spec)
        except ValueError as exc:
            out.skipped.append(f"{item.key}: {exc}")
            return None
        # the demo set is the public shelf: what it loads, the demo visitor may see
        self.inventory.set_public(created.id, True)
        if photos:
            try:
                self.photos.add(created.id, photos)
            except (OSError, BadImageError, PhotoError) as exc:
                out.skipped.append(f"{item.key}: the photos could not be kept: {exc}")
            else:
                await self.check_photos(item, created.id, out)
        out.items += 1
        if item.accept_all:
            for assertion in created.assertions:
                if assertion.review == "proposed":
                    try:
                        self.inventory.review(created.id, assertion.id, "accepted")
                    except (ValueError, LookupError) as exc:
                        out.skipped.append(f"{item.key}: accepting {assertion.field}: {exc}")
        for field, value in item.fields.items():
            try:
                self.inventory.add_field(created.id, FieldCreate(field=field, value=value))
            except ValueError as exc:
                out.skipped.append(f"{item.key}: field {field}: {exc}")
        for measurement in item.measurements:
            await self.measure(item, created.id, measurement, base, out)
        if item.parent_photos or item.parent_device_model:
            await self.load_parent(item, created.id, base, out)
        if item.parent_device:
            try:
                self.inventory.add_field(
                    created.id, FieldCreate(field=PARENT_DEVICE, value=item.parent_device)
                )
            except ValueError as exc:
                out.skipped.append(f"{item.key}: parent device: {exc}")
        if item.voice_note:
            file = base / item.voice_note
            if not file.is_file():
                out.skipped.append(f"{item.key}: voice note {item.voice_note} missing")
            else:
                try:
                    note = await self.voice.note(created.id, file.read_bytes())
                except (OSError, ValueError, ModelApiError) as exc:
                    out.skipped.append(f"{item.key}: voice note: {exc}")
                else:
                    out.voice_notes += 1
                    out.cost_usd += note.cost_usd
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
        if item.picture:
            await self.draw(item, created.id, out)
        await self.decide(item, created.id, out)
        return created.id

    async def measure(
        self, item: DemoItem, item_id: int, spec: DemoMeasurement, base: Path, out: Outcome
    ) -> None:
        """One feature measured from the marks the set gives, kept on the item as the owner's
        own capture is; an accepted value is confirmed like the item's other readings."""
        file = base / spec.photo
        if not file.is_file():
            out.skipped.append(f"{item.key}: measurement photo {spec.photo} missing")
            return
        try:
            photo = file.read_bytes()
            image = spec.image
            if image is None:
                width, height = dimensions(photo)
                image = ImageSize(width=width, height=height)
            request = MeasureRequest(
                feature=spec.feature,
                profile=item.profile or None,
                image=image,
                reference=spec.reference,
                points=spec.points,
                straight_on=spec.straight_on,
            )
            result, prepared = await self.measurer.measure(photo, request)
        except (OSError, ValueError, BadImageError) as exc:
            out.skipped.append(f"{item.key}: measurement of {spec.feature}: {exc}")
            return
        kept = self.inventory.add_measurement(item_id, result, prepared)
        if not result.accepted or kept.assertion_id is None:
            out.skipped.append(f"{item.key}: measurement of {spec.feature} refused: {result.redo}")
            return
        out.measurements += 1
        if item.accept_all:
            self.inventory.review(item_id, kept.assertion_id, "accepted")

    async def exactly(self, what: str, call: Callable[[], Awaitable[T]], out: Outcome) -> T | None:
        """One step the owner's button takes, answered in fixture mode only by the recording of
        this very request (never a stub passed off as the model's answer): without one it is
        left out and listed as not recorded yet."""
        token = exact_replay.set(True)
        try:
            return await call()
        except NoRecordingError:
            out.unrecorded.append(f"{what} (one ./dev record-fixtures run makes it)")
        except PicturesOffError:
            out.unrecorded.append(f"{what} (left out: PICTURE_ENABLED is off)")
        except (ValueError, LookupError, ModelApiError) as exc:
            out.skipped.append(f"{what}: {exc}")
        finally:
            exact_replay.reset(token)
        return None

    async def decide(self, item: DemoItem, item_id: int, out: Outcome) -> None:
        """What the owner asked under Decide, kept on the item as the buttons keep it: the
        ideas and the cards (written from the items loaded before it) with the first reuse card
        drawn, so the visitor reads them without asking a model; the plan chosen is recorded
        at the end of the run (record_decisions)."""
        if item.ideas:
            uses = await self.exactly(f"{item.key}: ideas", lambda: self.decider.uses(item_id), out)
            if uses is not None:
                out.ideas += 1
                out.cost_usd += uses.cost_usd
        if item.decide:
            cards = await self.exactly(
                f"{item.key}: Decide cards", lambda: self.decider.scenarios(item_id), out
            )
            if cards is not None:
                out.cards += 1
                out.cost_usd += cards.cost_usd
                if item.reuse_picture and cards.reuse and self.pictures is not None:
                    pictures = self.pictures
                    drawn = await self.exactly(
                        f"{item.key}: reuse card picture",
                        lambda: pictures.draw_card(cards, 0),
                        out,
                    )
                    if drawn is not None:
                        out.pictures += 1
                        out.cost_usd += drawn.cost_usd

    def record_decisions(self, demo: DemoSet, out: Outcome) -> None:
        """The plan chosen for each item, recorded after everything else is asked: keep and fix
        writes the repair steps into the item's notes, and nothing asked before may read them."""
        for item in demo.items:
            item_id = self.ids.get(item.key)
            if item.decision is None or item_id is None:
                continue
            try:
                self.decider.decide(
                    item_id, DecisionCreate(choice=item.decision, note=item.decision_note)
                )
            except (ValueError, LookupError) as exc:
                out.skipped.append(f"{item.key}: decision: {exc}")
            else:
                out.decisions += 1

    async def check_photos(self, item: DemoItem, item_id: int, out: Outcome) -> None:
        """The item's photos checked for private details, as an upload is, so the demo visitor
        gets them with those areas black; in fixture mode only the recording of each very
        photo answers (never a stub), and a photo without one stays out of the visitor's view
        and is listed as not recorded yet."""
        if self.privacy is None:
            return
        for n in range(1, self.photos.count(item_id) + 1):
            token = exact_replay.set(True)
            try:
                check = await self.privacy.check(self.photos.read(item_id, n))
            except NoRecordingError:
                out.unrecorded.append(
                    f"{item.key}: the check of photo {n} for private details (one"
                    " ./dev record-fixtures run makes it)"
                )
                continue
            finally:
                exact_replay.reset(token)
            if check.status == "failed":
                out.skipped.append(f"{item.key}: photo {n} check: {check.reason}")
                continue
            out.checked += 1
            out.hidden += len(check.areas)
            out.cost_usd += check.cost_usd

    async def load_parent(self, item: DemoItem, item_id: int, base: Path, out: Outcome) -> None:
        """The device a part came from, as the owner answers the app's question: photos of it
        read once as a label (only a recording of these very photos answers in fixture mode,
        never the stub), the model read off them accepted as parent_device_model; until that
        reading is recorded, the model the set states is saved as typed."""
        photos: list[bytes] = []
        for name in item.parent_photos:
            file = base / name
            if not file.is_file():
                out.skipped.append(f"{item.key}: parent photo {name} missing")
                continue
            try:
                photos.append(file.read_bytes())
            except OSError as exc:
                out.skipped.append(f"{item.key}: parent photo {name}: {exc}")
        model = ""
        if photos:
            token = exact_replay.set(True)
            try:
                reading = await self.extractor.extract(photos)
            except NoRecordingError:
                out.unrecorded.append(
                    f"{item.key}: the reading of the device photos (one ./dev record-fixtures"
                    " run reads them)"
                )
            except (BadImageError, ModelApiError) as exc:
                out.skipped.append(f"{item.key}: the device photos could not be read: {exc}")
            else:
                out.photos += len(photos)
                out.cost_usd += reading.cost_usd
                model, confidence, raw = device_model(reading)
                if model:
                    read = self.inventory.add_observation(
                        item_id, PARENT_MODEL, model, confidence=confidence, source="photo", raw=raw
                    )
                    self.inventory.review(item_id, read.fields[PARENT_MODEL].id, "accepted")
            finally:
                exact_replay.reset(token)
            # kept apart from the part's own photos: never in a draft or seen by the visitor
            try:
                self.device_photos.add(item_id, photos)
            except (OSError, BadImageError, PhotoError) as exc:
                out.skipped.append(f"{item.key}: the device photos could not be kept: {exc}")
        if not model and item.parent_device_model:
            try:
                self.inventory.add_field(
                    item_id,
                    FieldCreate(
                        field=PARENT_MODEL, value=item.parent_device_model, provenance="documented"
                    ),
                )
            except ValueError as exc:
                out.skipped.append(f"{item.key}: parent device model: {exc}")

    async def search_web(self, key: str, search_id: int, out: Outcome) -> None:
        """Search the web for the search, as the owner's button does. Only the recording of
        this very request answers in fixture mode (its brief names the device the part came
        from as read from its photos): without one the step is left out and listed as not
        recorded yet, never the stub's pages passed off as finds."""
        token = exact_replay.set(True)
        try:
            found = await self.finder.search_web(search_id)
        except NoRecordingError:
            out.unrecorded.append(f"search {key}: Search the web (one record run searches it)")
        except (ValueError, ModelApiError) as exc:
            out.skipped.append(f"search {key}: Search the web: {exc}")
        else:
            out.web_finds += found.added
            out.cost_usd += found.cost_usd
        finally:
            exact_replay.reset(token)

    async def draw(self, item: DemoItem, item_id: int, out: Outcome) -> None:
        """The item's picture, after its drafts. With a key it is drawn (and kept, in record
        mode); in fixture mode only the recording of this very drawing answers: without one
        the picture is left out and listed as not recorded yet, never the stub image passed
        off as a drawing."""
        if self.pictures is None:
            out.skipped.append(f"{item.key}: picture: no pictures service in this run")
            return
        token = exact_replay.set(True)
        try:
            picture = await self.pictures.draw(item_id, item.picture)
        except NoRecordingError:
            out.unrecorded.append(f"{item.key}: picture (one ./dev record-fixtures run draws it)")
        except PicturesOffError:
            out.unrecorded.append(f"{item.key}: picture (left out: PICTURE_ENABLED is off)")
        except (ValueError, LookupError, ModelApiError) as exc:
            out.skipped.append(f"{item.key}: picture: {exc}")
        else:
            out.pictures += 1
            out.cost_usd += picture.cost_usd
        finally:
            exact_replay.reset(token)

    # the set's currency and country, read once per run
    currency: str = "USD"
    country: str = ""
    ids: dict[str, int] = {}


def reset(settings: Settings) -> list[str]:
    """Start over: the inventory file goes, and with it the captures' media, the items'
    photos, the checks of those photos for private details and the pictures drawn for items
    and projects (their rows were in the file; the next inventory counts from 1 again); the
    spend ledger stays (the cap is cumulative)."""
    gone: list[str] = []
    db = settings.inventory_db_path
    for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm"), Path(f"{db}-journal")):
        if path.is_file():
            path.unlink()
            gone.append(path.name)
    for name in ("captures", "items", "projects", "privacy"):
        folder = settings.data_dir / name
        if folder.is_dir():
            shutil.rmtree(folder)
            gone.append(f"{name}/")
    return gone
