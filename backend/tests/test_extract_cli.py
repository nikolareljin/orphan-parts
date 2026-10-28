import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.extract.__main__ import main
from tests.conftest import RECORDED_FIXTURES, make_photo


@pytest.fixture
def fixture_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("OPL_FAKE_API", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIXTURES_DIR", str(RECORDED_FIXTURES))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_prints_the_extraction_as_json(
    fixture_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    photo = tmp_path / "label.jpg"
    photo.write_bytes(make_photo())

    assert main([str(photo)]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["fields"]["output_power"]["value"] == "65"
    assert out["from_fixture"] is True


def test_cli_reports_a_bad_photo(
    fixture_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not a photo")

    assert main([str(bad)]) == 1
    assert "not an image" in capsys.readouterr().err


def test_cli_usage_error_without_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert main(["/no/such/file.jpg"]) == 2
    assert "usage:" in capsys.readouterr().err
