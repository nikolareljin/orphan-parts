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
# the tests read requests nobody recorded on the operations' stand-ins; the refusal a person
# gets instead is tested with FIXTURE_STUBS off
os.environ["FIXTURE_STUBS"] = "1"
# A code left in the shell (or passed through by Compose) would gate every test's app: the
# tests that want the gate set their own.
os.environ.pop("DEMO_ACCESS_CODE", None)

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


# The drawing parameters as version 1 had them: the prompt builder as it was before the
# parameters were tuned, which the tests of its mechanics were written against.
V1_TAIL = "on a plain background, no text, no logos, no people"
V1_PROJECT_TAIL = "finished and in use in a home, no text, no logos, no people"


def params_v1_text() -> str:
    from app.picture.params import ClosingRules, DrawingParams, dump

    rules = ClosingRules(item=V1_TAIL, use=V1_TAIL, card=V1_TAIL, project=V1_PROJECT_TAIL)
    return dump(DrawingParams(version=1, rules=rules))


@pytest.fixture
def v1_params(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "params-v1.yaml"
    path.write_text(params_v1_text(), encoding="utf-8")
    monkeypatch.setattr("app.picture.params.PARAMS_FILE", path)
    return path
