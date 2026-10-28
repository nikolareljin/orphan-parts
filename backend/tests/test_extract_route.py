from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import CostLedger, LedgerEntry
from tests.conftest import make_photo


def upload(client: TestClient, *photos: bytes, names: list[str] | None = None) -> dict[str, object]:
    files = [
        ("photos", (name, data, "image/jpeg"))
        for name, data in zip(
            names or [f"p{i}.jpg" for i in range(len(photos))], photos, strict=True
        )
    ]
    res = client.post("/api/extract", files=files)
    body: dict[str, object] = res.json()
    body["_status"] = res.status_code
    return body


def test_extract_returns_fields_with_evidence(recorded_client: TestClient) -> None:
    body = upload(recorded_client, make_photo())
    assert body["_status"] == 200
    assert body["item_type"] == "laptop power adapter"
    assert body["from_fixture"] is True
    assert body["photos"] == 1
    fields = body["fields"]
    assert isinstance(fields, dict)
    assert fields["output_voltage"] == {
        "value": "19.5",
        "unit": "V",
        "confidence": 0.97,
        "source": "photo",
        "raw": "19.5V",
    }
    assert body["warnings"] == []


def test_extract_rejects_a_non_image_with_400(recorded_client: TestClient) -> None:
    body = upload(recorded_client, b"not a photo", names=["notes.txt"])
    assert body["_status"] == 400
    assert body["detail"] == "the file is not an image"


def test_extract_rejects_too_many_photos(recorded_client: TestClient) -> None:
    body = upload(recorded_client, *([make_photo()] * 5))
    assert body["_status"] == 400
    assert body["detail"] == "at most 4 photos per request"


def test_extract_requires_the_photos_field(recorded_client: TestClient) -> None:
    assert recorded_client.post("/api/extract").status_code == 422


def test_extract_answers_503_without_a_recorded_fixture(client: TestClient) -> None:
    body = upload(client, make_photo())
    assert body["_status"] == 503
    assert body["detail"] == "no recorded answer for this request in fixture mode"


def test_extract_answers_503_when_the_spend_cap_is_reached(tmp_path: Path) -> None:
    settings = Settings(
        OPL_FAKE_API=False,
        model_api_key="sample-value-for-tests",
        data_dir=tmp_path / "data",
        spend_cap_usd=1.0,
        log_format="text",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        ledger: CostLedger = client.app.state.ledger  # type: ignore[attr-defined]
        ledger.record(
            LedgerEntry(op="extract", model="muse-spark-1.3", endpoint="/responses", usd=1.0)
        )
        body = upload(client, make_photo())
    assert body["_status"] == 503
    assert "cap" in str(body["detail"])


def test_extract_is_in_the_openapi_document(recorded_client: TestClient) -> None:
    paths = recorded_client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/extract"]
