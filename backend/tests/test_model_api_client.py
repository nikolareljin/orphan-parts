import base64
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.model_api import (
    CostLedger,
    FixtureMissingError,
    FixtureStore,
    IncompleteResponseError,
    ModelApiClient,
    ModelApiError,
    SpendCapError,
    image_part,
    strict_schema,
    text_part,
    user_message,
)

pytestmark = pytest.mark.anyio

SAMPLE_VALUE = "sample-value-for-tests"
Handler = Callable[[httpx.Request], httpx.Response]


def completed(text: str, *, input_tokens: int = 100, output_tokens: int = 20) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "model": "muse-spark-1.3",
        "output": [
            {"id": "rs_1", "type": "reasoning", "summary": []},
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens,
        },
    }


def error_body(status: int, error_type: str, code: str | None, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={"error": {"message": message, "type": error_type, "code": code}}
    )


class Harness:
    def __init__(self, settings: Settings, handler: Handler, cap: float = 25.0) -> None:
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.ledger = CostLedger(cap_usd=cap)

        def wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)

        self.client = ModelApiClient(
            settings,
            self.ledger,
            FixtureStore(settings.fixtures_dir),
            transport=httpx.MockTransport(wrapped),
            sleep=fake_sleep,
            rng=random.Random(7),
        )

    def body(self, index: int = -1) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.requests[index].content)
        return data


@pytest.fixture
def live(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=False,
        model_api_key=SAMPLE_VALUE,
        model_api_max_attempts=3,
        fixtures_dir=tmp_path / "fixtures",
        _env_file=None,
    )


@pytest.fixture
def fixture_mode(tmp_path: Path) -> Settings:
    return Settings(OPL_FAKE_API=True, fixtures_dir=tmp_path / "fixtures", _env_file=None)


# --- live calls --------------------------------------------------------------


async def test_successful_call_sends_auth_and_records_cost(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("DDR4 8GB")))
    result = await h.client.respond(model="muse-spark-1.3", input="read", op="extract")

    assert result.text == "DDR4 8GB"
    assert result.attempts == 1
    assert result.from_fixture is False
    assert result.cost_usd == pytest.approx((100 * 1.25 + 20 * 4.25) / 1_000_000)
    assert h.requests[0].headers["authorization"] == f"Bearer {SAMPLE_VALUE}"
    assert h.requests[0].url.path == "/v1/responses"
    body = h.body()
    assert body["model"] == "muse-spark-1.3"
    assert body["store"] is False
    assert body["prompt_cache_key"] == "orphan-parts"
    summary = h.ledger.summary()
    assert summary.calls == 1
    assert summary.total_usd == pytest.approx(result.cost_usd)
    assert summary.by_model["muse-spark-1.3"].input_tokens == 100


async def test_request_carries_effort_instructions_and_limits(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("ok")))
    await h.client.respond(
        model="muse-spark-1.3",
        input=[user_message(text_part("hi"))],
        instructions="be brief",
        effort="low",
        max_output_tokens=64,
        tools=[{"type": "function", "name": "lookup", "parameters": {}}],
    )
    body = h.body()
    assert body["reasoning"] == {"effort": "low"}
    assert body["instructions"] == "be brief"
    assert body["max_output_tokens"] == 64
    assert body["tools"][0]["name"] == "lookup"
    assert body["input"][0]["content"][0] == {"type": "input_text", "text": "hi"}


async def test_unknown_effort_is_rejected_before_any_request(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("ok")))
    with pytest.raises(ValueError, match="reasoning effort"):
        await h.client.respond(model="m", input="x", effort="turbo")
    assert h.requests == []


async def test_rate_limit_is_retried_after_the_header_delay(live: Settings) -> None:
    answers = iter(
        [
            httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={"error": {"message": "slow down", "type": "rate_limit_error"}},
            ),
            httpx.Response(200, json=completed("ok")),
        ]
    )
    h = Harness(live, lambda _: next(answers))
    result = await h.client.respond(model="muse-spark-1.3", input="x")
    assert result.attempts == 2
    assert h.sleeps == [2.0]
    assert len(h.requests) == 2


