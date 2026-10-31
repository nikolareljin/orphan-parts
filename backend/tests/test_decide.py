import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decide import (
    Decider,
    DecisionCreate,
    KeepFix,
    ReuseScenario,
    ScenariosWriting,
    SellCard,
    Use,
    UsesWriting,
    decided_line,
    parse_decided,
    scenarios_brief,
    suggested,
    templates_for,
)
from app.decide.schema import MAX_REUSE, Scenarios
from app.decide.service import (
    MORE,
    NEEDS_MAX,
    NO_PROFILE,
    TEXT_MAX,
    brief,
    kind_named,
    known_fields,
    owned_items,
    repair_plan,
)
from app.inventory import Inventory
from app.inventory.schema import TEXT_MAX as NOTES_MAX
from app.inventory.schema import FieldCreate, ItemCreate, ItemPatch
from app.main import create_app
from app.model_api import ModelApiClient
from app.model_api.client import ModelResponse, StructuredResponse
from app.ops.gate import DEMO_LINE, expensive
from app.projects import Templates
from app.projects.schema import Preferences
from app.projects.service import Planner
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


class _Writes:
    """A client that answers a uses call with what it was given, as the model wrote it."""

    def __init__(self, uses: list[Use]) -> None:
        self.uses = uses

    async def respond_structured(self, model_cls: type, **_: Any) -> StructuredResponse[Any]:
        response = ModelResponse.model_construct(
            model="muse-spark", from_fixture=False, cost_usd=0.01
        )
        return StructuredResponse.model_construct(
            parsed=UsesWriting(uses=self.uses), response=response
        )


class _Owner:
    def preferences(self) -> Preferences:
        return Preferences()

    def has_preferences(self) -> bool:
        return False


async def test_the_models_text_is_trimmed_and_capped_before_it_is_kept(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory)
    long = "x" * (TEXT_MAX + 50)
    written = [
        Use(title="   ", what_it_does="no title", needs=[], effort="low", note=""),
        Use(
            title=f"  {long}  ",
            what_it_does=long,
            needs=["  a cable  ", "   ", *[f"part {n}" for n in range(NEEDS_MAX + 2)]],
            effort="high",
            note=long,
        ),
        *[
            Use(title=f"use {n}", what_it_does="", needs=[], effort="medium", note="")
            for n in range(4)
        ],
    ]
    decider = Decider(
        settings,
        cast(ModelApiClient, _Writes(written)),
        inventory,
        Templates(),
        cast(Planner, _Owner()),
        cast(Any, None),
        cast(Any, None),
    )
    kept = await decider.uses(item_id)
    # the untitled one dropped, three kept, each text cut to its bound
    assert [u.title for u in kept.uses] == ["x" * TEXT_MAX, "use 0", "use 1"]
    first = kept.uses[0]
    assert len(first.what_it_does) == TEXT_MAX and len(first.note) == TEXT_MAX
    assert first.needs[0] == "a cable" and len(first.needs) == NEEDS_MAX
    assert kept.model == "muse-spark" and kept.from_fixture is False
    assert decider.latest_uses(item_id) == kept


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
    # the guidance and the uses were written before the decision: a decision does not change
    # what the item is worth, so the guidance stays current; the uses say the item changed
    assert view["worth"]["stale"] is False and view["uses"]["stale"] is True

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


def test_a_choice_made_from_an_older_version_is_refused_and_nothing_is_written(
    recorded_client: TestClient,
) -> None:
    item = recorded_client.post("/api/items", json={"item_type": "laptop"}).json()
    item_id, version = item["id"], item["version"]
    # another tab decides first: the item moves on
    given = recorded_client.post(
        f"/api/items/{item_id}/decision", json={"choice": "give", "version": version}
    )
    assert given.status_code == 200 and given.json()["version"] == version + 1
    events = recorded_client.get(f"/api/items/{item_id}/events").json()
    # the stale tab's choice is refused
    stale = recorded_client.post(
        f"/api/items/{item_id}/decision", json={"choice": "keep_build", "version": version}
    )
    assert stale.status_code == 409
    after = recorded_client.get(f"/api/items/{item_id}").json()
    assert after["intent"] == "give" and after["version"] == version + 1
    assert recorded_client.get(f"/api/items/{item_id}/events").json() == events
    # made from the current version, it goes through
    kept = recorded_client.post(
        f"/api/items/{item_id}/decision", json={"choice": "keep_build", "version": version + 1}
    )
    assert kept.status_code == 200 and kept.json()["intent"] == "build"


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
    # the same project counting on the item twice is named once
    inventory: Inventory = recorded_client.app.state.inventory  # type: ignore[attr-defined]
    inventory.add_allocation(desk["id"], laptop_id, "spare", "a second slot", True)
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


