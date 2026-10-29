import json
from typing import Any

from fastapi.testclient import TestClient

from tests.measure_images import OPENING_A, OPENING_B, RULER_A, RULER_B, RULER_MM, ruler_photo


def request_json(**overrides: Any) -> str:
    body: dict[str, Any] = {
        "feature": "opening_inner_diameter",
        "profile": "vacuum_attachment",
        "image": {"width": 640, "height": 480},
        "reference": {
            "kind": "two_point",
            "points": [{"x": RULER_A[0], "y": RULER_A[1]}, {"x": RULER_B[0], "y": RULER_B[1]}],
            "length_mm": RULER_MM,
        },
        "points": [{"x": OPENING_A[0], "y": OPENING_A[1]}, {"x": OPENING_B[0], "y": OPENING_B[1]}],
        "straight_on": True,
    }
    body.update(overrides)
    return json.dumps(body)


def post(client: TestClient, path: str, request: str, photo: bytes | None = None) -> Any:
    return client.post(
        path,
        files=[("photo", ("opening.png", photo or ruler_photo(), "image/png"))],
        data={"request": request},
    )


def test_measure_answers_without_storing(client: TestClient) -> None:
    res = post(client, "/api/measure", request_json())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["accepted"] is True
    assert abs(body["value_mm"] - 35.0) < 0.3
    assert body["unit"] == "mm"
    assert body["needs_direct_reading"] is True
    assert client.get("/api/items").json() == []


def test_bad_request_json_and_unknown_profile_are_422(client: TestClient) -> None:
    bad = post(client, "/api/measure", '{"feature": "x"}')
    assert bad.status_code == 422
    assert any("request" in d["loc"] for d in bad.json()["detail"])
    unknown = post(client, "/api/measure", request_json(profile="toaster"))
    assert unknown.status_code == 422
    assert "toaster" in unknown.json()["detail"]
    not_photo = post(client, "/api/measure", request_json(), photo=b"not a photo")
    assert not_photo.status_code == 400


def test_a_measurement_on_an_item_proposes_an_observed_value(client: TestClient) -> None:
    item = client.post(
        "/api/items", json={"item_type": "crevice tool", "profile": "vacuum_attachment"}
    )
    assert item.status_code == 201
    item_id = item.json()["id"]

    res = post(client, f"/api/items/{item_id}/measurements", request_json())
    assert res.status_code == 201, res.text
    stored = res.json()
    assert stored["item_id"] == item_id
    assert stored["accepted"] is True
    assert stored["assertion_id"] is not None

    page = client.get(f"/api/items/{item_id}").json()
    field = page["fields"]["opening_inner_diameter"]
    assert field["id"] == stored["assertion_id"]
    assert field["value"] == "35.0"
    assert field["unit"] == "mm"
    assert field["provenance"] == "observed"
    assert field["source"] == "measurement"
    assert field["review"] == "proposed"
    assert "two point scale" in field["raw"]
    assert page["version"] == 2

    listed = client.get(f"/api/items/{item_id}/measurements").json()
    assert [m["id"] for m in listed] == [stored["id"]]
    photo = client.get(f"/api/items/{item_id}/measurements/{stored['id']}/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.content[:2] == b"\xff\xd8"
    events = client.get(f"/api/items/{item_id}/events").json()
    assert events[-1]["change"].startswith("opening_inner_diameter measured: 35.")


def test_a_refused_capture_is_kept_without_a_value(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "crevice tool"}).json()["id"]
    res = post(client, f"/api/items/{item_id}/measurements", request_json(straight_on=False))
    assert res.status_code == 201
    stored = res.json()
    assert stored["accepted"] is False
    assert stored["assertion_id"] is None
    assert stored["value_mm"] is None
    assert client.get(f"/api/items/{item_id}").json()["fields"] == {}
    assert len(client.get(f"/api/items/{item_id}/measurements").json()) == 1
    assert "capture refused" in client.get(f"/api/items/{item_id}/events").json()[-1]["change"]


def test_missing_item_or_measurement_is_404(client: TestClient) -> None:
    assert post(client, "/api/items/42/measurements", request_json()).status_code == 404
    assert client.get("/api/items/42/measurements").status_code == 404
    item_id = client.post("/api/items", json={"item_type": "x"}).json()["id"]
    assert client.get(f"/api/items/{item_id}/measurements/9/photo").status_code == 404


def test_openapi_documents_measuring(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/measure"]
    assert {"post", "get"} <= set(paths["/api/items/{item_id}/measurements"])
    assert "get" in paths["/api/items/{item_id}/measurements/{measurement_id}/photo"]
