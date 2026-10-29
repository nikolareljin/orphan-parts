import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extract import Extractor
from app.find import (
    Candidate,
    CandidateCreate,
    Finder,
    FindError,
    SearchCreate,
    SearchPatch,
    handoff_url,
    seller_message,
    state_for,
)
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.match import Assessor, Check
from app.match.schema import Assessment
from app.model_api import CostLedger, ModelApiClient
from app.profiles import Profiles
from tests.conftest import make_photo

pytestmark = pytest.mark.anyio


def test_the_handoff_is_a_search_link_with_the_title_and_the_top_price() -> None:
    url = handoff_url("https://example.org/marketplace/search/", "65 W laptop adapter", 25.0)
    assert url == "https://example.org/marketplace/search/?query=65+W+laptop+adapter&maxPrice=25"
    assert handoff_url("https://example.org/s/", "x", None) == "https://example.org/s/?query=x"
    assert handoff_url("https://example.org/s/", "x", 0) == "https://example.org/s/?query=x"


def assessment(verdict: str, checks: list[Check] | None = None) -> Assessment:
    return Assessment(
        profile="power_adapter",
        verdict=verdict,  # type: ignore[arg-type]
        summary="",
        checks=checks or [],
        questions=["What is the part number?"],
        missing=[],
        to_confirm=[],
        need_item=None,
        candidate_item=None,
    )


def check(status: str, hard: bool) -> Check:
    return Check(
        key="k",
        label="K",
        kind="equal",
        hard=hard,
        identity=False,
        status=status,  # type: ignore[arg-type]
        needed="x",
        observed="y",
        unit="",
        basis="",
    )


def test_the_ladder_maps_onto_the_candidate_states() -> None:
    assert state_for(assessment("EXACT_MATCH")) == "documented"
    assert state_for(assessment("COMPATIBLE_LIKELY")) == "documented"
    assert state_for(assessment("CONFLICT")) == "rejected"
    assert state_for(assessment("INSUFFICIENT_INFO")) == "needs_evidence"
    assert state_for(assessment("VISUALLY_SIMILAR", [check("unknown", True)])) == "needs_evidence"
    assert state_for(assessment("VISUALLY_SIMILAR", [check("fail", False)])) == "conflicting"


def test_the_seller_message_is_the_rules_questions_as_a_note() -> None:
    base: dict[str, Any] = {
        "id": 3,
        "search_id": 1,
        "source_kind": "text",
        "observed_on": "2026-10-01",
        "expires_on": "2026-10-15",
        "expired": False,
        "asking_price": "15",
        "currency": "USD",
        "location": "",
        "included_parts": "",
        "url": "",
        "title": "Orbital charger",
        "text": "",
        "note": "",
        "fields": {},
        "warnings": [],
        "assessment": None,
        "state": "needs_evidence",
        "questions": ["What is the part number?", "Is the centre positive?"],
        "model": "",
        "from_fixture": True,
        "cost_usd": 0.0,
        "created_at": "",
        "assessed_at": "",
    }
    note = seller_message(Candidate(**base))
    assert note.subject == "About your listing: Orbital charger"
    assert "1. What is the part number?" in note.message
    assert "2. Is the centre positive?" in note.message
    assert note.message.endswith("Is it still available, and when could I pick it up?")
    nothing = seller_message(Candidate(**{**base, "questions": [], "title": ""}))
    assert nothing.subject == "About your listing: the item"
    assert "answers everything I needed to check" in nothing.message


@pytest.fixture
def finder(recorded_settings: Settings) -> Finder:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    profiles = Profiles()
    return Finder(
        recorded_settings,
        client,
        inventory,
        profiles,
        Extractor(recorded_settings, client),
        Assessor(profiles, inventory),
    )


def laptop(inventory: Inventory) -> int:
    item = inventory.create(ItemCreate(item_type="laptop", name="Laptop", profile="power_adapter"))
    for field, value, unit in [
        ("output_voltage", "19.5", "V"),
        ("output_current", "3.33", "A"),
        ("polarity", "center positive", ""),
        ("plug_outer_diameter", "4.5", "mm"),
        ("plug_inner_diameter", "3.0", "mm"),
    ]:
        inventory.add_field(
            item.id, FieldCreate(field=field, value=value, unit=unit, provenance="documented")
        )
    return item.id


