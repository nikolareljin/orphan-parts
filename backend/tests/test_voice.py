import json
import wave
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import ItemCreate
from app.listing import BadAudioError, VoiceNotes, wav_seconds
from app.model_api import CostLedger, FixtureStore, ModelApiClient
from app.model_api.pricing import VOICE_USD_PER_HOUR

pytestmark = pytest.mark.anyio


def silence(seconds: float = 1.5, rate: int = 8000) -> bytes:
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(b"\x80" * int(seconds * rate))
    return out.getvalue()


def test_wav_seconds_reads_the_header_and_refuses_other_files() -> None:
    assert wav_seconds(silence(1.5)) == pytest.approx(1.5)
    with pytest.raises(BadAudioError, match="not a WAV"):
        wav_seconds(b"ID3 not a wav")
    with pytest.raises(BadAudioError):
        wav_seconds(silence(0))


async def test_a_note_is_transcribed_from_the_fixture_and_kept_as_the_owners_words(
    recorded_settings: Settings,
) -> None:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    item = inventory.create(ItemCreate(item_type="laptop power adapter"))
    note = await VoiceNotes(recorded_settings, client, inventory).note(item.id, silence())
    assert note.transcript.startswith("Case is scuffed")
    assert note.from_fixture is True and note.cost_usd == 0.0
    assert note.seconds == 1.5
    field = note.item.fields["condition_notes"]
    assert (field.provenance, field.source, field.review) == (
        "owner_reported",
        "voice_note",
        "accepted",
    )
    assert field.value == note.transcript
    assert note.item.version == 2


async def test_a_live_call_is_multipart_and_priced_by_the_seconds_heard(
    live_settings: Settings,
) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "sessionId": "s1",
                "transcript": " Frayed sleeve. ",
                "audioDurationMs": 90000,
                "turns": [],
            },
        )

    ledger = CostLedger(cap_usd=25.0)
    client = ModelApiClient(live_settings, ledger, transport=httpx.MockTransport(handler))
    transcript = await client.transcribe(silence(), keywords=["Orbital"])
    assert seen["path"].endswith("/asr/transcribe")
    assert str(seen["content_type"]).startswith("multipart/form-data")
    body = bytes(seen["body"])  # type: ignore[arg-type]
    assert b'name="request"' in body and b"application/json" in body
    assert b'"audioEncoding": "WAV"' in body and b'"keywords": ["Orbital"]' in body
    assert b'name="audio"; filename="note.wav"' in body and b"RIFF" in body
    assert transcript.text == "Frayed sleeve."
    assert transcript.seconds == 90.0
    assert transcript.cost_usd == pytest.approx(90 / 3600 * VOICE_USD_PER_HOUR)
    entry = ledger.entries()[0]
    assert entry.op == "transcribe" and entry.endpoint == "/asr/transcribe"
    assert entry.usage.audio_seconds == 90.0


async def test_limits_before_any_call(recorded_settings: Settings) -> None:
    settings = recorded_settings.model_copy(update={"voice_max_seconds": 2})
    inventory = Inventory(settings)
    client = ModelApiClient(settings, CostLedger(cap_usd=25.0), FixtureStore(settings.fixtures_dir))
    item = inventory.create(ItemCreate(item_type="kettle"))
    notes = VoiceNotes(settings, client, inventory)
    with pytest.raises(BadAudioError, match="at most 2 s"):
        await notes.note(item.id, silence(3))
    with pytest.raises(BadAudioError, match="not a WAV"):
        await notes.note(item.id, b"nope")
    assert inventory.get(item.id).version == 1


def test_voice_route(recorded_client: TestClient) -> None:
    item_id = recorded_client.post("/api/items", json={"item_type": "adapter"}).json()["id"]
    res = recorded_client.post(
        f"/api/items/{item_id}/voice", files=[("audio", ("note.wav", silence(), "audio/wav"))]
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["field"] == "condition_notes" and body["item"]["fields"]["condition_notes"]
    bad = recorded_client.post(
        f"/api/items/{item_id}/voice", files=[("audio", ("note.mp3", b"ID3xx", "audio/mpeg"))]
    )
    assert bad.status_code == 400 and "not a WAV" in bad.json()["detail"]
    gone = recorded_client.post(
        "/api/items/999/voice", files=[("audio", ("n.wav", silence(), "audio/wav"))]
    )
    assert gone.status_code == 404
    assert "/api/items/{item_id}/voice" in recorded_client.get("/openapi.json").json()["paths"]


def test_a_note_without_a_recorded_answer_is_a_503(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "adapter"}).json()["id"]
    res = client.post(
        f"/api/items/{item_id}/voice", files=[("audio", ("n.wav", silence(), "audio/wav"))]
    )
    assert res.status_code == 503


def test_fixture_file_shape() -> None:
    from tests.conftest import RECORDED_FIXTURES

    data = json.loads((RECORDED_FIXTURES / "asr-transcribe" / "transcribe.json").read_text())
    assert data["op"] == "transcribe" and data["response"]["transcript"]
