import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.segment.__main__ import main
from tests.conftest import RECORDED_FIXTURES, make_photo


@pytest.fixture
def fixture_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("OPL_FAKE_API", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIXTURES_DIR", str(RECORDED_FIXTURES))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_prints_regions_and_writes_the_overlay_and_crops(
    fixture_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    photo = tmp_path / "item.jpg"
    photo.write_bytes(make_photo())
    out = tmp_path / "out"

    assert main([str(photo), "--concepts", "item,label", "--out", str(out)]) == 0

    summary = json.loads(capsys.readouterr().out)
    assert [r["concept"] for r in summary["regions"]] == ["item", "label", "label"]
    assert "crop" not in summary["regions"][0]
    assert "overlay" not in summary
    assert sorted(p.name for p in out.iterdir()) == [
        "item-1.jpg",
        "label-1.jpg",
        "label-2.jpg",
        "overlay.jpg",
    ]


def test_cli_keeps_crop_filenames_inside_the_out_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = tmp_path / "fixtures" / "responses"
    fixtures.mkdir(parents=True)
    recorded = json.loads((RECORDED_FIXTURES / "responses" / "segment-label.json").read_text())
    recorded["op"] = "segment-evil"
    (fixtures / "segment-evil.json").write_text(json.dumps(recorded))
    monkeypatch.setenv("OPL_FAKE_API", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIXTURES_DIR", str(tmp_path / "fixtures"))
    get_settings.cache_clear()
    try:
        photo = tmp_path / "item.jpg"
        photo.write_bytes(make_photo())
        out = tmp_path / "out"
        assert main([str(photo), "--concepts", "../evil", "--out", str(out)]) == 0
    finally:
        get_settings.cache_clear()
    capsys.readouterr()
    assert sorted(p.name for p in out.iterdir()) == ["evil-1.jpg", "evil-2.jpg", "overlay.jpg"]
    assert list(tmp_path.glob("evil-*.jpg")) == []


def test_cli_reports_a_bad_photo(
    fixture_env: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not a photo")
    assert main([str(bad)]) == 1
    assert "not an image" in capsys.readouterr().err


def test_cli_usage_error_for_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["/no/such/file.jpg"]) == 2
    assert "not a file" in capsys.readouterr().err
