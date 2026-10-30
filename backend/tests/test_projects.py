import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extract import Extractor
from app.find import Finder
from app.inventory import Inventory
from app.inventory.schema import ItemCreate
from app.match import Assessor
from app.model_api import CostLedger, IncompleteResponseError, ModelApiClient
from app.profiles import Profiles
from app.projects import (
    AllocationConflictError,
    FillRequest,
    Planner,
    Preferences,
    ProjectsError,
    ProposeRequest,
    Templates,
    UnknownTemplateError,
    fits,
)
from tests.conftest import RECORDED_FIXTURES

pytestmark = pytest.mark.anyio


def test_the_shipped_templates_load_and_say_what_they_need() -> None:
    templates = Templates()
    assert templates.ids() == [
        "document_camera",
        "external_monitor_workaround",
        "home_music_setup",
        "homework_workstation",
        "vacuum_restored",
    ]
    vacuum = templates.get("vacuum_restored")
    assert [r.key for r in vacuum.requirements] == ["vacuum", "attachment"]
    assert (
        next(r for r in vacuum.requirements if r.key == "attachment").profile == "vacuum_attachment"
    )
    summary = next(s for s in templates.summaries() if s.id == "homework_workstation")
    assert summary.requirements[0].startswith("laptop:")
    with pytest.raises(UnknownTemplateError):
        templates.get("castle")


def test_template_files_are_checked(tmp_path: Path) -> None:
    def write(text: str) -> None:
        (tmp_path / "shed.yaml").write_text(text)

    base = (
        "id: shed\nlabel: Shed\ngoal: g\nresult: r\neffort: low\n"
        "typical_cost: {low: 0, high: 1}\nrequirements:\n"
    )
    write(base + "  - {key: a, label: A}\n  - {key: a, label: Again}\n")
    with pytest.raises(ValueError, match="repeats"):
        Templates(tmp_path)
    write(base + "  - {key: a, label: A, blocking: false}\n")
    with pytest.raises(ValueError, match="no blocking"):
        Templates(tmp_path)
    write(base.replace("id: shed", "id: barn") + "  - {key: a, label: A}\n")
    with pytest.raises(ValueError, match="file name must match"):
        Templates(tmp_path)
    write(base + "  - {key: a, label: A}\n")
    assert Templates(tmp_path).get("shed").typical_cost.high == 1


def test_fits_reads_the_kind_off_the_type_not_the_name(settings: Settings) -> None:
    inventory = Inventory(settings)
    laptop = inventory.create(ItemCreate(item_type="laptop", name="Old laptop"))
    cable = inventory.create(ItemCreate(item_type="HDMI cable", name="The long one"))
    toaster = inventory.create(ItemCreate(item_type="toaster", name="Laptop-sized toaster"))
    assert fits(["laptop", "notebook"], laptop) and not fits(["monitor"], laptop)
    assert fits(["hdmi"], cable) and fits([], cable)
    assert not fits(["laptop"], toaster)


@pytest.fixture
def planner(recorded_settings: Settings) -> Planner:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    profiles = Profiles()
    finder = Finder(
        recorded_settings,
        client,
        inventory,
        profiles,
        Extractor(recorded_settings, client),
        Assessor(profiles, inventory),
    )
    return Planner(recorded_settings, client, inventory, Templates(), finder)


def household(inventory: Inventory) -> dict[str, int]:
    ids: dict[str, int] = {}
    for item_type, name, intent in (
        ("laptop", "Old laptop", "keep"),
        ("monitor", "Spare monitor", "keep"),
        ("keyboard", "USB keyboard", "keep"),
        ("vacuum", "Upright vacuum", "build"),
        ("phone", "Cracked phone", "sell"),
    ):
        ids[name] = inventory.create(ItemCreate(item_type=item_type, name=name, intent=intent)).id  # type: ignore[arg-type]
    return ids


