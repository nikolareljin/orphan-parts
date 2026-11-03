"""Find a part, Build and reuse and the profile, read-only for the demo visitor: the searches
made for public items with their candidates and listings, the projects built on public items
alone with their packs, and the skills; never the notes, the budget, the radius or an outcome
not shared, and every write and every call that spends still behind the code."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.listing.voice import FIELD as VOICE_FIELD
from app.main import create_app
from app.ops.door import live_request
from app.ops.gate import DEMO_LINE, demo_allowed, expensive
from app.projects.schema import VOICE_LINE, Project, visitor_markdown
from tests.conftest import RECORDED_FIXTURES
from tests.test_gate import CODE, gated_settings

NOTE = "ask my neighbor first"
LISTING_NOTE = "the seller sounded unsure"
CONFIGURATION = "wand taped in the hall closet"
# the owner's words on an item's condition, where a voice note is kept: they reach the pack
SPOKEN = "rattles since the move upstairs"
BUDGET, RADIUS, LEFT = 75.0, 30, 12.5


@pytest.fixture
def gated(tmp_path: Path) -> Iterator[TestClient]:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        yield c


def _owner_records(c: TestClient) -> dict[str, Any]:
    """As the owner: public items with a search, a candidate, a listing and a project with a
    pack and an outcome; a private item with its own search; a search from values; the
    preferences with a budget and a radius. The session stays open."""
    c.post("/api/access", json={"code": CODE})
    ids: dict[str, Any] = {}
    for key, item_type, name in (
        ("vacuum", "vacuum", "Upright vacuum"),
        ("tool", "crevice tool", "Narrow tool"),
        ("private", "laptop", "Private laptop"),
    ):
        ids[key] = c.post("/api/items", json={"item_type": item_type, "name": name}).json()["id"]
    for key in ("vacuum", "tool"):
        assert c.post(f"/api/items/{ids[key]}/public", json={"public": True}).status_code == 200
    prefs = {
        "interests": "a quiet desk",
        "skills": [{"skill": "electronics and soldering", "level": "confident"}],
        "tools": "a screwdriver set",
        "budget": BUDGET,
        "radius_km": RADIUS,
    }
    assert c.put("/api/preferences", json=prefs).status_code == 200
    search = {
        "need_item_id": ids["vacuum"],
        "profile": "vacuum_attachment",
        "title": "a hose for the upright vacuum",
        "notes": NOTE,
        "radius_km": RADIUS,
        "budget_left": LEFT,
        "max_price": 20,
    }
    ids["search"] = c.post("/api/searches", json=search).json()["id"]
    ids["private_search"] = c.post(
        "/api/searches", json={**search, "need_item_id": ids["private"], "title": "a battery"}
    ).json()["id"]
    ids["values_search"] = c.post(
        "/api/searches",
        json={"profile": "power_adapter", "title": "a 19 V adapter", "notes": NOTE},
    ).json()["id"]
    added = c.post(
        f"/api/searches/{ids['search']}/candidates",
        data={"request": f'{{"text": "Vacuum hose, 1.5 m, $12", "note": "{LISTING_NOTE}"}}'},
    )
    assert added.status_code == 201, added.text
    ids["candidate"] = added.json()["id"]
    private = c.post(
        f"/api/searches/{ids['private_search']}/candidates",
        data={"request": '{"text": "Laptop battery, $15"}'},
    )
    ids["private_candidate"] = private.json()["id"]
    back = c.post(f"/api/searches/{ids['search']}/listings", json={"texts": ["Hose, 1.5 m, $9"]})
    assert back.status_code == 201
    projects = c.post("/api/projects/propose", json={}).json()
    project = next(p for p in projects if p["template"] == "vacuum_restored")
    ids["project"] = pid = project["id"]
    assert {a["item_id"] for a in project["allocations"]} <= {ids["vacuum"], ids["tool"]}
    assert c.post(f"/api/projects/{pid}/select", json={}).status_code == 200
    c.post(f"/api/projects/{pid}/requirements/attachment/fill", json={"item_id": ids["tool"]})
    assert c.post(f"/api/projects/{pid}/advance/building").status_code == 200
    record = {
        "configuration": CONFIGURATION,
        "test": "the stairs",
        "tested_on": "2026-10-28",
        "working": False,
    }
    assert c.post(f"/api/projects/{pid}/outcome", json=record).status_code == 200
    spoken = {"field": VOICE_FIELD, "value": SPOKEN}
    assert c.post(f"/api/items/{ids['vacuum']}/fields", json=spoken).status_code == 200
    written = c.post(f"/api/projects/{pid}/pack")
    assert written.status_code == 201, written.text
    ids["pack"] = written.json()["id"]
    return ids


def _visitor(c: TestClient) -> None:
    c.cookies.clear()
    assert c.get("/api/access").json()["granted"] is False


def test_the_owner_gets_the_notes_the_budget_and_the_outcome(gated: TestClient) -> None:
    ids = _owner_records(gated)
    search = gated.get(f"/api/searches/{ids['search']}").json()
    assert search["notes"] == NOTE and search["radius_km"] == RADIUS
    assert search["budget_left"] == LEFT
    assert len(gated.get("/api/searches").json()) == 3
    assert gated.get(f"/api/candidates/{ids['candidate']}").json()["note"] == LISTING_NOTE
    prefs = gated.get("/api/preferences").json()
    assert prefs["budget"] == BUDGET and prefs["radius_km"] == RADIUS
    listed = gated.get("/api/projects").json()
    assert listed["budget"]["budget"] == BUDGET and listed["budget"]["remaining"] is not None
    project = gated.get(f"/api/projects/{ids['project']}").json()
    assert project["outcome"]["configuration"] == CONFIGURATION
    pack = gated.get(f"/api/packs/{ids['pack']}").json()["markdown"]
    assert "Across the selected projects: " in pack and "## Outcome" in pack
    assert f"condition notes: {SPOKEN}" in pack


def test_the_demo_visitor_reads_find_build_and_the_profile(gated: TestClient) -> None:
    ids = _owner_records(gated)
    _visitor(gated)
    # Find a part: the search for the public item, its candidate and its listing
    searches = gated.get("/api/searches")
    assert searches.status_code == 200
    assert [s["id"] for s in searches.json()] == [ids["search"]]
    search = gated.get(f"/api/searches/{ids['search']}").json()
    assert search["title"] == "a hose for the upright vacuum" and search["max_price"] == 20
    assert search["notes"] == "" and search["radius_km"] is None
    assert search["budget_left"] is None
    candidates = gated.get(f"/api/searches/{ids['search']}/candidates").json()
    assert [c["id"] for c in candidates] == [ids["candidate"]]
    assert candidates[0]["note"] == ""
    assert gated.get(f"/api/candidates/{ids['candidate']}").json()["note"] == ""
    assert gated.get(f"/api/candidates/{ids['candidate']}/questions").status_code == 200
    listings = gated.get(f"/api/searches/{ids['search']}/listings").json()
    assert [entry["text"] for entry in listings] == ["Hose, 1.5 m, $9"]
    # the profile: the skills and the rest, without the budget and the radius
    prefs = gated.get("/api/preferences").json()
    assert prefs["skills"] == [{"skill": "electronics and soldering", "level": "confident"}]
    assert prefs["interests"] == "a quiet desk" and prefs["tools"] == "a screwdriver set"
    assert prefs["budget"] is None and prefs["radius_km"] is None
    # Build and reuse: the project, without the budget or the outcome not shared
    listed = gated.get("/api/projects").json()
    assert [p["id"] for p in listed["projects"]] == [ids["project"]]
    assert listed["budget"]["budget"] is None and listed["budget"]["remaining"] is None
    project = gated.get(f"/api/projects/{ids['project']}").json()
    assert project["outcome"] is None and project["status"] == "building"
    assert project["dropped"] == []
    assert [p["id"] for p in gated.get(f"/api/projects/{ids['project']}/packs").json()] == [
        ids["pack"]
    ]
    for path in (f"/api/packs/{ids['pack']}", f"/api/packs/{ids['pack']}.md"):
        answer = gated.get(path)
        assert answer.status_code == 200, path
        text = answer.json()["markdown"] if path.endswith(str(ids["pack"])) else answer.text
        assert text.startswith("# ") and "## Steps" in text
        assert "Across the selected projects" not in text and "## Outcome" not in text
    assert gated.get(f"/api/projects/{ids['project']}/pictures").status_code == 200


def test_the_demo_visitor_never_sees_a_private_search_or_project(gated: TestClient) -> None:
    ids = _owner_records(gated)
    _visitor(gated)
    for path in (
        f"/api/searches/{ids['private_search']}",
        f"/api/searches/{ids['private_search']}/candidates",
        f"/api/searches/{ids['private_search']}/listings",
        f"/api/searches/{ids['values_search']}",
        f"/api/candidates/{ids['private_candidate']}",
        f"/api/candidates/{ids['private_candidate']}/questions",
    ):
        assert gated.get(path).status_code == 404, path
    # a project with an item the owner keeps private is not there for the visitor
    gated.post("/api/access", json={"code": CODE})
    assert gated.post(f"/api/items/{ids['tool']}/public", json={"public": False}).status_code == 200
    _visitor(gated)
    assert gated.get("/api/projects").json()["projects"] == []
    for path in (
        f"/api/projects/{ids['project']}",
        f"/api/projects/{ids['project']}/packs",
        f"/api/projects/{ids['project']}/pictures",
        f"/api/projects/{ids['project']}/pictures/1",
        f"/api/packs/{ids['pack']}",
        f"/api/packs/{ids['pack']}.md",
    ):
        assert gated.get(path).status_code == 404, path


def test_no_page_the_visitor_reads_carries_the_owners_words(gated: TestClient) -> None:
    ids = _owner_records(gated)
    _visitor(gated)
    for path in (
        "/api/searches",
        f"/api/searches/{ids['search']}",
        f"/api/searches/{ids['search']}/candidates",
        f"/api/searches/{ids['search']}/listings",
        f"/api/candidates/{ids['candidate']}",
        f"/api/candidates/{ids['candidate']}/questions",
        "/api/preferences",
        "/api/projects",
        f"/api/projects/{ids['project']}",
        f"/api/projects/{ids['project']}/packs",
        f"/api/packs/{ids['pack']}",
        f"/api/packs/{ids['pack']}.md",
    ):
        answer = gated.get(path)
        assert answer.status_code == 200, path
        for secret in (NOTE, LISTING_NOTE, CONFIGURATION, SPOKEN):
            assert secret not in answer.text, (path, secret)
        if path.endswith(".md"):
            continue
        for key, value in _pairs(answer.json()):
            if key in ("budget", "remaining", "radius_km", "budget_left") and not isinstance(
                value, dict
            ):
                assert value is None, (path, key)


def _pairs(value: Any) -> Iterator[tuple[str, Any]]:
    """Every key and value in a JSON answer, however deep."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from _pairs(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _pairs(inner)