async def test_uses_keep_the_version_read_before_the_request(settings: Settings) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory)
    before = inventory.get(item_id).version

    class ChangingWriter(_Writes):
        async def respond_structured(self, model_cls: type, **kw: Any) -> StructuredResponse[Any]:
            inventory.add_field(item_id, FieldCreate(field="ram", value="16", unit="GB"))
            return await super().respond_structured(model_cls, **kw)

    decider = Decider(
        settings,
        cast(ModelApiClient, ChangingWriter([])),
        inventory,
        Templates(),
        cast(Planner, _Owner()),
        cast(Any, None),
        cast(Any, None),
    )
    uses = await decider.uses(item_id)
    assert uses.item_version == before
    assert uses.stale is True
    assert decider.latest_uses(item_id) == uses


# --- what to do with it: the three scenarios -------------------------------------------------

RATED = Preferences.model_validate(
    {
        "skills": [
            {"skill": "electronics and soldering", "level": "confident"},
            {"skill": "woodworking", "level": "some"},
            {"skill": "software", "level": "pro"},
            {"skill": "plumbing", "level": "none"},
        ],
        "tools": "soldering iron, multimeter",
        "interests": "a quiet desk",
        "opens_devices": True,
        "budget": 40,
    }
)


def test_the_scenarios_brief_carries_the_rated_skills_and_nothing_private(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory, location="top shelf", notes="was my brother's")
    inventory.add_field(item_id, FieldCreate(field="serial_number", value="XK12-99"))
    inventory.add_field(item_id, FieldCreate(field="imei", value="IMEI-XYZ-77"))
    inventory.create(ItemCreate(item_type="monitor", name="Spare monitor", location="garage"))
    item = inventory.get(item_id)
    others = ["monitor (1)"]
    text = scenarios_brief(item, known_fields(item), RATED, profiled=True, others=others)
    assert "electronics and soldering: confident" in text and "plumbing: none" in text
    assert "software: pro" in text and "- tools: soldering iron, multimeter" in text
    assert "battery holds an hour" in text and "- ram: 8 GB" in text
    assert "- monitor (1)" in text and "opens devices up: yes" in text
    assert NO_PROFILE not in text
    for private in ("XK12-99", "IMEI-XYZ-77", "top shelf", "brother", "garage"):
        assert private not in text, private
    # no profile: the brief says to answer for an average person and holds no skills
    bare = scenarios_brief(item, known_fields(item), Preferences(), profiled=False, others=[])
    assert NO_PROFILE in bare and "skills" not in bare
    assert "(nothing else listed)" in bare


def test_the_brief_names_the_other_kinds_the_owner_has(settings: Settings) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory)
    for item_type in ("monitor", "monitor", "keyboard"):
        inventory.create(ItemCreate(item_type=item_type, name=item_type))
    gone = inventory.create(ItemCreate(item_type="router", name="Old router"))
    inventory.update(gone.id, ItemPatch(availability="gone"))
    decider = Decider(
        settings,
        cast(ModelApiClient, None),
        inventory,
        Templates(),
        cast(Planner, _Owner()),
        cast(Any, None),
        cast(Any, None),
    )
    assert decider.others(item_id) == ["monitor (2)", "keyboard (1)"]


def _card(title: str) -> ReuseScenario:
    return ReuseScenario(
        title=title,
        what_it_does="x" * (TEXT_MAX + 10),
        with_items=["monitor (2)", "  "],
        difficulty="easy",
        why="",
        extra_parts=[],
        cost="",
        time="",
    )


