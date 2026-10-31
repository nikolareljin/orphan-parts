import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import ComponentCreate, FieldCreate, ItemCreate
from app.model_api import CostLedger, ModelApiClient, citations, search_results, searches
from app.model_api.pricing import SEARCH_QUERY_USD
from app.value import (
    Comparable,
    PriceReportCreate,
    PriceRequest,
    Quantity,
    Valuer,
    backed,
    brief,
    quantity,
    strategies,
)
from tests.conftest import RECORDED_FIXTURES

pytestmark = pytest.mark.anyio

PAGE = "https://example.org/listings/one"


def comparable(**over: Any) -> Comparable:
    spec: dict[str, Any] = {
        "kind": "asking",
        "title": "One",
        "price": 20.0,
        "currency": "USD",
        "condition": "used",
        "observed": "",
        "source_url": PAGE,
        "source_title": "One",
    }
    spec.update(over)
    return Comparable(**spec)


def output_with(urls: list[str], cited: list[str] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {
            "type": "web_search_call",
            "status": "completed",
            "results": [{"type": "web_search_result", "title": "t", "url": u} for u in urls],
        }
    ]
    if cited:
        out.append(
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "x",
                        "annotations": [
                            {"type": "url_citation", "url": u, "title": "c"} for u in cited
                        ],
                    }
                ],
            }
        )
    return out


def test_search_calls_results_and_citations_are_read_off_the_output() -> None:
    out = output_with(["https://a.example/x", "https://b.example/y"], ["https://c.example/z"])
    assert searches(out) == 1
    assert [r["url"] for r in search_results(out)] == ["https://a.example/x", "https://b.example/y"]
    assert citations(out) == [{"url": "https://c.example/z", "title": "c"}]
    assert searches([]) == 0 and search_results([]) == [] and citations([]) == []


def test_only_a_comparable_a_page_backs_is_kept() -> None:
    out = output_with(["https://example.org/listings/one/"], ["HTTPS://www.example.org/cited"])
    found = [
        comparable(),
        comparable(source_url="https://example.org/cited?utm_source=search#top", price=30),
        comparable(source_url="https://example.org/cited?id=999", price=35),
        comparable(source_url="https://example.org/nowhere", price=40),
        comparable(price=0),
        comparable(currency="EUR", price=19),
    ]
    kept, dropped, caveats = backed(found, out, "USD")
    # tracking parameters or a fragment are the same page; another query is another page
    assert [c.price for c in kept] == [20.0, 30.0]
    assert kept[1].source_url == "HTTPS://www.example.org/cited"  # as the search gave it
    assert dropped == 4
    assert kept[0].observed  # the day it was seen, when the page gave no date
    assert any("rest on no search result" in c for c in caveats)
    assert any("carried no price" in c for c in caveats)
    assert any("another currency" in c for c in caveats)
    assert not any("no web search" in c or "no pages" in c for c in caveats)


def test_one_comparable_per_page_and_the_models_text_is_cut() -> None:
    out = output_with(["https://example.org/listings/one"])
    found = [
        comparable(title="x" * 500, condition="y" * 500),
        comparable(price=25, source_url="https://example.org/listings/one#other"),
    ]
    kept, dropped, _ = backed(found, out, "USD")
    assert len(kept) == 1 and dropped == 1
    assert len(kept[0].title) == 200 and len(kept[0].condition) == 200


def test_no_search_or_no_pages_is_said_as_the_reason() -> None:
    kept, dropped, caveats = backed([comparable()], [], "USD")
    assert kept == [] and dropped == 1
    assert caveats[0] == "the model made no web search, so nothing it wrote can be backed"
    searched_nothing = [{"type": "web_search_call", "status": "completed", "results": []}]
    _, _, caveats = backed([comparable()], searched_nothing, "USD")
    assert caveats[0] == "the search returned no pages, so nothing the model wrote can be backed"
    assert backed([], [], "USD") == ([], 0, [])


def test_quantities_and_strategies_come_from_figures_that_exist() -> None:
    asking = quantity("asking", [18, 22, 12.5], "USD", "seen")
    assert (asking.count, asking.low, asking.high, asking.typical) == (3, 12.5, 22, 18)
    none = quantity("sold", [], "USD", "none")
    assert none.count == 0 and none.low is None and none.typical is None
    estimate = Quantity(
        kind="estimate", label="e", count=1, low=12, high=22, typical=17, currency="USD", basis="b"
    )
    plans = strategies(asking, estimate, weak=False)
    assert [s.name for s in plans] == ["quick_sale", "typical", "patient"]
    assert [s.price for s in plans] == [12, 18, 22]
    assert not any("weak" in s.note for s in plans)
    only_estimate = strategies(none, estimate, weak=True)
    assert [s.price for s in only_estimate] == [12, 17, 22]
    assert all("weak" in s.note for s in only_estimate)
    nothing = strategies(none, quantity("estimate", [], "USD", "n"), weak=True)
    assert [s.price for s in nothing] == [None, None, None]


