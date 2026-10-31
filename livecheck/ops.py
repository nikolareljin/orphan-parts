"""The api mode: each operation once, through the service the route calls, on one item made
from the demo set in a temporary inventory. The spend ledger is the backend's own file, so what
the check spends counts against SPEND_CAP_USD like any other call."""

import logging
import math
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from app.config import Settings, get_settings
from app.decide import Decider
from app.extract import Extractor
from app.find import Finder
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.listing import Lister
from app.listing.schema import DraftRequest
from app.listing.voice import VoiceNotes
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient
from app.picture import Pictures
from app.profiles import Profiles
from app.projects import Planner, Templates
from app.projects.schema import ProposeRequest
from app.segment import Segmenter
from app.value import Valuer
from app.value.schema import PriceRequest
from livecheck import inputs
from livecheck.ceilings import Ceiling, ceiling
from livecheck.report import FAIL, HEADER, PASS, SKIP, RefusedError, Result, Run, one_line, said

# cheapest first; picture (Muse Image, priced per image) only when asked for by name
OPS = ["segment", "transcribe", "extract", "listing-text", "draft", "uses", "propose", "price"]
PICTURE = "picture"
ALL_OPS = [*OPS, PICTURE]
SEGMENT_CONCEPT = "label"

log = logging.getLogger("livecheck")


@dataclass
class Services:
    settings: Settings
    client: ModelApiClient
    ledger: CostLedger
    inventory: Inventory
    extractor: Extractor
    segmenter: Segmenter
    lister: Lister
    valuer: Valuer
    finder: Finder
    planner: Planner
    pictures: Pictures
    decider: Decider
    voice: VoiceNotes
    item_id: int
    photo: bytes
    audio: bytes
    text: str
    currency: str
    country: str


def _settings(work: Path) -> Settings:
    """The backend's settings with a temporary data directory for the inventory and the
    pictures, the backend's own ledger file kept, and pictures allowed for the picture op. The
    inventory file is named again: an absolute INVENTORY_DB_FILE would take the probe item
    past the temporary directory into the real inventory."""
    base = get_settings()
    ledger_file = base.spend_ledger_path.resolve()
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    return base.model_copy(
        update={
            "data_dir": work,
            "spend_ledger_file": str(ledger_file),
            "inventory_db_file": "inventory.sqlite3",
            "picture_enabled": True,
        }
    )


def _wire(settings: Settings, client: ModelApiClient, ledger: CostLedger, out: TextIO) -> Services:
    """The services as app.main builds them, on one item from the demo set."""
    inventory = Inventory(settings)
    extractor = Extractor(settings, client)
    profiles = Profiles()
    assessor = Assessor(profiles, inventory)
    finder = Finder(settings, client, inventory, profiles, extractor, assessor)
    templates = Templates()
    planner = Planner(settings, client, inventory, templates, finder)
    valuer = Valuer(settings, client, inventory)
    base = inputs.demo_dir()
    item = inputs.demo_item(base)
    created = inventory.create(
        ItemCreate(
            name=item.name,
            item_type=item.item_type or "item",
            profile=item.profile,
            condition=item.condition,
            tests_done=item.tests_done,
            intent="keep",
        )
    )
    for field, value in item.fields.items():
        inventory.add_field(created.id, FieldCreate(field=field, value=value))
    photo, photo_from = inputs.label_photo(base, item)
    audio, audio_from = inputs.voice_note(base, item)
    text, text_from = inputs.listing_text(base)
    currency, country = inputs.currency_country(base)
    print(
        f"item: {item.name} ({item.key}); photo: {photo_from}; note: {audio_from};"
        f" text: {text_from}",
        file=out,
    )
    return Services(
        settings=settings,
        client=client,
        ledger=ledger,
        inventory=inventory,
        extractor=extractor,
        segmenter=Segmenter(settings, client),
        lister=Lister(settings, client, inventory),
        valuer=valuer,
        finder=finder,
        planner=planner,
        pictures=Pictures(settings, client, inventory, templates),
        decider=Decider(settings, client, inventory, templates, planner, valuer, finder),
        voice=VoiceNotes(settings, client, inventory),
        item_id=created.id,
        photo=photo,
        audio=audio,
        text=text,
        currency=currency,
        country=country,
    )


