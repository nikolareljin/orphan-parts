"""A picture of what an item could become: off unless enabled, drawn by Muse Image on a click
from the recorded stub, kept beside the photos and never counted as one, charged in the
ledger, shown but never drawn for the demo visitor, gone with the item."""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory import FieldCreate, Inventory, ItemCreate
from app.inventory.schema import Assertion, Review
from app.inventory.service import NotFoundError
from app.main import create_app
from app.model_api import CostLedger, ModelApiClient
from app.ops.door import live_request
from app.ops.gate import DEMO_LINE
from app.picture import OFF_LINE, Pictures, PicturesOffError, prompt_for
from app.projects import Templates
from tests.conftest import RECORDED_FIXTURES, make_photo
from tests.test_gate import CODE, gated_settings

pytestmark = pytest.mark.anyio


def create(client: TestClient, **spec: Any) -> int:
    res = client.post("/api/items", json=spec)
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


@pytest.fixture
def drawing_settings(tmp_path: Path) -> Settings:
    """Pictures on, answered from the committed stub."""
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        picture_enabled=True,
        log_format="text",
        _env_file=None,
    )


@pytest.fixture
def drawing(drawing_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(drawing_settings)) as c:
        yield c


def test_pictures_are_off_unless_enabled(client: TestClient) -> None:
    item_id = create(client, item_type="laptop")
    assert client.get("/api/version").json()["pictures"] is False
    listed = client.get(f"/api/items/{item_id}/pictures")
    assert listed.status_code == 200 and listed.json() == {"enabled": False, "pictures": []}
    refused = client.post(f"/api/items/{item_id}/picture", json={"use": "smart mirror"})
    assert refused.status_code == 503
    assert refused.json()["detail"] == OFF_LINE
    assert client.get("/api/spend").json()["calls"] == 0


def test_a_picture_is_drawn_kept_served_and_charged(
    drawing: TestClient, drawing_settings: Settings
) -> None:
    assert drawing.get("/api/version").json()["pictures"] is True
    item_id = create(drawing, item_type="laptop", condition="scuffed lid")
    drawing.post(
        f"/api/items/{item_id}/photos", files=[("uploads", ("a.jpg", make_photo(), "image/jpeg"))]
    )
    drawn = drawing.post(f"/api/items/{item_id}/picture", json={"use": "smart_mirror"})
    assert drawn.status_code == 201, drawn.text
    picture = drawn.json()
    assert picture["n"] == 1
    assert picture["use"] == "Smart mirror"  # the template id names its project
    assert picture["model"] == drawing_settings.model_image
    assert picture["from_fixture"] is True and picture["cost_usd"] == 0.0
    assert picture["created_at"].endswith("+00:00")
    # listed, served as a JPEG that is never cached, and not a photo of the item
    listed = drawing.get(f"/api/items/{item_id}/pictures").json()
    assert listed["enabled"] is True and [p["n"] for p in listed["pictures"]] == [1]
    served = drawing.get(f"/api/items/{item_id}/pictures/1")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.headers["cache-control"] == "no-store"
    assert served.content[:2] == b"\xff\xd8"
    assert drawing.get(f"/api/items/{item_id}/pictures/2").status_code == 404
    assert drawing.get(f"/api/items/{item_id}/photos").json() == {"count": 1}
    folder = drawing_settings.data_dir / "items" / str(item_id)
    assert sorted(p.name for p in folder.iterdir()) == [
        "photo-1.jpg",
        "picture-1.jpg",
        "picture-1.json",
    ]
    # one ledger line under Muse Image, a stub answer at no cost
    spend = drawing.get("/api/spend").json()
    assert spend["calls"] == 1 and spend["fixture_calls"] == 1
    assert spend["by_model"][drawing_settings.model_image]["calls"] == 1
    # a second one is numbered past the first, in the owner's own words
    again = drawing.post(f"/api/items/{item_id}/picture", json={"use": "a bedside lamp"})
    assert again.status_code == 201 and again.json()["n"] == 2
    assert again.json()["use"] == "a bedside lamp"
    assert [p["n"] for p in drawing.get(f"/api/items/{item_id}/pictures").json()["pictures"]] == [
        1,
        2,
    ]


