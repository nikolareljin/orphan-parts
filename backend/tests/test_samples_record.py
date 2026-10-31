"""Recording the samples: every reading a click can ask for is run once through the same code
the route runs, so a record run keeps what the gallery will ask for and fixture mode can say
which reading has none. And a demo item's picture: drawn in record mode, replayed after it,
left out (never the stub image) before."""

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.demo import load_set
from app.demo.__main__ import build_loader, build_sample_reader, main
from app.model_api import CostLedger, ModelApiClient
from app.samples import record_samples, selections
from tests.conftest import RECORDED_FIXTURES

pytestmark = pytest.mark.anyio

DEMO = Path(__file__).resolve().parents[2] / "demo"


def stub(endpoint: str, op: str) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((RECORDED_FIXTURES / endpoint / f"{op}.json").read_text())[
        "response"
    ]
    return found


def small_set(root: Path, extra: str = "") -> Path:
    """Two items of the demo set, its own photos: one photo, and two."""
    (root / "photos").mkdir(parents=True)
    for name in ("dell-u2419h-label.jpg", "evga-9800gt-front.jpg", "evga-9800gt-back.jpg"):
        shutil.copy(DEMO / "photos" / name, root / "photos" / name)
    path = root / "set.yaml"
    path.write_text(
        "items:\n"
        "  - key: monitor_u2419h\n"
        "    name: Dell U2419H monitor, 24 inch\n"
        "    item_type: monitor\n"
        "    photos: [photos/dell-u2419h-label.jpg]\n"
        f"{extra}"
        "  - key: gpu_9800gt\n"
        "    name: EVGA GeForce 9800 GT graphics card\n"
        "    item_type: graphics card\n"
        "    photos: [photos/evga-9800gt-front.jpg, photos/evga-9800gt-back.jpg]\n",
        encoding="utf-8",
    )
    return path