# --- one call per operation, as the route makes it -------------------------------------------


async def _extract(s: Services) -> str:
    reading = await s.extractor.extract([s.photo])
    return f"fields={len(reading.fields)} from_fixture={reading.from_fixture}"


async def _segment(s: Services) -> str:
    found = await s.segmenter.segment(s.photo, [SEGMENT_CONCEPT])
    return f"regions={len(found.regions)} from_fixture={found.from_fixture}"


async def _transcribe(s: Services) -> str:
    # the route's own service: the length check before the call, the empty check after it
    heard = await s.voice.note(s.item_id, s.audio)
    return (
        f"{heard.seconds:.1f}s heard, {len(heard.transcript)} chars,"
        f" from_fixture={heard.from_fixture}"
    )


async def _listing_text(s: Services) -> str:
    parsed, response = await s.finder.read_text(s.text, [])
    return f"fields={len(parsed.fields)} from_fixture={response.from_fixture}"


async def _draft(s: Services) -> str:
    draft = await s.lister.draft(s.item_id, DraftRequest(mode="sell"))
    return (
        f"facts={len(draft.facts)} warnings={len(draft.warnings)} from_fixture={draft.from_fixture}"
    )


async def _uses(s: Services) -> str:
    uses = await s.decider.uses(s.item_id)
    return f"uses={len(uses.uses)} from_fixture={uses.from_fixture}"


async def _propose(s: Services) -> str:
    projects = await s.planner.propose(ProposeRequest(count=1))
    return f"proposed={s.planner.last_proposed} kept={len(projects)}"


async def _price(s: Services) -> str:
    guidance = await s.valuer.guide(s.item_id, PriceRequest(currency=s.currency, country=s.country))
    return (
        f"searches={guidance.searches} comparables={len(guidance.comparables)}"
        f" from_fixture={guidance.from_fixture}"
    )


async def _picture(s: Services) -> str:
    picture = await s.pictures.draw(s.item_id, None)
    return f"drawn as {picture.use!r} from_fixture={picture.from_fixture}"


CALLS: dict[str, Callable[[Services], Awaitable[str]]] = {
    "segment": _segment,
    "transcribe": _transcribe,
    "extract": _extract,
    "listing-text": _listing_text,
    "draft": _draft,
    "uses": _uses,
    "propose": _propose,
    "price": _price,
    PICTURE: _picture,
}


# --- the run -------------------------------------------------------------------------------


async def _one(s: Services, op: str, live: bool) -> Result:
    before = len(s.ledger.entries())
    started = time.perf_counter()
    try:
        note = await CALLS[op](s)
        status = PASS
    except Exception as exc:
        note = one_line(exc)
        status = FAIL
    ms = round((time.perf_counter() - started) * 1000, 1)
    entries = s.ledger.entries()[before:]
    if live and status == PASS and not any(not e.fixture for e in entries):
        # a live pass is a call the API answered and billed, not a recording or a cache
        status = FAIL
        note = f"no live call on the ledger for this op; {note}"
    return Result(
        op=op,
        model=entries[-1].model if entries else "-",
        status=status,
        ms=ms,
        input_tokens=sum(e.usage.input_tokens for e in entries),
        output_tokens=sum(e.usage.output_tokens for e in entries),
        reasoning_tokens=sum(e.usage.reasoning_tokens for e in entries),
        usd=round(sum(e.usd for e in entries), 6),
        note=note,
    )


