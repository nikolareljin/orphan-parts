import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.listing import (
    DraftRequest,
    Lister,
    StepChange,
    brief,
    checklist,
    claims_working,
    disclosures,
    ready,
)
from app.model_api import CostLedger, ModelApiClient
from tests.conftest import RECORDED_FIXTURES, make_photo

pytestmark = pytest.mark.anyio


def test_checklists_follow_the_mode_and_whether_data_is_held() -> None:
    sell = checklist("sell", holds_data=False)
    assert [s.group for s in sell].count("data") == 0
    assert {s.key for s in sell if s.required} >= {"clean", "test", "faults", "photo_faults"}
    give = checklist("give", holds_data=True)
    assert next(s for s in give if s.key == "test").label.startswith("Say what was tested")
    assert [s.key for s in give if s.group == "data"] == ["sign_out", "reset", "media", "limits"]
    assert ready(sell) is False
    for s in sell:
        if s.required:
            s.done = True
    assert ready(sell) is True


def adapter(inventory: Inventory, **over: str) -> int:
    spec = {
        "item_type": "laptop power adapter",
        "name": "Orbital charger",
        "condition": "scuffed case",
        "faults": "frayed sleeve near the plug",
        "tests_done": "",
        "accessories": "",
    }
    spec.update(over)
    item = inventory.create(ItemCreate(**spec))  # type: ignore[arg-type]
    inventory.add_field(
        item.id, FieldCreate(field="output_voltage", value="19.5", unit="V", provenance="tested")
    )
    inventory.add_field(item.id, FieldCreate(field="polarity", value="center positive"))
    return item.id