def test_every_write_and_every_call_that_spends_on_these_pages_is_refused(
    gated: TestClient,
) -> None:
    ids = _owner_records(gated)
    _visitor(gated)
    concrete = {
        "{search_id}": str(ids["search"]),
        "{candidate_id}": str(ids["candidate"]),
        "{project_id}": str(ids["project"]),
        "{pack_id}": str(ids["pack"]),
        "{listing_id}": "1",
        "{key}": "attachment",
        "{to}": "done",
        "{n}": "1",
    }
    checked = 0
    for path, ops in gated.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        if not path.startswith(
            ("/api/searches", "/api/candidates", "/api/projects", "/api/packs", "/api/preferences")
        ):
            continue
        for method in ops:
            if method == "get":
                continue
            real = path
            for name, value in concrete.items():
                real = real.replace(name, value)
            assert not demo_allowed(method.upper(), real), (method, real)
            answer = gated.request(method.upper(), real, json={})
            assert answer.status_code == 403, (method, real, answer.text)
            assert answer.json() == {"detail": DEMO_LINE}
            checked += 1
    assert checked >= 20
    # what spends on these pages is among the refused
    assert expensive("POST", f"/api/searches/{ids['search']}/web")
    assert expensive("POST", "/api/projects/propose")
    # and nothing the owner had changed
    gated.post("/api/access", json={"code": CODE})
    assert gated.get(f"/api/searches/{ids['search']}").json()["notes"] == NOTE
    assert gated.get("/api/preferences").json()["budget"] == BUDGET


