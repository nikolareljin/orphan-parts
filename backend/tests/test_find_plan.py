import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extract import Extractor
from app.find import (
    Finder,
    FindError,
    ListingsBack,
    PatternError,
    PatternTest,
    PlanEdit,
    SearchCreate,
    SearchPatch,
    handoff_url,
    score_listing,
    validate_pattern,
)
from app.find.plan import MAX_PATTERN_LEN, SCAN_MAX, clean_exclusions, price_of
from app.find.schema import Phrasing
from app.find.service import clean_phrasings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import demo_allowed, expensive
from app.profiles import Profiles
from tests.conftest import RECORDED_FIXTURES, make_photo

pytestmark = pytest.mark.anyio

EXAMPLE = r"OP-?065-?19-?333|19\.5\s*V.{0,20}3\.3\d?\s*A"
FITS = "Orbital 65W laptop charger, 19.5V 3.34A, barrel plug 4.5 x 3.0 mm. Works. $15, Astoria."
WRONG = "Laptop charger 20V 3.25A, works fine, $8"
PARTS = "Orbital charger OP065-19-333, for parts, cord frayed, $5"


def test_the_example_pattern_is_accepted_and_case_insensitive() -> None:
    compiled = validate_pattern(EXAMPLE)
    assert compiled.search("model op065-19-333")
    assert compiled.search("19.5 v  3.34 a")
    assert not compiled.search("20V 3.25A")


@pytest.mark.parametrize(
    "pattern",
    [
        "(a+)+",
        "(.*)*",
        r"(\w+\s?)*",
        "(a|aa)+",
        r"(?:\d+-)+x",
        "(a{2,})+",
        "((ab)*c)+",
        "(a|b){2,5}",
        ".*charger",
        "charger.+",
        r"\d+\d+",
        r"\s*\s+",
        r"a\d+b\d+c\d+d\d+e\d+f\d+g\d+",
    ],
)
def test_shapes_that_run_away_are_refused(pattern: str) -> None:
    with pytest.raises(PatternError):
        validate_pattern(pattern)


def test_long_empty_broken_and_backreferencing_patterns_are_refused() -> None:
    with pytest.raises(PatternError, match="longer than 300"):
        validate_pattern("a" * (MAX_PATTERN_LEN + 1))
    validate_pattern("a" * MAX_PATTERN_LEN)
    with pytest.raises(PatternError, match="empty"):
        validate_pattern("   ")
    with pytest.raises(PatternError, match="compile"):
        validate_pattern("(abc")
    with pytest.raises(PatternError, match="compile"):
        validate_pattern("abc)")
    with pytest.raises(PatternError, match="backreference"):
        validate_pattern(r"(a)\1")
    with pytest.raises(PatternError, match="backreference"):
        validate_pattern("(?P<x>a)(?P=x)")
    with pytest.raises(PatternError, match="every listing"):
        validate_pattern(r"\d*")


def test_safe_shapes_pass() -> None:
    for pattern in (
        r"(?:op)?-?065",
        r"[+*]{1,3}",  # quantifier characters inside a class are literals
        r"(foo|bar)?\s*baz",
        r"(?:dvi|dual)[-\s]?link",
        r"\bDVI-?D\b.{0,30}(?:6|10)\s?(?:ft|feet)",
        r"a{3}b",
    ):
        validate_pattern(pattern)


def test_an_accepted_pattern_stays_fast_on_text_that_nearly_matches() -> None:
    compiled = validate_pattern(r"\w+x\s*y\d+z")
    hostile = "a" * (SCAN_MAX * 3)
    started = time.monotonic()
    score = score_listing(hostile, compiled, [], None)
    assert time.monotonic() - started < 2.0
    assert score.matched is False


