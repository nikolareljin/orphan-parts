import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

os.environ.setdefault("OPL_FAKE_API", "1")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(OPL_FAKE_API=True, data_dir=tmp_path / "data", log_format="text")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
