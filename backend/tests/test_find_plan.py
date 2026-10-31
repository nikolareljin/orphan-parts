import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.extract import Extractor
from app.find import (
    BusyError,
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
from app.find.plan import MAX_PATTERN_LEN, SCAN_MAX, clean_exclusions, money, price_of
from app.find.schema import Phrasing
from app.find.schema import SearchPlan as PlanModel
from app.find.service import MAX_LISTINGS, clean_phrasings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.main import create_app
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient
from app.ops.gate import demo_allowed, expensive
from app.profiles import Profiles
from tests.conftest import RECORDED_FIXTURES, make_photo
from tests.test_gate import CODE, gated_settings

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


# Patterns that freeze a backtracking engine on text that nearly matches, each with the unit
# its adversarial text repeats: open repeats side by side, optional separators between them,
# [\s\S]+, bounded repeats nested or in a row, the .{0,40} gaps.
ADVERSARIAL = [
    (r"\w+a\w+a\w+x", "a"),
    (r"\w+a\w+x", "a"),
    (r"\d+[.]?\d+[.]?\d+x", "1"),
    (r"\w+\s?\w+\s?\w+!", "a"),
    (r"\w+\s?\w+!", "a"),
    (r"\w*a\w*a\w*a\w*x", "a"),
    (r"[\s\S]+a[\s\S]+a[\s\S]+x", "a"),
    (r"[^\n]+a[^\n]+a[^\n]+x", "a"),
    (r"(?:\w+)a(?:\w+)a(?:\w+)x", "a"),
    (r"(?:\w+a){3}x", "a"),
    (r"(?:a|a){0,30}b", "a"),
    (r"(a{0,30}){0,30}b", "a"),
    (r"(?:a{1,10}){1,10}x", "a"),
    (r"\w{0,99}\w{0,99}\w{0,99}x", "a"),
    (r"\w{0,999}\w{0,999}\w{0,999}x", "a"),
    (r"\w{0,9999}\w{0,9999}x", "a"),
    (r"\w{0,4000}a\w{0,4000}a\w{0,4000}x", "a"),
    (r"[a-z]{1,40}[a-z]{1,40}[a-z]{1,40}[a-z]{1,40}x", "a"),
    (r"(?=\w+a\w+a\w+x)", "a"),
    (r"\w+?a\w+?a\w+?x", "a"),
    (r"\w++a\w++x", "a"),
    (r"[^x]+a[^x]+a[^x]+y", "a"),
    (r"\S+-\S+-\S+-\S+z", "a-"),
    (r"a+b?a+b?a+b?x", "a"),
    (r"\w{1,}a\w{1,}a\w{1,}x", "a"),
    (r"(?:a|\w){0,50}x", "a"),
    (r"(?:\w{0,40}\s?){0,5}x", "a"),
    (r"(?:[a-z]\d?){0,60}x", "a"),
    (r"\d+\.?\d*\s?v", "1"),
    (r"\d+\.?\d*\s?v.{0,20}\d+\.?\d*\s?a", "1"),
    (r"\d+\s?\d+\s?\d+w", "1"),
    (r"\d+\s?\d+w", "1 "),
    (r"[a-z ]+charger[a-z ]+adapter", "charger "),
    (r"\w+\W?\w+x", "a"),
    (r"\d+-?\d+-?\d+-?\d+x", "1"),
    (r"\d.{0,40}\d.{0,40}\d.{0,40}\d.{0,40}x", "1"),
    (r".{0,60}.{0,60}.{0,60}x", "a"),
]

_TIMING = """
import json, sys, time
from app.find.plan import PatternError, score_listing, validate_pattern
for pattern, unit in json.loads(sys.argv[1]):
    try:
        compiled = validate_pattern(pattern)
    except PatternError:
        print(json.dumps([pattern, None]), flush=True)
        continue
    text = (unit * 4000)[:4000]
    started = time.perf_counter()
    score_listing(text, compiled, ["for parts", "broken"], None)
    print(json.dumps([pattern, time.perf_counter() - started]), flush=True)
"""


def test_every_adversarial_pattern_is_refused_or_answers_in_linear_time() -> None:
    # in a child process: a backtracking engine holds the interpreter until it is killed
    try:
        run = subprocess.run(
            [sys.executable, "-c", _TIMING, json.dumps(ADVERSARIAL)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).resolve().parents[1],
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        done = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        pytest.fail(f"a pattern ran for more than 30 s on 4,000 characters, after: {done[-300:]}")
    timings = dict(json.loads(line) for line in run.stdout.splitlines())
    assert set(timings) == {p for p, _ in ADVERSARIAL}
    slow = {p: t for p, t in timings.items() if t is not None and t > 0.2}
    assert slow == {}
    # the shapes that froze the backtracking engine are accepted now, and quick
    for pattern in (r"\w+a\w+x", r"\d+-?\d+-?\d+-?\d+x", r"[\s\S]+a[\s\S]+a[\s\S]+x"):
        assert timings[pattern] is not None
    # counted repeats that expand too far are refused
    assert timings[r"(a{0,30}){0,30}b"] is None
    assert timings[r"\w{0,999}\w{0,999}\w{0,999}x"] is None


@pytest.mark.parametrize(
    ("pattern", "why"),
    [
        ("(?=charger)", "lookahead"),
        ("(?!broken)charger", "lookahead"),
        ("(?<=19.5)V", "lookbehind"),
        ("(?<!not )working", "lookbehind"),
        (r"(a)\1", "backreference"),
        ("(?P<x>a)(?P=x)", "backreference"),
        ("(?#a comment)charger", "comments"),
        ("(?x) char ger", "inline flags"),
        ("(?s)a.b", "inline flags"),
        ("(?i:dvi)", "inline flags"),
        ("(?-i)DVI", "inline flags"),
        (r"\Cx", "any byte"),
        (r"\w{0,999}x", "expand past"),
        (r"(a{0,30}){0,30}b", "expand past"),
        (r"(?:\w{0,20}\s){1,30}x", "expand past"),
        (r"\w++x", "compile"),
        (r"\x{61}{999}", "expand past"),
        (r"(\x{1}{300}){2}", "expand past"),
    ],
)
def test_what_the_engine_lacks_or_could_expand_is_refused_with_a_reason(
    pattern: str, why: str
) -> None:
    with pytest.raises(PatternError, match=why):
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
        # refused by the old checks, harmless on a linear-time engine
        "(a+)+",
        ".*charger",
        r"\d+\d+",
        r"(\w+\s?)*charger",
        "(?i)dvi",
        r"\pL+ cable",
        r"(?:\w{0,40}\s?){0,5}x",
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


def test_offsets_count_code_points_as_the_highlighting_does() -> None:
    plug = chr(0x1F50C)  # one code point, two UTF-16 units, four UTF-8 bytes
    text = f"{plug}{plug} DVI-D dual link, for parts"
    score = score_listing(text, validate_pattern("dvi-d"), ["for parts"], None)
    match = next(h for h in score.hits if h.kind == "match")
    excluded = next(h for h in score.hits if h.kind == "excluded")
    assert (match.start, match.end) == (3, 8) and text[match.start : match.end] == "DVI-D"
    assert text[excluded.start : excluded.end] == excluded.text == "for parts"


def test_exclusions_match_any_case_and_whole_words_only() -> None:
    capitals = score_listing("Orbital charger, FOR PARTS ONLY", None, ["for parts"], None)
    assert capitals.verdict == "no" and capitals.excluded == ["for parts"]
    assert capitals.hits[0].text == "FOR PARTS"
    assert score_listing("brokenly honest seller", None, ["broken"], None).excluded == []
    assert score_listing("unbroken seal", None, ["broken"], None).excluded == []
    assert score_listing("screen broken.", None, ["broken"], None).excluded == ["broken"]
    spaced = "sold for" + chr(0xA0) + "parts"
    assert score_listing(spaced, None, ["for parts"], None).excluded == ["for parts"]


def test_only_the_first_scan_max_characters_are_read() -> None:
    compiled = validate_pattern("dvi-d")
    assert score_listing("x" * (SCAN_MAX - 5) + "DVI-D", compiled, [], None).matched
    beyond = "x" * SCAN_MAX + " DVI-D for parts $5"
    late = score_listing(beyond, compiled, ["for parts"], 1)
    assert late.matched is False and late.excluded == [] and late.price is None


def test_a_price_at_the_limit_fits_and_zero_is_no_limit() -> None:
    compiled = validate_pattern("dvi")
    at = score_listing("DVI cable $20", compiled, [], 20)
    assert at.verdict == "fits" and at.price_ok is True
    assert "$20 is within the limit" in at.reasons
    assert score_listing("DVI cable $20.01", compiled, [], 20).verdict == "no"
    unlimited = score_listing("DVI cable $900", compiled, [], 0)
    assert unlimited.verdict == "fits" and unlimited.price_ok is None
    dear = score_listing("Desk, $1,200,000", None, [], 1000)
    assert dear.reasons == ["asks $1,200,000, over the limit of $1,000"]
    assert money(1_200_000.0) == "$1,200,000" and money(9.5) == "$9.50"


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
    assert price_of("FREE, pick up today") == 0
    assert price_of("6 ft cable") is None
    # a k after the number is thousands
    assert price_of("$1.2k firm") == 1200
    assert price_of("1.5k usd") == 1500
    assert price_of("$5 kit included") == 5
    # free of something, or something else free, is not a price; a number wins over free
    for text in ("smoke-free", "pet free", "smoke-free home", "free shipping", "free delivery"):
        assert price_of(text) is None, text
    assert price_of("free home delivery") is None
    assert price_of("free delivery, $30") == 30
    # another dollar is not a US one
    assert price_of("CA$30") is None
    assert price_of("US$30") == 30
    # the first amount is the asking one: a listing states it first
    assert price_of("$40, $10 off if you pick up today") == 40
    assert price_of("$20 (retail $50)") == 20
    assert price_of("$45 each or 2 for $80") == 45
    assert price_of("2 batteries $60 (will sell separately for $35)") == 60
    # a number in groups of three after a space is not guessed at
    assert price_of("$1 200") is None
    assert price_of("1 200 dollars") is None
    assert price_of("$15 100W charger") == 15


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
    with pytest.raises(FindError, match="comments"):
        finder.edit_plan(search.id, PlanEdit(pattern="(?#x)20V"))
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
    tried = finder.test_pattern(PatternTest(pattern="(?x)dual link", text="x"))
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
    text |= {"pattern": r"(?=charger)\w+", "exclusions": []}
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
    assert "was refused" in plan.pattern_error and "lookahead" in plan.pattern_error
    assert plan.exclusions == ["for parts", "parts only", "broken", "not working", "does not work"]
    # a refused pattern never empties one already kept, the owner's or a plan's
    finder._keep_plan(search.id, plan.model_copy(update={"pattern": "adapter"}))
    again = (await finder.plan(search.id)).plan
    assert again is not None and again.pattern == "adapter" and "was refused" in again.pattern_error
    finder.edit_plan(search.id, PlanEdit(pattern=r"19\.5\s?V"))
    mine = (await finder.plan(search.id)).plan
    assert mine is not None and mine.pattern == r"19\.5\s?V" and mine.suggested_pattern == ""


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


def test_listings_are_kept_trimmed_and_capped_checked_ones_last_to_go(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="generic_item", title="DVI-D cable"))
    first = finder.add_listings(search.id, ListingsBack(texts=["DVI-D " + "y" * SCAN_MAX]))
    assert len(first[0].text) == SCAN_MAX
    finder._remember_candidate(search.id, first[0].id, 77)
    for batch in range(3):
        finder.add_listings(
            search.id, ListingsBack(texts=[f"cable {batch}-{i} $3" for i in range(20)])
        )
    kept = finder.listings(search.id)
    assert len(kept) == MAX_LISTINGS == 50
    ids = {b.id for b in kept}
    # 61 in all: the checked one stays, the eleven oldest unchecked go
    assert first[0].id in ids and not ids & set(range(2, 13)) and 13 in ids
    assert finder.search(search.id).listings == MAX_LISTINGS
    # every one kept is checked: the one just brought back still stays, the oldest checked goes
    for b in kept:
        finder._remember_candidate(search.id, b.id, 78)
    oldest = min(b.id for b in kept)
    latest = finder.add_listings(search.id, ListingsBack(texts=["DVI-D new $4"]))
    ids = {b.id for b in latest}
    assert len(ids) == MAX_LISTINGS and max(ids) == 62 and oldest not in ids


def test_a_pattern_saved_while_listings_come_in_loses_neither(
    finder: Finder, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = finder.create(SearchCreate(profile="generic_item", title="DVI-D cable"))
    finder.edit_plan(search.id, PlanEdit(pattern="dvi"))
    real = finder.inventory.update_search

    def slow(search_id: int, status: str, content: str) -> object:
        time.sleep(0.05)  # both read before either writes, unless the search is locked
        return real(search_id, status, content)

    monkeypatch.setattr(finder.inventory, "update_search", slow)
    start = threading.Barrier(2)

    def patch() -> None:
        start.wait()
        finder.edit_plan(search.id, PlanEdit(pattern=r"dual[-\s]?link"))

    def post() -> None:
        start.wait()
        finder.add_listings(search.id, ListingsBack(texts=["dual link DVI-D, $5"]))

    threads = [threading.Thread(target=patch), threading.Thread(target=post)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    after = finder.search(search.id)
    assert after.plan is not None and after.plan.pattern == r"dual[-\s]?link"
    assert after.listings == 1


def test_each_screenshot_is_counted_against_the_allowance(tmp_path: Path) -> None:
    settings = gated_settings(
        tmp_path, fixtures_dir=RECORDED_FIXTURES, demo_visitor_calls_per_hour=3
    )
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        made = c.post("/api/searches", json={"profile": "generic_item", "title": "cable"})
        url = f"/api/searches/{made.json()['id']}/listings/screenshots"

        def shots(n: int) -> list[tuple[str, tuple[str, bytes, str]]]:
            return [("screenshots", (f"{i}.jpg", make_photo(), "image/jpeg")) for i in range(n)]

        four = c.post(url, files=shots(4))
        assert four.status_code == 429 and "4 screenshots are 4 readings" in four.json()["detail"]
        # refused whole: nothing counted, the one the gate took given back
        assert c.get("/readyz").json()["demo"]["daily_used"] == 0
        two = c.post(url, files=shots(2))
        assert two.status_code == 201, two.text
        assert c.get("/readyz").json()["demo"]["daily_used"] == 2
        assert c.post(url, files=shots(2)).status_code == 429
        assert c.post(url, files=shots(1)).status_code == 201
        assert c.get("/readyz").json()["demo"]["daily_used"] == 3


def test_several_prices_either_side_of_the_limit_leave_the_price_undecided() -> None:
    compiled = validate_pattern("battery|charger|cable")
    cases = {
        "charger $40, $10 off if you pick up today": (30, 40, [10, 40]),
        "charger $20 (retail $50)": (30, 20, [20, 50]),
        "cable $45 each or 2 for $80": (50, 45, [45, 80]),
        "2 battery packs $60 (will sell separately for $35)": (50, 60, [35, 60]),
    }
    for text, (limit, first, stated) in cases.items():
        score = score_listing(text, compiled, [], limit)
        assert score.price == first, text
        assert score.verdict == "maybe" and score.price_ok is None, text
        assert "states several prices" in score.reasons[0], text
        assert all(f"${a}" in score.reasons[0] for a in stated), text
    # all on one side: the price decides as before
    assert score_listing("charger $20 (retail $30)", compiled, [], 50).verdict == "fits"
    assert score_listing("charger $60 (retail $90)", compiled, [], 50).verdict == "no"
    # an exclusion word still rules it out
    assert (
        score_listing("charger $40, $60 new, for parts", compiled, ["for parts"], 50).verdict
        == "no"
    )


async def test_screenshots_are_kept_as_they_are_read(
    finder: Finder, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = finder.create(SearchCreate(profile="generic_item", title="DVI-D cable"))
    reads = 0

    async def extract(shots: list[bytes]) -> SimpleNamespace:
        nonlocal reads
        reads += 1
        if reads == 2:
            raise RuntimeError("cut off")
        return SimpleNamespace(label_text=f"DVI-D cable {reads}, $4", fields={})

    monkeypatch.setattr(finder.extractor, "extract", extract)
    with pytest.raises(RuntimeError):
        await finder.add_screenshots(search.id, [b"a", b"b", b"c"], "")
    kept = finder.listings(search.id)
    assert [b.text for b in kept] == ["DVI-D cable 1, $4"]


def test_listing_ids_are_never_given_again(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="generic_item", title="DVI-D cable"))
    added = finder.add_listings(search.id, ListingsBack(texts=["one $1", "two $2"]))
    newest = max(b.id for b in added)
    finder.remove_listing(search.id, newest)
    again = finder.add_listings(search.id, ListingsBack(texts=["three $3"]))
    assert max(b.id for b in again) == newest + 1
    assert finder.search(search.id).listings == 2


async def test_check_fit_twice_at_once_reads_the_listing_once(
    finder: Finder, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = finder.create(SearchCreate(profile="power_adapter", title="65 W adapter"))
    listing = finder.add_listings(search.id, ListingsBack(texts=[FITS]))[0]
    real = finder.add_candidate
    calls = 0

    async def slow(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return await real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(finder, "add_candidate", slow)
    first, second = await asyncio.gather(
        finder.check_listing(search.id, listing.id),
        finder.check_listing(search.id, listing.id),
        return_exceptions=True,
    )
    assert calls == 1
    assert sorted(type(r).__name__ for r in (first, second)) == ["BusyError", "Candidate"]
    made = first if isinstance(second, BusyError) else second
    assert (await finder.check_listing(search.id, listing.id)).id == made.id  # type: ignore[union-attr]
    assert calls == 1


async def test_a_failed_check_fit_frees_the_listing(
    finder: Finder, monkeypatch: pytest.MonkeyPatch
) -> None:
    search = finder.create(SearchCreate(profile="power_adapter", title="65 W adapter"))
    listing = finder.add_listings(search.id, ListingsBack(texts=[FITS]))[0]
    real = finder.add_candidate

    async def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("no answer")

    monkeypatch.setattr(finder, "add_candidate", broken)
    with pytest.raises(RuntimeError):
        await finder.check_listing(search.id, listing.id)
    monkeypatch.setattr(finder, "add_candidate", real)
    assert (await finder.check_listing(search.id, listing.id)).assessment is not None


async def test_planning_again_keeps_the_owners_pattern_and_offers_the_new_one(
    finder: Finder,
) -> None:
    search = finder.create(SearchCreate(profile="power_adapter", title="65 W adapter"))
    first = (await finder.plan(search.id)).plan
    assert first is not None and first.pattern == EXAMPLE and first.suggested_pattern == ""
    finder.edit_plan(search.id, PlanEdit(pattern=r"20\s?V", exclusions=["frayed"]))
    again = (await finder.plan(search.id)).plan
    assert again is not None and again.pattern == r"20\s?V" and again.exclusions == ["frayed"]
    assert again.suggested_pattern == EXAMPLE and again.edited_at
    assert PlanModel(**again.model_dump()).suggested_pattern == EXAMPLE
    # saving clears the offer
    saved = finder.edit_plan(search.id, PlanEdit(pattern=EXAMPLE)).plan
    assert saved is not None and saved.suggested_pattern == ""


def test_refused_screenshot_requests_cost_nothing(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        made = c.post("/api/searches", json={"profile": "generic_item", "title": "cable"}).json()
        photo = ("screenshots", ("p.jpg", make_photo(), "image/jpeg"))
        seven = c.post(f"/api/searches/{made['id']}/listings/screenshots", files=[photo] * 7)
        assert seven.status_code == 422
        unknown = c.post("/api/searches/999/listings/screenshots", files=[photo])
        assert unknown.status_code == 404
        c.patch(f"/api/searches/{made['id']}", json={"status": "closed"})
        closed = c.post(f"/api/searches/{made['id']}/listings/screenshots", files=[photo] * 2)
        assert closed.status_code == 422 and "closed" in closed.json()["detail"]
        assert c.get("/readyz").json()["demo"]["daily_used"] == 0