def test_the_visitor_pages_take_only_plain_ids() -> None:
    for path in (
        "/api/searches",
        "/api/searches/1",
        "/api/searches/1/candidates",
        "/api/searches/1/listings",
        "/api/candidates/1",
        "/api/candidates/1/questions",
        "/api/preferences",
        "/api/projects",
        "/api/projects/1",
        "/api/projects/1/packs",
        "/api/packs/1",
        "/api/packs/1.md",
        "/api/projects/1/pictures",
        "/api/projects/1/pictures/2",
    ):
        assert demo_allowed("GET", path), path
        assert not demo_allowed("POST", path), path
    for path in (
        "/api/searches/+1",
        "/api/searches/1/plan",
        "/api/searches/1/listings/1",
        "/api/candidates/1/recheck",
        "/api/projects/1/outcome/share",
        "/api/projects/propose",
        "/api/packs/1.txt",
        "/api/projects/1/pictures/x",
        "/api/searches/1\n",
    ):
        assert not demo_allowed("GET", path), path


def test_a_pack_for_the_visitor_leaves_the_budget_and_the_outcome_out() -> None:
    pack = "\n".join(
        [
            "# A build",
            "",
            "## Costs",
            "",
            "Expected spending for this project: 10 USD.",
            "Across the selected projects: 10 of 50 USD, 40 left.",
            "",
            "## Steps",
            "",
            "1. [ ] Begin",
            "",
            "## Outcome",
            "",
            "Configuration: in the hall",
            "",
        ]
    )
    shown = visitor_markdown(pack)
    assert "Across the selected" not in shown and "## Outcome" not in shown
    assert "in the hall" not in shown
    assert "Expected spending for this project: 10 USD." in shown and "1. [ ] Begin" in shown
    assert shown.endswith("Begin\n")