async def test_retry_after_is_capped(live: Settings) -> None:
    answers = iter(
        [
            httpx.Response(503, headers={"Retry-After": "600"}, json={}),
            httpx.Response(200, json=completed("ok")),
        ]
    )
    h = Harness(live, lambda _: next(answers))
    await h.client.respond(model="muse-spark-1.3", input="x")
    assert h.sleeps == [live.model_api_retry_after_max_s]


async def test_server_errors_back_off_and_give_up_after_max_attempts(live: Settings) -> None:
    h = Harness(live, lambda _: error_body(500, "server_error", None, "boom"))
    with pytest.raises(ModelApiError) as info:
        await h.client.respond(model="muse-spark-1.3", input="x")
    assert info.value.status == 500
    assert info.value.attempts == 3
    assert len(h.requests) == 3
    assert len(h.sleeps) == 2
    assert 0.5 <= h.sleeps[0] < 1.5
    assert 1.0 <= h.sleeps[1] < 2.0
    assert "HTTP 500 server_error: boom" in str(info.value)
    assert h.ledger.summary().calls == 0


async def test_client_errors_are_not_retried(live: Settings) -> None:
    h = Harness(live, lambda _: error_body(400, "invalid_request_error", None, "bad input"))
    with pytest.raises(ModelApiError) as info:
        await h.client.respond(model="muse-spark-1.3", input="x")
    assert info.value.status == 400
    assert info.value.retryable is False
    assert len(h.requests) == 1
    assert h.sleeps == []


async def test_error_messages_never_contain_the_key(live: Settings) -> None:
    h = Harness(
        live,
        lambda _: error_body(
            401, "authentication_error", "invalid_api_key", f"bad key {SAMPLE_VALUE}"
        ),
    )
    with pytest.raises(ModelApiError) as info:
        await h.client.respond(model="muse-spark-1.3", input="x")
    assert SAMPLE_VALUE not in str(info.value)
    assert "***" in str(info.value)
    assert info.value.code == "invalid_api_key"


async def test_timeouts_are_retried(live: Settings) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=completed("ok"))

    h = Harness(live, handler)
    result = await h.client.respond(model="muse-spark-1.3", input="x")
    assert result.attempts == 2


async def test_spend_cap_blocks_before_the_request(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("ok")), cap=0.0)
    with pytest.raises(SpendCapError):
        await h.client.respond(model="muse-spark-1.3", input="x")
    assert h.requests == []


async def test_voice_call_prices_the_audio_it_transcribed(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("hello")))
    result = await h.client.respond(
        model="muse-voice-transcribe-1.0", input="x", op="transcribe", audio_seconds=1800
    )
    assert result.cost_usd == pytest.approx(0.09)
    (entry,) = h.ledger.entries()
    assert entry.usage.audio_seconds == 1800


async def test_negative_caller_counts_are_rejected(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed("hello")))
    with pytest.raises(ValidationError):
        await h.client.respond(model="muse-voice-transcribe-1.0", input="x", audio_seconds=-1)
    with pytest.raises(ValidationError):
        await h.client.respond(model="muse-spark-1.3", input="x", search_queries=-1)


async def test_incomplete_and_refused_responses_raise(live: Settings) -> None:
    incomplete = completed("partial")
    incomplete["status"] = "incomplete"
    incomplete["incomplete_details"] = {"reason": "max_output_tokens"}
    h = Harness(live, lambda _: httpx.Response(200, json=incomplete))
    with pytest.raises(IncompleteResponseError, match="max_output_tokens"):
        await h.client.respond(model="muse-spark-1.3", input="x")
    # the call is still on the ledger: tokens were billed
    assert h.ledger.summary().calls == 1

    refused = completed("")
    refused["output"][1]["content"] = [{"type": "refusal", "refusal": "no"}]
    h2 = Harness(live, lambda _: httpx.Response(200, json=refused))
    with pytest.raises(IncompleteResponseError, match="refused"):
        await h2.client.respond(model="muse-spark-1.3", input="x")


# --- structured output -------------------------------------------------------


class Label(BaseModel):
    part_number: str
    capacity_gb: int | None
    tags: list[str]


def test_strict_schema_closes_every_object() -> None:
    schema = strict_schema(Label)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["part_number", "capacity_gb", "tags"]


