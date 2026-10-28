import tempfile

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.api.deps import SettingsDep
from app.config import Settings

router = APIRouter()


class Health(BaseModel):
    status: str


class Readiness(BaseModel):
    status: str
    model_api: str
    data_dir_writable: bool


class Version(BaseModel):
    name: str
    version: str
    models: dict[str, str]


@router.get("/healthz", response_model=Health, tags=["ops"])
def healthz() -> Health:
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness, tags=["ops"])
def readyz(settings: SettingsDep) -> Readiness:
    writable = _writable(settings)
    return Readiness(
        status="ok" if writable else "degraded",
        model_api=settings.model_api_mode,
        data_dir_writable=writable,
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
    )


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
