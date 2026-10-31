"""The demo samples: the demo set's photos are what the demo visitor reads. A file of their
own is refused on every reading route; a sample is answered by the recording made of that
exact photo, or said to have none, never by an operation's stub. The owner uploads as before."""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.samples import MISSING_LINE, VISITOR_UPLOAD_LINE, Samples
from tests.conftest import RECORDED_FIXTURES, SAMPLE_VALUE, make_photo
from tests.test_gate import CODE, gated_settings

DEMO_SET = Path(__file__).resolve().parents[2] / "demo" / "set.yaml"
STUB_TYPE = json.loads((RECORDED_FIXTURES / "responses" / "extract.json").read_text())
MEASURE = json.dumps(
    {
        "feature": "rod_diameter",
        "image": {"width": 739, "height": 1600},
        "reference": {
            "kind": "two_point",
            "points": [{"x": 100, "y": 100}, {"x": 500, "y": 100}],
            "length_mm": 40,
        },
        "points": [{"x": 100, "y": 300}, {"x": 140, "y": 300}],
        "straight_on": True,
    }
)

pytestmark = pytest.mark.skipif(not DEMO_SET.is_file(), reason="the demo set is not in this tree")


def visitor_settings(tmp_path: Path, **over: object) -> Settings:
    spec: dict[str, object] = {
        "fixtures_dir": RECORDED_FIXTURES,
        "demo_set": DEMO_SET,
        "demo_visitor_calls_per_hour": 10_000,
        "demo_requests_per_minute": 10_000,
    }
    spec.update(over)
    return gated_settings(tmp_path, **spec)


@pytest.fixture
def visitor(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(visitor_settings(tmp_path))) as c:
        yield c


def photo_ids() -> list[str]:
    catalog = Samples(Settings(OPL_FAKE_API=True, demo_set=DEMO_SET, _env_file=None)).catalog()
    return [p.id for item in catalog.items for p in item.photos]


def stub_item_type() -> str:
    text = STUB_TYPE["response"]["output"][-1]["content"][0]["text"]
    found: str = json.loads(text)["item_type"]
    return found


# --- the catalog ---------------------------------------------------------------------


def test_the_catalog_lists_every_photo_by_item_and_the_listings(visitor: TestClient) -> None:
    got = visitor.get("/api/samples")
    assert got.status_code == 200
    body = got.json()
    photos = [p for item in body["items"] for p in item["photos"]]
    assert len(body["items"]) == 10 and len(photos) == 19
    gpu = next(i for i in body["items"] if i["key"] == "gpu_9800gt")
    assert gpu["name"] == "EVGA GeForce 9800 GT graphics card"
    assert [p["id"] for p in gpu["photos"]] == ["evga-9800gt-front", "evga-9800gt-back"]
    assert all(p["item_key"] == "gpu_9800gt" for p in gpu["photos"])
    assert [li["id"] for li in body["listings"]] == [
        "listing-l1",
        "listing-l2",
        "listing-l3",
        "listing-l4",
    ]
    assert body["notes"] == []  # the set has no voice note yet
    # a request names an id, never a path
    assert all("/" not in p["id"] and "/" not in p["file"] for p in photos)


def test_samples_are_served_whole_and_small(visitor: TestClient) -> None:
    whole = visitor.get("/api/samples/evga-9800gt-front/file")
    assert whole.status_code == 200 and whole.headers["content-type"] == "image/jpeg"
    assert whole.content == (DEMO_SET.parent / "photos" / "evga-9800gt-front.jpg").read_bytes()
    thumb = visitor.get("/api/samples/evga-9800gt-front/thumb")
    assert thumb.status_code == 200 and len(thumb.content) < len(whole.content)
    listing = visitor.get("/api/samples/listing-l1/file")
    assert listing.status_code == 200 and listing.headers["content-type"].startswith("text/plain")
    assert visitor.get("/api/samples/listing-l1/thumb").status_code == 404
    assert visitor.get("/api/samples/nothing-here/file").status_code == 404
    # nothing outside the catalog: the id is a slug, a path is no id at all
    assert visitor.get("/api/samples/..%2Fset.yaml/file").status_code in (403, 404, 422)


def test_no_demo_set_is_an_empty_catalog(tmp_path: Path) -> None:
    settings = visitor_settings(tmp_path, demo_set=tmp_path / "none" / "set.yaml")
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/samples").json() == {
            "title": "",
            "items": [],
            "listings": [],
            "notes": [],
        }


# --- the demo visitor's uploads ------------------------------------------------------