async def test_structured_output_sends_schema_and_parses(live: Settings) -> None:
    payload = '{"part_number": "M378A1K43CB2", "capacity_gb": 8, "tags": ["ddr4"]}'
    h = Harness(live, lambda _: httpx.Response(200, json=completed(payload)))
    result = await h.client.respond_structured(Label, model="muse-spark-1.3", input="read")
    assert result.parsed.part_number == "M378A1K43CB2"
    assert result.parsed.capacity_gb == 8
    fmt = h.body()["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "Label"
    assert fmt["strict"] is True
    assert fmt["schema"]["additionalProperties"] is False


async def test_structured_output_that_does_not_parse_raises(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json=completed('{"part_number": 1}')))
    with pytest.raises(IncompleteResponseError, match="did not match Label"):
        await h.client.respond_structured(Label, model="muse-spark-1.3", input="read")


# --- fixture and record modes -------------------------------------------------


def never(_: httpx.Request) -> httpx.Response:
    raise AssertionError("no request may leave the process in fixture mode")


async def test_fixture_mode_replays_without_network(fixture_mode: Settings) -> None:
    store = FixtureStore(fixture_mode.fixtures_dir)
    path = store.path_for("/responses", "extract")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": "/responses",
                "op": "extract",
                "key": "x",
                "response": completed("from fixture"),
            }
        )
    )
    h = Harness(fixture_mode, never)
    result = await h.client.respond(model="muse-spark-1.3", input="anything", op="extract")
    assert result.text == "from fixture"
    assert result.from_fixture is True
    assert result.cost_usd == 0.0
    assert h.ledger.summary().fixture_calls == 1
    assert h.ledger.total_usd == 0.0


async def test_fixture_mode_reports_a_missing_fixture(fixture_mode: Settings) -> None:
    h = Harness(fixture_mode, never)
    with pytest.raises(FixtureMissingError, match="op=extract"):
        await h.client.respond(model="muse-spark-1.3", input="x", op="extract")


async def test_recorded_failures_replay_as_errors(fixture_mode: Settings) -> None:
    store = FixtureStore(fixture_mode.fixtures_dir)
    path = store.path_for("/responses", "extract")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "endpoint": "/responses",
                "op": "extract",
                "key": "x",
                "status": 400,
                "response": {"error": {"message": "nope", "type": "invalid_request_error"}},
            }
        )
    )
    h = Harness(fixture_mode, never)
    with pytest.raises(ModelApiError, match="HTTP 400 invalid_request_error: nope"):
        await h.client.respond(model="muse-spark-1.3", input="x", op="extract")


async def test_record_mode_saves_a_fixture_that_replays(tmp_path: Path) -> None:
    recording = Settings(
        OPL_FAKE_API=False,
        OPL_RECORD_FIXTURES=True,
        model_api_key=SAMPLE_VALUE,
        fixtures_dir=tmp_path / "fixtures",
        _env_file=None,
    )
    assert recording.model_api_mode == "record"
    h = Harness(recording, lambda _: httpx.Response(200, json=completed("recorded")))
    first = await h.client.respond(model="muse-spark-1.3", input="same", op="extract")
    assert first.from_fixture is False
    assert len(list((tmp_path / "fixtures" / "responses").glob("*.json"))) == 1

    replay = Settings(OPL_FAKE_API=True, fixtures_dir=tmp_path / "fixtures", _env_file=None)
    h2 = Harness(replay, never)
    second = await h2.client.respond(model="muse-spark-1.3", input="same", op="extract")
    assert second.text == "recorded"
    assert second.from_fixture is True


async def test_each_recording_gets_its_own_transcribe_fixture(tmp_path: Path) -> None:
    recording = Settings(
        OPL_FAKE_API=False,
        OPL_RECORD_FIXTURES=True,
        model_api_key=SAMPLE_VALUE,
        fixtures_dir=tmp_path / "fixtures",
        _env_file=None,
    )
    heard = {"transcript": "one", "audioDurationMs": 1000}
    h = Harness(recording, lambda _: httpx.Response(200, json=heard))
    await h.client.transcribe(b"RIFF one")
    await h.client.transcribe(b"RIFF two")
    assert len(list((tmp_path / "fixtures").rglob("*.json"))) == 2
    # the key names the recording; the request on the wire carries the bytes, not the digest
    assert b"audio_sha256" not in h.requests[-1].content


# --- pictures ----------------------------------------------------------------


