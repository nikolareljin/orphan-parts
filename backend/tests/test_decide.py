from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decide import DecisionCreate, decided_line, parse_decided, suggested, templates_for
from app.decide.service import brief, known_fields
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.main import create_app
from app.ops.gate import DEMO_LINE, expensive
from app.projects import Templates
from app.projects.schema import Preferences
from app.value.schema import Strategy

pytestmark = pytest.mark.anyio

CODE = "a-demo-code-with-length"


def laptop(inventory: Inventory, **over: str) -> int:
    spec = {
        "item_type": "laptop",
        "name": "Old laptop",
        "condition": "scuffed lid",
        "faults": "battery holds an hour",
        "tests_done": "boots to the desktop",
    }
    spec.update(over)
    item = inventory.create(ItemCreate(**spec))  # type: ignore[arg-type]
    inventory.add_field(item.id, FieldCreate(field="ram", value="8", unit="GB"))
    return item.id


def test_the_rules_name_the_templates_a_laptop_fills(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.get(laptop(inventory))
    fills = templates_for(item, Templates())
    by_id = {t.id: t.fills for t in fills}
    assert by_id["homework_workstation"] == ["laptop"]
    assert "vacuum_restored" not in by_id
    # a charger is not a laptop, whatever its name; it is a power supply for the mirror
    charger = inventory.get(laptop(inventory, item_type="laptop charger"))
    charger_fills = {t.id: t.fills for t in templates_for(charger, Templates())}
    assert "homework_workstation" not in charger_fills
    assert charger_fills["smart_mirror"] == ["power"]


def test_the_brief_carries_the_accepted_values_and_nothing_that_identifies(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory, location="top shelf", notes="was my brother's")
    inventory.add_field(item_id, FieldCreate(field="serial_number", value="XK12-99"))
    inventory.add_field(item_id, FieldCreate(field="mac", value="00:11:22:33:44:55"))
    inventory.add_field(item_id, FieldCreate(field="screen_size", value="15", unit="in"))
    item = inventory.get(item_id)
    assert known_fields(item) == {"ram": "8 GB", "screen_size": "15 in"}
    text = brief(item, known_fields(item), Preferences(), templates_for(item, Templates()))
    assert "scuffed lid" in text and "- ram: 8 GB" in text
    for private in ("XK12-99", "00:11:22", "top shelf", "brother"):
        assert private not in text, private


def test_the_strategy_to_start_from_is_typical_when_it_has_a_figure() -> None:
    quick = Strategy(name="quick_sale", label="Quick sale", price=12.0, note="")
    typical = Strategy(name="typical", label="Typical", price=18.0, note="")
    none = Strategy(name="patient", label="Patient", price=None, note="")
    assert suggested([quick, typical, none]) is typical
    assert suggested([quick, typical.model_copy(update={"price": None}), none]) is quick
    assert suggested([none]) is None
    assert suggested([]) is None


def test_the_decision_line_round_trips() -> None:
    assert decided_line(DecisionCreate(choice="sell", note="worth the listing")) == (
        "decided: sell: worth the listing"
    )
    assert decided_line(DecisionCreate(choice="not_worth")) == "decided: not_worth"
    assert parse_decided("decided: sell: worth the listing") == ("sell", "worth the listing")
    assert parse_decided("decided: not_worth") == ("not_worth", "")
    assert parse_decided("decided: lend: it") is None
    assert parse_decided("changed intent") is None


def test_uses_come_from_the_stub_and_are_kept_on_the_item(recorded_client: TestClient) -> None:
    item = recorded_client.post(
        "/api/items",
        json={"item_type": "laptop", "name": "Old laptop", "tests_done": "boots"},
    ).json()
    recorded_client.post(f"/api/items/{item['id']}/fields", json={"field": "ram", "value": "8"})
    asked = recorded_client.post(f"/api/items/{item['id']}/uses")
    assert asked.status_code == 201, asked.text
    uses = asked.json()
    assert uses["from_fixture"] is True and uses["cost_usd"] == 0
    assert uses["version"] == 1 and uses["stale"] is False
    assert [t["id"] for t in uses["templates"]] and uses["templates"][0]["fills"]
    assert len(uses["uses"]) == 3
    first = uses["uses"][0]
    assert first["title"].startswith("Homework workstation")
    assert first["effort"] == "low" and first["needs"]
    events = [e["change"] for e in recorded_client.get(f"/api/items/{item['id']}/events").json()]
    assert "uses written (v1)" in events
    # asking again is a new version; an edit in between makes the first stale
    recorded_client.patch(f"/api/items/{item['id']}", json={"condition": "scuffed"})
    again = recorded_client.post(f"/api/items/{item['id']}/uses").json()
    assert again["version"] == 2 and again["stale"] is False
    assert recorded_client.get(f"/api/items/{item['id']}/decide").json()["uses"]["version"] == 2
    assert recorded_client.post("/api/items/999/uses").status_code == 404


def test_the_view_gathers_guidance_uses_searches_and_the_decision(
    recorded_client: TestClient,
) -> None:
    item = recorded_client.post(
        "/api/items", json={"item_type": "laptop", "name": "Old laptop", "profile": "generic_item"}
    ).json()
    item_id = item["id"]
    bare = recorded_client.get(f"/api/items/{item_id}/decide")
    assert bare.status_code == 200, bare.text
    view = bare.json()
    assert view["item"]["id"] == item_id and view["accepted_fields"] == 0
    assert view["worth"] is None and view["uses"] is None and view["searches"] == []
    assert [t["id"] for t in view["templates"]]
    assert view["intent"] == "keep" and view["last"] is None

    recorded_client.post(f"/api/items/{item_id}/fields", json={"field": "ram", "value": "8"})
    assert recorded_client.post(f"/api/items/{item_id}/price", json={}).status_code == 201
    assert recorded_client.post(f"/api/items/{item_id}/uses").status_code == 201
    search = recorded_client.post(
        "/api/searches", json={"need_item_id": item_id, "title": "A monitor for it"}
    )
    assert search.status_code == 201, search.text
    closed = recorded_client.post(
        "/api/searches", json={"need_item_id": item_id, "title": "A cable"}
    ).json()
    recorded_client.patch(f"/api/searches/{closed['id']}", json={"status": "closed"})

    view = recorded_client.get(f"/api/items/{item_id}/decide").json()
    assert view["accepted_fields"] == 1
    worth = view["worth"]
    assert worth["version"] == 1 and worth["currency"] == "USD"
    assert worth["typical"] is not None and worth["strategy"]["name"] == "typical"
    assert view["uses"]["version"] == 1 and len(view["uses"]["uses"]) == 3
    assert [s["title"] for s in view["searches"]] == ["A monitor for it"]
    assert view["searches"][0]["candidates"] == 0
    assert view["searches"][0]["handoff_url"].startswith("http")

    decided = recorded_client.post(
        f"/api/items/{item_id}/decision", json={"choice": "sell", "note": "worth a listing"}
    )
    assert decided.status_code == 200, decided.text
    after = decided.json()
    assert after["intent"] == "sell" and after["version"] == item["version"] + 2
    events = [e["change"] for e in recorded_client.get(f"/api/items/{item_id}/events").json()]
    assert events[-1] == "decided: sell: worth a listing"
    view = recorded_client.get(f"/api/items/{item_id}/decide").json()
    assert view["intent"] == "sell"
    assert view["last"]["choice"] == "sell" and view["last"]["note"] == "worth a listing"
    assert view["last"]["version"] == after["version"]
    # the guidance and the uses were written before the decision: they say the item changed
    assert view["worth"]["stale"] is True and view["uses"]["stale"] is True

    for choice, intent in (("keep_build", "build"), ("give", "give"), ("not_worth", "keep")):
        changed = recorded_client.post(
            f"/api/items/{item_id}/decision", json={"choice": choice, "note": ""}
        ).json()
        assert changed["intent"] == intent, choice
    assert recorded_client.get(f"/api/items/{item_id}/decide").json()["last"]["note"] == ""
    assert view["committed_to"] == []
    assert (
        recorded_client.post(f"/api/items/{item_id}/decision", json={"choice": "lend"}).status_code
        == 422
    )
    assert (
        recorded_client.post(
            f"/api/items/{item_id}/decision", json={"choice": "sell", "note": "x" * 201}
        ).status_code
        == 422
    )
    assert recorded_client.get("/api/items/999/decide").status_code == 404
    missing = recorded_client.post("/api/items/999/decision", json={"choice": "sell"})
    assert missing.status_code == 404


@pytest.fixture
def gated(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        demo_access_code=CODE,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as c:
        yield c


def test_the_demo_visitor_is_refused_on_every_decide_route(gated: TestClient) -> None:
    gated.post("/api/access", json={"code": CODE})
    item = gated.post("/api/items", json={"item_type": "laptop"}).json()
    gated.post(f"/api/items/{item['id']}/public", json={"public": True})
    assert gated.get(f"/api/items/{item['id']}/decide").status_code == 200
    gated.cookies.clear()
    for method, path in (
        ("POST", f"/api/items/{item['id']}/uses"),
        ("GET", f"/api/items/{item['id']}/decide"),
        ("POST", f"/api/items/{item['id']}/decision"),
    ):
        answer = gated.request(method, path, json={"choice": "sell"} if method == "POST" else None)
        assert answer.status_code == 403 and answer.json() == {"detail": DEMO_LINE}, path
    assert expensive("POST", "/api/items/12/uses")
    assert not expensive("GET", "/api/items/12/decide")
    assert not expensive("POST", "/api/items/12/decision")


def test_the_same_choice_again_is_an_event_and_not_a_new_version(
    recorded_client: TestClient,
) -> None:
    item = recorded_client.post("/api/items", json={"item_type": "laptop"}).json()
    item_id, version = item["id"], item["version"]
    assert recorded_client.post(f"/api/items/{item_id}/price", json={}).status_code == 201
    # the intent is keep already: nothing changes, nothing is said, the version stays
    same = recorded_client.post(f"/api/items/{item_id}/decision", json={"choice": "not_worth"})
    assert same.status_code == 200 and same.json()["version"] == version
    view = recorded_client.get(f"/api/items/{item_id}/decide").json()
    assert view["last"]["choice"] == "not_worth" and view["last"]["version"] == version
    assert view["worth"]["stale"] is False
    # a note gives the item a new why: that is a change
    noted = recorded_client.post(
        f"/api/items/{item_id}/decision", json={"choice": "not_worth", "note": "parts only"}
    ).json()
    assert noted["intent"] == "keep" and noted["version"] == version + 1
    # a new intent is a change, with or without a note
    sold = recorded_client.post(f"/api/items/{item_id}/decision", json={"choice": "sell"}).json()
    assert sold["intent"] == "sell" and sold["version"] == version + 2
    again = recorded_client.post(f"/api/items/{item_id}/decision", json={"choice": "sell"}).json()
    assert again["version"] == version + 2
    events = [e["change"] for e in recorded_client.get(f"/api/items/{item_id}/events").json()]
    assert events[-4:] == [
        "decided: not_worth",
        "decided: not_worth: parts only",
        "decided: sell",
        "decided: sell",
    ]


def test_the_view_names_the_selected_project_that_counts_on_the_item(
    recorded_client: TestClient,
) -> None:
    for item_type, name in (("laptop", "Old laptop"), ("monitor", "Spare monitor")):
        recorded_client.post("/api/items", json={"item_type": item_type, "name": name})
    laptop_id = recorded_client.get("/api/items").json()[0]["id"]
    assert recorded_client.get(f"/api/items/{laptop_id}/decide").json()["committed_to"] == []
    proposed = recorded_client.post("/api/projects/propose", json={"count": 3}).json()
    desk = next(p for p in proposed if p["template"] == "homework_workstation")
    assert laptop_id in [a["item_id"] for a in desk["allocations"]]
    # proposed is not reserved; selected is
    assert recorded_client.get(f"/api/items/{laptop_id}/decide").json()["committed_to"] == []
    selected = recorded_client.post(f"/api/projects/{desk['id']}/select", json={})
    assert selected.status_code == 200, selected.text
    view = recorded_client.get(f"/api/items/{laptop_id}/decide").json()
    assert view["committed_to"] == [desk["title"]]
    assert view["item"]["availability"] == "reserved"
    # the decision is still the owner's; the view only says what it breaks
    sold = recorded_client.post(f"/api/items/{laptop_id}/decision", json={"choice": "sell"})
    assert sold.status_code == 200 and sold.json()["intent"] == "sell"
    # given up, the project releases the item
    given_up = recorded_client.post(f"/api/projects/{desk['id']}/abandon")
    assert given_up.status_code == 200, given_up.text
    assert recorded_client.get(f"/api/items/{laptop_id}/decide").json()["committed_to"] == []