LISTING = (
    "Orbital 65W laptop charger, 19.5V 3.34A, centre positive barrel plug 4.5 x 3.0 mm."
    " Works, light wear, comes with the power cord. $15, Astoria."
)


def test_a_search_takes_its_profile_from_the_item_and_names_the_handoff(finder: Finder) -> None:
    need = laptop(finder.inventory)
    search = finder.create(
        SearchCreate(need_item_id=need, title="65 W laptop adapter", max_price=25, radius_km=10)
    )
    assert search.profile == "power_adapter" and search.status == "open"
    assert search.handoff_url.endswith("/marketplace/search/?query=65+W+laptop+adapter&maxPrice=25")
    assert search.candidates == 0 and search.radius_km == 10
    assert any(
        e.change == "search opened: 65 W laptop adapter" for e in finder.inventory.events(need)
    )
    assert [s.id for s in finder.searches()] == [search.id]
    closed = finder.update(search.id, SearchPatch(status="closed", notes="found one elsewhere"))
    assert closed.status == "closed" and closed.notes == "found one elsewhere"
    # the item's profile decides, whatever the request says beside it
    other = finder.create(SearchCreate(need_item_id=need, title="x", profile="vacuum_attachment"))
    assert other.profile == "power_adapter"


def test_a_search_without_a_profile_or_with_an_unknown_one_is_refused(finder: Finder) -> None:
    with pytest.raises(FindError, match="no profile"):
        finder.create(SearchCreate(title="something"))
    with pytest.raises(FindError, match="no profile 'toaster'"):
        finder.create(SearchCreate(title="something", profile="toaster"))
    with pytest.raises(LookupError):
        finder.create(SearchCreate(title="x", need_item_id=999))


async def test_a_text_candidate_is_read_assessed_and_dated(finder: Finder) -> None:
    need = laptop(finder.inventory)
    search = finder.create(SearchCreate(need_item_id=need, title="adapter"))
    candidate = await finder.add_candidate(
        search.id,
        CandidateCreate(text=LISTING, observed_on="2026-10-20", url="https://x.example/1"),
    )
    assert candidate.from_fixture and candidate.cost_usd == 0.0
    assert candidate.title.startswith("Orbital 65W laptop charger")
    assert (candidate.asking_price, candidate.currency, candidate.location) == (
        "15",
        "USD",
        "Astoria",
    )
    assert candidate.included_parts == "power cord" and candidate.url == "https://x.example/1"
    assert candidate.fields["output_voltage"].value == "19.5"
    assert candidate.fields["output_voltage"].source == "listing_text"
    assert candidate.fields["polarity"].value == "center positive"
    # a rule key the label set does not know is kept as read; a name neither knows is not
    assert candidate.fields["plug_outer_diameter"].value == "4.5"
    assert candidate.fields["plug_outer_diameter"].source == "listing_text"
    assert "colour" not in candidate.fields
    assert not any("does not know" in w for w in candidate.warnings)
    assert candidate.assessment is not None
    assert candidate.assessment.verdict == "COMPATIBLE_LIKELY"
    assert candidate.state == "documented"
    assert (candidate.observed_on, candidate.expires_on) == ("2026-10-20", "2026-11-03")
    assert candidate.expired is False
    assert finder.search(search.id).candidates == 1
    assert [c.id for c in finder.candidates(search.id)] == [candidate.id]