def test_preferences_are_kept_once_and_default_when_unset(planner: Planner) -> None:
    assert planner.preferences() == Preferences()
    saved = planner.set_preferences(
        Preferences(interests="a quiet desk", effort="low", skills=[" soldering ", ""], budget=50)
    )
    assert saved.skills == ["soldering"] and saved.budget == 50
    assert planner.preferences().interests == "a quiet desk"


def test_the_tools_show_only_what_a_build_may_use(planner: Planner) -> None:
    ids = household(planner.inventory)
    listed = json.loads(planner.tool("list_inventory", {}))
    assert {i["name"] for i in listed} == {
        "Old laptop",
        "Spare monitor",
        "USB keyboard",
        "Upright vacuum",
    }
    catalog = json.loads(planner.tool("template_catalog", {}))
    assert {t["id"] for t in catalog} == set(Templates().ids())
    details = json.loads(planner.tool("item_details", {"item_id": ids["Old laptop"]}))
    assert details["name"] == "Old laptop" and "components" in details
    assert json.loads(planner.tool("item_details", {"item_id": 999})) == {"error": "no such item"}
    assert "no tool" in json.loads(planner.tool("fly", {}))["error"]


async def test_proposals_keep_only_what_the_inventory_backs(planner: Planner) -> None:
    ids = household(planner.inventory)
    planner.set_preferences(Preferences(budget=100))
    projects = await planner.propose(ProposeRequest())
    # three proposed; the one built on an item nobody has is not shown
    assert [p.template for p in projects] == ["homework_workstation", "vacuum_restored"]
    desk = projects[0]
    assert desk.status == "proposed" and desk.from_fixture and desk.cost_usd == 0.0
    assert {a.item_name for a in desk.allocations} == {
        "Old laptop",
        "Spare monitor",
        "USB keyboard",
    }
    assert all(not a.committed for a in desk.allocations)
    by_key = {r.key: r for r in desk.requirements}
    assert by_key["laptop"].state == "pass" and by_key["laptop"].item_id == ids["Old laptop"]
    assert by_key["video_cable"].state == "unknown" and by_key["video_cable"].blocking
    assert by_key["mouse"].state == "unknown" and not by_key["mouse"].blocking
    assert desk.spend_estimate == 12 and desk.currency == "USD"
    assert desk.unknowns and desk.steps and desk.sources
    assert desk.dropped == []
    assert planner.inventory.get(ids["Old laptop"]).availability == "available"
    with pytest.raises(ProjectsError, match="on this project already"):
        planner.fill(desk.id, "video_cable", FillRequest(item_id=ids["Old laptop"]))
    events = [e.change for e in planner.inventory.events(ids["Old laptop"])]
    assert any(e.startswith("proposed for: Homework desk") for e in events)
    listing = planner.projects()
    assert listing.budget.budget == 100 and listing.budget.committed_spend == 0
    assert listing.budget.remaining == 100 and listing.budget.selected == 0


async def test_an_allocation_that_does_not_fit_is_dropped_and_said(planner: Planner) -> None:
    inv = planner.inventory
    inv.create(
        ItemCreate(item_type="toaster", name="Old laptop")
    )  # the name says laptop, the type does not
    inv.create(ItemCreate(item_type="monitor", name="Spare monitor"))
    inv.create(ItemCreate(item_type="vacuum", name="Upright vacuum"))
    projects = await planner.propose(ProposeRequest())
    desk = next(p for p in projects if p.template == "homework_workstation")
    assert {a.requirement for a in desk.allocations} == {"monitor"}
    assert any("does not fill" in d for d in desk.dropped)
    assert any("not in the inventory" in d for d in desk.dropped)  # the keyboard nobody has


async def test_nothing_usable_is_refused_before_any_call(planner: Planner) -> None:
    planner.inventory.create(ItemCreate(item_type="phone", name="For sale", intent="sell"))  # type: ignore[arg-type]
    with pytest.raises(ProjectsError, match="nothing in the inventory"):
        await planner.propose(ProposeRequest())