def plan(ops: list[str], ceilings: dict[str, Ceiling], beyond: list[str], max_usd: float) -> str:
    """What the guard will do with ``ops`` at ``max_usd``, said before the first call."""
    total = sum(c.usd for c in ceilings.values())
    if total <= max_usd:
        return f"ceilings: ${total:.4f} for {len(ops)} ops, under --max-usd {max_usd:.2f}"
    text = f"ceilings: ${total:.4f} for {len(ops)} ops, above --max-usd {max_usd:.2f};"
    if beyond:
        named = ", ".join(
            f"{op} (${ceilings[op].usd:.4f}; alone: --ops {op} --max-usd"
            f" {math.ceil(ceilings[op].usd * 100) / 100:.2f})"
            for op in beyond
        )
        text += f" skipped, each above it on its own: {named};"
    return text + " the rest run while what is spent plus the next ceiling stays under it"


async def run_api(ops: list[str], max_usd: float, keep_going: bool, out: TextIO) -> Run:
    """Every operation asked for, once each, cheapest first; the lines printed as they come."""
    with tempfile.TemporaryDirectory(prefix="livecheck-") as tmp:
        settings = _settings(Path(tmp))
        key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
        if settings.record_fixtures:
            # record mode makes real calls and writes what they answer into the recordings;
            # refused even beside OPL_FAKE_API, which would only hide it
            raise RefusedError("the live check does not record fixtures; unset OPL_RECORD_FIXTURES")
        live = settings.model_api_mode == "live"
        ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
        print(said("MODEL_API_KEY", key), file=out)
        print(
            f"mode: {settings.model_api_mode}; ledger: spent ${ledger.total_usd:.4f} of"
            f" ${ledger.cap_usd:.2f} (headroom ${ledger.remaining_usd:.4f}); this run at most"
            f" ${max_usd:.2f}",
            file=out,
        )
        if live and ledger.remaining_usd < max_usd:
            raise RefusedError(
                f"the spend cap leaves ${ledger.remaining_usd:.4f}, below --max-usd {max_usd:.2f};"
                " raise SPEND_CAP_USD or lower --max-usd"
            )
        client = ModelApiClient(settings, ledger)
        try:
            if live:
                probe = await client.check()
                if not probe.get("reachable"):
                    raise RefusedError(
                        f"the API did not answer GET /models: {probe.get('error', '')}"
                    )
                print(f"api: reachable, {len(probe.get('models', []))} models listed", file=out)
            else:
                print("fixture mode: recorded answers, nothing spent, the guard is off", file=out)
            s = _wire(settings, client, ledger, out)
            seconds = inputs.wav_seconds(s.audio)
            ceilings = {op: ceiling(op, settings, audio_seconds=seconds) for op in ops}
            beyond = [op for op in ops if ceilings[op].usd > max_usd]
            if live:
                print(plan(ops, ceilings, beyond, max_usd), file=out)
            run = Run()
            print(file=out)
            print(HEADER, file=out)
            stop = False
            for op in ops:
                most = ceilings[op]
                if live and op in beyond:
                    run.results.append(
                        Result(
                            op=op,
                            model=most.model,
                            note=(
                                f"ceiling ${most.usd:.4f} ({most.why}) is above --max-usd"
                                f" {max_usd:.2f} on its own"
                            ),
                            planned=True,
                        )
                    )
                    print(run.results[-1].line(), file=out)
                    continue
                if stop:
                    run.results.append(Result(op=op, note="not run"))
                    print(run.results[-1].line(), file=out)
                    continue
                if live and run.spent + most.usd > max_usd:
                    run.results.append(
                        Result(
                            op=op,
                            model=most.model,
                            status=SKIP,
                            note=(
                                f"ceiling ${most.usd:.4f} ({most.why}) would take the run past"
                                f" --max-usd {max_usd:.2f}"
                            ),
                        )
                    )
                    print(run.results[-1].line(), file=out)
                    stop = not keep_going
                    continue
                result = await _one(s, op, live)
                run.results.append(result)
                print(result.line(), file=out)
                if result.status == FAIL and not keep_going:
                    stop = True
            print(file=out)
            print(run.total(), file=out)
            return run
        finally:
            await client.aclose()
