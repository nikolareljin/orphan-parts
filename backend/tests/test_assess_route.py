from typing import Any

from fastapi.testclient import TestClient


def create(client: TestClient, **spec: Any) -> int:
    res = client.post("/api/items", json=spec)
    assert res.status_code == 201, res.text
    item_id: int = res.json()["id"]
    return item_id


def add(client: TestClient, item_id: int, **fields: str) -> None:
    for field, value in fields.items():
        res = client.post(f"/api/items/{item_id}/fields", json={"field": field, "value": value})
        assert res.status_code == 200, res.text


def test_assess_two_items_and_the_rules_of_a_profile(client: TestClient) -> None:
    laptop = create(client, item_type="laptop", profile="power_adapter")
    add(client, laptop, output_voltage="19.5", output_current="3.33", polarity="center positive")
    adapter = create(client, item_type="power adapter")
    add(client, adapter, output_voltage="19.5", output_current="4.62", polarity="center positive")

    res = client.post(
        "/api/assess", json={"need": {"item_id": laptop}, "candidate": {"item_id": adapter}}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile"] == "power_adapter"
    assert body["verdict"] == "VISUALLY_SIMILAR"
    statuses = {c["key"]: c["status"] for c in body["checks"]}
    assert statuses["output_voltage"] == "pass"
    assert statuses["plug_outer_diameter"] == "unknown"
    assert body["missing"] == [
        "Part number",
        "Model number",
        "Connector",
        "Plug outer diameter",
        "Plug inner diameter",
        "Plug length",
    ]
    assert body["questions"] == []

    rules = client.get("/api/profiles/power_adapter/rules")
    assert rules.status_code == 200
    keys = [r["key"] for r in rules.json()]
    assert keys[:3] == ["part_number", "model_number", "output_voltage"]
    voltage = next(r for r in rules.json() if r["key"] == "output_voltage")
    assert voltage["tolerance_pct"] == 5 and voltage["hard"] is True
    plug = next(r for r in rules.json() if r["key"] == "plug_outer_diameter")
    assert plug["tolerance"] == 0.1 and plug["unit"] == "mm"


def test_values_written_in_on_both_sides(client: TestClient) -> None:
    res = client.post(
        "/api/assess",
        json={
            "need": {"profile": "power_adapter", "values": {"output_voltage": "19.5"}},
            "candidate": {"values": {"output_voltage": "12 V"}},
        },
    )
    assert res.status_code == 200
    assert res.json()["verdict"] == "CONFLICT"
    assert res.json()["need_item"] is None


def test_assess_errors(client: TestClient) -> None:
    no_profile = client.post("/api/assess", json={"need": {}, "candidate": {}})
    assert no_profile.status_code == 422
    assert "no profile" in no_profile.json()["detail"]
    unknown = client.post("/api/assess", json={"need": {"profile": "toaster"}, "candidate": {}})
    assert unknown.status_code == 422
    gone = client.post("/api/assess", json={"need": {"item_id": 999}, "candidate": {}})
    assert gone.status_code == 404
    bad = client.post("/api/assess", json={"need": {"item_id": "x"}, "candidate": {}})
    assert bad.status_code == 422
    item = create(client, item_type="laptop", profile="power_adapter")
    same = client.post(
        "/api/assess", json={"need": {"item_id": item}, "candidate": {"item_id": item}}
    )
    assert same.status_code == 422
    assert "same item" in same.json()["detail"]
    assert client.get("/api/profiles/toaster/rules").status_code == 404


def test_assess_is_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/assess" in paths
    assert "/api/profiles/{profile_id}/rules" in paths


def test_an_all_metal_rod_fits_the_worn_one_and_a_plastic_rod_does_not(client: TestClient) -> None:
    # the need is the worn rod's dimensions with the material wanted in its replacement
    need = {
        "profile": "blender_agitator",
        "values": {"rod_diameter": "4", "tab_span": "9", "material": "metal"},
    }
    metal = {"values": {"rod_diameter": "4", "tab_span": "9", "material": "metal"}}
    plastic = {"values": {"rod_diameter": "4", "tab_span": "9", "material": "plastic"}}
    same = client.post("/api/assess", json={"need": need, "candidate": metal}).json()
    statuses = {c["key"]: c["status"] for c in same["checks"]}
    assert statuses["material"] == "pass" and statuses["rod_diameter"] == "pass"
    assert same["verdict"] != "CONFLICT"
    other = client.post("/api/assess", json={"need": need, "candidate": plastic}).json()
    assert other["verdict"] == "CONFLICT"
    assert {c["key"]: c["status"] for c in other["checks"]}["material"] == "fail"