async def test_typed_values_are_the_owners_word_and_a_conflict_is_rejected(
    finder: Finder,
) -> None:
    need = laptop(finder.inventory)
    search = finder.create(SearchCreate(need_item_id=need, title="adapter"))
    manual = await finder.add_candidate(
        search.id,
        CandidateCreate(
            source_kind="manual",
            values={"output_voltage": "12 V", "polarity": "center positive"},
            observed_on="2026-01-05",
            asking_price="9",
        ),
    )
    assert manual.fields["output_voltage"].source == "user_edit"
    assert manual.state == "rejected" and manual.expired is True
    assert manual.assessment is not None and manual.assessment.verdict == "CONFLICT"
    # text with a typed value beside it: the typed value replaces what was read
    corrected = await finder.add_candidate(
        search.id, CandidateCreate(text=LISTING, values={"output_voltage": "12"})
    )
    assert corrected.fields["output_voltage"].value == "12"
    assert corrected.state == "rejected"
    questions = finder.questions(manual.id)
    assert questions.candidate_id == manual.id
    assert any("output current" in q.lower() for q in questions.questions)


async def test_a_screenshot_candidate_goes_through_the_extractor(finder: Finder) -> None:
    need = laptop(finder.inventory)
    search = finder.create(SearchCreate(need_item_id=need, title="adapter"))
    shot = await finder.add_candidate(
        search.id, CandidateCreate(source_kind="screenshot"), screenshot=make_photo()
    )
    assert shot.fields and all(e.source == "screenshot" for e in shot.fields.values())
    assert shot.assessment is not None and shot.title
    assert shot.state in ("documented", "needs_evidence", "conflicting", "rejected")


async def test_a_candidate_is_rechecked_against_the_need_as_it_stands(finder: Finder) -> None:
    need = laptop(finder.inventory)
    search = finder.create(SearchCreate(need_item_id=need, title="adapter"))
    candidate = await finder.add_candidate(search.id, CandidateCreate(text=LISTING))
    assert candidate.state == "documented"
    # the laptop turns out to need 12 V: the same listing now conflicts
    finder.inventory.add_field(
        need, FieldCreate(field="output_voltage", value="12", unit="V", provenance="documented")
    )
    again = finder.recheck(candidate.id)
    assert again.state == "rejected" and again.observed_on == candidate.observed_on
    assert again.assessed_at >= candidate.assessed_at
    gone = finder.withdraw(candidate.id)
    assert gone.state == "withdrawn"
    with pytest.raises(FindError, match="withdrawn"):
        finder.recheck(candidate.id)


async def test_a_search_from_values_needs_no_item(finder: Finder) -> None:
    search = finder.create(
        SearchCreate(
            profile="power_adapter",
            title="19.5 V adapter",
            spec={"output_voltage": "19.5", "polarity": "center positive"},
        )
    )
    assert search.need_item_id is None
    candidate = await finder.add_candidate(search.id, CandidateCreate(text=LISTING))
    assert candidate.assessment is not None
    # the need states two values; the other hard rules stay open, so it needs evidence
    assert candidate.assessment.verdict == "VISUALLY_SIMILAR"
    assert candidate.state == "needs_evidence" and candidate.questions == []


async def test_a_candidate_needs_its_source(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="power_adapter", title="adapter"))
    with pytest.raises(FindError, match="listing text"):
        await finder.add_candidate(search.id, CandidateCreate(text=""))
    with pytest.raises(FindError, match="screenshot"):
        await finder.add_candidate(search.id, CandidateCreate(source_kind="screenshot"))
    with pytest.raises(FindError, match="at least one value"):
        await finder.add_candidate(search.id, CandidateCreate(source_kind="manual"))
    finder.update(search.id, SearchPatch(status="closed"))
    with pytest.raises(FindError, match="closed"):
        await finder.add_candidate(
            search.id, CandidateCreate(source_kind="manual", values={"output_voltage": "19.5"})
        )
    finder.update(search.id, SearchPatch(status="found"))
    found = await finder.add_candidate(
        search.id, CandidateCreate(source_kind="manual", values={"output_voltage": "19.5"})
    )
    assert found.state != "withdrawn"
    with pytest.raises(ValueError, match="future"):
        CandidateCreate(text="x", observed_on="2999-01-01")
    with pytest.raises(ValueError, match="real date"):
        CandidateCreate(text="x", observed_on="2026-13-40")