def test_scoring_ranks_by_pattern_exclusions_and_price() -> None:
    compiled = validate_pattern(EXAMPLE)
    words = clean_exclusions(["For  Parts", "broken", "for parts", " ", "not working"])
    assert words == ["for parts", "broken", "not working"]
    fits = score_listing(FITS, compiled, words, 20)
    assert fits.verdict == "fits" and fits.matched and fits.price == 15 and fits.price_ok
    match = next(h for h in fits.hits if h.kind == "match")
    assert FITS[match.start : match.end] == match.text == "19.5V 3.34A"
    assert "matches the pattern" in fits.reasons
    maybe = score_listing(WRONG, compiled, words, 20)
    assert maybe.verdict == "maybe" and maybe.matched is False
    ruled_out = score_listing(PARTS, compiled, words, 20)
    assert ruled_out.verdict == "no" and ruled_out.excluded == ["for parts"]
    assert {h.kind for h in ruled_out.hits} == {"match", "excluded"}
    assert ruled_out.reasons[0] == 'says "for parts"'
    dear = score_listing(FITS, compiled, words, 10)
    assert dear.verdict == "no" and dear.price_ok is False
    assert "over the limit of $10" in dear.reasons[0]
    # no pattern yet: nothing fits, the exclusions and the price still apply
    assert score_listing(FITS, None, words, 20).verdict == "maybe"
    assert score_listing(PARTS, None, words, 20).verdict == "no"
    # a word inside another word is not the word
    assert score_listing("unbroken seal", None, ["broken"], None).excluded == []


def test_prices_are_read_as_dollars() -> None:
    assert price_of("asking $1,200 obo") == 1200
    assert price_of("$ 9.50 firm") == 9.5
    assert price_of("40 bucks") == 40
    assert price_of("free to a good home") == 0
    assert price_of("6 ft cable") is None


def test_search_links_are_encoded_one_per_phrasing() -> None:
    base = "https://www.facebook.com/marketplace/search/"
    url = handoff_url(base, 'DVI-D "dual link" & 6 ft', 10)
    query = parse_qs(urlparse(url).query)
    assert query == {"query": ['DVI-D "dual link" & 6 ft'], "maxPrice": ["10"]}
    assert "&+6" not in url and "%26" in url
    kept = clean_phrasings(
        [
            Phrasing(text="  dvi-d   cable ", why="plain"),
            Phrasing(text="DVI-D cable", why="again"),
            Phrasing(text="", why="empty"),
        ],
        "DVI-D dual link cable",
        base,
        None,
    )
    assert [p.text for p in kept] == ["dvi-d cable", "DVI-D dual link cable"]
    assert kept[0].url == f"{base}?query=dvi-d+cable"
    many = clean_phrasings([Phrasing(text=f"p{i}", why="") for i in range(9)], "t", base, 5)
    assert len(many) == 6 and all(p.url.endswith("maxPrice=5") for p in many)


def test_the_plan_and_the_screenshots_and_check_fit_are_counted_as_spending() -> None:
    assert expensive("POST", "/api/searches/3/plan")
    assert expensive("POST", "/api/searches/3/listings/screenshots")
    assert expensive("POST", "/api/searches/3/listings/2/check")
    assert not expensive("PATCH", "/api/searches/3/plan")
    assert not expensive("POST", "/api/searches/3/listings")
    assert not expensive("POST", "/api/find/pattern")
    assert not demo_allowed("POST", "/api/searches/3/plan")
    assert not demo_allowed("POST", "/api/searches/3/listings")


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


