import tempfile

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import GateDep, LedgerDep, SettingsDep
from app.config import Settings
from app.model_api import LedgerSummary

router = APIRouter()


class Health(BaseModel):
    status: str


class Demo(BaseModel):
    """The gate as it stands: whether a code is needed, what is left today, what is paused."""

    gated: bool
    live_models: bool = Field(
        default=False, description="whether the code's door reaches the live models at all"
    )
    paused: bool = Field(description="the operator's switch; the spend cap is reported apart")
    daily_used: int
    daily_cap: int
    visitor_cap_per_hour: int


class Readiness(BaseModel):
    status: str
    model_api: str
    data_dir_writable: bool
    spend_usd: float
    spend_cap_usd: float
    paused: bool
    demo: Demo


class Limits(BaseModel):
    """Upload limits the web form follows, so they are set in one place."""

    max_photos: int
    max_upload_mb: int
    max_clip_mb: int


class Version(BaseModel):
    name: str
    version: str
    models: dict[str, str]
    limits: Limits


@router.get("/healthz", response_model=Health, tags=["ops"])
def healthz() -> Health:
    return Health(status="ok")


def _model_api_label(request: Request, settings: SettingsDep, gate: GateDep) -> str:
    """What answers: the mode, and behind a gate with a key, which door gets the key."""
    label = str(getattr(request.app.state, "model_api_label", settings.model_api_mode))
    if gate.enabled and gate.live_models:
        return f"{label} for the code, recorded otherwise"
    return label


@router.get("/readyz", response_model=Readiness, tags=["ops"])
def readyz(request: Request, settings: SettingsDep, ledger: LedgerDep, gate: GateDep) -> Readiness:
    writable = _writable(settings)
    return Readiness(
        status="ok" if writable else "degraded",
        model_api=_model_api_label(request, settings, gate),
        data_dir_writable=writable,
        spend_usd=ledger.total_usd,
        spend_cap_usd=ledger.cap_usd,
        paused=ledger.paused,
        demo=Demo(
            gated=gate.enabled,
            live_models=gate.live_models,
            paused=gate.paused,
            daily_used=gate.daily.used,
            daily_cap=gate.daily.limit,
            visitor_cap_per_hour=gate.visitor.limit,
        ),
    )


@router.get("/api/version", response_model=Version, tags=["ops"])
def version(settings: SettingsDep) -> Version:
    return Version(
        name="orphan-parts",
        version=__version__,
        models={
            "spark": settings.model_spark,
            "wonder": settings.model_wonder,
            "image": settings.model_image,
            "voice": settings.model_voice,
            "sam": settings.model_sam,
        },
        limits=Limits(
            max_photos=settings.max_photos,
            max_upload_mb=settings.max_upload_mb,
            max_clip_mb=settings.max_clip_mb,
        ),
    )


@router.get("/api/spend", response_model=LedgerSummary, tags=["ops"])
def spend(ledger: LedgerDep) -> LedgerSummary:
    return ledger.summary()


def _writable(settings: Settings) -> bool:
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        # A unique probe per call: concurrent checks must not unlink each other's file.
        with tempfile.NamedTemporaryFile(dir=settings.data_dir, prefix=".write-probe-") as probe:
            probe.write(b"ok")
            probe.flush()
        return True
    except OSError:
        return False