def test_a_visitor_upload_is_refused_on_every_reading_route(visitor: TestClient) -> None:
    jpeg = ("p.jpg", make_photo(), "image/jpeg")
    refused = [
        visitor.post("/api/extract", files=[("photos", jpeg)]),
        visitor.post(
            "/api/extract", files=[("crops", jpeg)], data={"sample_ids": ["agitator-head"]}
        ),
        visitor.post("/api/segment", files=[("photo", jpeg)]),
        visitor.post("/api/measure", files=[("photo", jpeg)], data={"request": MEASURE}),
    ]
    for answer in refused:
        assert answer.status_code == 403, answer.text
        assert answer.json()["detail"] == VISITOR_UPLOAD_LINE
    # the routes that take a file and are not the visitor's stay behind the code
    for path in ("/api/captures", "/api/items/1/voice", "/api/searches/1/listings/screenshots"):
        assert visitor.post(path, files=[("photos", jpeg)]).status_code == 403, path


# --- the demo visitor's samples ------------------------------------------------------


@pytest.mark.parametrize("find_label", [True, False])
def test_every_sample_photo_answers_with_its_own_recording(
    visitor: TestClient, find_label: bool
) -> None:
    client = visitor.app.state.model_api  # type: ignore[attr-defined]
    stubs_before = client.fixture_fallbacks
    stub = stub_item_type()
    ids = photo_ids()
    assert len(ids) == 19
    for sid in ids:
        got = visitor.post(
            "/api/samples/read", json={"sample_ids": [sid], "find_label": find_label}
        )
        assert got.status_code == 200, (sid, got.text)
        [result] = got.json()["results"]
        assert result["sample_ids"] == [sid]
        assert result["missing"] is False, sid
        reading = result["extraction"]
        assert reading["from_fixture"] is True and reading["photos"] == 1
        assert reading["item_type"] and reading["item_type"] != stub, sid
        assert (result["segmentation"] is not None) is find_label
    # not one answer came from an operation's stub
    assert client.fixture_fallbacks == stubs_before


def test_the_reading_routes_take_sample_ids_and_answer_the_same(visitor: TestClient) -> None:
    read = visitor.post(
        "/api/samples/read", json={"sample_ids": ["dell-u2419h-label"], "find_label": False}
    ).json()["results"][0]["extraction"]
    extract = visitor.post("/api/extract", data={"sample_ids": ["dell-u2419h-label"]})
    assert extract.status_code == 200, extract.text
    assert extract.json() == read
    segment = visitor.post("/api/segment", data={"sample_id": "dell-u2419h-label"})
    assert segment.status_code == 200 and segment.json()["from_fixture"] is True
    measured = visitor.post(
        "/api/measure", data={"sample_id": "agitator-ruler", "request": MEASURE}
    )
    assert measured.status_code == 200, measured.text


def test_an_items_whole_group_is_one_reading(visitor: TestClient) -> None:
    got = visitor.post(
        "/api/samples/read",
        json={"sample_ids": ["evga-9800gt-back", "evga-9800gt-front"], "find_label": True},
    )
    assert got.status_code == 200, got.text
    [result] = got.json()["results"]
    assert result["whole_item"] is True and result["item_key"] == "gpu_9800gt"
    assert result["sample_ids"] == ["evga-9800gt-front", "evga-9800gt-back"]  # the set's order
    assert result["extraction"]["photos"] == 2 and result["missing"] is False


def test_a_mix_is_one_reading_per_photo(visitor: TestClient) -> None:
    mix = ["agitator-head", "evga-9800gt-front", "dell-u2419h-label", "agitator-head"]
    got = visitor.post("/api/samples/read", json={"sample_ids": mix, "find_label": False})
    assert got.status_code == 200, got.text
    results = got.json()["results"]
    # once each, in the catalog's order; a one-photo item is its whole group
    assert [r["sample_ids"] for r in results] == [
        ["dell-u2419h-label"],
        ["evga-9800gt-front"],
        ["agitator-head"],
    ]
    assert [r["whole_item"] for r in results] == [True, False, False]
    for r in results:
        alone = visitor.post(
            "/api/samples/read", json={"sample_ids": r["sample_ids"], "find_label": False}
        ).json()["results"][0]
        assert r["extraction"] == alone["extraction"]  # each photo's own recorded answer
    assert len({r["extraction"]["item_type"] for r in results}) == 3


def test_an_unknown_sample_is_404(visitor: TestClient) -> None:
    assert visitor.post("/api/samples/read", json={"sample_ids": ["no-such"]}).status_code == 404
    assert visitor.post("/api/extract", data={"sample_ids": ["no-such"]}).status_code == 404
    assert visitor.post("/api/segment", data={"sample_id": "no-such"}).status_code == 404
    # a listing is a sample, not a photo to read
    assert visitor.post("/api/samples/read", json={"sample_ids": ["listing-l1"]}).status_code == 404
    assert visitor.post("/api/samples/read", json={"sample_ids": []}).status_code == 422


