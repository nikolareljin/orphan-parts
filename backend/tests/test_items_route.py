from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import make_photo


def create(client: TestClient, **spec: Any) -> dict[str, Any]:
    res = client.post("/api/items", json=spec)
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


def test_a_reading_is_saved_privately_as_an_item(recorded_client: TestClient) -> None:
    reading = recorded_client.post(
        "/api/extract", files=[("photos", ("p.jpg", make_photo(), "image/jpeg"))]
    ).json()
    item = create(recorded_client, extraction=reading, name="Orbital charger")
    assert item["name"] == "Orbital charger"
    assert item["item_type"] == "laptop power adapter"
    volts = item["fields"]["output_voltage"]
    assert volts["value"] == "19.5"
    assert volts["provenance"] == "observed"
    assert volts["review"] == "proposed"
    assert item["field_count"] == len(reading["fields"])
    listed = recorded_client.get("/api/items").json()
    assert [s["id"] for s in listed] == [item["id"]]
    assert listed[0]["field_count"] == item["field_count"]


def test_item_pages_and_edits(client: TestClient) -> None:
    item = create(client, item_type="USB webcam", condition="works", location="shelf")
    item_id = item["id"]
    assert client.get(f"/api/items/{item_id}").json()["location"] == "shelf"

    patched = client.patch(
        f"/api/items/{item_id}", json={"intent": "sell", "version": item["version"]}
    )
    assert patched.status_code == 200
    assert patched.json()["intent"] == "sell"
    assert patched.json()["version"] == 2

    stale = client.patch(f"/api/items/{item_id}", json={"intent": "give", "version": 1})
    assert stale.status_code == 409
    assert "version 2" in stale.json()["detail"]

    bad = client.patch(f"/api/items/{item_id}", json={"intent": "lend"})
    assert bad.status_code == 422

    with_field = client.post(
        f"/api/items/{item_id}/fields", json={"field": "resolution", "value": "1080p"}
    )
    assert with_field.status_code == 200
    field = with_field.json()["fields"]["resolution"]
    assert (field["provenance"], field["review"], field["source"]) == (
        "owner_reported",
        "accepted",
        "user_edit",
    )
    bad_name = client.post(f"/api/items/{item_id}/fields", json={"field": "Bad Name", "value": "x"})
    assert bad_name.status_code == 422

    events = client.get(f"/api/items/{item_id}/events").json()
    assert [e["change"] for e in events] == [
        "created",
        "changed intent",
        "resolution set to 1080p (owner_reported)",
    ]


def test_review_component_and_delete(recorded_client: TestClient) -> None:
    reading = recorded_client.post(
        "/api/extract", files=[("photos", ("p.jpg", make_photo(), "image/jpeg"))]
    ).json()
    item = create(recorded_client, extraction=reading)
    item_id = item["id"]
    volts = item["fields"]["output_voltage"]

    reviewed = recorded_client.post(
        f"/api/items/{item_id}/assertions/{volts['id']}/review", json={"review": "accepted"}
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["fields"]["output_voltage"]["review"] == "accepted"
    missing = recorded_client.post(
        f"/api/items/{item_id}/assertions/999/review", json={"review": "accepted"}
    )
    assert missing.status_code == 404

    child = recorded_client.post(
        f"/api/items/{item_id}/components", json={"name": "power cable", "condition": "frayed"}
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == item_id
    parent = recorded_client.get(f"/api/items/{item_id}").json()
    assert parent["components"] == [child.json()["id"]]
    assert "power cable separated" in parent["faults"]

    gone = recorded_client.delete(f"/api/items/{item_id}")
    assert gone.status_code == 204
    assert recorded_client.get(f"/api/items/{item_id}").status_code == 404
    assert recorded_client.delete(f"/api/items/{item_id}").status_code == 404
    assert [s["id"] for s in recorded_client.get("/api/items").json()] == [child.json()["id"]]
    assert recorded_client.get(f"/api/items/{item_id}/events").status_code == 200


def test_unknown_item_is_404_with_a_message(client: TestClient) -> None:
    res = client.get("/api/items/42")
    assert res.status_code == 404
    assert res.json() == {"detail": "no item 42"}


def test_openapi_documents_the_inventory(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"post", "get"} <= set(paths["/api/items"])
    assert {"get", "patch", "delete"} <= set(paths["/api/items/{item_id}"])
    assert "post" in paths["/api/items/{item_id}/fields"]
    assert "post" in paths["/api/items/{item_id}/components"]
    assert "post" in paths["/api/items/{item_id}/assertions/{assertion_id}/review"]
    assert "get" in paths["/api/items/{item_id}/events"]


def test_blank_edits_are_422(client: TestClient) -> None:
    item = create(client, item_type="hub")
    item_id = item["id"]
    assert client.patch(f"/api/items/{item_id}", json={"name": "  "}).status_code == 422
    blank = {"field": "colour", "value": " "}
    assert client.post(f"/api/items/{item_id}/fields", json=blank).status_code == 422
    assert client.post(f"/api/items/{item_id}/components", json={"name": " "}).status_code == 422
    assert client.get(f"/api/items/{item_id}").json()["version"] == 1