async def test_selection_commits_items_once_and_reserves_them(planner: Planner) -> None:
    ids = household(planner.inventory)
    planner.set_preferences(Preferences(budget=20))
    projects = await planner.propose(ProposeRequest())
    desk, vacuum = projects
    selected = planner.select(desk.id)
    assert selected.status == "selected" and all(a.committed for a in selected.allocations)
    assert planner.inventory.get(ids["Old laptop"]).availability == "reserved"
    budget = planner.projects().budget
    assert (budget.committed_spend, budget.remaining, budget.selected) == (12, 8, 1)
    # a second project that wants the same laptop: a conflict, unless it takes the item
    again = await planner.propose(ProposeRequest())
    other = next(p for p in again if p.template == "homework_workstation")
    with pytest.raises(AllocationConflictError) as caught:
        planner.select(other.id)
    assert caught.value.conflicts[0].item_name == "Old laptop"
    assert caught.value.conflicts[0].project_id == desk.id
    moved = planner.select(other.id, take=True)
    assert moved.status == "selected"
    lost = planner.project(desk.id)
    assert next(r for r in lost.requirements if r.key == "laptop").state == "unknown"
    assert all(a.item_name != "Old laptop" for a in lost.allocations)
    assert planner.inventory.get(ids["Old laptop"]).availability == "reserved"  # by the other now
    # abandoning releases what nobody else holds
    planner.abandon(other.id)
    planner.abandon(desk.id)
    assert planner.inventory.get(ids["Old laptop"]).availability == "available"
    assert planner.select(vacuum.id).status == "selected"
    # the attachment the proposal left open blocks the build until an item of yours fills it
    with pytest.raises(ProjectsError, match="still needed before building: attachment"):
        planner.advance(vacuum.id, "building")
    tool = planner.inventory.create(ItemCreate(item_type="crevice tool", name="Narrow tool"))
    gone = planner.inventory.create(
        ItemCreate(item_type="crevice tool", name="Lost tool", availability="gone")  # type: ignore[arg-type]
    )
    with pytest.raises(ProjectsError, match="not one a build may use"):
        planner.fill(vacuum.id, "attachment", FillRequest(item_id=gone.id))
    with pytest.raises(ProjectsError, match="not a kind that fills"):
        planner.fill(vacuum.id, "attachment", FillRequest(item_id=ids["Spare monitor"]))
    with pytest.raises(ProjectsError, match="filled already"):
        planner.fill(vacuum.id, "vacuum", FillRequest(item_id=tool.id))
    filled = planner.fill(vacuum.id, "attachment", FillRequest(item_id=tool.id, why="bought it"))
    assert next(r for r in filled.requirements if r.key == "attachment").state == "pass"
    assert any(
        a.item_id == tool.id and a.committed and a.why == "bought it" for a in filled.allocations
    )
    assert planner.inventory.get(tool.id).availability == "reserved"
    with pytest.raises(ProjectsError, match="filled already"):
        planner.fill(vacuum.id, "attachment", FillRequest(item_id=tool.id))
    assert planner.advance(vacuum.id, "building").status == "building"
    # a project moves one way: a build is not shortlisted again
    with pytest.raises(ProjectsError, match="a building project cannot be changed"):
        planner.shortlist(vacuum.id)
    assert planner.advance(vacuum.id, "done").status == "done"
    with pytest.raises(ProjectsError, match="is over"):
        planner.fill(vacuum.id, "attachment", FillRequest(item_id=tool.id))
    for change in (planner.abandon, planner.select, planner.shortlist):
        with pytest.raises(ProjectsError, match="a done project cannot be changed"):
            change(vacuum.id)
    with pytest.raises(ProjectsError):
        planner.advance(desk.id, "building")
    with pytest.raises(ProjectsError):
        planner.advance(vacuum.id, "flying")


async def test_a_deleted_item_leaves_its_project_open(planner: Planner) -> None:
    ids = household(planner.inventory)
    planner.set_preferences(Preferences(budget=20))
    desk, _vacuum = await planner.propose(ProposeRequest())
    planner.select(desk.id)
    planner.inventory.delete(ids["Old laptop"])
    project = planner.project(desk.id)
    assert all(a.item_name != "Old laptop" for a in project.allocations)
    assert next(r for r in project.requirements if r.key == "laptop").state == "unknown"
    # the project is still the owner's to change: nothing 404s on the item that is gone
    assert planner.abandon(desk.id).status == "abandoned"


