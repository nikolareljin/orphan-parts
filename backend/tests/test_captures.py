import json
import wave
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.captures import CaptureError, Captures, looks_like_video
from app.config import Settings
from app.extract import Extractor
from app.inventory import Inventory
from app.listing import VoiceNotes
from app.model_api import CostLedger, FixtureMissingError, ModelApiClient
from app.segment import Segmenter
from tests.conftest import RECORDED_FIXTURES, make_photo

pytestmark = pytest.mark.anyio


def wav_bytes(seconds: float = 1.0) -> bytes:
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * int(seconds * 16_000))
    return out.getvalue()


def mp4_bytes(size: int = 2048) -> bytes:
    """The start of an MP4 file: a size, the ftyp box, a brand, then padding."""
    head = (24).to_bytes(4, "big") + b"ftyp" + b"isom" + (512).to_bytes(4, "big") + b"isomiso2"
    return head + b"\0" * (size - len(head))


def service(settings: Settings) -> Captures:
    client = ModelApiClient(settings, CostLedger(25.0))
    inventory = Inventory(settings)
    return Captures(
        settings,
        inventory,
        Extractor(settings, client),
        Segmenter(settings, client),
        VoiceNotes(settings, client, inventory),
    )


def test_a_video_is_known_by_its_box() -> None:
    assert looks_like_video(mp4_bytes())
    assert not looks_like_video(make_photo())
    assert not looks_like_video(b"short")


async def test_a_capture_is_kept_as_sent_and_processed_into_an_item(
    recorded_settings: Settings,
) -> None:
    captures = service(recorded_settings)
    from app.captures import CaptureCreate

    kept = captures.create(
        CaptureCreate(note="the old adapter from the drawer", find_label=True),
        [make_photo(2000, 1500), make_photo()],
        mp4_bytes(),
        wav_bytes(2.0),
    )
    assert kept.status == "received" and kept.photos == 2 and kept.clip and kept.audio
    assert kept.audio_seconds == 2.0 and kept.clip_bytes == 2048 and kept.item_id is None
    folder = recorded_settings.data_dir / "captures" / str(kept.id)
    assert sorted(p.name for p in folder.iterdir()) == [
        "clip.mp4",
        "note.wav",
        "photo-1.jpg",
        "photo-2.jpg",
    ]
    # photos are re-encoded on arrival: the first one was shrunk to the service's size
    from app.extract.imaging import dimensions

    assert dimensions(captures.photo(kept.id, 1))[0] <= recorded_settings.image_max_px
    assert captures.media(kept.id, "clip.mp4") == mp4_bytes()
    with pytest.raises(LookupError):
        captures.photo(kept.id, 3)

    done = await captures.process(kept.id)
    assert done.status == "processed" and done.item_id is not None and done.processed_at
    assert done.model and done.cost_usd == 0.0
    item = captures.inventory.get(done.item_id)
    assert item.item_type and item.fields["output_voltage"].source in ("label_crop", "photo")
    assert item.fields["condition_notes"].source == "voice_note"
    assert "the old adapter from the drawer" in item.notes and "a clip of 2 KB" in item.notes
    with pytest.raises(CaptureError, match="already processed"):
        await captures.process(kept.id)
    assert [c.id for c in captures.captures()] == [kept.id]

    captures.delete(kept.id)
    assert not folder.exists()
    with pytest.raises(LookupError):
        captures.capture(kept.id)
    assert captures.inventory.get(done.item_id).id == done.item_id  # the item stays


async def test_a_capture_without_photos_still_becomes_an_item(recorded_settings: Settings) -> None:
    from app.captures import CaptureCreate

    captures = service(recorded_settings)
    kept = captures.create(CaptureCreate(note="just a note", name="Mystery box"), [], None, None)
    done = await captures.process(kept.id)
    item = captures.inventory.get(done.item_id or 0)
    assert item.name == "Mystery box" and item.item_type == "item" and item.notes == "just a note"
    spoken = captures.create(CaptureCreate(), [], None, wav_bytes(1.0))
    done2 = await captures.process(spoken.id)
    item2 = captures.inventory.get(done2.item_id or 0)
    assert item2.name == "Capture" and item2.fields["condition_notes"].source == "voice_note"


def test_bundles_are_checked_before_anything_is_kept(recorded_settings: Settings) -> None:
    from app.captures import CaptureCreate

    captures = service(recorded_settings)
    with pytest.raises(CaptureError, match="empty capture"):
        captures.create(CaptureCreate(note="   "), [], None, None)
    with pytest.raises(CaptureError, match="at most 4 photos"):
        captures.create(CaptureCreate(), [make_photo()] * 5, None, None)
    with pytest.raises(CaptureError, match="photo 2:"):
        captures.create(CaptureCreate(), [make_photo(), b"not a photo"], None, None)
    with pytest.raises(CaptureError, match="not an MP4"):
        captures.create(CaptureCreate(), [], b"x" * 100, None)
    with pytest.raises(CaptureError, match="the note:"):
        captures.create(CaptureCreate(), [], None, b"not a wav")
    small = recorded_settings.model_copy(update={"max_clip_mb": 0})
    with pytest.raises(CaptureError, match="larger than 0 MB"):
        service(small).create(CaptureCreate(), [], mp4_bytes(), None)
    assert not (recorded_settings.data_dir / "captures").exists()