class _Scenarios:
    """A client that answers a scenarios call with what it was given and keeps the request."""

    def __init__(self, written: ScenariosWriting) -> None:
        self.written = written
        self.asked: dict[str, Any] = {}

    async def respond_structured(self, model_cls: type, **kw: Any) -> StructuredResponse[Any]:
        self.asked = kw
        response = ModelResponse.model_construct(
            model="muse-spark", from_fixture=False, cost_usd=0.02
        )
        return StructuredResponse.model_construct(parsed=self.written, response=response)


async def test_scenarios_are_one_low_effort_call_and_the_text_is_cut(settings: Settings) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory)
    inventory.create(ItemCreate(item_type="monitor", name="Spare monitor"))
    written = ScenariosWriting(
        keep_fix=KeepFix(
            worth_fixing=True,
            problems=["worn battery", "  "],
            steps=[f"step {n}" for n in range(NEEDS_MAX + 3)],
            difficulty="easy",
            why="y" * (TEXT_MAX + 5),
            parts=["battery, 40 USD"],
            cost="40 USD",
            time="half an hour",
        ),
        reuse=[_card("  "), *[_card(f"use {n}") for n in range(MAX_REUSE + 1)]],
        sell=SellCard(selling_points=["boots"], effort="a listing", note=""),
        recommended="keep_fix",
        reason="you solder",
    )
    client = _Scenarios(written)

    class Owner(_Owner):
        def preferences(self) -> Preferences:
            return RATED

        def has_preferences(self) -> bool:
            return True

    decider = Decider(
        settings,
        cast(ModelApiClient, client),
        inventory,
        Templates(),
        cast(Planner, Owner()),
        cast(Any, None),
        cast(Any, None),
    )
    kept = await decider.scenarios(item_id)
    assert client.asked["op"] == "scenarios" and client.asked["effort"] == "low"
    assert client.asked["max_output_tokens"] == 1200
    assert "software: pro" in client.asked["input"][0]["content"][0]["text"]
    assert kept.profiled is True and kept.recommended == "keep_fix"
    assert kept.keep_fix.problems == ["worn battery"] and len(kept.keep_fix.steps) == NEEDS_MAX
    assert len(kept.keep_fix.why) == TEXT_MAX
    assert [r.title for r in kept.reuse] == [f"use {n}" for n in range(MAX_REUSE)]
    assert kept.reuse[0].with_items == ["monitor"]
    assert len(kept.reuse[0].what_it_does) == TEXT_MAX
    assert decider.latest_scenarios(item_id) == kept


def test_scenarios_come_from_the_recording_and_are_kept_on_the_item(
    recorded_client: TestClient,
) -> None:
    item = recorded_client.post(
        "/api/items",
        json={"item_type": "laptop", "name": "Old laptop", "faults": "battery holds an hour"},
    ).json()
    item_id = item["id"]
    asked = recorded_client.post(f"/api/items/{item_id}/scenarios")
    assert asked.status_code == 201, asked.text
    found = asked.json()
    assert found["from_fixture"] is True and found["cost_usd"] == 0
    assert found["version"] == 1 and found["stale"] is False
    # no profile filled in yet: written for an average person, and it says so
    assert found["profiled"] is False
    assert found["keep_fix"]["worth_fixing"] is True and found["keep_fix"]["steps"]
    assert found["keep_fix"]["difficulty"] in ("easy", "moderate", "hard")
    assert 2 <= len(found["reuse"]) <= 3 and found["reuse"][0]["title"]
    assert found["sell"]["selling_points"] and found["sell"]["effort"]
    assert found["recommended"] in ("keep_fix", "reuse", "sell", "give") and found["reason"]
    events = [e["change"] for e in recorded_client.get(f"/api/items/{item_id}/events").json()]
    assert "scenarios written (v1)" in events
    assert recorded_client.get(f"/api/items/{item_id}/decide").json()["scenarios"] == found

    # an edit marks them stale; asking again is a new version, written for the profile
    recorded_client.patch(f"/api/items/{item_id}", json={"condition": "scuffed"})
    view = recorded_client.get(f"/api/items/{item_id}/decide").json()
    assert view["scenarios"]["stale"] is True
    recorded_client.put("/api/preferences", json={"skills": ["soldering"]})
    again = recorded_client.post(f"/api/items/{item_id}/scenarios").json()
    assert again["version"] == 2 and again["stale"] is False and again["profiled"] is True
    assert recorded_client.post("/api/items/999/scenarios").status_code == 404