def test_a_sample_without_a_recording_says_so_instead_of_the_stub(tmp_path: Path) -> None:
    # only the operations' stubs: every upload would be answered, no sample is
    fixtures = tmp_path / "stubs" / "responses"
    fixtures.mkdir(parents=True)
    for name in ("extract", "segment-item", "segment-label", "segment-connector"):
        shutil.copy(RECORDED_FIXTURES / "responses" / f"{name}.json", fixtures / f"{name}.json")
    settings = visitor_settings(tmp_path, fixtures_dir=tmp_path / "stubs")
    with TestClient(create_app(settings)) as c:
        got = c.post(
            "/api/samples/read",
            json={"sample_ids": ["evga-9800gt-front", "dell-u2419h-label"], "find_label": True},
        )
        assert got.status_code == 200, got.text
        results = got.json()["results"]
        assert len(results) == 2
        for r in results:
            assert r["missing"] is True and r["note"] == MISSING_LINE
            assert r["extraction"] is None and r["segmentation"] is None
        one = c.post("/api/extract", data={"sample_ids": ["evga-9800gt-front"]})
        assert one.status_code == 404 and one.json()["detail"] == MISSING_LINE
        # the owner's upload still takes the stub, as fixture mode always has
        c.post("/api/access", json={"code": CODE})
        upload = c.post("/api/extract", files=[("photos", ("p.jpg", make_photo(), "image/jpeg"))])
        assert upload.status_code == 200 and upload.json()["item_type"] == stub_item_type()


# --- the owner -------------------------------------------------------------------------


def test_the_owner_uploads_live_while_the_visitor_reads_recordings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.main as main_module

    answer: dict[str, Any] = STUB_TYPE["response"]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=answer)

    real = main_module.ModelApiClient

    class Faked(real):  # type: ignore[misc,valid-type]
        def __init__(self, settings: Settings, ledger: object, **kw: object) -> None:
            super().__init__(settings, ledger, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "ModelApiClient", Faked)
    settings = visitor_settings(
        tmp_path,
        OPL_FAKE_API=False,
        OPL_KEY_PROBE=False,
        model_api_key=SAMPLE_VALUE,
    )
    with TestClient(create_app(settings)) as c:
        # the visitor: refused an upload, answered from the recordings, the key never called
        jpeg = ("p.jpg", make_photo(), "image/jpeg")
        assert c.post("/api/extract", files=[("photos", jpeg)]).status_code == 403
        sample = c.post(
            "/api/samples/read", json={"sample_ids": ["agitator-head"], "find_label": False}
        )
        assert sample.status_code == 200
        assert sample.json()["results"][0]["extraction"]["from_fixture"] is True
        assert calls == []
        # the owner: the upload is read live
        assert c.post("/api/access", json={"code": CODE}).status_code == 200
        live = c.post("/api/extract", files=[("photos", jpeg)])
        assert live.status_code == 200, live.text
        assert live.json()["from_fixture"] is False and len(calls) == 1
        # samples are offered to the owner too, read live through the key
        mine = c.post(
            "/api/samples/read", json={"sample_ids": ["agitator-head"], "find_label": False}
        )
        assert mine.status_code == 200
        assert mine.json()["results"][0]["extraction"]["from_fixture"] is False
        assert len(calls) == 2


def test_a_visitor_pays_one_try_per_reading(tmp_path: Path) -> None:
    settings = visitor_settings(tmp_path, demo_visitor_calls_per_hour=4)
    with TestClient(create_app(settings)) as c:
        three = ["dell-u2419h-label", "evga-9800gt-front", "agitator-head"]
        first = c.post("/api/samples/read", json={"sample_ids": three, "find_label": False})
        assert first.status_code == 200 and len(first.json()["results"]) == 3
        # one try is left: three more readings are refused before any is made, and the
        # refused request's own try is given back
        again = c.post("/api/samples/read", json={"sample_ids": three, "find_label": False})
        assert again.status_code == 429 and "Retry-After" in again.headers
        assert "pick fewer photos" in again.json()["detail"]
        one = c.post("/api/samples/read", json={"sample_ids": three[:1], "find_label": False})
        assert one.status_code == 200


def test_a_repeated_reading_is_answered_from_memory(visitor: TestClient) -> None:
    ledger = visitor.app.state.model_api.ledger  # type: ignore[attr-defined]
    body = {"sample_ids": ["evga-9800gt-back"], "find_label": True}
    first = visitor.post("/api/samples/read", json=body).json()
    made = len(ledger.entries())
    assert made > 0
    second = visitor.post("/api/samples/read", json=body).json()
    assert second == first and len(ledger.entries()) == made  # no call, no decoding