def adapter(inventory: Inventory) -> int:
    item = inventory.create(
        ItemCreate(
            item_type="laptop power adapter",
            name="Orbital charger",
            condition="scuffed",
            faults="frayed sleeve near the plug",
        )
    )
    inventory.add_field(
        item.id, FieldCreate(field="output_voltage", value="19.5", unit="V", provenance="tested")
    )
    return item.id


def test_the_brief_holds_confirmed_values_the_place_and_the_currency(settings: Settings) -> None:
    inventory = Inventory(settings)
    item = inventory.get(adapter(inventory))
    request = PriceRequest(currency="EUR", city=" Lyon \n 3e ")
    text = brief(item, {"output_voltage": "19.5 V"}, request)
    assert "currency: EUR" in text and "market: Lyon 3e" in text
    assert "- output_voltage: 19.5 V" in text
    assert "faults: frayed sleeve near the plug" in text


@pytest.fixture
def valuer(recorded_settings: Settings) -> Valuer:
    inventory = Inventory(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    return Valuer(recorded_settings, client, inventory)


async def test_guidance_keeps_four_quantities_apart_from_the_recorded_search(
    valuer: Valuer,
) -> None:
    item_id = adapter(valuer.inventory)
    guide = await valuer.guide(item_id, PriceRequest())
    assert guide.from_fixture and guide.cost_usd == 0.0 and guide.searches == 1
    assert guide.version == 1 and guide.stale is False
    assert valuer.inventory.get(item_id).version == 2  # asking is not a change to the item
    by_kind = {q.kind: q for q in guide.quantities}
    assert [q.kind for q in guide.quantities] == ["asking", "sold", "reported", "estimate"]
    assert (by_kind["asking"].count, by_kind["asking"].low, by_kind["asking"].high) == (3, 12.5, 22)
    assert by_kind["asking"].typical == 18
    assert (by_kind["sold"].count, by_kind["sold"].typical) == (1, 15)
    assert by_kind["reported"].count == 0
    assert (by_kind["estimate"].low, by_kind["estimate"].typical, by_kind["estimate"].high) == (
        12,
        17,
        22,
    )
    assert guide.estimate_label == "estimate" and "labelled as such" in by_kind["estimate"].basis
    # the forum line rests on no search result: dropped and said
    assert guide.dropped == 1 and len(guide.comparables) == 4
    assert not any("forum" in c.source_url for c in guide.comparables)
    assert any("rest on no search result" in c for c in guide.caveats)
    assert all(c.observed for c in guide.comparables)
    assert {s.url for s in guide.sources} == {c.source_url for c in guide.comparables}
    assert guide.weak is False and guide.weak_reason == ""
    assert [s.price for s in guide.strategies] == [12, 18, 22]
    assert guide.parts is None
    # a decision is no change to what it is worth: the guidance stays current
    moved = valuer.inventory.decide(item_id, "sell", "decided: sell: worth a listing", said=True)
    assert moved.version > guide.item_version
    assert valuer.guidances(item_id)[0].stale is False
    # the item changed since: stale; a report counts in the next guidance
    valuer.inventory.add_field(item_id, FieldCreate(field="colour", value="black"))
    assert valuer.guidances(item_id)[0].stale is True
    valuer.report(item_id, PriceReportCreate(price=16, sold_on="2026-09-30", note="a friend"))
    again = await valuer.guide(item_id, PriceRequest())
    reported = next(q for q in again.quantities if q.kind == "reported")
    assert (reported.count, reported.typical) == (1, 16)
    assert again.version == 2
    events = [e.change for e in valuer.inventory.events(item_id)]
    assert "price guidance written (v1)" in events
    assert any(e.startswith("sale reported: 16 USD on 2026-09-30") for e in events)


async def test_a_report_in_another_currency_stays_out_of_the_count(valuer: Valuer) -> None:
    item_id = adapter(valuer.inventory)
    valuer.report(item_id, PriceReportCreate(price=14, currency="EUR", sold_on="2026-09-01"))
    guide = await valuer.guide(item_id, PriceRequest())
    assert next(q for q in guide.quantities if q.kind == "reported").count == 0
    assert len(valuer.reports(item_id)) == 1


async def test_whole_against_parts_uses_the_parts_own_guidance(valuer: Valuer) -> None:
    inv = valuer.inventory
    laptop = inv.create(ItemCreate(item_type="laptop", name="Old laptop"))
    inv.add_component(laptop.id, ComponentCreate(item_type="charger", name="Its charger"))
    inv.add_component(laptop.id, ComponentCreate(item_type="battery", name="Its battery"))
    whole = await valuer.guide(laptop.id, PriceRequest())
    assert whole.parts is not None
    assert (whole.parts.components, whole.parts.priced, whole.parts.sum_typical) == (2, 0, None)
    assert "none priced yet" in whole.parts.note
    charger = inv.get(laptop.id).components[0]
    await valuer.guide(charger, PriceRequest())
    whole_again = valuer.guidances(laptop.id)[0]
    assert whole_again.parts is not None
    assert (whole_again.parts.priced, whole_again.parts.sum_typical) == (1, 18)
    assert whole_again.parts.whole_typical == 18
    assert "1 of 2 part(s) priced" in whole_again.parts.note


async def test_a_live_call_carries_the_search_tool_and_bills_each_search(
    live_settings: Settings,
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["body"] = body
        fixture = json.loads((RECORDED_FIXTURES / "responses" / "price.json").read_text())
        response: dict[str, Any] = fixture["response"]
        # two searches this time
        response["output"].insert(1, dict(response["output"][1], id="ws_2"))
        return httpx.Response(200, json=response)

    ledger = CostLedger(cap_usd=25.0)
    client = ModelApiClient(live_settings, ledger, transport=httpx.MockTransport(handler))
    settings = live_settings.model_copy(update={"price_country": "US"})
    valuer = Valuer(settings, client, Inventory(settings))
    item_id = adapter(valuer.inventory)
    guide = await valuer.guide(item_id, PriceRequest(city="Austin"))
    body = seen["body"]
    assert body["tools"] == [
        {
            "type": "web_search",
            "search_context_size": "low",
            "user_location": {"type": "approximate", "country": "US", "city": "Austin"},
        }
    ]
    assert body["include"] == ["web_search_call.results"]
    assert body["max_tool_calls"] == 4
    assert body["instructions"].endswith(
        "Search at most 4 times, then answer with what those searches found."
    )
    assert body["text"]["format"]["name"] == "Findings"
    assert guide.searches == 2 and guide.from_fixture is False
    entry = ledger.entries()[0]
    assert entry.usage.search_queries == 2
    assert entry.usd >= 2 * SEARCH_QUERY_USD


async def test_a_line_written_before_the_search_does_not_hide_the_answer(
    live_settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        fixture = json.loads((RECORDED_FIXTURES / "responses" / "price.json").read_text())
        response: dict[str, Any] = fixture["response"]
        # the shape seen live: a message before the search, the schema in the one after it
        aside = {
            "id": "msg_0",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "Tracking it down.", "annotations": []}],
        }
        response["output"].insert(1, aside)
        return httpx.Response(200, json=response)

    client = ModelApiClient(
        live_settings, CostLedger(cap_usd=25.0), transport=httpx.MockTransport(handler)
    )
    valuer = Valuer(live_settings, client, Inventory(live_settings))
    guide = await valuer.guide(adapter(valuer.inventory), PriceRequest())
    assert guide.searches == 1 and len(guide.comparables) == 4
    by_kind = {q.kind: q for q in guide.quantities}
    assert (by_kind["estimate"].low, by_kind["estimate"].typical) == (12, 17)


def test_price_routes(recorded_client: TestClient) -> None:
    item_id = recorded_client.post("/api/items", json={"item_type": "laptop power adapter"}).json()[
        "id"
    ]
    res = recorded_client.post(f"/api/items/{item_id}/price", json={})
    assert res.status_code == 201, res.text
    guide = res.json()
    assert guide["estimate_label"] == "estimate" and guide["dropped"] == 1
    assert [q["kind"] for q in guide["quantities"]] == ["asking", "sold", "reported", "estimate"]
    assert recorded_client.get(f"/api/items/{item_id}/price").json()[0]["id"] == guide["id"]
    report = recorded_client.post(
        f"/api/items/{item_id}/price/reports",
        json={"price": 16, "sold_on": "2026-09-30", "note": "a friend"},
    )
    assert report.status_code == 201, report.text
    assert report.json()["currency"] == "USD"
    assert len(recorded_client.get(f"/api/items/{item_id}/price/reports").json()) == 1
    for bad in (
        {"price": 0, "sold_on": "2026-09-30"},
        {"price": 5, "sold_on": "yesterday"},
        {"price": 5, "sold_on": "2026-13-45"},
        {"price": 5, "sold_on": "2999-01-01"},
        {"price": 5, "sold_on": "2026-09-30", "currency": "usd"},
        {"price": 5, "sold_on": "2026-09-30", "note": "n" * 201},
    ):
        assert (
            recorded_client.post(f"/api/items/{item_id}/price/reports", json=bad).status_code == 422
        ), bad
    bad_currency = recorded_client.post(f"/api/items/{item_id}/price", json={"currency": "us"})
    assert bad_currency.status_code == 422
    assert recorded_client.post("/api/items/999/price", json={}).status_code == 404
    assert recorded_client.get("/api/items/999/price/reports").status_code == 404


def test_a_price_without_a_recorded_answer_is_a_503(client: TestClient) -> None:
    item_id = client.post("/api/items", json={"item_type": "kettle"}).json()["id"]
    res = client.post(f"/api/items/{item_id}/price", json={})
    assert res.status_code == 503


def test_paths_are_in_the_openapi_document(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/items/{item_id}/price" in paths
    assert "/api/items/{item_id}/price/reports" in paths