def test_the_pictures_go_with_the_item(drawing: TestClient, drawing_settings: Settings) -> None:
    item_id = create(drawing, item_type="laptop")
    assert drawing.post(f"/api/items/{item_id}/picture", json={}).status_code == 201
    folder = drawing_settings.data_dir / "items" / str(item_id)
    assert (folder / "picture-1.jpg").is_file()
    assert drawing.delete(f"/api/items/{item_id}").status_code == 204
    assert not folder.exists()
    assert drawing.get(f"/api/items/{item_id}/pictures").status_code == 404
    assert drawing.get(f"/api/items/{item_id}/pictures/1").status_code == 404
    assert drawing.post(f"/api/items/{item_id}/picture", json={}).status_code == 404
    assert drawing.post("/api/items/999/picture", json={}).status_code == 404


def test_the_demo_visitor_sees_public_pictures_and_only_the_code_draws(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES, picture_enabled=True)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        item_id = create(c, item_type="laptop")
        c.post(f"/api/items/{item_id}/public", json={"public": True})
        assert c.post(f"/api/items/{item_id}/picture", json={}).status_code == 201
        assert c.get("/readyz").json()["demo"]["daily_used"] == 1  # a call that spends
        c.cookies.clear()
        refused = c.post(f"/api/items/{item_id}/picture", json={"use": "lamp"})
        assert refused.status_code == 403 and refused.json()["detail"] == DEMO_LINE
        # what was drawn for a public item is shown; a private item stays out of sight
        listed = c.get(f"/api/items/{item_id}/pictures")
        assert listed.status_code == 200 and [p["n"] for p in listed.json()["pictures"]] == [1]
        served = c.get(f"/api/items/{item_id}/pictures/1")
        assert served.status_code == 200 and served.content[:3] == b"\xff\xd8\xff"
        c.post("/api/access", json={"code": CODE})
        hidden = create(c, item_type="phone")
        assert c.post(f"/api/items/{hidden}/picture", json={}).status_code == 201
        c.cookies.clear()
        assert c.get(f"/api/items/{hidden}/pictures").status_code == 404
        assert c.get(f"/api/items/{hidden}/pictures/1").status_code == 404
        assert c.post(f"/api/items/{hidden}/picture", json={}).status_code == 403


def test_the_prompt_rests_on_what_is_known(drawing_settings: Settings) -> None:
    inventory = Inventory(drawing_settings)
    item = inventory.create(
        ItemCreate(item_type="laptop", condition="scuffed lid", faults="dead battery")
    )
    item = inventory.add_field(
        item.id, FieldCreate(field="screen_size", value="14", unit="in", provenance="tested")
    )
    prompt = prompt_for(item, "a smart mirror")
    assert prompt.startswith("a semi-realistic illustration of a smart mirror built from laptop")
    assert "screen size 14 in" in prompt
    assert "condition: scuffed lid" in prompt and "known faults: dead battery" in prompt
    assert prompt.endswith("on a plain background, no text, no logos, no people")
    # the item as itself, and nothing from a value still to confirm
    assert "cleaned up and ready to use" in prompt_for(item, "Laptop")
    assert "cleaned up" in prompt_for(item, "")


