import os
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# Default to fixture mode before the app modules load: importing app.main builds
# the app from the environment, which fails without a key in live mode.
os.environ.setdefault("OPL_FAKE_API", "1")

from app.config import Settings
from app.main import create_app

RECORDED_FIXTURES = Path(__file__).parent / "fixtures" / "api"
SAMPLE_VALUE = "sample-value-for-tests"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
    )


@pytest.fixture
def recorded_settings(tmp_path: Path) -> Settings:
    """Fixture mode against the fixtures committed with the repository."""
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        log_format="text",
    )


@pytest.fixture
def live_settings(tmp_path: Path) -> Settings:
    """Live mode with a placeholder key; pair it with a mock transport."""
    return Settings(
        OPL_FAKE_API=False,
        OPL_KEY_PROBE=False,
        model_api_key=SAMPLE_VALUE,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        _env_file=None,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def recorded_client(recorded_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(recorded_settings)) as c:
        yield c


def make_photo(width: int = 640, height: int = 480, fmt: str = "JPEG") -> bytes:
    """A plain test image; the fixtures answer regardless of its pixels."""
    img = Image.new("RGB", (width, height), (200, 200, 200))
    out = BytesIO()
    img.save(out, fmt)
    return out.getvalue()


@pytest.fixture
def photo() -> bytes:
    return make_photo()