def test_the_brief_holds_only_confirmed_values_and_the_owner_details(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = adapter(inventory, accessories="original cable")
    item = inventory.get(item_id)
    text = brief(item, {"output_voltage": "19.5 V"}, DraftRequest(mode="sell", pickup="Astoria"))
    assert "- output_voltage: 19.5 V" in text
    assert "polarity" not in text.split("Field keys")[0]  # only what was passed as known
    assert "faults: frayed sleeve near the plug" in text
    assert "asking price: (the owner sets it)" in text
    keys = text.split("Field keys a fact may name: ")[1]
    assert "accessories" in keys and "pickup" in keys
    assert "tests_done" not in keys  # empty, so no line may rest on it
    lines = disclosures(item, DraftRequest(mode="sell", asking_price="$15"))
    assert lines[0] == "Known faults: frayed sleeve near the plug"
    assert lines[1] == "Not tested; sold as is."
    assert lines[2] == "Included: original cable"
    assert lines[3] == "Price: $15"
    free = disclosures(item, DraftRequest(mode="give", pickup="porch"))
    assert free[1] == "Not tested." and free[-1] == "Free to collect. Pickup: porch"


@pytest.fixture
def lister(recorded_settings: Settings) -> Lister:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    return Lister(recorded_settings, client, inventory)


async def test_a_sell_draft_keeps_confirmed_facts_and_adds_the_disclosures(
    lister: Lister,
) -> None:
    item_id = adapter(lister.inventory)
    draft = await lister.draft(item_id, DraftRequest(mode="sell", asking_price="$15"))
    assert draft.from_fixture is True and draft.cost_usd == 0.0
    assert draft.version == 1 and draft.item_version == 3 and draft.stale is False
    assert lister.inventory.get(item_id).version == 3  # writing a draft is not a change
    assert draft.title.startswith("Orbital 65 W laptop power adapter")
    # the recorded text rests two lines on fields this item does not confirm: both are dropped
    assert [f.field for f in draft.facts] == ["output_voltage", "polarity"]
    assert len([w for w in draft.warnings if "rested on nothing" in w]) == 2
    assert "Known faults: frayed sleeve near the plug" in draft.description
    assert "Not tested; sold as is." in draft.description
    assert "Nothing else included." in draft.description
    assert draft.description.endswith("Price: $15")
    assert draft.asking_price == "$15" and draft.uses == []
    assert draft.handoff_url.startswith("https://www.facebook.com/marketplace/")
    assert draft.ready is False
    assert [s.key for s in draft.checklist if s.group == "data"] == []
    # the item changed since: the draft is stale, and a second draft bumps the version
    lister.inventory.add_field(item_id, FieldCreate(field="colour", value="black"))
    assert lister.get(draft.id).stale is True
    again = await lister.draft(item_id, DraftRequest(mode="sell"))
    assert again.version == 2 and again.stale is False
    assert [d.version for d in lister.drafts(item_id)] == [1, 2]
    # another draft, in the other mode, does not make this one stale
    free = await lister.draft(item_id, DraftRequest(mode="give"))
    assert free.version == 1 and lister.get(again.id).stale is False


def test_a_claim_of_working_is_read_but_not_its_opposite() -> None:
    assert claims_working("Works perfectly.")
    assert claims_working("Charger, fully functional")
    assert claims_working("In working order, tested last week")
    assert not claims_working("Not tested; sold as is.")
    assert not claims_working("Never tested, untested, not working as far as I know")


async def test_a_hidden_items_drafts_are_hidden_with_it(lister: Lister) -> None:
    item_id = adapter(lister.inventory)
    draft = await lister.draft(item_id, DraftRequest(mode="sell"))
    lister.inventory.delete(item_id)
    with pytest.raises(LookupError, match="no draft"):
        lister.get(draft.id)
    with pytest.raises(LookupError, match="no draft"):
        lister.set_step(draft.id, StepChange(key="clean", done=True))
    with pytest.raises(LookupError, match="no item"):
        lister.drafts(item_id)


async def test_a_give_draft_is_free_lists_uses_and_data_steps(lister: Lister) -> None:
    item_id = adapter(lister.inventory, tests_done="charges a laptop for an hour")
    draft = await lister.draft(
        item_id, DraftRequest(mode="give", holds_data=True, pickup="porch, evenings")
    )
    assert draft.title.startswith("Free: ")
    assert draft.uses[0].startswith("Spare charger")
    assert "Tested: charges a laptop for an hour" in draft.description
    assert draft.description.endswith("Free to collect. Pickup: porch, evenings")
    assert draft.asking_price == ""
    assert [s.key for s in draft.checklist if s.group == "data"] == [
        "sign_out",
        "reset",
        "media",
        "limits",
    ]
    assert not any("claims a test" in w for w in draft.warnings)


async def test_observations_still_to_confirm_are_left_out_and_said(
    lister: Lister, recorded_settings: Settings
) -> None:
    # an item saved from the recorded reading: every field is proposed, none confirmed
    from app.extract import Extractor

    extractor = Extractor(recorded_settings, lister.client)
    reading = await extractor.extract([make_photo()])
    item = lister.inventory.create(ItemCreate(extraction=reading, name="Orbital"))
    draft = await lister.draft(item.id, DraftRequest(mode="sell"))
    assert draft.facts == []
    assert draft.to_confirm and "output_voltage" in draft.to_confirm
    assert any(w.startswith("observed values still to confirm") for w in draft.warnings)


async def test_a_working_claim_without_a_recorded_test_is_flagged(
    live_settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["text"]["format"]["name"] == "DraftWriting"
        assert body["instructions"].startswith("You write short, honest Marketplace")
        assert "Confirmed fields" in body["input"][0]["content"][0]["text"]
        writing = {
            "title": "Charger, fully functional",
            "description": "Works perfectly.",
            "uses": [],
            "keywords": [],
            "facts": [{"text": "Works perfectly", "field": "tests_done"}],
        }
        fixture = json.loads((RECORDED_FIXTURES / "responses" / "draft-sell.json").read_text())
        response: dict[str, Any] = fixture["response"]
        msg = next(o for o in response["output"] if o["type"] == "message")
        msg["content"][0]["text"] = json.dumps(writing)
        return httpx.Response(200, json=response)

    client = ModelApiClient(
        live_settings, CostLedger(cap_usd=25.0), transport=httpx.MockTransport(handler)
    )
    lister = Lister(live_settings, client, Inventory(live_settings))
    item_id = adapter(lister.inventory)
    draft = await lister.draft(item_id, DraftRequest(mode="sell"))
    assert draft.from_fixture is False and draft.cost_usd > 0
    assert draft.facts == []  # tests_done is empty, so a line resting on it is dropped
    assert any("claims a test or a working state" in w for w in draft.warnings)


def test_draft_routes(recorded_client: TestClient) -> None:
    res = recorded_client.post("/api/items", json={"item_type": "laptop power adapter"})
    item_id = res.json()["id"]
    recorded_client.post(
        f"/api/items/{item_id}/fields",
        json={"field": "output_voltage", "value": "19.5", "unit": "V"},
    )
    written = recorded_client.post(
        f"/api/items/{item_id}/drafts", json={"mode": "sell", "asking_price": "$10"}
    )
    assert written.status_code == 201, written.text
    draft = written.json()
    assert draft["title"] and draft["description"].endswith("Price: $10")
    assert draft["ready"] is False

    step = recorded_client.post(
        f"/api/drafts/{draft['id']}/checklist", json={"key": "clean", "done": True}
    )
    assert step.status_code == 200
    assert next(s for s in step.json()["checklist"] if s["key"] == "clean")["done"] is True
    assert (
        recorded_client.post(
            f"/api/drafts/{draft['id']}/checklist", json={"key": "fly", "done": True}
        ).status_code
        == 422
    )
    assert recorded_client.get(f"/api/drafts/{draft['id']}").json()["id"] == draft["id"]
    assert [d["id"] for d in recorded_client.get(f"/api/items/{item_id}/drafts").json()] == [
        draft["id"]
    ]
    assert recorded_client.get("/api/drafts/999").status_code == 404
    assert recorded_client.post("/api/items/999/drafts", json={"mode": "give"}).status_code == 404
    assert (
        recorded_client.post(f"/api/items/{item_id}/drafts", json={"mode": "lend"}).status_code
        == 422
    )
    events = recorded_client.get(f"/api/items/{item_id}/events").json()
    assert any(e["change"] == "sell draft written (v1)" for e in events)


def test_a_draft_without_a_recorded_answer_is_a_503(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "kettle"}).json()["id"]
    res = client.post(f"/api/items/{item_id}/drafts", json={"mode": "give"})
    assert res.status_code == 503
    assert "no recorded answer" in res.json()["detail"]


def test_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/items/{item_id}/drafts" in paths
    assert "/api/drafts/{draft_id}/checklist" in paths
