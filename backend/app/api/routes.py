import tempfile

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.api.deps import LedgerDep, SettingsDep
from app.config import Settings
from app.model_api import LedgerSummary

router = APIRouter()


class Health(BaseModel):
    status: str


class Readiness(BaseModel):
    status: str
    model_api: str
    data_dir_writable: bool
    spend_usd: float
    spend_cap_usd: float
    paused: bool


class Limits(BaseModel):
    """Upload limits the web form follows, so they are set in one place."""

    max_photos: int
    max_upload_mb: int


class Version(BaseModel):
    name: str
    version: str
    models: dict[str, str]
    limits: Limits


@router.get("/healthz", response_model=Health, tags=["ops"])
def healthz() -> Health:
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness, tags=["ops"])
def readyz(settings: SettingsDep, ledger: LedgerDep) -> Readiness:
    writable = _writable(settings)
    return Readiness(
        status="ok" if writable else "degraded",
        model_api=settings.model_api_mode,
        data_dir_writable=writable,
        spend_usd=ledger.total_usd,
        spend_cap_usd=ledger.cap_usd,
        paused=ledger.paused,
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
        limits=Limits(max_photos=settings.max_photos, max_upload_mb=settings.max_upload_mb),
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
