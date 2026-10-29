import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.extract import router as extract_router
from app.api.items import error_handlers as inventory_handlers
from app.api.items import router as items_router
from app.api.measure import router as measure_router
from app.api.profiles import router as profiles_router
from app.api.routes import router
from app.api.segment import router as segment_router
from app.config import Settings, get_settings
from app.extract import Extractor
from app.inventory import Inventory
from app.measure import Measurer
from app.model_api import CostLedger, ModelApiClient
from app.ops.logging import configure_logging
from app.ops.middleware import RequestContextMiddleware
from app.profiles import Profiles
from app.segment import Segmenter

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    app.state.ledger = ledger
    app.state.model_api = client
    app.state.extractor = Extractor(settings, client)
    app.state.segmenter = Segmenter(settings, client)
    app.state.inventory = Inventory(settings)
    app.state.profiles = Profiles()
    app.state.measurer = Measurer(settings, app.state.profiles)
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
    # Last added runs first: every response, including CORS preflights, gets an id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    app.include_router(extract_router)
    app.include_router(segment_router)
    app.include_router(items_router)
    app.include_router(profiles_router)
    app.include_router(measure_router)
    for exc_type, handler in inventory_handlers.items():
        app.add_exception_handler(exc_type, handler)
    return app


app = create_app()