async def test_the_recorded_plan_is_kept_and_ranks_what_comes_back(finder: Finder) -> None:
    search = finder.create(
        SearchCreate(
            profile="power_adapter", title="65 W laptop adapter", max_price=20, radius_km=15
        )
    )
    planned = await finder.plan(search.id)
    plan = planned.plan
    assert plan is not None and plan.from_fixture and plan.cost_usd == 0.0
    assert 3 <= len(plan.phrasings) <= 6
    assert plan.phrasings[1].text == "Orbital OP065-19-333"
    assert plan.phrasings[1].url.endswith("?query=Orbital+OP065-19-333&maxPrice=20")
    assert all(p.why for p in plan.phrasings)
    assert plan.pattern == EXAMPLE and plan.pattern_error == ""
    assert plan.exclusions[:2] == ["for parts", "parts only"] and "frayed" in plan.exclusions
    assert plan.exclusions.count("broken") == 1
    assert plan.radius_km == 15 and plan.max_price == 20
    ranked = finder.add_listings(
        search.id, ListingsBack(texts=[PARTS, WRONG, FITS], observed_on="2026-10-20")
    )
    assert [b.score.verdict for b in ranked] == ["fits", "maybe", "no"]
    assert ranked[0].text == FITS and ranked[0].observed_on == "2026-10-20"
    assert finder.search(search.id).listings == 3
    # the owner's pattern: kept after the check, and every listing scored again by it
    edited = finder.edit_plan(search.id, PlanEdit(pattern=r"20\s?V", exclusions=["frayed"]))
    assert edited.plan is not None and edited.plan.edited_at
    again = finder.listings(search.id)
    assert again[0].text == WRONG and again[0].score.verdict == "fits"
    assert next(b for b in again if b.text == PARTS).score.verdict == "no"
    with pytest.raises(FindError, match=r"\(a\+\)\+"):
        finder.edit_plan(search.id, PlanEdit(pattern="(a+)+"))
    # Check fit: one reading, the rules' verdict, the same candidate when asked again
    candidate = await finder.check_listing(search.id, again[0].id)
    assert candidate.assessment is not None
    assert finder.listings(search.id)[0].candidate_id == candidate.id
    assert (await finder.check_listing(search.id, again[0].id)).id == candidate.id
    left = finder.remove_listing(search.id, again[-1].id)
    assert len(left) == 2
    with pytest.raises(LookupError):
        finder.remove_listing(search.id, 999)
    finder.update(search.id, SearchPatch(status="closed"))
    with pytest.raises(FindError, match="closed"):
        finder.add_listings(search.id, ListingsBack(texts=[FITS]))


async def test_a_pattern_written_by_hand_needs_no_plan_call(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="generic_item", title="DVI-D dual link cable"))
    edited = finder.edit_plan(search.id, PlanEdit(pattern=r"dual[-\s]?link"))
    assert edited.plan is not None and edited.plan.model == ""
    assert [p.text for p in edited.plan.phrasings] == ["DVI-D dual link cable"]
    tried = finder.test_pattern(PatternTest(pattern="(.*)*", text="x"))
    assert tried.score is None and "refused" in tried.error
    line = finder.test_pattern(
        PatternTest(pattern="dual link", exclusions=["vga"], text="Dual link DVI, $4", max_price=10)
    )
    assert line.error == "" and line.score is not None and line.score.verdict == "fits"


async def test_a_written_pattern_that_fails_the_checks_is_not_kept(
    settings: Settings,
) -> None:
    folder = settings.fixtures_dir / "responses"
    folder.mkdir(parents=True)
    recorded = json.loads((RECORDED_FIXTURES / "responses" / "search-plan.json").read_text())
    text = json.loads(recorded["response"]["output"][1]["content"][0]["text"])
    text |= {"pattern": r"(\w+\s?)*charger", "exclusions": []}
    recorded["response"]["output"][1]["content"][0]["text"] = json.dumps(text)
    (folder / "search-plan.json").write_text(json.dumps(recorded))
    inventory = Inventory(settings)
    client = ModelApiClient(settings, CostLedger(cap_usd=25.0))
    profiles = Profiles()
    finder = Finder(
        settings,
        client,
        inventory,
        profiles,
        Extractor(settings, client),
        Assessor(profiles, inventory),
    )
    search = finder.create(SearchCreate(profile="power_adapter", title="adapter"))
    plan = (await finder.plan(search.id)).plan
    assert plan is not None and plan.pattern == ""
    assert "was refused" in plan.pattern_error and "repeats inside" in plan.pattern_error
    assert plan.exclusions == ["for parts", "parts only", "broken", "not working", "does not work"]