def test_a_pack_for_the_visitor_leaves_the_spoken_notes_and_the_searches_out() -> None:
    # the searches opened for what is still needed are made from values, with the budget left
    # as their top price: the owner's, like a voice note kept as the condition notes
    pack = "\n".join(
        [
            "## From the inventory",
            "",
            "- **Upright vacuum** as body (committed). It runs.",
            "  - condition: worn",
            f"{VOICE_LINE}it rattles",
            "since the move",
            "",
            "  - weight: 5 kg",
            "- **Narrow tool** as attachment (committed).",
            "",
            "## Still needed",
            "",
            "- Hose (blocks the build). Search: Hose for A build, top price 40 USD; 1 candidate(s),"
            " 1 documented",
            "  - Vacuum hose, 12 USD seen 2026-10-30",
            "- Filter (optional)",
            "",
            "## Costs",
            "",
            "Expected spending for this project: 10 USD.",
            "",
        ]
    )
    shown = visitor_markdown(pack)
    for secret in ("rattles", "since the move", "Search:", "top price 40", "Vacuum hose"):
        assert secret not in shown, secret
    for kept in (
        "  - condition: worn",
        "  - weight: 5 kg",
        "- **Narrow tool** as attachment (committed).",
        "- Hose (blocks the build)\n- Filter (optional)\n\n## Costs",
        "Expected spending for this project: 10 USD.",
    ):
        assert kept in shown, kept
    assert f"  - {VOICE_FIELD.replace('_', ' ')}: " == VOICE_LINE


def test_lines_the_inventory_does_not_back_are_the_owners(gated: TestClient) -> None:
    # a dropped line may name an item the owner keeps private: the visitor never gets one
    ids = _owner_records(gated)
    kept = gated.get(f"/api/projects/{ids['project']}").json()
    project = Project(**{**kept, "dropped": ["Private laptop as screen: not the right kind"]})
    assert project.model_dump()["dropped"] == project.dropped
    token = live_request.set(False)
    try:
        shown = project.model_dump()
    finally:
        live_request.reset(token)
    assert shown["dropped"] == [] and shown["outcome"] is None
