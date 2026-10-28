import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import Settings, get_settings
from app.model_api import CostLedger, ModelApiClient
from app.ops.logging import configure_logging
from app.ops.middleware import RequestContextMiddleware

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    app.state.ledger = ledger
    app.state.model_api = client
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
        description="Identify, evaluate, list and reuse spare parts and used devices.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Last added runs first: every response, including CORS preflights, gets an id.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    return app


app = create_app()
