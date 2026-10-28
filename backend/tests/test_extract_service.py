import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.extract import BadImageError, Extractor, LabelReading
from app.extract.service import INSTRUCTIONS, MAX_OUTPUT_TOKENS, assemble, prompt
from app.model_api import CostLedger, ModelApiClient, ModelResponse, Usage
from tests.conftest import make_photo

pytestmark = pytest.mark.anyio


def reading(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_type": "laptop power adapter",
        "label_text": "OUTPUT 19.5V 3.33A",
        "fields": [
            {"name": "output_voltage", "value": "19.5V", "unit": "V", "confidence": 0.97},
            {"name": "part_number", "value": "P/N OP065", "unit": "", "confidence": 0.9},
        ],
    }
    base.update(overrides)
    return base


def api_response(text: str) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "model": "muse-spark-1.3",
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 1500, "output_tokens": 200, "images_processed": 1},
    }


class Capture:
    """A live client whose server is a function; keeps the request body."""

    def __init__(self, settings: Settings, body: dict[str, Any]) -> None:
        self.sent: list[dict[str, Any]] = []
        self.ledger = CostLedger(cap_usd=25.0)

        def handler(request: httpx.Request) -> httpx.Response:
            self.sent.append(json.loads(request.content))
            return httpx.Response(200, json=body)

        self.client = ModelApiClient(settings, self.ledger, transport=httpx.MockTransport(handler))
        self.extractor = Extractor(settings, self.client)


async def test_recorded_fixture_yields_normalised_fields(recorded_settings: Settings) -> None:
    client = ModelApiClient(recorded_settings, CostLedger(cap_usd=25.0))
    result = await Extractor(recorded_settings, client).extract([make_photo()])

    assert result.from_fixture is True
    assert result.cost_usd == 0.0
    assert result.model == "muse-spark-1.3"
    assert result.item_type == "laptop power adapter"
    assert result.fields["output_voltage"].value == "19.5"
    assert result.fields["output_voltage"].unit == "V"
    assert result.fields["output_current"].value == "3.33"
    assert result.fields["part_number"].value == "OP065-19-333"
    assert result.fields["part_number"].raw == "P/N OP065-19-333"
    assert result.fields["connector"].value == "barrel 4.5 x 3 mm"
    assert result.fields["certifications"].value == "UL, CE, FCC"
    assert all(e.source == "photo" for e in result.fields.values())
    assert result.warnings == []


async def test_request_carries_prompt_schema_and_one_image_per_photo(
    live_settings: Settings,
) -> None:
    cap = Capture(live_settings, api_response(json.dumps(reading())))
    result = await cap.extractor.extract([make_photo(), make_photo(50, 50, "PNG")])

    (body,) = cap.sent
    assert body["model"] == live_settings.model_spark
    assert body["instructions"] == INSTRUCTIONS
    assert body["reasoning"] == {"effort": live_settings.extract_reasoning_effort}
    assert body["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert body["text"]["format"]["name"] == "LabelReading"
    assert body["text"]["format"]["strict"] is True
    parts = body["input"][0]["content"]
    assert parts[0] == {"type": "input_text", "text": prompt()}
    assert [p["type"] for p in parts[1:]] == ["input_image", "input_image"]
    assert all(p["image_url"].startswith("data:image/jpeg;base64,") for p in parts[1:])
    assert result.photos == 2
    assert result.from_fixture is False
    assert result.cost_usd > 0


async def test_unknown_blank_and_weak_fields_become_warnings(live_settings: Settings) -> None:
    fields = [
        {"name": "wattage", "value": "65", "unit": "W", "confidence": 0.9},
        {"name": "brand", "value": "   ", "unit": "", "confidence": 0.9},
        {"name": "connector", "value": "5.5x2.1", "unit": "", "confidence": 0.3},
    ]
    cap = Capture(live_settings, api_response(json.dumps(reading(fields=fields))))
    result = await cap.extractor.extract([make_photo()])

    assert set(result.fields) == {"connector"}
    assert result.warnings == [
        "ignored a field the label set does not know: 'wattage'",
        "no part or model number was read; add a sharper photo of the label",
        "low confidence: connector",
    ]


async def test_duplicate_field_keeps_the_more_confident_reading(live_settings: Settings) -> None:
    fields = [
        {"name": "output_voltage", "value": "19V", "unit": "V", "confidence": 0.4},
        {"name": "OUTPUT_VOLTAGE", "value": "19.5V", "unit": "V", "confidence": 0.9},
        {"name": "output_voltage", "value": "12V", "unit": "V", "confidence": 0.5},
        {"name": "model_number", "value": "X1", "unit": "", "confidence": 1.7},
    ]
    cap = Capture(live_settings, api_response(json.dumps(reading(fields=fields))))
    result = await cap.extractor.extract([make_photo()])

    assert result.fields["output_voltage"].value == "19.5"
    assert result.fields["output_voltage"].confidence == 0.9
    assert result.fields["model_number"].confidence == 1.0


async def test_photo_limits_are_enforced_before_any_call(live_settings: Settings) -> None:
    cap = Capture(live_settings, api_response("{}"))
    with pytest.raises(BadImageError, match="at least one photo"):
        await cap.extractor.extract([])
    too_many = [make_photo()] * (live_settings.max_photos + 1)
    with pytest.raises(BadImageError, match=f"at most {live_settings.max_photos} photos"):
        await cap.extractor.extract(too_many)
    with pytest.raises(BadImageError, match="not an image"):
        await cap.extractor.extract([b"nope"])
    assert cap.sent == []


def test_assemble_handles_an_empty_reading() -> None:
    response = ModelResponse(
        id="r",
        model="muse-spark-1.3",
        status="completed",
        text="{}",
        output=[],
        usage=Usage(),
        cost_usd=0.0,
        from_fixture=True,
        attempts=1,
    )
    result = assemble(LabelReading(item_type="  ", label_text="", fields=[]), response, 1)
    assert result.item_type == "unknown item"
    assert result.fields == {}
    assert result.warnings == ["no part or model number was read; add a sharper photo of the label"]
