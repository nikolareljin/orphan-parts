import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.model_api import LedgerEntry, Usage
from app.model_api.__main__ import main


def test_spend_starts_empty_and_reflects_the_cap(client: TestClient) -> None:
    body = client.get("/api/spend").json()
    assert body["calls"] == 0
    assert body["total_usd"] == 0.0
    assert body["cap_usd"] == 25.0
    assert body["paused"] is False


def test_spend_lists_recorded_calls(client: TestClient) -> None:
    ledger = client.app.state.ledger  # type: ignore[attr-defined]
    ledger.record(
        LedgerEntry(
            op="extract",
            model="muse-spark-1.3",
            endpoint="/responses",
            usage=Usage(input_tokens=10, output_tokens=2),
            usd=0.01,
        )
    )
    body = client.get("/api/spend").json()
    assert body["calls"] == 1
    assert body["live_calls"] == 1
    assert body["by_model"]["muse-spark-1.3"]["usd"] == 0.01


def test_readyz_reports_spend_and_pause_state(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body["spend_usd"] == 0.0
    assert body["spend_cap_usd"] == 25.0
    assert body["paused"] is False


def test_ledger_file_lives_in_the_data_dir(client: TestClient) -> None:
    settings = client.app.state.settings  # type: ignore[attr-defined]
    ledger = client.app.state.ledger  # type: ignore[attr-defined]
    ledger.record(LedgerEntry(op="t", model="m", endpoint="/responses", usd=0.0))
    assert (settings.data_dir / "model_api_spend.jsonl").exists()


def test_check_command_prints_mode_and_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPL_FAKE_API", "1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert main(["check"]) == 0
    finally:
        get_settings.cache_clear()
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "fixture"
    assert "muse-spark-1.3" in out["models"]
    assert out["spend"]["calls"] == 0


def test_check_command_rejects_other_arguments() -> None:
    assert main(["frobnicate"]) == 2
