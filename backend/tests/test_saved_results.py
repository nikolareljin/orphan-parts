"""What was asked for an item is kept and read back: the Decide cards and ideas, the drafts, the
price guidance, the listing details and the outcomes. The demo visitor reads a public item's
results as they were saved (masked, without the owner's own words), never a private one's, and
nothing is asked of a model when any of them is read, by the visitor or the owner."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ops.gate import DEMO_LINE
from tests.conftest import RECORDED_FIXTURES
from tests.test_gate import CODE, gated_settings

SERIAL = "CN0J5C3H742613AB"
SECRETS = ("garage shelf B", "paid 40 for it", "moving to Denver in March", "Astoria")
LOWEST = 27.5
NOTE = "the owner's own reason"


@pytest.fixture
def gated(tmp_path: Path) -> Iterator[TestClient]:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        yield c


def calls(c: TestClient) -> int:
    """Every model call this process made, recorded answers included."""
    by_model: dict[str, Any] = c.get("/api/spend").json()["by_model"]
    return sum(int(m.get("calls", 0)) for m in by_model.values())


def _saved_item(c: TestClient, *, public: bool = True) -> int:
    """As the owner: an item with a location, notes and a serial number, asked for everything
    once: ideas, cards (and a second set, with the serial written into it), a sell draft from
    listing details with the private ones, price guidance and a decision with a note."""
    c.post("/api/access", json={"code": CODE})
    item = c.post(
        "/api/items",
        json={
            "name": "Spare monitor",
            "item_type": "monitor",
            "condition": "works",
            "location": SECRETS[0],
            "notes": SECRETS[1],
        },
    ).json()["id"]
    c.post(f"/api/items/{item}/fields", json={"field": "serial_number", "value": SERIAL})
    details = {
        "condition_words": f"works well; S/N {SERIAL} on the back",
        "handover": "pickup",
        "area": SECRETS[3],
        "asking_price": 35,
        "lowest_price": LOWEST,
        "reason": SECRETS[2],
    }
    assert c.put(f"/api/items/{item}/sell-details", json=details).status_code == 200
    assert c.post(f"/api/items/{item}/uses").status_code == 201
    first = c.post(f"/api/items/{item}/scenarios")
    assert first.status_code == 201, first.text
    assert c.post(f"/api/items/{item}/drafts", json={"mode": "sell"}).status_code == 201
    assert c.post(f"/api/items/{item}/price", json={}).status_code == 201
    # a second set of cards whose words carry the serial: asking again adds, never replaces
    inventory = c.app.state.inventory  # type: ignore[attr-defined]
    row = inventory.scenarios(item)[-1]
    content = json.loads(row["content"])
    content["reason"] = f"check S/N {SERIAL} before anything"
    inventory.add_scenarios(item, json.dumps(content), item_version=int(row["item_version"]))
    decided = c.post(f"/api/items/{item}/decision", json={"choice": "sell", "note": NOTE})
    assert decided.status_code == 200
    if public:
        assert c.post(f"/api/items/{item}/public", json={"public": True}).status_code == 200
    return int(item)


def _reads(item: int, c: TestClient) -> list[str]:
    draft = c.get(f"/api/items/{item}/drafts").json()[-1]["id"]
    return [
        f"/api/items/{item}/decide",
        f"/api/items/{item}/scenarios",
        f"/api/items/{item}/uses",
        f"/api/items/{item}/drafts",
        f"/api/drafts/{draft}",
        f"/api/items/{item}/price",
        f"/api/items/{item}/sell-details",
        f"/api/items/{item}/marketplace",
    ]


def test_the_visitor_reads_every_saved_result_of_a_public_item(gated: TestClient) -> None:
    item = _saved_item(gated)
    paths = _reads(item, gated)
    gated.cookies.clear()
    for path in paths:
        seen = gated.get(path)
        assert seen.status_code == 200, (path, seen.text)
        for secret in (*SECRETS, NOTE, SERIAL, "27.5"):
            assert secret not in seen.text, (path, secret)
    view = gated.get(f"/api/items/{item}/decide").json()
    # the latest cards, the serial in them masked; the choice without the owner's note
    assert view["scenarios"]["version"] == 2
    assert "13AB" in view["scenarios"]["reason"] and SERIAL not in view["scenarios"]["reason"]
    assert view["last"]["choice"] == "sell" and view["last"]["note"] == ""
    assert view["uses"] is not None and view["worth"] is not None
    # the history: both sets of cards, oldest first
    kept = gated.get(f"/api/items/{item}/scenarios").json()
    assert [s["version"] for s in kept] == [1, 2]
    draft = gated.get(f"/api/items/{item}/drafts").json()[-1]
    assert draft["title"] and draft["description"] and draft["checklist"]
    details = gated.get(f"/api/items/{item}/sell-details").json()["details"]
    assert details["lowest_price"] is None and details["reason"] == "" and details["area"] == ""
    # the list marks what is saved, and the plan chosen
    listed = next(i for i in gated.get("/api/items").json() if i["id"] == item)
    assert set(listed["saved"]) == {"cards", "ideas", "sell_draft", "price"}
    assert listed["decided"] == "sell"


def test_the_owner_reads_them_whole(gated: TestClient) -> None:
    item = _saved_item(gated)
    view = gated.get(f"/api/items/{item}/decide").json()
    assert view["last"]["note"] == NOTE
    assert SERIAL in view["scenarios"]["reason"]
    details = gated.get(f"/api/items/{item}/sell-details").json()["details"]
    assert details["lowest_price"] == LOWEST and details["reason"] == SECRETS[2]


def test_a_private_items_results_are_not_there_for_the_visitor(gated: TestClient) -> None:
    item = _saved_item(gated, public=False)
    paths = _reads(item, gated)
    gated.cookies.clear()
    for path in paths:
        assert gated.get(path).status_code == 404, path
    assert gated.get(f"/api/items/{item}/scenarios/1/reuse/0/pictures").status_code == 404


def test_the_visitor_asks_nothing_and_writes_nothing(gated: TestClient) -> None:
    item = _saved_item(gated)
    draft = gated.get(f"/api/items/{item}/drafts").json()[-1]["id"]
    gated.cookies.clear()
    for method, path in (
        ("POST", f"/api/items/{item}/scenarios"),
        ("POST", f"/api/items/{item}/uses"),
        ("POST", f"/api/items/{item}/decision"),
        ("POST", f"/api/items/{item}/drafts"),
        ("POST", f"/api/items/{item}/price"),
        ("POST", f"/api/items/{item}/price/reports"),
        ("PUT", f"/api/items/{item}/sell-details"),
        ("POST", f"/api/items/{item}/marketplace/listed"),
        ("POST", f"/api/drafts/{draft}/checklist"),
        ("DELETE", f"/api/items/{item}/drafts"),
        ("PUT", f"/api/items/{item}/scenarios"),
        ("GET", f"/api/items/{item}/price/reports"),
        ("GET", f"/api/drafts/{draft}/photos.zip"),
    ):
        refused = gated.request(method, path, json={})
        assert refused.status_code == 403 and refused.json()["detail"] == DEMO_LINE, path


def test_reading_saved_results_asks_no_model(gated: TestClient) -> None:
    item = _saved_item(gated)
    paths = _reads(item, gated)
    before = calls(gated)
    for path in (*paths, "/api/items", f"/api/items/{item}/pictures"):
        assert gated.get(path).status_code == 200, path
    assert calls(gated) == before
    # the visitor's reads ask nothing either
    gated.cookies.clear()
    for path in paths:
        assert gated.get(path).status_code == 200, path
    gated.post("/api/access", json={"code": CODE})
    assert calls(gated) == before


def test_asking_again_adds_a_version_and_keeps_the_earlier_ones(gated: TestClient) -> None:
    item = _saved_item(gated)
    before = len(gated.get(f"/api/items/{item}/scenarios").json())
    again = gated.post(f"/api/items/{item}/scenarios").json()
    kept = gated.get(f"/api/items/{item}/scenarios").json()
    assert len(kept) == before + 1 and kept[-1]["id"] == again["id"]
    assert gated.get(f"/api/items/{item}/decide").json()["scenarios"]["id"] == again["id"]
    gated.post(f"/api/items/{item}/uses")
    assert len(gated.get(f"/api/items/{item}/uses").json()) == 2
    gated.post(f"/api/items/{item}/drafts", json={"mode": "sell"})
    assert [d["version"] for d in gated.get(f"/api/items/{item}/drafts").json()] == [1, 2]


def test_the_visitor_reads_no_pickup_area_of_any_draft(gated: TestClient) -> None:
    item = _saved_item(gated)
    # the details saved again with another area, and a draft whose pickup was typed for it
    # alone: neither the earlier area, the later one nor the typed pickup reaches the visitor
    details = {"handover": "pickup", "area": "Sunnyside", "asking_price": 35}
    assert gated.put(f"/api/items/{item}/sell-details", json=details).status_code == 200
    typed = gated.post(
        f"/api/items/{item}/drafts", json={"mode": "sell", "pickup": "Corner of Elm and 5th"}
    )
    assert typed.status_code == 201 and "Elm" in typed.json()["pickup"]
    assert gated.post(f"/api/items/{item}/drafts", json={"mode": "sell"}).status_code == 201
    gated.cookies.clear()
    seen = gated.get(f"/api/items/{item}/drafts")
    assert seen.status_code == 200 and len(seen.json()) == 3
    for secret in (SECRETS[3], "Sunnyside", "Elm"):
        assert secret not in seen.text, secret
    assert all("the owner's area" in d["pickup"] for d in seen.json())


@pytest.mark.anyio
@pytest.mark.parametrize("pictures_on", [True, False])
async def test_every_item_of_the_committed_set_has_its_saved_outcome(
    recorded_settings: Settings, pictures_on: bool
) -> None:
    # the demo set as ./dev demo loads it: every result replayed from its own recording, and
    # each item kept with what its plan calls for, so a visitor reads them and nothing is asked;
    # the recorded drawings are shown whatever PICTURE_ENABLED says (the hosted load's case)
    from app.demo import load_set
    from app.demo.__main__ import build_loader

    path = Path(__file__).resolve().parents[2] / "demo" / "set.yaml"
    demo = load_set(path)
    loader, client = build_loader(
        recorded_settings.model_copy(update={"picture_enabled": pictures_on})
    )
    try:
        outcome = await loader.run(demo, path.parent)
    finally:
        await client.aclose()
    assert outcome.stub_answers == 0 and outcome.skipped == [] and outcome.unrecorded == []
    assert outcome.cost_usd == 0.0
    inventory = loader.inventory
    for item in demo.items:
        item_id = loader.ids[item.key]
        kept = loader.decider.decision(item_id)
        if item.decide:
            # current as loaded: a project selected later reserves the item, which is no edit
            assert kept.scenarios is not None and not kept.scenarios.stale, item.key
        if item.ideas:
            assert kept.uses is not None, item.key
        if item.decision:
            assert kept.last is not None and kept.last.choice == item.decision, item.key
        if item.draft:
            assert [d["mode"] for d in inventory.drafts(item_id)] == [item.draft], item.key
        if item.price:
            assert kept.worth is not None, item.key
    search = loader.finder.searches()[0]
    assert search.plan is not None and search.plan.phrasings
    projects = loader.planner.projects().projects
    # the projects the set selects have their build packs; every project its drawing
    selected = [p for p in projects if p.status == "selected"]
    assert demo.propose is not None and len(selected) == len(demo.propose.select)
    assert all(loader.planner.packs_of(p.id) for p in selected)
    assert all(loader.pictures and loader.pictures.project_list(p.id).pictures for p in projects)
