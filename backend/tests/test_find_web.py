"""Search the web for a part, and the device a part came from."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decide.service import known_fields
from app.extract import Extractor
from app.find import Finder, FindError, ListingsBack, SearchCreate, SearchPatch, WebFind
from app.find.service import MAX_LISTINGS, WEB_MAX, backed_finds, part_instructions, web_text
from app.inventory import Inventory
from app.inventory.parent import needs_parent, profile_of
from app.inventory.schema import FieldCreate, ItemCreate
from app.main import create_app
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient, norm_url
from app.ops.gate import demo_allowed, expensive
from app.profiles import Profiles
from app.projects.pack import private_field
from tests.conftest import RECORDED_FIXTURES, make_photo
from tests.test_gate import CODE, gated_settings

pytestmark = pytest.mark.anyio

FIXTURE = RECORDED_FIXTURES / "responses" / "part-search.json"


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


def agitator(inventory: Inventory, **fields: str) -> int:
    item = inventory.create(
        ItemCreate(item_type="blender agitator", name="Agitator", profile="blender_agitator")
    )
    for field, value in fields.items():
        inventory.add_field(item.id, FieldCreate(field=field, value=value))
    return item.id


def find(url: str, title: str = "a part") -> WebFind:
    return WebFind(
        url=url,
        title=title,
        site="example.org",
        price_as_stated="$5",
        dimensions_as_stated="",
        quote="",
    )


def search_output(*urls: str, cited: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "type": "web_search_call",
            "results": [{"type": "web_search_result", "url": u, "title": ""} for u in urls],
        }
    ]
    if cited:
        out.append(
            {
                "type": "message",
                "content": [{"annotations": [{"type": "url_citation", "url": u} for u in cited]}],
            }
        )
    return out


# --- the brief ----------------------------------------------------------------


def test_the_web_brief_leads_with_the_device_and_carries_nothing_private(
    finder: Finder,
) -> None:
    item = agitator(
        finder.inventory,
        rod_diameter="4",
        serial_number="SN-PRIVATE-9",
        parent_device_model="Hamilton Beach 729",
        parent_device="the drink mixer, type DM01",
    )
    search = finder.create(SearchCreate(need_item_id=item, title="metal agitator rod"))
    brief = finder.web_brief(search)
    first = brief.splitlines()[0]
    assert first.startswith(
        "Look first for the maker's own part: Hamilton Beach 729 blender agitator"
    )
    assert "rod diameter 4" in brief and "SN-PRIVATE-9" not in brief
    assert "It came from this device: model Hamilton Beach 729; the drink mixer" in brief
    # the parent fields are said once, in their own line, not among the values
    assert "parent device" not in brief
    plain = finder.create(SearchCreate(profile="blender_agitator", title="agitator"))
    assert finder.web_brief(plain) == finder.plan_brief(plain)
    assert "Search at most 4 times" in part_instructions(4)
    assert "Search at most 1 time," in part_instructions(1)


def test_the_plan_brief_is_unchanged_without_a_parent_device(finder: Finder) -> None:
    item = agitator(finder.inventory, rod_diameter="4")
    search = finder.create(SearchCreate(need_item_id=item, title="rod"))
    assert "came from" not in finder.plan_brief(search)
    assert finder.web_brief(search) == finder.plan_brief(search)


def test_the_owners_words_about_the_device_stay_out_of_other_briefs(finder: Finder) -> None:
    assert private_field("parent_device") and not private_field("parent_device_model")
    item = agitator(finder.inventory, parent_device="from my mother's kitchen")
    for a in finder.inventory.get(item).assertions:
        finder.inventory.review(item, a.id, "accepted")
    assert "parent_device" not in known_fields(finder.inventory.get(item))


# --- what is kept -------------------------------------------------------------


def test_only_finds_a_search_result_or_a_citation_carries_are_kept() -> None:
    output = search_output(
        "https://www.example.org/a?ref=x",
        "https://example.org/b",
        "https://shop.example.org/item?id=1&utm_source=feed",
        "https://example.org",
        cited=("http://example.org/c",),
    )
    kept, dropped, notes = backed_finds(
        [
            find("https://example.org/a?ref=x"),
            find("https://example.org/a/?ref=x#again"),  # the same page: one find per page
            find("https://example.org/a"),  # the query is part of the page
            find("https://example.org/b"),
            find("https://example.org/c"),
            find("https://shop.example.org/item?id=1"),  # tracking parameters let go
            find("https://shop.example.org/item?id=999"),  # another product: not backed
            find("https://example.org/"),  # the bare domain, a slash either way
            find("https://example.org/made-up"),
            find("javascript:alert(1)//example.org/b"),
            find("https://example.org/b?x=1"),
        ],
        output,
    )
    # each kept as the search gave it, not as the model wrote it
    assert [f.url for f in kept] == [
        "https://www.example.org/a?ref=x",
        "https://example.org/b",
        "http://example.org/c",
        "https://shop.example.org/item?id=1&utm_source=feed",
        "https://example.org",
    ]
    assert dropped == 5 and notes == ["5 find(s) rest on no search result and were left out"]
    _, _, none = backed_finds([find("https://example.org/a")], [])
    assert none[0] == "the model made no web search, so nothing it wrote can be backed"
    many = [find(f"https://example.org/{i}") for i in range(WEB_MAX + 5)]
    kept, _, _ = backed_finds(many, search_output(*(f.url for f in many)))
    assert len(kept) == WEB_MAX
    # a find with nothing to score is left out and said
    bare = WebFind(
        url="https://example.org/b",
        title=" ",
        site="example.org",
        price_as_stated="",
        dimensions_as_stated="",
        quote="",
    )
    kept, dropped, notes = backed_finds([bare], output)
    assert kept == [] and dropped == 1
    assert notes == ["1 find(s) said nothing about the part and were left out"]


def test_a_page_is_its_path_and_query_without_tracking_or_fragment() -> None:
    assert norm_url("https://WWW.Example.org/a/?id=1#top") == "example.org/a?id=1"
    assert norm_url("https://example.org/a?id=1") != norm_url("https://example.org/a?id=999")
    assert norm_url("https://example.org/a?utm_medium=x&id=1") == "example.org/a?id=1"
    assert norm_url("example.org/") == norm_url("https://example.org") == "example.org"


def test_a_find_reads_as_a_listing_the_pattern_and_the_price_can_score() -> None:
    text = web_text(
        WebFind(
            url="https://example.org/a",
            title="Spindle",
            site="example.org",
            price_as_stated="$12",
            dimensions_as_stated="4 mm",
            quote="stainless",
        )
    )
    assert text == "Spindle · $12 · 4 mm · stainless (found on example.org)"


async def test_one_search_adds_the_backed_finds_as_listings_with_their_links(
    finder: Finder,
) -> None:
    item = agitator(finder.inventory, parent_device_model="Hamilton Beach 729")
    search = finder.create(SearchCreate(need_item_id=item, title="agitator", max_price=20))
    calls_before = finder.client.ledger.summary().calls
    result = await finder.search_web(search.id)
    assert finder.client.ledger.summary().calls == calls_before + 1
    assert result.added == 3 and result.dropped == 1 and result.from_fixture
    assert result.searches == 1
    web = [b for b in result.listings if b.source_kind == "web"]
    assert {b.source_url for b in web} == {
        "https://example.org/parts/drink-mixer-spindle-metal",
        "https://example.org/listings/agitator-rod-used",
        "https://example.org/listings/frappe-whisk-lot",
    }
    assert "https://example.org/forum/where-to-buy-spindle" not in {b.source_url for b in web}
    # scored like any listing: the lot for parts is ruled out, the priced ones under the limit
    lot = next(b for b in web if "whisk" in b.source_url)
    assert lot.score.verdict == "no"
    # asked again, a page already kept is not added twice
    again = await finder.search_web(search.id)
    assert again.added == 0 and "already in the listings" in again.notes[-1]
    assert finder.search(search.id).listings == 3
    # Check fit reads it like any listing and keeps its link on the candidate
    candidate = await finder.check_listing(search.id, web[0].id)
    assert candidate.url == web[0].source_url


async def test_web_finds_are_capped_with_the_rest(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="blender_agitator", title="agitator"))
    for batch in range(3):
        finder.add_listings(
            search.id, ListingsBack(texts=[f"rod {batch}-{i} $3" for i in range(20)])
        )
    result = await finder.search_web(search.id)
    assert len(result.listings) == MAX_LISTINGS
    assert sum(b.source_kind == "web" for b in result.listings) == 3


async def test_a_closed_search_is_not_searched(finder: Finder) -> None:
    search = finder.create(SearchCreate(profile="blender_agitator", title="agitator"))
    finder.update(search.id, SearchPatch(status="closed"))
    calls = finder.client.ledger.summary().calls
    with pytest.raises(FindError, match="closed"):
        await finder.search_web(search.id)
    assert finder.client.ledger.summary().calls == calls


def test_the_stub_fixture_is_a_stub_not_a_recording() -> None:
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert body["op"] == "part-search" and body["digest"].startswith("fallback-")
    assert all("example.org" in r["url"] for r in body["response"]["output"][1]["results"])


# --- the route and the gate ---------------------------------------------------


def test_the_web_search_is_counted_and_closed_to_the_visitor() -> None:
    for odd in ("3", "+3", "03", " 3", "3 "):
        assert expensive("POST", f"/api/searches/{odd}/web")
        assert not demo_allowed("POST", f"/api/searches/{odd}/web")
        assert expensive("POST", f"/api/items/{odd}/parent-photo")
        assert not demo_allowed("POST", f"/api/items/{odd}/parent-photo")
    assert not expensive("GET", "/api/searches/3/web")
    assert not expensive("POST", "/api/searches/3/web/x")


def test_one_click_is_one_counted_call_and_the_visitor_is_refused(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        made = c.post("/api/searches", json={"profile": "blender_agitator", "title": "rod"})
        sid = made.json()["id"]
        used = c.get("/readyz").json()["demo"]["daily_used"]
        got = c.post(f"/api/searches/{sid}/web")
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["added"] == 3 and body["dropped"] == 1
        assert all(b["source_url"].startswith("https://example.org/") for b in body["listings"])
        assert c.get("/readyz").json()["demo"]["daily_used"] == used + 1
        # an odd spelling of the id is the same search, counted the same
        assert c.post(f"/api/searches/+{sid}/web").status_code == 200
        assert c.get("/readyz").json()["demo"]["daily_used"] == used + 2
        # refused before the call (no such search, a closed one): nothing counted
        assert c.post("/api/searches/999/web").status_code == 404
        c.patch(f"/api/searches/{sid}", json={"status": "closed"})
        assert c.post(f"/api/searches/{sid}/web").status_code == 422
        assert c.get("/readyz").json()["demo"]["daily_used"] == used + 2
        c.cookies.clear()
        assert c.post(f"/api/searches/{sid}/web").status_code == 403


# --- the device a part came from ----------------------------------------------


def test_a_part_with_no_model_and_no_device_asks_for_the_device(
    recorded_settings: Settings,
) -> None:
    inventory = Inventory(recorded_settings)
    bare = agitator(inventory, rod_diameter="4")
    assert inventory.get(bare).needs_parent is True
    # the owner's words, the model read or typed, or a model number of its own: answered
    for field, value in (
        ("parent_device", "the drink mixer in the kitchen"),
        ("parent_device_model", "Hamilton Beach 729"),
        ("model_number", "729"),
        ("part_number", "990010200"),
    ):
        item = agitator(inventory)
        assert (
            inventory.add_field(item, FieldCreate(field=field, value=value)).needs_parent is False
        )
    # a rejected model does not answer it
    item = agitator(inventory)
    added = inventory.add_field(item, FieldCreate(field="model_number", value="X1"))
    rejected = inventory.review(item, added.fields["model_number"].id, "rejected")
    assert rejected.needs_parent is True
    # a part recorded under its device, and a thing that is not a part, are not asked about
    whole = inventory.create(ItemCreate(item_type="drink mixer", name="Mixer"))
    part = inventory.create(
        ItemCreate(item_type="agitator", profile="blender_agitator", parent_id=whole.id)
    )
    assert part.needs_parent is False
    adapter = inventory.create(ItemCreate(item_type="adapter", profile="power_adapter"))
    assert adapter.needs_parent is False
    assert inventory.create(ItemCreate(item_type="rod")).needs_parent is False
    assert needs_parent({}, None, None) is False
    assert needs_parent({}, None, profile_of("vacuum_attachment")) is True
    assert profile_of("no_such_profile") is None


def test_the_visitor_never_gets_the_owners_words_about_the_device(tmp_path: Path) -> None:
    with TestClient(create_app(gated_settings(tmp_path))) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post(
            "/api/items", json={"item_type": "agitator", "profile": "blender_agitator"}
        ).json()["id"]
        assert c.get(f"/api/items/{item}").json()["needs_parent"] is True
        for field, value in (
            ("parent_device", "my aunt's mixer"),
            ("parent_device_model", "Hamilton Beach 729"),
        ):
            assert (
                c.post(
                    f"/api/items/{item}/fields", json={"field": field, "value": value}
                ).status_code
                == 200
            )
        owner = c.get(f"/api/items/{item}").json()
        assert owner["fields"]["parent_device"]["source"] == "user_edit"
        assert owner["needs_parent"] is False
        c.post(f"/api/items/{item}/public", json={"public": True})
        c.cookies.clear()
        seen = c.get(f"/api/items/{item}")
        assert "my aunt" not in seen.text
        assert seen.json()["fields"]["parent_device_model"]["value"] == "Hamilton Beach 729"
        assert (
            c.post(
                f"/api/items/{item}/fields", json={"field": "parent_device", "value": "x"}
            ).status_code
            == 403
        )


def test_a_photo_of_the_device_is_kept_and_its_model_proposed(
    recorded_client: TestClient,
) -> None:
    c = recorded_client
    item = c.post("/api/items", json={"item_type": "agitator", "profile": "blender_agitator"})
    item_id = item.json()["id"]
    sent = c.post(
        f"/api/items/{item_id}/parent-photo",
        files={"photo": ("base.jpg", make_photo(), "image/jpeg")},
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    # the extract stub reads a brand and a model number
    assert body["model"] == "Orbital Power OP-65N"
    read = body["item"]["fields"]["parent_device_model"]
    assert read["source"] == "photo" and read["review"] == "proposed"
    assert read["provenance"] == "observed"
    assert body["item"]["needs_parent"] is False
    # kept apart: the device's photos are not the part's
    assert c.get(f"/api/items/{item_id}/photos").json()["count"] == 0
    assert c.get(f"/api/items/{item_id}/device-photos").json()["count"] == 1
    assert c.get(f"/api/items/{item_id}/device-photos/1").headers["content-type"] == "image/jpeg"
    assert body["item"]["version"] == item.json()["version"] + 1
    assert (
        c.post(
            "/api/items/999/parent-photo", files={"photo": ("a.jpg", make_photo(), "image/jpeg")}
        ).status_code
        == 404
    )
    empty = c.post(
        f"/api/items/{item_id}/parent-photo", files={"photo": ("a.jpg", b"", "image/jpeg")}
    )
    assert empty.status_code == 400


def test_a_device_photo_with_no_model_still_makes_a_new_version(
    recorded_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.extract import Extraction

    c = recorded_client

    async def nothing(photos: list[bytes], crops: list[bytes] | None = None) -> Extraction:
        return Extraction(
            item_type="",
            label_text="",
            fields={},
            warnings=[],
            photos=1,
            model="m",
            from_fixture=True,
            cost_usd=0.0,
        )

    monkeypatch.setattr(c.app.state.extractor, "extract", nothing)  # type: ignore[attr-defined]
    made = c.post("/api/items", json={"item_type": "agitator", "profile": "blender_agitator"})
    sent = c.post(
        f"/api/items/{made.json()['id']}/parent-photo",
        files={"photo": ("base.jpg", make_photo(), "image/jpeg")},
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["model"] == "" and body["item"]["needs_parent"] is True
    # the photo row reads the count again: the item is a new version
    assert body["item"]["version"] == made.json()["version"] + 1


def test_device_photos_stay_out_of_the_parts_photos_drafts_zip_and_the_visitor(
    tmp_path: Path,
) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post(
            "/api/items", json={"item_type": "agitator", "profile": "blender_agitator"}
        ).json()["id"]
        for _ in range(2):
            sent = c.post(
                f"/api/items/{item}/parent-photo",
                files={"photo": ("base.jpg", make_photo(), "image/jpeg")},
            )
            assert sent.status_code == 201, sent.text
        # not counted against the part's own photos: all four still fit
        own = [("uploads", (f"{i}.jpg", make_photo(), "image/jpeg")) for i in range(4)]
        assert c.post(f"/api/items/{item}/photos", files=own).json()["count"] == 4
        assert c.get(f"/api/items/{item}/device-photos").json()["count"] == 2
        # a draft reads, and its zip carries, the part's photos alone
        lister = c.app.state.lister  # type: ignore[attr-defined]
        assert sum(p["type"] == "input_image" for p in lister._photo_parts(item)) == 4
        draft = c.post(f"/api/items/{item}/drafts", json={"mode": "give"})
        assert draft.status_code == 201, draft.text
        assert {p["photo"] for p in draft.json()["photos"]} <= {1, 2, 3, 4}
        zipped = c.get(f"/api/drafts/{draft.json()['id']}/photos.zip")
        assert zipped.status_code == 200
        import io
        import zipfile

        assert len(zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()) <= 4
        c.post(f"/api/items/{item}/public", json={"public": True})
        c.cookies.clear()
        # the visitor sees the part and its photos, never the device's
        assert c.get(f"/api/items/{item}/photos").json()["count"] == 4
        assert c.get(f"/api/items/{item}/device-photos").status_code == 403
        assert c.get(f"/api/items/{item}/device-photos/1").status_code == 403
