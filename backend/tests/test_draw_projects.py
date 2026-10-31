"""Draw it for a finished project: a reuse card or a Build project drawn by Muse Image only on a
click, from a prompt written by the rules that never carries an identifying or private value;
kept with the card or the project; refused to the demo visitor; 503 while pictures are off."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decide import ReuseScenario
from app.demo.service import reset
from app.inventory import FieldCreate, Inventory, ItemCreate
from app.main import create_app
from app.ops.gate import DEMO_LINE, demo_allowed, expensive
from app.picture import OFF_LINE, card_prompt, finished_prompt, part_of, project_prompt
from app.picture.service import PARTS_MAX, TAIL, TITLE_MAX
from tests.conftest import RECORDED_FIXTURES
from tests.test_decide import _scenarios
from tests.test_gate import CODE, gated_settings


@pytest.fixture
def drawing_settings(tmp_path: Path) -> Settings:
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


def image_calls(client: TestClient, settings: Settings) -> int:
    by_model: dict[str, Any] = client.get("/api/spend").json()["by_model"]
    return int(by_model.get(settings.model_image, {}).get("calls", 0))


def household(client: TestClient) -> dict[str, int]:
    ids = {}
    for item_type, name in (
        ("laptop", "Old laptop"),
        ("monitor", "Spare monitor"),
        ("vacuum", "Upright vacuum"),
    ):
        res = client.post("/api/items", json={"item_type": item_type, "name": name})
        assert res.status_code == 201, res.text
        ids[name] = int(res.json()["id"])
    return ids


def private_laptop(inventory: Inventory) -> int:
    item = inventory.create(
        ItemCreate(
            item_type="laptop",
            name="Nik's work laptop",
            location="kitchen drawer",
            notes="password on a sticker",
        )
    )
    for key, value, unit in (
        ("screen_size", "14", "in"),
        ("serial_number", "SN-PRIVATE-1", ""),
        ("mac_address", "00:11:22:33:44:55", ""),
        ("imei", "IMEI-PRIVATE-7", ""),
        ("purchase_price", "899", "USD"),
    ):
        inventory.add_field(
            item.id, FieldCreate(field=key, value=value, unit=unit, provenance="tested")
        )
    return item.id


PRIVATE = (
    "SN-PRIVATE-1",
    "serial",
    "00:11:22",
    "mac",
    "IMEI-PRIVATE-7",
    "imei",
    "899",
    "price",
    "Nik",
    "kitchen drawer",
    "password",
)


# --- the prompt ---------------------------------------------------------------------------


def test_the_card_prompt_names_the_project_its_parts_and_one_line(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.get(private_laptop(inventory))
    scenarios = _scenarios()
    scenarios.reuse = [
        ReuseScenario(
            title="Kitchen recipe display",
            what_it_does="shows recipes on the wall",
            with_items=["monitor", "keyboard"],
            difficulty="easy",
            why="",
            extra_parts=["wall mount, 20 USD"],
            cost="20 USD",
            time="an afternoon",
        )
    ]
    prompt = card_prompt(scenarios, 0, item)
    assert prompt == (
        "a semi-realistic illustration of Kitchen recipe display built from laptop (screen size"
        " 14 in), monitor, keyboard; shows recipes on the wall, " + TAIL
    )
    for value in PRIVATE:
        assert value not in prompt
    # the card's cost and parts are not in it either
    assert "20 USD" not in prompt and "wall mount" not in prompt


def test_the_project_prompt_uses_only_the_allocated_items(settings: Settings) -> None:
    from app.projects.schema import Allocation, Project

    inventory = Inventory(settings)
    laptop = inventory.get(private_laptop(inventory))
    monitor = inventory.create(ItemCreate(item_type="monitor", name="Spare monitor"))
    project = Project.model_validate(
        {
            "id": 1,
            "template": "homework_workstation",
            "title": "Homework workstation",
            "status": "proposed",
            "version": 1,
            "result": "a desk set-up for homework",
            "requirements": [],
            "allocations": [
                Allocation(
                    item_id=laptop.id, item_name="", requirement="computer", committed=False, why=""
                ).model_dump()
            ],
            "effort": "low",
            "skills": [],
            "spend_estimate": 45.0,
            "currency": "USD",
            "unknowns": [],
            "sources": [],
            "steps": [],
            "safety": [],
            "dropped": [],
            "model": "muse-spark",
            "from_fixture": True,
            "cost_usd": 0.0,
            "created_at": "t",
            "updated_at": "t",
        }
    )
    prompt = project_prompt(project, [laptop])
    assert prompt.startswith(
        "a semi-realistic illustration of Homework workstation built from laptop"
        " (screen size 14 in)"
    )
    assert "; a desk set-up for homework, " in prompt and prompt.endswith(TAIL)
    assert "monitor" not in prompt and monitor.item_type == "monitor"
    for value in (*PRIVATE, "45"):
        assert value not in prompt


def test_the_prompt_is_capped() -> None:
    prompt = finished_prompt("t" * 500, [f"part {n}" for n in range(20)], "w" * 900)
    assert "t" * TITLE_MAX in prompt and "t" * (TITLE_MAX + 1) not in prompt
    assert f"part {PARTS_MAX - 1}" in prompt and f"part {PARTS_MAX}," not in prompt
    assert "w" * 201 not in prompt
    assert len(prompt) < 1200
    # no title and no parts still says what it is, and repeats are named once
    assert finished_prompt("", ["Lamp", "lamp"], "").startswith(
        "a semi-realistic illustration of a reused project built from Lamp, " + TAIL
    )


def test_a_part_is_its_kind_and_a_few_safe_values(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.get(private_laptop(inventory))
    assert part_of(item) == "laptop (screen size 14 in)"
    assert part_of(inventory.create(ItemCreate(name="mystery box"))) == "item"


# --- on demand ----------------------------------------------------------------------------


def test_proposing_writing_and_deciding_draw_nothing(
    drawing: TestClient, drawing_settings: Settings
) -> None:
    ids = household(drawing)
    laptop = ids["Old laptop"]
    assert drawing.post("/api/projects/propose", json={"count": 3}).status_code == 201
    projects = drawing.get("/api/projects").json()["projects"]
    for p in projects:
        assert drawing.get(f"/api/projects/{p['id']}").status_code == 200
        listed = drawing.get(f"/api/projects/{p['id']}/pictures").json()
        assert listed == {"enabled": True, "pictures": []}
    found = drawing.post(f"/api/items/{laptop}/scenarios").json()
    drawing.get(f"/api/items/{laptop}/decide")
    for k in range(len(found["reuse"])):
        listed = drawing.get(f"/api/items/{laptop}/scenarios/{found['id']}/reuse/{k}/pictures")
        assert listed.json() == {"enabled": True, "pictures": []}
    assert drawing.post(f"/api/items/{laptop}/decision", json={"choice": "keep_build"}).is_success
    assert image_calls(drawing, drawing_settings) == 0
    assert not (drawing_settings.data_dir / "projects").exists()


def test_a_reuse_card_is_drawn_once_per_click_and_kept_with_the_card(
    drawing: TestClient, drawing_settings: Settings
) -> None:
    laptop = household(drawing)["Old laptop"]
    found = drawing.post(f"/api/items/{laptop}/scenarios").json()
    base = f"/api/items/{laptop}/scenarios/{found['id']}/reuse/0"
    drawn = drawing.post(f"{base}/picture")
    assert drawn.status_code == 201, drawn.text
    picture = drawn.json()
    assert picture["n"] == 1 and picture["use"] == found["reuse"][0]["title"]
    assert picture["from_fixture"] is True and picture["cost_usd"] == 0.0
    assert image_calls(drawing, drawing_settings) == 1
    assert [p["n"] for p in drawing.get(f"{base}/pictures").json()["pictures"]] == [1]
    served = drawing.get(f"{base}/pictures/1")
    assert served.status_code == 200 and served.content[:3] == b"\xff\xd8\xff"
    assert served.headers["cache-control"] == "no-store"
    assert drawing.get(f"{base}/pictures/2").status_code == 404
    # the other cards have none, and the item's own pictures and photos are untouched
    assert (
        drawing.get(f"/api/items/{laptop}/scenarios/{found['id']}/reuse/1/pictures").json()[
            "pictures"
        ]
        == []
    )
    assert drawing.get(f"/api/items/{laptop}/pictures").json()["pictures"] == []
    assert drawing.get(f"/api/items/{laptop}/photos").json() == {"count": 0}
    # a card that is not there, scenarios of another item, an item that is not there
    assert (
        drawing.post(f"/api/items/{laptop}/scenarios/{found['id']}/reuse/9/picture").status_code
        == 404
    )
    other = household(drawing)["Old laptop"]
    assert (
        drawing.post(f"/api/items/{other}/scenarios/{found['id']}/reuse/0/picture").status_code
        == 404
    )
    assert (
        drawing.get(f"/api/items/999/scenarios/{found['id']}/reuse/0/pictures").status_code == 404
    )
    assert image_calls(drawing, drawing_settings) == 1
    # a second click is a second call
    assert drawing.post(f"{base}/picture").json()["n"] == 2
    assert image_calls(drawing, drawing_settings) == 2
    # gone with the item
    folder = drawing_settings.data_dir / "items" / str(laptop)
    assert (folder / f"scenarios-{found['id']}-reuse-0" / "picture-1.jpg").is_file()
    assert drawing.delete(f"/api/items/{laptop}").status_code == 204
    assert not folder.exists()
    assert drawing.get(f"{base}/pictures").status_code == 404


def test_a_project_is_drawn_once_per_click_and_kept_with_the_project(
    drawing: TestClient, drawing_settings: Settings
) -> None:
    household(drawing)
    desk = drawing.post("/api/projects/propose", json={"count": 3}).json()[0]
    drawn = drawing.post(f"/api/projects/{desk['id']}/picture")
    assert drawn.status_code == 201, drawn.text
    assert drawn.json()["n"] == 1 and drawn.json()["use"] == desk["title"]
    assert image_calls(drawing, drawing_settings) == 1
    listed = drawing.get(f"/api/projects/{desk['id']}/pictures").json()
    assert listed["enabled"] is True and [p["n"] for p in listed["pictures"]] == [1]
    served = drawing.get(f"/api/projects/{desk['id']}/pictures/1")
    assert served.status_code == 200 and served.content[:3] == b"\xff\xd8\xff"
    assert drawing.get(f"/api/projects/{desk['id']}/pictures/2").status_code == 404
    assert drawing.post("/api/projects/999/picture").status_code == 404
    assert drawing.get("/api/projects/999/pictures").status_code == 404
    assert image_calls(drawing, drawing_settings) == 1
    folder = drawing_settings.data_dir / "projects" / str(desk["id"])
    assert sorted(p.name for p in folder.iterdir()) == ["picture-1.jpg", "picture-1.json"]
    # starting the inventory over takes the project pictures with it
    assert "projects/" in reset(drawing_settings)
    assert not folder.exists()


# --- the gate and the switch --------------------------------------------------------------


def test_pictures_off_is_a_503_and_nothing_is_called(
    client: TestClient, settings: Settings
) -> None:
    laptop = household(client)["Old laptop"]
    # off is said before anything is looked up, so no project or card is needed for it
    refused = client.post("/api/projects/1/picture")
    assert refused.status_code == 503 and refused.json()["detail"] == OFF_LINE
    refused = client.post(f"/api/items/{laptop}/scenarios/1/reuse/0/picture")
    assert refused.status_code == 503 and refused.json()["detail"] == OFF_LINE
    assert image_calls(client, settings) == 0


def test_the_switch_off_lists_as_off(tmp_path: Path) -> None:
    settings = Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        log_format="text",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as c:
        laptop = household(c)["Old laptop"]
        desk = c.post("/api/projects/propose", json={"count": 3}).json()[0]
        assert c.get(f"/api/projects/{desk['id']}/pictures").json() == {
            "enabled": False,
            "pictures": [],
        }
        assert c.post(f"/api/projects/{desk['id']}/picture").status_code == 503
        found = c.post(f"/api/items/{laptop}/scenarios").json()
        base = f"/api/items/{laptop}/scenarios/{found['id']}/reuse/0"
        assert c.get(f"{base}/pictures").json()["enabled"] is False
        assert c.post(f"{base}/picture").status_code == 503
        assert image_calls(c, settings) == 0


def test_only_the_code_draws_a_project_or_a_card(tmp_path: Path) -> None:
    for path in ("/api/projects/3/picture", "/api/items/2/scenarios/5/reuse/1/picture"):
        assert expensive("POST", path)
        assert not demo_allowed("POST", path)
    for path in ("/api/projects/3/pictures/1", "/api/items/2/scenarios/5/reuse/1/pictures"):
        assert not demo_allowed("GET", path)
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES, picture_enabled=True)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        laptop = household(c)["Old laptop"]
        c.post(f"/api/items/{laptop}/public", json={"public": True})
        desk = c.post("/api/projects/propose", json={"count": 3}).json()[0]
        found = c.post(f"/api/items/{laptop}/scenarios").json()
        base = f"/api/items/{laptop}/scenarios/{found['id']}/reuse/0"
        assert c.post(f"/api/projects/{desk['id']}/picture").status_code == 201
        assert c.post(f"{base}/picture").status_code == 201
        c.cookies.clear()
        for path in (f"/api/projects/{desk['id']}/picture", f"{base}/picture"):
            refused = c.post(path)
            assert refused.status_code == 403 and refused.json()["detail"] == DEMO_LINE
        # what was drawn is the owner's: the demo visitor does not read it
        assert c.get(f"/api/projects/{desk['id']}/pictures").status_code == 403
        assert c.get(f"{base}/pictures/1").status_code == 403


def test_the_draw_routes_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/projects/{project_id}/picture",
        "/api/projects/{project_id}/pictures",
        "/api/projects/{project_id}/pictures/{n}",
        "/api/items/{item_id}/scenarios/{scenarios_id}/reuse/{card}/picture",
        "/api/items/{item_id}/scenarios/{scenarios_id}/reuse/{card}/pictures",
        "/api/items/{item_id}/scenarios/{scenarios_id}/reuse/{card}/pictures/{n}",
    ):
        assert path in paths


# --- what the model wrote never carries a name -------------------------------------------


def test_an_item_name_the_model_repeated_is_said_as_its_kind(settings: Settings) -> None:
    from app.projects.schema import Project

    inventory = Inventory(settings)
    laptop = inventory.get(private_laptop(inventory))
    scenarios = _scenarios()
    scenarios.reuse = [
        ReuseScenario(
            title="NIK'S  work LAPTOP as a recipe display",
            what_it_does="mount nik's work laptop on the wall",
            with_items=["monitor"],
            difficulty="easy",
            why="",
            extra_parts=[],
            cost="",
            time="",
        )
    ]
    prompt = card_prompt(scenarios, 0, laptop)
    assert "nik" not in prompt.lower() and "work laptop" not in prompt.lower()
    assert prompt.startswith("a semi-realistic illustration of laptop as a recipe display")
    assert "; mount laptop on the wall, " in prompt

    project = Project.model_validate(
        {
            **_project_fields(),
            "title": "Desk from Nik's work laptop and Grandma's TV",
            "result": "Nik's work laptop drives Grandma's TV",
            "allocations": [
                {
                    "item_id": laptop.id,
                    "item_name": laptop.name,
                    "requirement": "computer",
                    "committed": False,
                    "why": "",
                },
                {
                    "item_id": 99,
                    "item_name": "Grandma's TV",
                    "requirement": "screen",
                    "committed": False,
                    "why": "",
                },
            ],
        }
    )
    prompt = project_prompt(project, [laptop], [("Spare monitor", "monitor")])
    assert "Nik" not in prompt and "Grandma" not in prompt
    assert prompt.startswith("a semi-realistic illustration of Desk from laptop and item")


def _project_fields() -> dict[str, Any]:
    return {
        "id": 1,
        "template": "homework_workstation",
        "title": "",
        "status": "proposed",
        "version": 1,
        "result": "",
        "requirements": [],
        "allocations": [],
        "effort": "low",
        "skills": [],
        "spend_estimate": 0.0,
        "currency": "USD",
        "unknowns": [],
        "sources": [],
        "steps": [],
        "safety": [],
        "dropped": [],
        "model": "muse-spark",
        "from_fixture": True,
        "cost_usd": 0.0,
        "created_at": "t",
        "updated_at": "t",
    }


def test_money_and_device_ids_stay_out_of_a_part(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.create(ItemCreate(item_type="phone"))
    for key, value in (
        ("storage", "64 GB"),
        ("resale_value", "120"),
        ("est_worth", "130"),
        ("retail", "499"),
        ("service_tag", "7XK2Q1"),
        ("imsi", "IMSI-PRIVATE"),
        ("iccid", "ICCID-PRIVATE"),
        ("meid", "MEID-PRIVATE"),
    ):
        inventory.add_field(item.id, FieldCreate(field=key, value=value, provenance="tested"))
    part = part_of(inventory.get(item.id))
    assert part == "phone (storage 64 GB)"
