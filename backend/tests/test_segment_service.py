import dataclasses
import json
from typing import Any

import anyio
import httpx
import pytest

from app.config import Settings
from app.extract import BadImageError
from app.model_api import CostLedger, ModelApiClient, ModelApiError
from app.segment import DEFAULT_CONCEPTS, Segmenter, phrase_for
from app.segment.parse import parse_matches
from app.segment.service import MAX_REGIONS_PER_CONCEPT, assemble, op_for
from tests.conftest import RECORDED_FIXTURES, make_photo

pytestmark = pytest.mark.anyio


def fixture_line(name: str) -> str:
    body = json.loads((RECORDED_FIXTURES / "responses" / f"{name}.json").read_text())
    text: str = body["response"]["output"][0]["content"][0]["text"]
    return text


def sam_response(text: str) -> dict[str, Any]:
    return {
        "id": "resp_sam",
        "object": "response",
        "status": "completed",
        "model": "sam-3.1",
        "output": [
            {
                "id": "msg_sam",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 0, "output_tokens": 0, "images_processed": 1},
    }


class Capture:
    """A live client whose server answers from a table keyed by the concept phrase."""

    def __init__(self, settings: Settings, answers: dict[str, str]) -> None:
        self.sent: list[dict[str, Any]] = []
        self.ledger = CostLedger(cap_usd=25.0)

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.sent.append(body)
            phrase = body["input"][0]["content"][0]["text"]
            return httpx.Response(200, json=sam_response(answers.get(phrase, "")))

        self.client = ModelApiClient(settings, self.ledger, transport=httpx.MockTransport(handler))
        self.segmenter = Segmenter(settings, self.client)


async def test_recorded_fixtures_yield_regions_crops_and_an_overlay(
    recorded_settings: Settings,
) -> None:
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    result = await Segmenter(recorded_settings, client).segment(make_photo())

    assert result.from_fixture is True
    assert result.cost_usd == 0.0
    assert (result.width, result.height) == (640, 480)
    assert [r.concept for r in result.regions] == ["item", "label", "label", "connector"]
    label = result.regions[1]
    assert label.confidence == 0.88
    assert label.box.model_dump() == {"left": 200, "top": 300, "right": 440, "bottom": 380}
    assert label.coverage == 1.0
    assert label.crop.startswith("data:image/jpeg;base64,")
    assert label.svg_path.startswith("M ") and label.svg_path.endswith(" Z")
    assert float(label.svg_path.split()[1]) == pytest.approx(200, abs=1)
    assert result.overlay.startswith("data:image/jpeg;base64,")
    assert result.warnings == []
    assert result.regions[0].coverage < 1.0  # the item mask is an ellipse


async def test_one_request_per_concept_with_the_phrase_and_the_metadata(
    live_settings: Settings,
) -> None:
    cap = Capture(live_settings, {phrase_for("label"): fixture_line("segment-label")})
    result = await cap.segmenter.segment(make_photo(), ["label", "hinge"])

    # the calls are in flight together, so their order on the wire is not fixed
    assert [b["model"] for b in cap.sent] == [live_settings.model_sam] * 2
    sent_phrases = sorted(b["input"][0]["content"][0]["text"] for b in cap.sent)
    assert sent_phrases == sorted([phrase_for("label"), "hinge"])
    metadata = {"include_confidence": "true", "mask_encoding": "one_bit"}
    assert all(b["metadata"] == metadata for b in cap.sent)
    assert all(b["input"][0]["content"][1]["type"] == "input_image" for b in cap.sent)
    assert [r.concept for r in result.regions] == ["label", "label"]
    assert result.warnings == ["no hinge found"]
    assert result.from_fixture is False
    assert result.cost_usd == pytest.approx(2 * 2.50 / 1000)
    assert sorted(e.op for e in cap.ledger.entries()) == sorted([op_for("label"), op_for("hinge")])


async def test_concepts_are_asked_together(live_settings: Settings) -> None:
    # every request is held until all of them have arrived: one after another would never get there
    arrived = 0
    everyone = anyio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal arrived
        arrived += 1
        if arrived == len(DEFAULT_CONCEPTS):
            everyone.set()
        await everyone.wait()
        return httpx.Response(200, json=sam_response(""))

    client = ModelApiClient(
        live_settings, CostLedger(cap_usd=25.0), transport=httpx.MockTransport(handler)
    )
    with anyio.fail_after(5):
        result = await Segmenter(live_settings, client).segment(make_photo())
    assert arrived == len(DEFAULT_CONCEPTS)
    assert result.regions == []
    assert sorted(result.warnings) == sorted(f"no {k} found" for k in DEFAULT_CONCEPTS)


async def test_one_failed_concept_fails_the_request_with_its_own_error(
    live_settings: Settings,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["input"][0]["content"][0]["text"] == "hinge":
            return httpx.Response(
                400, json={"error": {"message": "no such concept", "type": "invalid_request"}}
            )
        return httpx.Response(200, json=sam_response(fixture_line("segment-label")))

    client = ModelApiClient(
        live_settings, CostLedger(cap_usd=25.0), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ModelApiError, match="no such concept") as info:
        await Segmenter(live_settings, client).segment(make_photo(), ["label", "hinge"])
    assert not isinstance(info.value, BaseExceptionGroup)


def test_boxes_fall_back_to_the_size_of_the_copy_that_was_sent() -> None:
    # a match that does not name the size the model saw is scaled by the copy's own size
    matches, _ = parse_matches(fixture_line("segment-label"))
    nameless = dataclasses.replace(matches[0], source_width=0, source_height=0)
    photo = make_photo(1280, 960)
    found = [("label", "p", nameless)]
    regions, _ = assemble(photo, 1280, 960, found, seen=(640, 480))
    assert regions[0].box.model_dump() == {"left": 400, "top": 600, "right": 880, "bottom": 760}
    regions, _ = assemble(photo, 1280, 960, found)
    assert regions[0].box.model_dump() == {"left": 200, "top": 300, "right": 440, "bottom": 380}


async def test_boxes_are_scaled_onto_the_prepared_photo(live_settings: Settings) -> None:
    # the fixture line was recorded at 640x480; a 1280x960 photo gets boxes twice the size
    cap = Capture(live_settings, {phrase_for("label"): fixture_line("segment-label")})
    result = await cap.segmenter.segment(make_photo(1280, 960), ["label"])

    assert result.regions[0].box.model_dump() == {
        "left": 400,
        "top": 600,
        "right": 880,
        "bottom": 760,
    }


async def test_matches_are_capped_and_ordered_by_confidence(live_settings: Settings) -> None:
    cap = Capture(live_settings, {phrase_for("label"): fixture_line("segment-label")})
    result = await cap.segmenter.segment(make_photo(), ["label"])
    confidences = [r.confidence for r in result.regions]
    assert confidences == sorted(confidences, key=lambda c: -(c or 0))
    assert len(result.regions) <= MAX_REGIONS_PER_CONCEPT


async def test_limits_are_checked_before_any_call(live_settings: Settings) -> None:
    cap = Capture(live_settings, {})
    with pytest.raises(BadImageError, match="at least one concept"):
        await cap.segmenter.segment(make_photo(), [" "])
    with pytest.raises(BadImageError, match="at most 6 concepts"):
        await cap.segmenter.segment(make_photo(), list("abcdefg"))
    with pytest.raises(BadImageError, match="not an image"):
        await cap.segmenter.segment(b"nope")
    assert cap.sent == []


def test_default_concepts_and_op_names() -> None:
    assert DEFAULT_CONCEPTS == ("item", "label", "connector")
    assert op_for("Hose Opening") == "segment-hose-opening"
    assert op_for("!!") == "segment-concept"