def test_keep_and_fix_adds_the_repair_steps_to_the_notes_once(
    recorded_client: TestClient,
) -> None:
    item = recorded_client.post(
        "/api/items", json={"item_type": "laptop", "name": "Old laptop", "notes": "from the attic"}
    ).json()
    item_id = item["id"]
    found = recorded_client.post(f"/api/items/{item_id}/scenarios").json()
    chose = recorded_client.post(
        f"/api/items/{item_id}/decision",
        json={"choice": "keep_fix", "version": item["version"]},
    )
    assert chose.status_code == 200, chose.text
    after = chose.json()
    assert after["intent"] == "keep" and after["version"] == item["version"] + 1
    assert after["notes"].startswith("from the attic\n\nRepair plan (scenarios v1")
    assert found["keep_fix"]["steps"][0] in after["notes"]
    events = [e["change"] for e in recorded_client.get(f"/api/items/{item_id}/events").json()]
    assert events[-1] == "decided: keep_fix"
    assert recorded_client.get(f"/api/items/{item_id}/decide").json()["last"]["choice"] == (
        "keep_fix"
    )
    # the decision is no change to the item: the cards stay current and say the steps are in
    # the notes; the same choice again adds nothing, and is no new version
    view = recorded_client.get(f"/api/items/{item_id}/decide").json()["scenarios"]
    assert view["stale"] is False and view["steps_in_notes"] is True
    again = recorded_client.post(f"/api/items/{item_id}/decision", json={"choice": "keep_fix"})
    assert again.json()["notes"] == after["notes"] and again.json()["version"] == after["version"]
    # an edit of the owner's makes them stale
    recorded_client.patch(f"/api/items/{item_id}", json={"condition": "dented"})
    view = recorded_client.get(f"/api/items/{item_id}/decide").json()["scenarios"]
    assert view["stale"] is True and view["steps_in_notes"] is True


def test_a_decision_leaves_the_scenarios_current_and_the_plan_still_applies(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory, notes="from the attic")
    _kept(inventory, item_id, _written())
    decider = _decider(settings, inventory)
    # reuse it first: the intent changes, the item version moves, the cards stay current
    moved = decider.decide(item_id, DecisionCreate(choice="keep_build", note="maybe a desk"))
    latest = decider.latest_scenarios(item_id)
    assert latest is not None and latest.item_version < moved.version
    assert not latest.stale and not latest.steps_in_notes
    # then keep and fix after all: the steps go in, once
    item = decider.decide(item_id, DecisionCreate(choice="keep_fix"))
    assert item.notes.startswith("from the attic\n\nRepair plan (scenarios v1, easy):")
    latest = decider.latest_scenarios(item_id)
    assert latest is not None and not latest.stale and latest.steps_in_notes
    again = decider.decide(item_id, DecisionCreate(choice="keep_fix"))
    assert again.notes == item.notes and again.version == item.version


def test_a_count_copied_from_the_brief_is_not_part_of_the_kind() -> None:
    for text in (
        "raspberry pi (1)",
        "raspberry pi (1) ",
        "raspberry pi (1).",
        "raspberry pi (x1)",
        " raspberry pi ( X 12 ), ",
        "raspberry pi (2);",
        "raspberry pi",
    ):
        assert kind_named(text) == "raspberry pi", text
    # a number that is part of the name stays
    assert kind_named("usb 3 hub") == "usb 3 hub"
    assert kind_named("monitor (27 inch)") == "monitor (27 inch)"


def test_with_items_are_the_kinds_the_owner_has() -> None:
    kinds = ["raspberry pi", "keyboard", "monitor"]
    texts = ["Raspberry Pi (1)", "keyboard (1).", "KEYBOARD (x1)", "toaster (1)", "  ", "a monitor"]
    assert owned_items(texts, kinds) == ["raspberry pi", "keyboard"]
    assert owned_items(["monitor"], []) == []
    # the owner's kind as they typed it, matched whatever the case the card wrote
    assert owned_items(["raspberry PI (2)"], ["Raspberry Pi"]) == ["Raspberry Pi"]


