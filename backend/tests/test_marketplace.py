"""Facebook Marketplace (US): the details the owner adds, the draft in Marketplace shape, the
photo zip and what happened after the owner posted."""

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.listing import DraftRequest, Lister, SellDetails, brief, price_for
from app.listing.marketplace import (
    data,
    personal_details,
    pick_category,
    pick_condition,
    strip_personal,
)
from app.main import create_app
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import demo_allowed, expensive
from tests.conftest import RECORDED_FIXTURES
from tests.test_gate import CODE, gated_settings

pytestmark = pytest.mark.anyio

# private values that must never reach the model or the listing
LOWEST = 27.5
REASON = "moving to Denver in March"


def details(**over: Any) -> SellDetails:
    spec: dict[str, Any] = {
        "condition_words": "Works well; one stuck pixel near the top left corner",
        "included": ["stand", "power_cord"],
        "included_other": "VGA cable",
        "faults": "one stuck pixel",
        "untested": "the DVI input",
        "handover": "pickup",
        "area": "Astoria",
        "asking_price": 35,
        "lowest_price": LOWEST,
        "reason": REASON,
        "availability": "weekday evenings",
    }
    spec.update(over)
    return SellDetails(**spec)


def monitor(inventory: Inventory) -> int:
    item = inventory.create(
        ItemCreate(item_type="LCD monitor", name="DELL 1800FP", condition="clean, light wear")
    )
    inventory.add_field(item.id, FieldCreate(field="screen_size", value="18", unit="in"))
    return item.id


def exif_photo() -> bytes:
    img = Image.new("RGB", (640, 480), (90, 120, 160))
    exif = Image.Exif()
    exif[0x010F] = "SampleCam"  # Make
    exif[0x0132] = "2026:10:30 12:00:00"  # DateTime
    out = BytesIO()
    img.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


# --- the data file -----------------------------------------------------------------------


def test_the_data_file_names_us_categories_and_the_four_conditions() -> None:
    paths = [c.path for c in data().categories]
    assert len(paths) == len(set(paths))
    assert "Electronics > Computers" in paths and data().free_category == "Free Stuff"
    assert data().conditions == ["New", "Used - Like New", "Used - Good", "Used - Fair"]
    assert pick_category("electronics >  computers") == "Electronics > Computers"
    assert pick_category("Electronics > Spaceships") == "Electronics"
    assert pick_category("Gadgets") == ""
    assert pick_condition("used - good") == "Used - Good" and pick_condition("Mint") == ""


def test_contact_details_are_found_and_taken_out_but_specs_are_not() -> None:
    assert personal_details("pick up at 12 Oak Street") == ["a street address"]
    assert personal_details("Apt 4B, ring twice") == ["a street address"]
    assert personal_details("mail me: someone@example.com") == ["an email address"]
    assert personal_details("call (212) 555-0147") == ["a phone number"]
    for spec in ("1 TB drive", "2 way speaker", "1280 x 1024 at 60 Hz", "19.5 V 3.33 A"):
        assert personal_details(spec) == [], spec
    text, found = strip_personal("Text 212-555-0147 or come to 450 W Elm Avenue")
    assert "555" not in text and "Elm" not in text and len(found) == 2


# --- Listing details ------------------------------------------------------------------------


def test_tell_us_more_refuses_a_street_address_and_contact_details() -> None:
    assert details(area="11105").area == "11105"
    assert details(area="  Upper  West Side ").area == "Upper West Side"
    for area in ("31-17 Ditmars Blvd", "12 Oak Street", "Apt 4B"):
        with pytest.raises(ValidationError, match="not a street address"):
            details(area=area)
    with pytest.raises(ValidationError, match="leave out a phone number"):
        details(availability="text 212-555-0147")
    with pytest.raises(ValidationError, match="leave out an email address"):
        details(faults="ask me at someone@example.com")
    with pytest.raises(ValidationError, match="lowest price is above"):
        details(asking_price=20, lowest_price=25)
    assert details(included=["stand", "stand", "box"]).included == ["stand", "box"]
    with pytest.raises(ValidationError):
        details(included=["a spare kidney"])


