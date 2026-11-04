"""Fixture mode served to a person: a request with no recording of its own is refused, not
answered (and saved) with the operation's stand-in, unless FIXTURE_STUBS lets it."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import CostLedger, ModelApiClient, NoStandInError
from app.model_api.errors import NO_STAND_IN_LINE
from app.ops.door import served_request
from tests.conftest import RECORDED_FIXTURES, make_photo


def _settings(tmp_path: Path, stubs: bool) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        FIXTURE_STUBS=stubs,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        log_format="text",
    )


@pytest.fixture
def strict(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(tmp_path, stubs=False))) as c:
        yield c


def _laptop(c: TestClient) -> int:
    item = c.post(
        "/api/items",
        json={"item_type": "laptop", "name": "Old laptop", "tests_done": "boots"},
    ).json()
    return int(item["id"])


def test_an_unrecorded_ask_is_refused_and_nothing_is_saved(strict: TestClient) -> None:
    item_id = _laptop(strict)
    asked = strict.post(f"/api/items/{item_id}/uses")
    assert asked.status_code == 409, asked.text
    assert asked.json()["detail"] == NO_STAND_IN_LINE
    assert "MODEL_API_KEY" in NO_STAND_IN_LINE and "OPL_FAKE_API=0" in NO_STAND_IN_LINE
    events = [e["change"] for e in strict.get(f"/api/items/{item_id}/events").json()]
    assert not [e for e in events if e.startswith("uses written")]
    assert strict.get(f"/api/items/{item_id}/decide").json()["uses"] is None


def test_an_own_photo_without_a_recording_is_refused(strict: TestClient) -> None:
    read = strict.post("/api/extract", files={"photos": ("label.jpg", make_photo(), "image/jpeg")})
    assert read.status_code == 409, read.text
    assert read.json()["detail"] == NO_STAND_IN_LINE


def test_the_stand_in_still_answers_when_stubs_are_on(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path, stubs=True))) as c:
        item_id = _laptop(c)
        asked = c.post(f"/api/items/{item_id}/uses")
        assert asked.status_code == 201, asked.text
        assert asked.json()["from_fixture"] is True


@pytest.mark.anyio
async def test_outside_a_served_request_the_stand_in_answers(tmp_path: Path) -> None:
    # the demo loader, the eval and the tools run outside the API: they keep the stand-ins
    settings = _settings(tmp_path, stubs=False)
    client = ModelApiClient(settings, CostLedger(settings.spend_cap_usd))
    try:
        answer = await client.respond(model=settings.model_spark, input="hello", op="extract")
        assert answer is not None
        token = served_request.set(True)
        try:
            with pytest.raises(NoStandInError):
                await client.respond(model=settings.model_spark, input="hello", op="extract")
        finally:
            served_request.reset(token)
    finally:
        await client.aclose()