def _decider(settings: Settings, inventory: Inventory) -> Decider:
    return Decider(
        settings,
        cast(ModelApiClient, None),
        inventory,
        Templates(),
        cast(Planner, _Owner()),
        cast(Any, None),
        cast(Any, None),
    )


def _written(**keep_fix: Any) -> ScenariosWriting:
    card: dict[str, Any] = {
        "worth_fixing": True,
        "problems": ["worn battery"],
        "steps": ["open the base", "swap the battery"],
        "difficulty": "easy",
        "why": "one connector",
        "parts": ["battery, 40 USD"],
        "cost": "40 USD",
        "time": "half an hour",
    }
    card.update(keep_fix)
    return ScenariosWriting(
        keep_fix=KeepFix(**card),
        reuse=[_card("desk")],
        sell=SellCard(selling_points=["boots"], effort="a listing", note=""),
        recommended="keep_fix",
        reason="you solder",
    )


def _kept(inventory: Inventory, item_id: int, written: ScenariosWriting) -> None:
    content = {
        "profiled": False,
        **written.model_dump(),
        "model": "muse-spark",
        "from_fixture": True,
        "cost_usd": 0.0,
    }
    item = inventory.get(item_id)
    inventory.add_scenarios(item_id, json.dumps(content), item_version=item.version)


def test_a_stored_row_with_counts_reads_as_owned_kinds(settings: Settings) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory)
    for item_type in ("monitor", "keyboard"):
        inventory.create(ItemCreate(item_type=item_type, name=item_type))
    written = _written()
    written.reuse[0].with_items = ["Monitor (1).", "keyboard (x2)", "toaster (1)"]
    _kept(inventory, item_id, written)
    read = _decider(settings, inventory).latest_scenarios(item_id)
    assert read is not None and read.reuse[0].with_items == ["monitor", "keyboard"]
    # the row stays as the model wrote it
    stored = json.loads(inventory.scenarios(item_id)[-1]["content"])
    assert stored["reuse"][0]["with_items"] == ["Monitor (1).", "keyboard (x2)", "toaster (1)"]


def _scenarios(**keep_fix: Any) -> Scenarios:
    written = _written(**keep_fix)
    return Scenarios(
        id=1,
        item_id=1,
        version=2,
        item_version=1,
        stale=False,
        profiled=True,
        keep_fix=written.keep_fix,
        reuse=written.reuse,
        sell=written.sell,
        recommended="keep_fix",
        reason="",
        model="muse-spark",
        from_fixture=True,
        cost_usd=0.0,
        at="t",
    )


def test_a_repair_not_worth_doing_has_no_plan() -> None:
    assert repair_plan(_scenarios(worth_fixing=False)) == ""
    assert repair_plan(_scenarios(steps=[])) == ""
    whole = repair_plan(_scenarios())
    assert whole.startswith("Repair plan (scenarios v2, easy):\n1. open the base\n2. swap")
    assert whole.endswith("Parts: battery, 40 USD\nCost: 40 USD. Time: half an hour.")
    assert MORE not in whole


def test_a_plan_too_long_for_the_notes_leaves_out_whole_steps() -> None:
    steps = [f"step {n} " + "x" * 150 for n in range(1, 7)]
    whole = repair_plan(_scenarios(steps=steps))
    room = len(whole) - 100
    cut = repair_plan(_scenarios(steps=steps), room)
    assert len(cut) <= room and cut.endswith(f"Cost: 40 USD. Time: half an hour.\n{MORE}")
    lines = cut.splitlines()
    # steps 1 to 5 whole, step 6 left out, no step cut in the middle
    assert [line[:2] for line in lines[1:6]] == ["1.", "2.", "3.", "4.", "5."]
    assert all(line == f"{n}. {steps[n - 1]}" for n, line in enumerate(lines[1:6], start=1))
    assert "6. " not in cut
    # only the heading fits: the plan says the rest is in the scenarios; nothing fits: empty
    head = "Repair plan (scenarios v2, easy):"
    assert repair_plan(_scenarios(steps=steps), len(head) + 1 + len(MORE)) == f"{head}\n{MORE}"
    assert repair_plan(_scenarios(steps=steps), 10) == ""


