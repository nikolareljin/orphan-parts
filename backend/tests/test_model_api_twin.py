"""The fixture twin: a request through the demo door is answered from the recordings by the
twin and recorded in its ledger that goes nowhere; the code's door reaches the key."""

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.model_api import CostLedger, FixtureMissingError, ModelApiClient
from app.ops.door import live_request

pytestmark = pytest.mark.anyio


async def test_the_door_picks_the_client(live_settings: Settings, tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    ledger = CostLedger(25.0)
    client = ModelApiClient(live_settings, ledger, transport=httpx.MockTransport(handler))
    twin_ledger = CostLedger(25.0)
    client.twin = ModelApiClient(
        live_settings.model_copy(update={"fake_api": True, "fixtures_dir": tmp_path / "none"}),
        twin_ledger,
    )
    spark = live_settings.model_spark

    # the demo door: the twin answers (an empty fixtures directory has nothing to answer
    # with), the key is never called, the live ledger stays empty
    token = live_request.set(False)
    try:
        with pytest.raises(FixtureMissingError):
            await client.respond(model=spark, input="what is this", op="extract")
        with pytest.raises(FixtureMissingError):
            await client.transcribe(b"RIFF....WAVE", op="transcribe")
        assert await client.list_models() == [
            live_settings.model_spark,
            live_settings.model_wonder,
            live_settings.model_image,
            live_settings.model_voice,
            live_settings.model_sam,
        ]
    finally:
        live_request.reset(token)
    assert calls == [] and ledger.total_usd == 0.0 and len(ledger.entries()) == 0

    # the code's door: the key answers and the ledger records it
    answer = await client.respond(model=spark, input="what is this", op="extract")
    assert answer.text == "hello" and answer.from_fixture is False
    assert calls == ["/v1/responses"] or calls == ["/responses"]
    assert len(ledger.entries()) == 1 and len(twin_ledger.entries()) == 0

    # no twin (a machine of your own): the door changes nothing
    client.twin = None
    token = live_request.set(False)
    try:
        assert (await client.respond(model=spark, input="again", op="extract")).text == "hello"
    finally:
        live_request.reset(token)
    assert len(calls) == 2
    await client.aclose()