async def test_a_picture_is_asked_for_as_documented_and_priced_per_image(live: Settings) -> None:
    jpeg = b"\xff\xd8\xff\xe0 a jpeg"
    answer = {
        "created": 1761868800,
        "data": [{"b64_json": base64.b64encode(jpeg).decode("ascii"), "revised_prompt": "lamp"}],
        "output_format": "jpeg",
        "usage": {
            "input_tokens": 48,
            "output_tokens": 1024,
            "total_tokens": 1072,
            "input_tokens_details": {"image_tokens": 0, "text_tokens": 48},
        },
    }
    h = Harness(live, lambda _: httpx.Response(200, json=answer))
    result = await h.client.picture("a lamp built from a laptop", op="picture")
    assert result.data == jpeg
    assert result.revised_prompt == "lamp"
    assert result.model == "muse-image-1.0"
    assert result.cost_usd == pytest.approx(0.01)  # one image, whatever the tokens
    assert result.from_fixture is False and result.attempts == 1
    assert h.requests[0].url.path == "/v1/images/generations"
    assert h.body() == {
        "model": "muse-image-1.0",
        "prompt": "a lamp built from a laptop",
        "n": 1,
        "size": "1024x1024",
        "response_format": "b64_json",
        "output_format": "jpeg",
        "reasoning_strength": "low",
    }
    totals = h.ledger.summary().by_model["muse-image-1.0"]
    assert (totals.calls, totals.input_tokens, totals.output_tokens) == (1, 48, 1024)
    assert h.ledger.entries()[0].usage.images == 1


async def test_an_answer_without_an_image_is_incomplete_and_still_charged(live: Settings) -> None:
    h = Harness(live, lambda _: httpx.Response(200, json={"created": 1, "data": [{"url": "x"}]}))
    with pytest.raises(IncompleteResponseError, match="no image"):
        await h.client.picture("a lamp")
    assert h.ledger.summary().calls == 1
    h = Harness(live, lambda _: httpx.Response(200, json={"data": [{"b64_json": "!!not base64"}]}))
    with pytest.raises(IncompleteResponseError, match="no image"):
        await h.client.picture("a lamp")
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n not a jpeg").decode("ascii")
    h = Harness(live, lambda _: httpx.Response(200, json={"data": [{"b64_json": png}]}))
    with pytest.raises(IncompleteResponseError, match="no image"):
        await h.client.picture("a lamp")
    assert h.ledger.summary().calls == 1


# --- models and readiness -----------------------------------------------------


async def test_list_models_in_fixture_mode_returns_the_configured_ids(
    fixture_mode: Settings,
) -> None:
    h = Harness(fixture_mode, never)
    assert await h.client.list_models() == [
        "muse-spark-1.3",
        "muse-wonder-1.0",
        "muse-image-1.0",
        "muse-voice-transcribe-1.0",
        "sam-3.1",
    ]
    assert (await h.client.check())["mode"] == "fixture"


async def test_list_models_live_parses_ids(live: Settings) -> None:
    h = Harness(
        live,
        lambda _: httpx.Response(
            200, json={"object": "list", "data": [{"id": "muse-spark-1.3"}, {"id": "sam-3.1"}]}
        ),
    )
    assert await h.client.list_models() == ["muse-spark-1.3", "sam-3.1"]
    assert h.requests[0].method == "GET"
    assert h.requests[0].url.path == "/v1/models"


async def test_check_reports_an_unreachable_api(live: Settings) -> None:
    h = Harness(live, lambda _: error_body(401, "authentication_error", "invalid_api_key", "no"))
    result = await h.client.check()
    assert result["reachable"] is False
    assert "invalid_api_key" in result["error"]
    await h.client.aclose()


# --- input helpers -------------------------------------------------------------


def test_image_part_builds_a_data_url() -> None:
    part = image_part(b"\xff\xd8\xff", "image/jpeg")
    assert part["type"] == "input_image"
    assert part["image_url"].startswith("data:image/jpeg;base64,")


def test_image_part_rejects_unsupported_types() -> None:
    with pytest.raises(ValueError, match="unsupported image type"):
        image_part(b"x", "image/tiff")


def test_user_message_wraps_parts() -> None:
    msg = user_message(text_part("a"), image_part(b"x", "image/png"))
    assert msg["role"] == "user"
    assert [p["type"] for p in msg["content"]] == ["input_text", "input_image"]