async def test_a_missing_requirement_becomes_a_search_under_the_budget_left(
    planner: Planner,
) -> None:
    household(planner.inventory)
    planner.set_preferences(Preferences(budget=50))
    projects = await planner.propose(ProposeRequest())
    vacuum = next(p for p in projects if p.template == "vacuum_restored")
    planner.select(vacuum.id)
    with_search = planner.search_for(vacuum.id, "attachment")
    req = next(r for r in with_search.requirements if r.key == "attachment")
    assert req.search_id is not None
    search = planner.finder.search(req.search_id)
    assert search.profile == "vacuum_attachment"
    assert search.title.startswith("A non-powered tool")
    assert search.max_price == 40  # 50 less the 10 the project expects to spend
    with pytest.raises(ProjectsError, match="open for attachment already"):
        planner.search_for(vacuum.id, "attachment")
    # the tool bought from that search fills the requirement and the search is found
    tool = planner.inventory.create(ItemCreate(item_type="crevice tool", name="Narrow tool"))
    planner.fill(vacuum.id, "attachment", FillRequest(item_id=tool.id))
    assert planner.finder.search(req.search_id).status == "found"
    with pytest.raises(ProjectsError, match="filled from the inventory"):
        planner.search_for(vacuum.id, "vacuum")
    with pytest.raises(ProjectsError, match="no requirement"):
        planner.search_for(vacuum.id, "wings")


async def test_the_tool_loop_replays_statelessly(live_settings: Settings) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        step = "propose-1" if len(bodies) == 1 else "propose-2"
        fixture = json.loads((RECORDED_FIXTURES / "responses" / f"{step}.json").read_text())
        return httpx.Response(200, json=fixture["response"])

    ledger = CostLedger(cap_usd=25.0)
    client = ModelApiClient(live_settings, ledger, transport=httpx.MockTransport(handler))
    inventory = Inventory(live_settings)
    profiles = Profiles()
    finder = Finder(
        live_settings,
        client,
        inventory,
        profiles,
        Extractor(live_settings, client),
        Assessor(profiles, inventory),
    )
    planner = Planner(live_settings, client, inventory, Templates(), finder)
    household(inventory)
    projects = await planner.propose(ProposeRequest(count=2))
    assert len(projects) == 2 and projects[0].from_fixture is False
    first, second = bodies
    assert first["store"] is False and first["tools"][0]["name"] == "list_inventory"
    assert first["text"]["format"]["name"] == "ProposalSet"
    # the second step carries the brief, the model's own output items, then one result per call
    kinds = [item["type"] for item in second["input"]]
    assert (
        kinds[0] == "message" and "function_call" in kinds and kinds[-1] == "function_call_output"
    )
    results = [item for item in second["input"] if item["type"] == "function_call_output"]
    assert [r["call_id"] for r in results] == ["call_fixture_1", "call_fixture_2"]
    assert "Old laptop" in results[0]["output"] and "homework_workstation" in results[1]["output"]
    assert len(ledger.entries()) == 2 and ledger.entries()[0].op == "propose-1"


