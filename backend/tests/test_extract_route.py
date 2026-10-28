import json
from pathlib import Path
from typing import Any

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


def fixture_client(tmp_path: Path, response: dict[str, Any], status: int) -> TestClient:
    settings = Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
    )
    responses = tmp_path / "fixtures" / "responses"
    responses.mkdir(parents=True)
    (responses / "extract.json").write_text(
        json.dumps(
            {
                "endpoint": "/responses",
                "op": "extract",
                "key": "extract",
                "response": response,
                "status": status,
            }
        )
    )
    return TestClient(create_app(settings))


def test_extract_answers_502_when_the_model_call_fails(tmp_path: Path) -> None:
    with fixture_client(
        tmp_path, {"error": {"message": "boom", "type": "server_error"}}, 500
    ) as client:
        body = upload(client, make_photo())
    assert body["_status"] == 502
    assert "boom" in str(body["detail"])


def test_extract_answers_502_when_the_response_is_incomplete(tmp_path: Path) -> None:
    with fixture_client(
        tmp_path,
        {
            "id": "resp_x",
            "model": "muse-spark-1.3",
            "status": "incomplete",
            "output": [],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "incomplete_details": {"reason": "max_output_tokens"},
        },
        200,
    ) as client:
        body = upload(client, make_photo())
    assert body["_status"] == 502
    assert "incomplete" in str(body["detail"])


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