async def test_the_service_refuses_without_the_switch(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.create(ItemCreate(item_type="laptop"))
    client = ModelApiClient(settings, CostLedger(cap_usd=25.0))
    pictures = Pictures(settings, client, inventory, Templates())
    with pytest.raises(PicturesOffError, match="PICTURE_ENABLED"):
        await pictures.draw(item.id, None)
    assert pictures.list(item.id).enabled is False
    await client.aclose()


async def test_the_demo_door_draws_from_the_stub(live_settings: Settings) -> None:
    """The gate refuses the demo visitor a picture; should a call come through that door all
    the same, the twin answers from the recordings and the key is never used."""

    def never(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the key must not be used through the demo door")

    client = ModelApiClient(live_settings, CostLedger(25.0), transport=httpx.MockTransport(never))
    twin_ledger = CostLedger(25.0)
    client.twin = ModelApiClient(
        live_settings.model_copy(update={"fake_api": True, "fixtures_dir": RECORDED_FIXTURES}),
        twin_ledger,
    )
    token = live_request.set(False)
    try:
        result = await client.picture("a lamp")
    finally:
        live_request.reset(token)
    assert result.from_fixture is True and result.cost_usd == 0.0
    assert result.data[:2] == b"\xff\xd8"
    assert twin_ledger.summary().calls == 1
    await client.aclose()


def test_the_prompt_never_carries_a_private_value(drawing_settings: Settings) -> None:
    """Private values stay home, and the values sent are picked after the filter, so accepted
    ones listed after many proposed still go."""
    item = Inventory(drawing_settings).create(ItemCreate(item_type="laptop"))

    def value(key: str, text: str, review: Review) -> Assertion:
        return Assertion(
            id=0,
            field=key,
            value=text,
            provenance="observed" if review == "proposed" else "tested",
            confidence=1.0,
            source="photo" if review == "proposed" else "user_edit",
            review=review,
            at="2026-10-30T00:00:00+00:00",
        )

    fields = {f"guess_{i}": value(f"guess_{i}", str(i), "proposed") for i in range(10)}
    fields["serial_number"] = value("serial_number", "SN-PRIVATE-1", "accepted")
    fields["mac_address"] = value("mac_address", "00:11:22:33:44:55", "accepted")
    fields["weight"] = value("weight", "1.4 kg", "accepted")
    prompt = prompt_for(item.model_copy(update={"fields": fields}), "a lamp")
    assert "SN-PRIVATE-1" not in prompt and "serial" not in prompt
    assert "00:11:22" not in prompt and "mac" not in prompt
    assert "guess" not in prompt
    assert "weight 1.4 kg" in prompt


async def test_two_draws_at_once_keep_both(drawing_settings: Settings) -> None:
    inventory = Inventory(drawing_settings)
    item = inventory.create(ItemCreate(item_type="laptop"))
    client = ModelApiClient(drawing_settings, CostLedger(cap_usd=25.0))
    pictures = Pictures(drawing_settings, client, inventory, Templates())
    drawn = await asyncio.gather(*(pictures.draw(item.id, use) for use in ("lamp", "mirror")))
    assert sorted(p.n for p in drawn) == [1, 2]
    assert {p.use for p in pictures.list(item.id).pictures} == {"lamp", "mirror"}
    await client.aclose()


async def test_a_picture_for_an_item_deleted_meanwhile_is_not_kept(
    drawing_settings: Settings,
) -> None:
    inventory = Inventory(drawing_settings)
    item = inventory.create(ItemCreate(item_type="laptop"))
    client = ModelApiClient(drawing_settings, CostLedger(cap_usd=25.0))
    pictures = Pictures(drawing_settings, client, inventory, Templates())
    drawn = client.picture

    async def delete_while_drawing(prompt: str, *, op: str = "picture") -> Any:
        result = await drawn(prompt, op=op)
        inventory.delete(item.id)
        return result

    client.picture = delete_while_drawing  # type: ignore[method-assign]
    with pytest.raises(NotFoundError):
        await pictures.draw(item.id, "lamp")
    assert not pictures.folder(item.id).exists()
    await client.aclose()


async def test_an_item_with_no_type_or_name_is_drawn_as_an_item(
    drawing_settings: Settings,
) -> None:
    inventory = Inventory(drawing_settings)
    item = inventory.create(ItemCreate())
    client = ModelApiClient(drawing_settings, CostLedger(cap_usd=25.0))
    pictures = Pictures(drawing_settings, client, inventory, Templates())
    picture = await pictures.draw(item.id, "")
    assert picture.use == "item"
    assert [p.name for p in pictures.folder(item.id).iterdir() if p.name.startswith(".")] == []
    await client.aclose()