async def test_a_loop_that_never_answers_is_an_error(live_settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        fixture = json.loads((RECORDED_FIXTURES / "responses" / "propose-1.json").read_text())
        return httpx.Response(200, json=fixture["response"])

    client = ModelApiClient(
        live_settings, CostLedger(cap_usd=25.0), transport=httpx.MockTransport(handler)
    )
    inventory = Inventory(live_settings)
    profiles = Profiles()
    finder = Finder(
        live_settings,
        client,
        inventory,
        profiles,
        Extractor(live_settings, client),
        Assessor(profiles, inventory),
    )
    planner = Planner(live_settings, client, inventory, Templates(), finder)
    household(inventory)
    with pytest.raises(IncompleteResponseError, match="did not finish"):
        await planner.propose(ProposeRequest())


def test_project_routes(recorded_client: TestClient) -> None:
    for item_type, name in (
        ("laptop", "Old laptop"),
        ("monitor", "Spare monitor"),
        ("vacuum", "Upright vacuum"),
    ):
        assert (
            recorded_client.post(
                "/api/items", json={"item_type": item_type, "name": name}
            ).status_code
            == 201
        )
    assert recorded_client.get("/api/preferences").json()["effort"] == "medium"
    saved = recorded_client.put(
        "/api/preferences", json={"budget": 30, "skills": ["basic computer setup"]}
    )
    assert saved.status_code == 200 and saved.json()["budget"] == 30
    assert recorded_client.put("/api/preferences", json={"effort": "heroic"}).status_code == 422
    assert len(recorded_client.get("/api/templates").json()) == 5

    proposed = recorded_client.post("/api/projects/propose", json={"count": 3})
    assert proposed.status_code == 201, proposed.text
    projects = proposed.json()
    assert [p["template"] for p in projects] == ["homework_workstation", "vacuum_restored"]
    desk, vacuum = projects
    listing = recorded_client.get("/api/projects").json()
    assert listing["budget"]["remaining"] == 30 and len(listing["projects"]) == 2
    assert recorded_client.get(f"/api/projects/{desk['id']}").json()["status"] == "proposed"
    assert (
        recorded_client.post(f"/api/projects/{desk['id']}/shortlist").json()["status"]
        == "shortlisted"
    )
    assert (
        recorded_client.post(f"/api/projects/{desk['id']}/select", json={}).json()["status"]
        == "selected"
    )

    again = recorded_client.post("/api/projects/propose", json={}).json()
    other = next(p for p in again if p["template"] == "homework_workstation")
    conflict = recorded_client.post(f"/api/projects/{other['id']}/select", json={})
    assert conflict.status_code == 409
    assert conflict.json()["conflicts"][0]["project_id"] == desk["id"]
    taken = recorded_client.post(f"/api/projects/{other['id']}/select", json={"take": True})
    assert taken.status_code == 200 and taken.json()["status"] == "selected"

    searched = recorded_client.post(f"/api/projects/{vacuum['id']}/requirements/attachment/search")
    assert searched.status_code == 200
    req = next(r for r in searched.json()["requirements"] if r["key"] == "attachment")
    assert req["search_id"] is not None
    assert recorded_client.get(f"/api/searches/{req['search_id']}").status_code == 200
    assert (
        recorded_client.post(f"/api/projects/{vacuum['id']}/requirements/wings/search").status_code
        == 422
    )
    assert recorded_client.post(f"/api/projects/{vacuum['id']}/advance/done").status_code == 422
    tool = recorded_client.post(
        "/api/items", json={"item_type": "crevice tool", "name": "Narrow tool"}
    ).json()
    filled = recorded_client.post(
        f"/api/projects/{vacuum['id']}/requirements/attachment/fill", json={"item_id": tool["id"]}
    )
    assert filled.status_code == 200, filled.text
    assert (
        next(r for r in filled.json()["requirements"] if r["key"] == "attachment")["state"]
        == "pass"
    )
    assert recorded_client.get(f"/api/searches/{req['search_id']}").json()["status"] == "found"
    assert (
        recorded_client.post(
            f"/api/projects/{vacuum['id']}/requirements/attachment/fill", json={"item_id": 999}
        ).status_code
        == 422
    )
    assert (
        recorded_client.post(f"/api/projects/{desk['id']}/abandon").json()["status"] == "abandoned"
    )
    assert recorded_client.get("/api/projects/999").status_code == 404
    assert recorded_client.post("/api/projects/propose", json={"count": 9}).status_code == 422


def test_a_proposal_without_a_recorded_loop_is_a_503(client: TestClient) -> None:
    client.post("/api/items", json={"item_type": "laptop", "name": "Old laptop"})
    res = client.post("/api/projects/propose", json={})
    assert res.status_code == 503


def test_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/preferences", "/api/projects/propose", "/api/projects/{project_id}/select"):
        assert path in paths
