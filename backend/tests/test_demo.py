import json
import wave
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.config import Settings
from app.demo import DemoSet, load_set, reset, scrub
from app.demo.__main__ import build_loader, main
from app.extract.imaging import dimensions
from app.model_api import CostLedger, ModelApiClient
from tests.conftest import RECORDED_FIXTURES, make_photo

pytestmark = pytest.mark.anyio


def wav_bytes(seconds: float = 1.0, rate: int = 16_000) -> bytes:
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(b"\x80" * int(seconds * rate))
    return out.getvalue()


def photo_with_exif(width: int = 2400, height: int = 1800) -> bytes:
    img = Image.new("RGB", (width, height), (90, 120, 150))
    exif = Image.Exif()
    exif[0x0110] = "A phone"  # Model
    exif[0x9003] = "2026:10:29 10:00:00"  # DateTimeOriginal
    out = BytesIO()
    img.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


SET_TEXT = """
title: a small set
currency: USD
country: US
items:
  - key: adapter
    name: Laptop power adapter
    item_type: power adapter
    profile: power_adapter
    photos: [photos/psu.jpg]
    voice_note: notes/note.wav
    draft: sell
    asking_price: "15"
    price: true
    fields:
      output_current: "3.33"
  - key: vacuum
    name: Upright vacuum
    item_type: vacuum
    profile: vacuum_attachment
    intent: build
    photos: [photos/missing.jpg]
    condition: runs
  - key: monitor
    name: Spare monitor
    item_type: monitor
    intent: build
  - key: laptop
    name: Old laptop
    item_type: laptop
    intent: build
  - key: keyboard
    name: USB keyboard
    item_type: keyboard
    intent: give
    draft: give
searches:
  - key: adapter_spare
    need: adapter
    title: spare adapter
    max_price: 25
    listings:
      - text: "@listings/L1.txt"
        observed_on: "2026-10-27"
        asking_price: "15"
      - text: "Charger 19.5V 3.3A, centre positive, $12"
  - key: by_profile
    profile: power_adapter
    title: any adapter
    spec: {output_voltage: "19.5"}
propose:
  count: 3
  preferences:
    interests: a desk
    budget: 50
"""


def write_set(base: Path, text: str = SET_TEXT, *, with_files: bool = True) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "set.yaml").write_text(text)
    if with_files:
        (base / "photos").mkdir(exist_ok=True)
        (base / "photos" / "psu.jpg").write_bytes(make_photo())
        (base / "notes").mkdir(exist_ok=True)
        (base / "notes" / "note.wav").write_bytes(wav_bytes())
        (base / "listings").mkdir(exist_ok=True)
        (base / "listings" / "L1.txt").write_text(
            "Orbital 65W laptop charger, 19.5V 3.34A, centre positive, 4.5 x 3.0 mm plug. $15."
        )
    return base / "set.yaml"


def test_the_set_is_checked(tmp_path: Path) -> None:
    found = load_set(write_set(tmp_path / "ok"))
    assert found.title == "a small set" and len(found.items) == 5 and found.propose is not None
    with pytest.raises(ValueError, match="keys repeat"):
        DemoSet.model_validate(
            {"items": [{"key": "a", "name": "A"}, {"key": "a", "name": "Again"}]}
        )
    with pytest.raises(ValueError, match="is not an item"):
        load_set(
            write_set(
                tmp_path / "bad",
                "items: []\nsearches:\n  - {key: s, need: ghost, title: x}\n",
                with_files=False,
            )
        )
    with pytest.raises(ValueError, match="an item or a profile"):
        load_set(
            write_set(tmp_path / "bad2", "searches:\n  - {key: s, title: x}\n", with_files=False)
        )
    with pytest.raises(ValueError, match="four photos"):
        DemoSet.model_validate(
            {"items": [{"key": "a", "name": "A", "photos": ["1", "2", "3", "4", "5"]}]}
        )
    assert load_set(write_set(tmp_path / "empty", "", with_files=False)).items == []


