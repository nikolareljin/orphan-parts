from fastapi.testclient import TestClient

from tests.conftest import make_photo


def post_segment(
    client: TestClient, photo: bytes, *, name: str = "p.jpg", concepts: list[str] | None = None
) -> dict[str, object]:
    data = {"concepts": concepts} if concepts else None
    res = client.post("/api/segment", files=[("photo", (name, photo, "image/jpeg"))], data=data)
    body: dict[str, object] = res.json()
    body["_status"] = res.status_code
    return body


def test_segment_returns_regions_and_an_overlay(recorded_client: TestClient) -> None:
    body = post_segment(recorded_client, make_photo())
    assert body["_status"] == 200
    assert body["from_fixture"] is True
    regions = body["regions"]
    assert isinstance(regions, list)
    assert [r["concept"] for r in regions] == ["item", "label", "label", "connector"]
    assert regions[2]["box"] == {"left": 60, "top": 60, "right": 140, "bottom": 100}
    assert str(body["overlay"]).startswith("data:image/jpeg;base64,")
    assert body["warnings"] == []


def test_segment_takes_its_own_concepts(recorded_client: TestClient) -> None:
    body = post_segment(recorded_client, make_photo(), concepts=["label"])
    regions = body["regions"]
    assert isinstance(regions, list)
    assert [r["concept"] for r in regions] == ["label", "label"]


def test_segment_rejects_a_non_image_with_400(recorded_client: TestClient) -> None:
    body = post_segment(recorded_client, b"not a photo", name="notes.txt")
    assert body["_status"] == 400
    assert body["detail"] == "the file is not an image"


def test_segment_requires_the_photo_field(recorded_client: TestClient) -> None:
    assert recorded_client.post("/api/segment").status_code == 422


def test_segment_answers_503_without_a_recorded_fixture(client: TestClient) -> None:
    body = post_segment(client, make_photo())
    assert body["_status"] == 503
    assert body["detail"] == "no recorded answer for this request in fixture mode"


def test_extract_with_crops_sources_evidence_from_the_crop(recorded_client: TestClient) -> None:
    res = recorded_client.post(
        "/api/extract",
        files=[
            ("photos", ("p.jpg", make_photo(), "image/jpeg")),
            ("crops", ("label-1.jpg", make_photo(240, 80), "image/jpeg")),
        ],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["photos"] == 1
    assert body["crops"] == 1
    assert {e["source"] for e in body["fields"].values()} == {"label_crop"}


def test_segment_is_in_the_openapi_document(recorded_client: TestClient) -> None:
    paths = recorded_client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/segment"]