def test_keep_and_fix_on_long_notes_keeps_them_whole_and_cuts_the_plan(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    long = "n" * (NOTES_MAX - 120)
    item_id = laptop(inventory, notes=long)
    _kept(inventory, item_id, _written(steps=[f"step {n} " + "x" * 40 for n in range(6)]))
    item = _decider(settings, inventory).decide(item_id, DecisionCreate(choice="keep_fix"))
    assert item.notes.startswith(long + "\n\nRepair plan") and len(item.notes) <= NOTES_MAX
    assert item.notes.endswith(MORE) and item.intent == "keep"


def test_keep_and_fix_after_an_edit_sets_the_intent_and_leaves_the_notes(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory, notes="from the attic", intent="sell")
    _kept(inventory, item_id, _written())
    edited = inventory.update(item_id, ItemPatch(condition="dented"))
    decider = _decider(settings, inventory)
    latest = decider.latest_scenarios(item_id)
    assert latest is not None and latest.stale
    item = decider.decide(item_id, DecisionCreate(choice="keep_fix"))
    assert item.notes == "from the attic" and item.intent == "keep"
    assert item.version == edited.version + 1


def test_the_plan_is_written_only_at_the_version_it_was_written_from(
    settings: Settings,
) -> None:
    inventory = Inventory(settings)
    item_id = laptop(inventory, notes="from the attic", intent="sell")
    at = inventory.get(item_id).version
    # an older version, with the field added since: nothing added, the intent still set
    item = inventory.decide(
        item_id, "keep", "decided: keep_fix", said=False, notes_add="plan", plan_item_version=at - 1
    )
    assert item.notes == "from the attic" and item.intent == "keep" and item.version == at + 1
    # at its version, with only a decision since: added once; the same plan again finds its
    # first line in the notes
    item = inventory.decide(
        item_id, "keep", "decided: keep_fix", said=False, notes_add="plan", plan_item_version=at
    )
    assert item.notes == "from the attic\n\nplan" and item.version == at + 2
    again = inventory.decide(
        item_id,
        "keep",
        "decided: keep_fix",
        said=False,
        notes_add="plan\nmore",
        plan_item_version=at,
    )
    assert again.notes == item.notes and again.version == item.version
    # an edit since its version: nothing added
    edited = inventory.update(item_id, ItemPatch(condition="dented"))
    late = inventory.decide(
        item_id, "keep", "decided: keep_fix", said=False, notes_add="other", plan_item_version=at
    )
    assert late.notes == item.notes and late.version == edited.version
    # no version given: no plan
    none = inventory.decide(item_id, "keep", "decided: keep_fix", said=False, notes_add="plan")
    assert none.notes == item.notes


def test_a_plan_that_does_not_fit_the_notes_is_not_cut_into_them(settings: Settings) -> None:
    inventory = Inventory(settings)
    long = "n" * (NOTES_MAX - 10)
    item_id = laptop(inventory, notes=long)
    at = inventory.get(item_id).version
    item = inventory.decide(
        item_id, "keep", "decided: keep_fix", said=False, notes_add="p" * 9, plan_item_version=at
    )
    assert item.notes == long
    fits = "p" * (NOTES_MAX - len(long) - 2)
    item = inventory.decide(
        item_id, "keep", "decided: keep_fix", said=False, notes_add=fits, plan_item_version=at
    )
    assert item.notes == f"{long}\n\n{fits}" and len(item.notes) == NOTES_MAX


def test_the_demo_visitor_is_refused_scenarios(gated: TestClient) -> None:
    gated.post("/api/access", json={"code": CODE})
    item = gated.post("/api/items", json={"item_type": "laptop"}).json()
    gated.post(f"/api/items/{item['id']}/public", json={"public": True})
    gated.cookies.clear()
    answer = gated.post(f"/api/items/{item['id']}/scenarios")
    assert answer.status_code == 403 and answer.json() == {"detail": DEMO_LINE}
    assert expensive("POST", "/api/items/12/scenarios")
    assert not expensive("GET", "/api/items/12/scenarios")