def test_scrub_drops_metadata_shrinks_and_copies_notes(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    (raw / "vac_a.JPG").write_bytes(photo_with_exif())
    (raw / "cam.png").write_bytes(make_photo(300, 200, "PNG"))
    (raw / "note.wav").write_bytes(wav_bytes(0.5))
    (raw / "notes.txt").write_text("not media")
    (raw / "broken.jpg").write_bytes(b"not a photo")
    notes = scrub(raw, out)
    cleaned = (out / "vac_a.jpg").read_bytes()
    assert dimensions(cleaned) == (1600, 1200)
    assert "exif" not in Image.open(BytesIO(cleaned)).info
    assert b"A phone" not in cleaned and b"2026:10:29" not in cleaned
    assert dimensions((out / "cam.jpg").read_bytes()) == (300, 200)
    assert (out / "note.wav").read_bytes() == (raw / "note.wav").read_bytes()
    assert not (out / "notes.txt").exists() and not (out / "broken.jpg").exists()
    assert any("not a photo or a WAV note" in n for n in notes)
    assert any(n.startswith("broken.jpg:") for n in notes)
    assert any("no metadata" in n for n in notes)
    # the raw directory is read, never written
    assert sorted(p.name for p in raw.iterdir()) == [
        "broken.jpg",
        "cam.png",
        "note.wav",
        "notes.txt",
        "vac_a.JPG",
    ]


async def test_the_set_loads_in_fixture_mode_and_says_what_it_skipped(
    recorded_settings: Settings,
) -> None:
    path = write_set(recorded_settings.data_dir.parent / "demo")
    loader, client = build_loader(recorded_settings)
    try:
        outcome = await loader.run(load_set(path), path.parent)
    finally:
        await client.aclose()
    assert outcome.mode == "fixture" and outcome.cost_usd == 0.0
    assert (outcome.items, outcome.photos, outcome.voice_notes) == (5, 1, 1)
    assert (outcome.drafts, outcome.guidances) == (2, 1)
    assert (outcome.searches, outcome.candidates, outcome.projects) == (2, 2, 2)
    assert outcome.skipped == ["vacuum: photo photos/missing.jpg missing"]
    items = {i.name: i for i in loader.inventory.list_items()}
    adapter = loader.inventory.get(items["Laptop power adapter"].id)
    # the reading's values are accepted, the owner value sits beside them, the note is kept
    assert adapter.fields["output_voltage"].review == "accepted"
    assert adapter.fields["output_current"].provenance == "owner_reported"
    assert adapter.fields["condition_notes"].source == "voice_note"
    assert adapter.profile == "power_adapter"
    vacuum = loader.inventory.get(items["Upright vacuum"].id)
    assert vacuum.condition == "runs" and vacuum.fields == {}
    assert len(loader.lister.drafts(adapter.id)) == 1
    assert len(loader.valuer.guidances(adapter.id)) == 1
    searches = loader.finder.searches()
    assert {s.title for s in searches} == {"spare adapter", "any adapter"}
    spare = next(s for s in searches if s.title == "spare adapter")
    assert spare.need_item_id == adapter.id and spare.candidates == 2
    assert {p.template for p in loader.planner.projects().projects} == {
        "homework_workstation",
        "vacuum_restored",
    }
    lines = outcome.lines()
    assert lines[0].startswith("mode fixture: 5 item(s) from 1 photo(s)")
    assert lines[1] == "skipped: vacuum: photo photos/missing.jpg missing"


async def test_record_mode_writes_a_fixture_per_answer(live_settings: Settings) -> None:
    recording = live_settings.model_copy(update={"record_fixtures": True})
    assert recording.model_api_mode == "record"
    extract = json.loads((RECORDED_FIXTURES / "responses" / "extract.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=extract["response"])

    client = ModelApiClient(recording, CostLedger(25.0), transport=httpx.MockTransport(handler))
    loader, _ = build_loader(recording)
    loader.client = loader.extractor.client = client
    path = write_set(
        recording.data_dir.parent / "demo",
        "items:\n  - {key: a, name: Adapter, photos: [photos/psu.jpg]}\n",
    )
    outcome = await loader.run(load_set(path), path.parent)
    assert outcome.mode == "record" and outcome.items == 1 and outcome.cost_usd > 0
    written = list((recording.fixtures_dir / "responses").glob("*.json"))
    assert len(written) == 1 and written[0].stem != "extract"  # keyed by the request digest
    fixture = json.loads(written[0].read_text())
    assert fixture["op"] == "extract" and fixture["response"] == extract["response"]


def test_reset_removes_only_the_inventory_file(recorded_settings: Settings) -> None:
    recorded_settings.data_dir.mkdir(parents=True)
    db = recorded_settings.inventory_db_path
    db.write_bytes(b"")
    Path(f"{db}-wal").write_bytes(b"")
    ledger = recorded_settings.spend_ledger_path
    ledger.write_text("{}\n")
    assert sorted(reset(recorded_settings)) == [db.name, f"{db.name}-wal"]
    assert not db.exists() and ledger.exists()
    assert reset(recorded_settings) == []


def test_the_command_line(
    tmp_path: Path,
    recorded_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import app.demo.__main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: recorded_settings)
    assert main([]) == 2
    assert main(["fly"]) == 2
    assert main(["load", "--set", str(tmp_path / "nowhere.yaml")]) == 1
    assert main(["load", "--what"]) == 2
    assert main(["scrub"]) == 2
    assert main(["scrub", str(tmp_path / "no-dir")]) == 1
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.jpg").write_bytes(make_photo())
    assert main(["scrub", str(raw), "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "a.jpg").is_file()
    path = write_set(tmp_path / "demo")
    recorded_settings.data_dir.mkdir(parents=True, exist_ok=True)
    recorded_settings.inventory_db_path.write_bytes(b"")
    assert main(["load", "--set", str(path), "--reset"]) == 0
    out = capsys.readouterr().out
    assert "removed inventory.sqlite3" in out and "mode fixture: 5 item(s)" in out
    # a set that does not parse
    bad = write_set(tmp_path / "bad", "items:\n  - {key: a}\n", with_files=False)
    assert main(["load", "--set", str(bad)]) == 1
    # record needs a key: fixture mode refuses
    monkeypatch.setenv("OPL_FAKE_API", "1")
    assert main(["record", "--set", str(path)]) == 1


def test_the_committed_set_parses_and_names_only_files_under_demo() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "demo" / "set.yaml"
    found = load_set(path)
    assert len(found.items) >= 5 and found.propose is not None
    for item in found.items:
        for photo in item.photos:
            assert photo.startswith("photos/") and not photo.startswith("/")
        if item.voice_note:
            assert item.voice_note.startswith("notes/")
    for search in found.searches:
        for listing in search.listings:
            if listing.text.startswith("@"):
                assert (path.parent / listing.text[1:]).is_file(), listing.text
                text = (path.parent / listing.text[1:]).read_text()
                assert text.startswith("DEMO DATA")