def test_the_lowest_price_and_the_reason_never_reach_the_brief(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.get(monitor(inventory))
    text = brief(item, {"screen_size": "18 in"}, DraftRequest(mode="sell"), details(), photos=2)
    assert "27.5" not in text and "Denver" not in text and "lowest" not in text.lower()
    assert "35" not in text  # the rules set the price; the model does not write one
    assert "condition_words (the owner's words): Works well; one stuck pixel" in text
    assert "Photos: 2, numbered 1 to 2" in text
    assert "Electronics > Computers" in text and "Used - Fair" in text
    assert "stand, power cord, VGA cable" in text


def test_the_price_is_the_asking_price_else_the_guidance_figure_named() -> None:
    sell = DraftRequest(mode="sell")
    assert price_for(sell, details(), None) == ("35", "your asking price")
    assert price_for(DraftRequest(mode="give"), details(), None) == ("0", "free")
    guidance = {
        "version": 2,
        "content": {
            "currency": "USD",
            "weak": False,
            "strategies": [{"name": "typical", "price": 31.6}, {"name": "patient", "price": 50}],
        },
    }
    price, basis = price_for(sell, details(asking_price=None), guidance)
    assert price == "32" and "price guidance v2" in basis and "$32" in basis
    assert price_for(sell, None, None)[0] == ""


# --- the draft ---------------------------------------------------------------------------


@pytest.fixture
def lister(recorded_settings: Settings) -> Lister:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    return Lister(recorded_settings, client, inventory)


async def test_a_draft_from_the_recorded_answer_is_in_marketplace_shape(lister: Lister) -> None:
    item_id = monitor(lister.inventory)
    lister.inventory.add_sell_details(item_id, details().model_dump_json())
    draft = await lister.draft(item_id, DraftRequest(mode="sell"))
    assert draft.from_fixture is True and draft.details_version == 1
    assert (draft.price, draft.price_basis) == ("35", "your asking price")
    assert draft.category == "Electronics > Computers" and draft.condition == "Used - Good"
    assert len(draft.title) <= 100 and len(draft.tags) <= 20
    text = draft.description
    assert "Known faults: one stuck pixel" in text
    assert "Not tested: the DVI input" in text
    assert "Included: stand, power cord, VGA cable" in text
    assert "Local pickup in Astoria." in text and "Available: weekday evenings" in text
    assert "27.5" not in text and "Denver" not in text
    assert draft.pickup == "Local pickup in Astoria."


async def test_a_give_away_is_free_under_free_stuff_with_pickup_wording(lister: Lister) -> None:
    item_id = monitor(lister.inventory)
    lister.inventory.add_sell_details(item_id, details(data="wiped").model_dump_json())
    draft = await lister.draft(item_id, DraftRequest(mode="give"))
    assert (draft.price, draft.category) == ("0", "Free Stuff")
    assert draft.title.startswith("Free: ")
    assert draft.description.endswith("Free. Local pickup in Astoria.\nAvailable: weekday evenings")
    assert "Data: signed out of every account and wiped." in draft.description
    assert any("Electronics > Computers fits" in w for w in draft.warnings)
    assert draft.holds_data is True and any(s.group == "data" for s in draft.checklist)


async def test_the_draft_is_checked_against_the_data_file_and_scrubbed(
    live_settings: Settings,
) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.update(body)
        writing = {
            "title": "DELL 1800FP 18 in LCD monitor " + "x" * 120,
            "category": "Gadgets",
            "condition": "New",
            "description": "Clean screen. Call 212-555-0147 or see me at 12 Oak Street.",
            "uses": [],
            "tags": [f"tag {n}" for n in range(30)] + ["Tag 1"],
            "facts": [],
            "photo_order": [{"photo": 1, "reason": "front"}, {"photo": 1, "reason": "again"}],
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
    item_id = monitor(lister.inventory)
    lister.photos.add(item_id, [exif_photo(), exif_photo()])
    lister.inventory.add_sell_details(item_id, details().model_dump_json())
    draft = await lister.draft(item_id, DraftRequest(mode="sell"))
    # one call, effort low, the photos attached and labeled
    assert sent["reasoning"]["effort"] == "low" and sent["text"]["format"]["name"] == "DraftWriting"
    parts = sent["input"][0]["content"]
    assert [p["type"] for p in parts] == ["input_text"] + ["input_text", "input_image"] * 2
    assert parts[1]["text"] == "Photo 1"
    assert len(draft.title) == 100
    assert draft.category == "" and any("not in the Marketplace list" in w for w in draft.warnings)
    assert draft.condition == "Used - Like New"
    assert any("the owner did not" in w for w in draft.warnings)
    assert "555" not in draft.description and "Oak" not in draft.description
    assert any("took out a phone number, a street address" in w for w in draft.warnings)
    assert len(draft.tags) == 20 and draft.tags.count("tag 1") == 1
    assert [p.photo for p in draft.photos] == [1, 2]
    assert draft.photos[1].reason.startswith("not placed by the draft")


# --- routes ------------------------------------------------------------------------------


def test_sell_details_routes_keep_versions(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "LCD monitor"}).json()["id"]
    assert client.get(f"/api/items/{item_id}/sell-details").json() is None
    body = details().model_dump()
    saved = client.put(f"/api/items/{item_id}/sell-details", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1 and saved.json()["details"]["lowest_price"] == LOWEST
    body["asking_price"] = 30
    assert client.put(f"/api/items/{item_id}/sell-details", json=body).json()["version"] == 2
    assert client.get(f"/api/items/{item_id}/sell-details").json()["details"]["asking_price"] == 30
    body["area"] = "12 Oak Street"
    assert client.put(f"/api/items/{item_id}/sell-details", json=body).status_code == 422
    assert client.put("/api/items/999/sell-details", json=details().model_dump()).status_code == 404
    events = [e["change"] for e in client.get(f"/api/items/{item_id}/events").json()]
    assert "listing details saved (v2)" in events
    us = client.get("/api/marketplace/us").json()
    assert us["free_category"] == "Free Stuff" and len(us["conditions"]) == 4


def test_the_zip_has_the_chosen_photos_in_order_and_no_metadata(
    recorded_client: TestClient,
) -> None:
    c = recorded_client
    item_id = c.post("/api/items", json={"item_type": "LCD monitor", "name": "DELL"}).json()["id"]
    sent = [("uploads", (f"{n}.jpg", exif_photo(), "image/jpeg")) for n in (1, 2)]
    assert c.post(f"/api/items/{item_id}/photos", files=sent).status_code == 201
    draft = c.post(f"/api/items/{item_id}/drafts", json={"mode": "sell"}).json()
    # the recorded order is 2, 1 and a photo 9 the item does not have
    assert [p["photo"] for p in draft["photos"]] == [2, 1]
    res = c.get(f"/api/drafts/{draft['id']}/photos.zip")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    assert f"item-{item_id}-photos.zip" in res.headers["content-disposition"]
    archive = zipfile.ZipFile(BytesIO(res.content))
    assert archive.namelist() == ["01-photo-2.jpg", "02-photo-1.jpg"]
    for name, n in (("01-photo-2.jpg", 2), ("02-photo-1.jpg", 1)):
        jpeg = archive.read(name)
        assert jpeg == c.get(f"/api/items/{item_id}/photos/{n}").content
        assert b"Exif" not in jpeg and b"SampleCam" not in jpeg
        assert not Image.open(BytesIO(jpeg)).getexif()
        assert archive.getinfo(name).date_time == (1980, 1, 1, 0, 0, 0)
    assert c.get("/api/drafts/999/photos.zip").status_code == 404


def test_listed_sold_and_given_are_recorded(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "LCD monitor"}).json()["id"]
    base = f"/api/items/{item_id}/marketplace"
    assert client.get(base).json() == {"item_id": item_id, "state": "", "events": []}
    bad = client.post(f"{base}/listed", json={"price": 35, "url": "https://example.com/x"})
    assert bad.status_code == 422
    url = "https://www.facebook.com/marketplace/item/1234567890/"
    listed = client.post(f"{base}/listed", json={"price": 35, "url": url, "on": "2026-10-01"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["state"] == "listed" and listed.json()["events"][0]["url"] == url
    assert client.post(f"{base}/sold", json={"price": 30, "on": "2999-01-01"}).status_code == 422
    sold = client.post(f"{base}/sold", json={"price": 30, "on": "2026-10-20"})
    assert sold.json()["state"] == "sold" and [e["kind"] for e in sold.json()["events"]] == [
        "listed",
        "sold",
    ]
    # the final price is a recorded sale for price guidance, and the item is gone
    reports = client.get(f"/api/items/{item_id}/price/reports").json()
    assert [(r["price"], r["sold_on"], r["note"]) for r in reports] == [
        (30.0, "2026-10-20", "Facebook Marketplace")
    ]
    assert client.get(f"/api/items/{item_id}").json()["availability"] == "gone"
    changes = [e["change"] for e in client.get(f"/api/items/{item_id}/events").json()]
    assert "listed on Facebook Marketplace at $35 on 2026-10-01" in changes
    assert "sold on Facebook Marketplace for $30 on 2026-10-20" in changes

    other = client.post("/api/items", json={"item_type": "kettle"}).json()["id"]
    given = client.post(f"/api/items/{other}/marketplace/given", json={})
    assert given.status_code == 200 and given.json()["state"] == "given"
    assert client.get(f"/api/items/{other}").json()["availability"] == "gone"
    assert client.post("/api/items/999/marketplace/given", json={}).status_code == 404


def test_the_draft_spends_and_the_rest_needs_the_code(tmp_path: Path) -> None:
    assert expensive("POST", "/api/items/3/drafts")
    for method, path in (
        ("PUT", "/api/items/3/sell-details"),
        ("GET", "/api/items/3/sell-details"),
        ("GET", "/api/drafts/3/photos.zip"),
        ("POST", "/api/items/3/marketplace/sold"),
    ):
        assert not expensive(method, path) and not demo_allowed(method, path), path
    with TestClient(create_app(gated_settings(tmp_path))) as gated:
        gated.post("/api/access", json={"code": CODE})
        item_id = gated.post("/api/items", json={"item_type": "LCD monitor"}).json()["id"]
        gated.cookies.clear()
        assert gated.put(f"/api/items/{item_id}/sell-details", json={}).status_code == 403
        assert gated.post(f"/api/items/{item_id}/drafts", json={}).status_code == 403
        assert gated.get(f"/api/items/{item_id}/marketplace").status_code == 403


def test_marketplace_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/marketplace/us",
        "/api/items/{item_id}/sell-details",
        "/api/drafts/{draft_id}/photos.zip",
        "/api/items/{item_id}/marketplace/listed",
        "/api/items/{item_id}/marketplace/sold",
        "/api/items/{item_id}/marketplace/given",
    ):
        assert path in paths, path