def test_plan_and_listing_routes(recorded_client: TestClient) -> None:
    search = recorded_client.post(
        "/api/searches", json={"profile": "power_adapter", "title": "65 W adapter", "max_price": 20}
    ).json()
    sid = search["id"]
    assert search["plan"] is None and search["listings"] == 0
    planned = recorded_client.post(f"/api/searches/{sid}/plan")
    assert planned.status_code == 200, planned.text
    assert planned.json()["plan"]["pattern"] == EXAMPLE
    bad = recorded_client.patch(f"/api/searches/{sid}/plan", json={"pattern": "x" * 301})
    assert bad.status_code == 422 and "300" in bad.json()["detail"]
    tried = recorded_client.post(
        "/api/find/pattern", json={"pattern": EXAMPLE, "text": FITS, "max_price": 20}
    ).json()
    assert tried["error"] == "" and tried["score"]["verdict"] == "fits"
    assert tried["score"]["highlights"][0]["text"] == "19.5V 3.34A"
    added = recorded_client.post(
        f"/api/searches/{sid}/listings", json={"texts": [WRONG, FITS, " "]}
    )
    assert added.status_code == 201, added.text
    assert [b["score"]["verdict"] for b in added.json()] == ["fits", "maybe"]
    assert recorded_client.get(f"/api/searches/{sid}").json()["listings"] == 2
    shots = recorded_client.post(
        f"/api/searches/{sid}/listings/screenshots",
        files=[("screenshots", ("one.jpg", make_photo(), "image/jpeg"))],
        data={"observed_on": "2026-10-21"},
    )
    assert shots.status_code == 201, shots.text
    shot = next(b for b in shots.json() if b["source_kind"] == "screenshot")
    assert shot["observed_on"] == "2026-10-21" and shot["text"]
    future = recorded_client.post(
        f"/api/searches/{sid}/listings/screenshots",
        files=[("screenshots", ("one.jpg", make_photo(), "image/jpeg"))],
        data={"observed_on": "2999-01-01"},
    )
    assert future.status_code == 422
    first = added.json()[0]["id"]
    checked = recorded_client.post(f"/api/searches/{sid}/listings/{first}/check")
    assert checked.status_code == 200, checked.text
    assert checked.json()["assessment"] is not None
    assert recorded_client.post(f"/api/searches/{sid}/listings/999/check").status_code == 404
    assert recorded_client.delete(f"/api/searches/{sid}/listings/999").status_code == 404
    gone = recorded_client.delete(f"/api/searches/{sid}/listings/{first}")
    assert gone.status_code == 200 and len(gone.json()) == 2
    assert (
        recorded_client.post(f"/api/searches/{sid}/listings", json={"texts": []}).status_code == 422
    )
    assert recorded_client.post("/api/searches/999/plan").status_code == 404
    paths = recorded_client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/searches/{search_id}/plan",
        "/api/searches/{search_id}/listings",
        "/api/searches/{search_id}/listings/{listing_id}/check",
        "/api/find/pattern",
    ):
        assert path in paths


def test_the_brief_carries_the_need_and_nothing_that_identifies_the_item(finder: Finder) -> None:
    item = finder.inventory.create(
        ItemCreate(item_type="laptop", name="Laptop", profile="power_adapter")
    )
    for field, value in (("output_voltage", "19.5"), ("serial_number", "SN-PRIVATE-1")):
        finder.inventory.add_field(
            item.id, FieldCreate(field=field, value=value, provenance="documented")
        )
    search = finder.create(
        SearchCreate(
            need_item_id=item.id,
            title="65 W adapter",
            spec={"output_current": "3.33"},
            max_price=20,
            notes="the barrel plug is 4.5 mm",
        )
    )
    brief = finder.plan_brief(search)
    assert "Needed: 65 W adapter" in brief and "output current 3.33" in brief
    assert "output voltage 19.5" in brief and "Top price: 20 USD" in brief
    assert "barrel plug is 4.5 mm" in brief and "SN-PRIVATE-1" not in brief