def fake_api(settings: Settings, calls: list[str]) -> httpx.MockTransport:
    """The Model API as the recordings answer it: SAM's stub for a segment, the extract stub
    for a reading, the picture stub for a drawing."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/images/generations"):
            return httpx.Response(200, json=stub("images-generations", "picture"))
        body = json.loads(request.content)
        if body.get("model") == settings.model_sam:
            return httpx.Response(200, json=stub("responses", "segment-label"))
        return httpx.Response(200, json=stub("responses", "extract"))

    return httpx.MockTransport(handler)


def test_the_selections_are_each_photo_then_each_group(recorded_settings: Settings) -> None:
    path = small_set(recorded_settings.data_dir.parent / "demo")
    client = ModelApiClient(recorded_settings, CostLedger(1.0))
    reader = build_sample_reader(recorded_settings, client, path)
    assert selections(reader) == [
        ["dell-u2419h-label"],
        ["evga-9800gt-front"],
        ["evga-9800gt-back"],
        ["evga-9800gt-front", "evga-9800gt-back"],
    ]


async def test_fixture_mode_finds_every_sample_recorded(recorded_settings: Settings) -> None:
    path = small_set(recorded_settings.data_dir.parent / "demo")
    client = ModelApiClient(recorded_settings, CostLedger(1.0))
    try:
        found = await record_samples(build_sample_reader(recorded_settings, client, path))
    finally:
        await client.aclose()
    # four selections, each with the label found first and without
    assert found.readings == 8 and found.missing == [] and found.failed == []
    assert found.cost_usd == 0.0 and client.fixture_fallbacks == 0


async def test_record_mode_keeps_what_a_click_asks_for(live_settings: Settings) -> None:
    recording = live_settings.model_copy(update={"record_fixtures": True})
    path = small_set(recording.data_dir.parent / "demo")
    calls: list[str] = []
    client = ModelApiClient(recording, CostLedger(25.0), transport=fake_api(recording, calls))
    try:
        found = await record_samples(build_sample_reader(recording, client, path))
    finally:
        await client.aclose()
    assert found.readings == 8 and found.missing == [] and found.cost_usd > 0
    bought = len(calls)
    assert bought > 0

    # replayed in fixture mode from what was written: every reading by its own recording
    replay = recording.model_copy(update={"record_fixtures": False, "fake_api": True})
    client = ModelApiClient(replay, CostLedger(1.0))
    try:
        again = await record_samples(build_sample_reader(replay, client, path))
    finally:
        await client.aclose()
    assert again.readings == 8 and again.missing == [] and client.fixture_fallbacks == 0

    # a second record run buys nothing: what is kept is replayed
    client = ModelApiClient(recording, CostLedger(25.0), transport=fake_api(recording, calls))
    try:
        third = await record_samples(build_sample_reader(recording, client, path))
    finally:
        await client.aclose()
    assert third.readings == 8 and len(calls) == bought and third.cost_usd == 0.0


async def test_a_sample_without_a_recording_is_named(settings: Settings) -> None:
    # only the operations' stubs: every reading would get one, none is taken as recorded
    for endpoint, op in (
        ("responses", "extract"),
        ("responses", "segment-item"),
        ("responses", "segment-label"),
        ("responses", "segment-connector"),
    ):
        target = settings.fixtures_dir / endpoint / f"{op}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(RECORDED_FIXTURES / endpoint / f"{op}.json", target)
    path = small_set(settings.data_dir.parent / "demo")
    client = ModelApiClient(settings, CostLedger(1.0))
    try:
        found = await record_samples(build_sample_reader(settings, client, path))
    finally:
        await client.aclose()
    assert found.readings == 0 and len(found.missing) == 8
    assert "dell-u2419h-label (label found first)" in found.missing
    assert any("no recording for" in line for line in found.lines())


def test_the_samples_command(
    recorded_settings: Settings, settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import app.demo.__main__ as cli

    path = small_set(recorded_settings.data_dir.parent / "demo")
    monkeypatch.setattr(cli, "get_settings", lambda: recorded_settings)
    assert main(["samples", "--set", str(path)]) == 0
    assert "samples: 8 reading(s) answered" in capsys.readouterr().out
    # with nothing recorded, the check fails and names what is missing
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert main(["samples", "--set", str(path)]) == 1
    assert "samples: no recording for" in capsys.readouterr().out


# --- a demo item's picture -------------------------------------------------------------


async def test_a_picture_named_in_the_set_waits_for_its_recording(
    recorded_settings: Settings,
) -> None:
    path = small_set(recorded_settings.data_dir.parent / "demo", "    picture: smart_mirror\n")
    loader, client = build_loader(recorded_settings)
    try:
        outcome = await loader.run(load_set(path), path.parent)
    finally:
        await client.aclose()
    # the stub image is never drawn onto the item: it is said to be not recorded yet
    assert outcome.pictures == 0 and outcome.skipped == []
    assert outcome.unrecorded == [
        "monitor_u2419h: picture (one ./dev record-fixtures run draws it)"
    ]
    assert "not recorded yet: monitor_u2419h" in "\n".join(outcome.lines())
    monitor = loader.ids["monitor_u2419h"]
    assert loader.pictures is not None
    assert loader.pictures.list(monitor).pictures == []


async def test_record_mode_draws_the_picture_and_fixture_mode_replays_it(
    live_settings: Settings,
) -> None:
    recording = live_settings.model_copy(update={"record_fixtures": True, "picture_enabled": True})
    path = small_set(recording.data_dir.parent / "demo", "    picture: smart_mirror\n")
    calls: list[str] = []
    loader, client = build_loader(recording)
    await client.aclose()
    faked = ModelApiClient(recording, CostLedger(25.0), transport=fake_api(recording, calls))
    loader.client = loader.extractor.client = faked
    assert loader.pictures is not None
    loader.pictures.client = faked
    try:
        outcome = await loader.run(load_set(path), path.parent)
    finally:
        await faked.aclose()
    assert outcome.pictures == 1 and outcome.unrecorded == []
    assert any(c.endswith("/images/generations") for c in calls)
    drawn = loader.pictures.list(loader.ids["monitor_u2419h"]).pictures
    assert len(drawn) == 1 and drawn[0].from_fixture is False

    replay = recording.model_copy(
        update={"record_fixtures": False, "fake_api": True, "data_dir": recording.data_dir / "r"}
    )
    loader, client = build_loader(replay)
    try:
        again = await loader.run(load_set(path), path.parent)
    finally:
        await client.aclose()
    assert again.pictures == 1 and again.unrecorded == []
    assert loader.pictures is not None
    kept = loader.pictures.list(loader.ids["monitor_u2419h"]).pictures
    assert len(kept) == 1 and kept[0].from_fixture is True


async def test_a_live_run_draws_no_picture_unless_pictures_are_on(live_settings: Settings) -> None:
    # load_demo on a host with a key: PICTURE_ENABLED off means no paid drawing
    path = small_set(live_settings.data_dir.parent / "demo", "    picture: smart_mirror\n")
    calls: list[str] = []
    loader, client = build_loader(live_settings)
    await client.aclose()
    faked = ModelApiClient(
        live_settings, CostLedger(25.0), transport=fake_api(live_settings, calls)
    )
    loader.client = loader.extractor.client = faked
    assert loader.pictures is not None
    loader.pictures.client = faked
    try:
        outcome = await loader.run(load_set(path), path.parent)
    finally:
        await faked.aclose()
    assert outcome.pictures == 0 and outcome.skipped == []
    assert outcome.unrecorded == ["monitor_u2419h: picture (left out: PICTURE_ENABLED is off)"]
    assert not any(c.endswith("/images/generations") for c in calls)