async def test_a_failed_processing_is_recorded_and_the_media_stays(settings: Settings) -> None:
    from app.captures import CaptureCreate

    captures = service(settings)  # fixture mode with an empty fixture directory: no answers
    kept = captures.create(CaptureCreate(find_label=False), [make_photo()], None, None)
    with pytest.raises(FixtureMissingError):
        await captures.process(kept.id)
    failed = captures.capture(kept.id)
    assert failed.status == "failed" and "fixture" in failed.error.lower()
    assert (settings.data_dir / "captures" / str(kept.id) / "photo-1.jpg").is_file()


async def test_the_label_is_found_first_when_asked(live_settings: Settings) -> None:
    from app.captures import CaptureCreate

    calls: list[str] = []
    segment = json.loads((RECORDED_FIXTURES / "responses" / "segment-label.json").read_text())
    extract = json.loads((RECORDED_FIXTURES / "responses" / "extract.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        model = body.get("model", "")
        calls.append(model)
        return httpx.Response(
            200, json=segment["response"] if "sam" in model else extract["response"]
        )

    client = ModelApiClient(live_settings, CostLedger(25.0), transport=httpx.MockTransport(handler))
    inventory = Inventory(live_settings)
    captures = Captures(
        live_settings,
        inventory,
        Extractor(live_settings, client),
        Segmenter(live_settings, client),
        VoiceNotes(live_settings, client, inventory),
    )
    kept = captures.create(CaptureCreate(find_label=True), [make_photo()], None, None)
    done = await captures.process(kept.id)
    assert [m for m in calls if "sam" in m] and [m for m in calls if "spark" in m]
    assert done.cost_usd > 0
    item = inventory.get(done.item_id or 0)
    assert any(a.source == "label_crop" for a in item.assertions)


def test_capture_routes(recorded_client: TestClient) -> None:
    files = [
        ("photos", ("a.jpg", make_photo(), "image/jpeg")),
        ("photos", ("b.jpg", make_photo(), "image/jpeg")),
        ("clip", ("clip.mp4", mp4_bytes(), "video/mp4")),
        ("audio", ("note.wav", wav_bytes(), "audio/wav")),
    ]
    created = recorded_client.post(
        "/api/captures", files=files, data={"request": '{"note": "from the phone"}'}
    )
    assert created.status_code == 201, created.text
    capture = created.json()
    assert capture["photos"] == 2 and capture["clip"] and capture["audio"]
    cid = capture["id"]
    assert recorded_client.get("/api/captures").json()["captures"][0]["id"] == cid
    assert (
        recorded_client.get(f"/api/captures/{cid}/photos/1").headers["content-type"] == "image/jpeg"
    )
    assert recorded_client.get(f"/api/captures/{cid}/clip").headers["content-type"] == "video/mp4"
    assert recorded_client.get(f"/api/captures/{cid}/note").headers["content-type"] == "audio/wav"
    assert recorded_client.get(f"/api/captures/{cid}/photos/9").status_code == 404
    done = recorded_client.post(f"/api/captures/{cid}/process")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "processed" and done.json()["item_id"]
    assert recorded_client.post(f"/api/captures/{cid}/process").status_code == 422
    assert recorded_client.get(f"/api/items/{done.json()['item_id']}").status_code == 200
    assert recorded_client.delete(f"/api/captures/{cid}").status_code == 204
    assert recorded_client.get(f"/api/captures/{cid}").status_code == 404
    # refusals
    assert recorded_client.post("/api/captures", data={"request": "{}"}).status_code == 422
    assert recorded_client.post("/api/captures", data={"request": "not json"}).status_code == 422
    bad_clip = [("clip", ("c.mp4", b"nope", "video/mp4"))]
    assert recorded_client.post("/api/captures", files=bad_clip).status_code == 422
    only_note = recorded_client.post("/api/captures", data={"request": '{"note": "a line"}'})
    assert only_note.status_code == 201 and only_note.json()["photos"] == 0


def test_capture_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/captures",
        "/api/captures/{capture_id}/process",
        "/api/captures/{capture_id}/clip",
    ):
        assert path in paths


def test_captures_folder_is_under_the_data_dir(settings: Settings) -> None:
    captures = service(settings)
    assert captures.folder(7) == settings.data_dir / "captures" / "7"
    assert isinstance(captures.folder(7), Path)