def test_find_routes(recorded_client: TestClient) -> None:
    item = recorded_client.post(
        "/api/items", json={"item_type": "laptop", "profile": "power_adapter"}
    ).json()["id"]
    for field, value in (
        ("output_voltage", "19.5"),
        ("output_current", "3.33"),
        ("polarity", "center positive"),
        ("plug_outer_diameter", "4.5"),
        ("plug_inner_diameter", "3.0"),
    ):
        recorded_client.post(f"/api/items/{item}/fields", json={"field": field, "value": value})
    created = recorded_client.post(
        "/api/searches", json={"need_item_id": item, "title": "65 W adapter", "max_price": 25}
    )
    assert created.status_code == 201, created.text
    search = created.json()
    assert search["handoff_url"].endswith("query=65+W+adapter&maxPrice=25")
    assert recorded_client.get("/api/searches").json()[0]["id"] == search["id"]
    assert recorded_client.get(f"/api/searches/{search['id']}").json()["candidates"] == 0

    text = recorded_client.post(
        f"/api/searches/{search['id']}/candidates",
        data={"request": json.dumps({"text": LISTING, "observed_on": "2026-10-20"})},
    )
    assert text.status_code == 201, text.text
    candidate = text.json()
    assert candidate["state"] == "documented" and candidate["expires_on"] == "2026-11-03"
    shot = recorded_client.post(
        f"/api/searches/{search['id']}/candidates",
        data={"request": json.dumps({"source_kind": "screenshot"})},
        files=[("screenshot", ("listing.jpg", make_photo(), "image/jpeg"))],
    )
    assert shot.status_code == 201, shot.text
    assert len(recorded_client.get(f"/api/searches/{search['id']}/candidates").json()) == 2
    assert recorded_client.get(f"/api/candidates/{candidate['id']}").json()["id"] == candidate["id"]
    questions = recorded_client.get(f"/api/candidates/{candidate['id']}/questions")
    assert questions.status_code == 200 and questions.json()["subject"].startswith("About your")
    assert recorded_client.post(f"/api/candidates/{candidate['id']}/recheck").status_code == 200
    gone = recorded_client.post(f"/api/candidates/{candidate['id']}/withdraw")
    assert gone.json()["state"] == "withdrawn"
    assert recorded_client.post(f"/api/candidates/{candidate['id']}/recheck").status_code == 422
    closed = recorded_client.patch(f"/api/searches/{search['id']}", json={"status": "closed"})
    assert closed.json()["status"] == "closed"
    refused = recorded_client.post(
        f"/api/searches/{search['id']}/candidates",
        data={"request": '{"source_kind": "manual", "values": {"output_voltage": "19.5"}}'},
    )
    assert refused.status_code == 422 and "closed" in refused.json()["detail"]

    assert recorded_client.post("/api/searches", json={"title": "x"}).status_code == 422
    assert (
        recorded_client.post(
            "/api/searches", json={"title": " ", "profile": "power_adapter"}
        ).status_code
        == 422
    )
    assert recorded_client.get("/api/searches/999").status_code == 404
    assert (
        recorded_client.post("/api/searches", json={"title": "x", "need_item_id": 999}).status_code
        == 404
    )
    assert recorded_client.get("/api/candidates/999").status_code == 404
    bad = recorded_client.post(
        f"/api/searches/{search['id']}/candidates", data={"request": json.dumps({"text": ""})}
    )
    assert bad.status_code == 422
    malformed = recorded_client.post(
        f"/api/searches/{search['id']}/candidates", data={"request": "{not json"}
    )
    assert malformed.status_code == 422


def test_a_text_candidate_without_a_recorded_answer_is_a_503(client: TestClient) -> None:
    search = client.post("/api/searches", json={"profile": "power_adapter", "title": "x"}).json()
    res = client.post(
        f"/api/searches/{search['id']}/candidates", data={"request": json.dumps({"text": "y"})}
    )
    assert res.status_code == 503


def test_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/searches",
        "/api/searches/{search_id}/candidates",
        "/api/candidates/{candidate_id}/questions",
    ):
        assert path in paths
