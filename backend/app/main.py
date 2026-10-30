import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.access import router as access_router
from app.api.assess import router as assess_router
from app.api.captures import router as captures_router
from app.api.drafts import router as drafts_router
from app.api.extract import router as extract_router
from app.api.find import router as find_router
from app.api.items import error_handlers as inventory_handlers
from app.api.items import router as items_router
from app.api.measure import router as measure_router
from app.api.pair import router as pair_router
from app.api.photos import router as photos_router
from app.api.profiles import router as profiles_router
from app.api.projects import router as projects_router
from app.api.routes import router
from app.api.segment import router as segment_router
from app.api.value import router as value_router
from app.api.voice import router as voice_router
from app.captures import Captures
from app.config import Settings, get_settings
from app.extract import Extractor
from app.find import Finder
from app.inventory import Inventory
from app.listing import Lister, VoiceNotes
from app.match import Assessor
from app.measure import Measurer
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import Gate, GateMiddleware
from app.ops.logging import configure_logging
from app.ops.middleware import RequestContextMiddleware
from app.photos import ItemPhotos
from app.profiles import Profiles
from app.projects import Planner, Templates
from app.segment import Segmenter
from app.value import Valuer

log = logging.getLogger("app")

# a probe answered with one of these says the key or the URL cannot work: refused, unpaid,
# forbidden, not there. A busy or failing API (429, 5xx, a timeout) is left alone: every
# request retries on its own and the key may answer the next one.
KEY_FAILURES = frozenset({401, 402, 403, 404})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    app.state.model_api_label = settings.model_api_mode
    if settings.model_api_mode == "live" and settings.key_probe:
        # a key that does not answer must not turn every call into an error: the service
        # runs on recorded answers and says so, until a restart with a working key. One
        # short try: a slow API must not hold the start, a busy one is left alone anyway
        quick = settings.model_copy(
            update={
                "model_api_max_attempts": 1,
                "model_api_timeout_s": min(settings.model_api_timeout_s, 15.0),
            }
        )
        prober = ModelApiClient(quick, ledger)
        probe = await prober.check()
        await prober.aclose()
        if not probe.get("reachable") and probe.get("status") not in KEY_FAILURES:
            log.warning(
                "the API did not answer the probe; staying live",
                extra={"error": probe.get("error", "")},
            )
        elif not probe.get("reachable"):
            log.warning(
                "the key did not answer; running in fixture mode",
                extra={"error": probe.get("error", "")},
            )
            await client.aclose()
            settings = settings.model_copy(update={"fake_api": True})
            app.state.settings = settings
            client = ModelApiClient(settings, ledger)
            app.state.model_api_label = "fixture (key failed)"
    app.state.ledger = ledger
    app.state.model_api = client
    app.state.extractor = Extractor(settings, client)
    app.state.segmenter = Segmenter(settings, client)
    app.state.inventory = Inventory(settings)
    app.state.photos = ItemPhotos(settings, app.state.inventory)
    app.state.profiles = Profiles()
    app.state.measurer = Measurer(settings, app.state.profiles)
    app.state.assessor = Assessor(app.state.profiles, app.state.inventory)
    app.state.lister = Lister(settings, client, app.state.inventory)
    app.state.voice = VoiceNotes(settings, client, app.state.inventory)
    app.state.valuer = Valuer(settings, client, app.state.inventory)
    app.state.finder = Finder(
        settings,
        client,
        app.state.inventory,
        app.state.profiles,
        app.state.extractor,
        app.state.assessor,
    )
    app.state.captures = Captures(
        settings,
        app.state.inventory,
        app.state.extractor,
        app.state.segmenter,
        app.state.voice,
        app.state.photos,
    )
    app.state.templates = Templates()
    app.state.planner = Planner(
        settings, client, app.state.inventory, app.state.templates, app.state.finder
    )
    log.info(
        "starting",
        extra={
            "version": __version__,
            "model_api": settings.model_api_mode,
            "spent_usd": ledger.total_usd,
            "cap_usd": ledger.cap_usd,
        },
    )
    try:
        yield
    finally:
        await client.aclose()
        log.info("stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_format, settings.log_level)

    app = FastAPI(
        title="Orphan Parts Lens",
        version=__version__,
        description="Show it, ask it, sell it, or find the one that fits.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.gate = Gate(settings)
    # Last added runs first: the gate runs inside the request context, so a refusal carries
    # the request id and the security headers like any other answer.
    app.add_middleware(GateMiddleware, gate=app.state.gate)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    app.include_router(access_router)
    app.include_router(pair_router)
    app.include_router(extract_router)
    app.include_router(segment_router)
    app.include_router(items_router)
    app.include_router(photos_router)
    app.include_router(profiles_router)
    app.include_router(measure_router)
    app.include_router(assess_router)
    app.include_router(drafts_router)
    app.include_router(voice_router)
    app.include_router(value_router)
    app.include_router(find_router)
    app.include_router(projects_router)
    app.include_router(captures_router)
    for exc_type, handler in inventory_handlers.items():
        app.add_exception_handler(exc_type, handler)
    return app


app = create_app()
