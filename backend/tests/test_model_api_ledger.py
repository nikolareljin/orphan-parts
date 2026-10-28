from pathlib import Path

import pytest

from app.model_api.errors import SpendCapError
from app.model_api.ledger import CostLedger, LedgerEntry
from app.model_api.pricing import Usage


def entry(usd: float, model: str = "muse-spark-1.3", fixture: bool = False) -> LedgerEntry:
    return LedgerEntry(
        op="t",
        model=model,
        endpoint="/responses",
        usage=Usage(input_tokens=10, output_tokens=5),
        usd=usd,
        fixture=fixture,
    )


def test_total_and_remaining_follow_the_entries() -> None:
    ledger = CostLedger(cap_usd=1.0)
    ledger.record(entry(0.25))
    ledger.record(entry(0.5))
    assert ledger.total_usd == pytest.approx(0.75)
    assert ledger.remaining_usd == pytest.approx(0.25)
    assert ledger.paused is False


def test_cap_pauses_live_calls() -> None:
    ledger = CostLedger(cap_usd=0.3)
    ledger.require_budget()
    ledger.record(entry(0.3))
    assert ledger.paused is True
    with pytest.raises(SpendCapError, match="spend cap reached"):
        ledger.require_budget()


def test_zero_cap_pauses_immediately() -> None:
    with pytest.raises(SpendCapError):
        CostLedger(cap_usd=0.0).require_budget()


def test_entries_persist_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "spend" / "ledger.jsonl"
    first = CostLedger(cap_usd=5.0, path=path)
    first.record(entry(0.1))
    first.record(entry(0.2, model="muse-wonder-1.0"))
    assert len(path.read_text().splitlines()) == 2

    again = CostLedger(cap_usd=5.0, path=path)
    assert again.total_usd == pytest.approx(0.3)
    assert len(again.entries()) == 2


def test_unreadable_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(entry(0.1).model_dump_json() + "\nnot json\n\n")
    ledger = CostLedger(cap_usd=5.0, path=path)
    assert ledger.total_usd == pytest.approx(0.1)


def test_summary_groups_by_model_and_counts_fixture_calls() -> None:
    ledger = CostLedger(cap_usd=5.0)
    ledger.record(entry(0.1))
    ledger.record(entry(0.0, fixture=True))
    ledger.record(entry(0.4, model="muse-wonder-1.0"))
    summary = ledger.summary()
    assert summary.calls == 3
    assert summary.live_calls == 2
    assert summary.fixture_calls == 1
    assert summary.by_model["muse-spark-1.3"].calls == 2
    assert summary.by_model["muse-spark-1.3"].input_tokens == 20
    assert summary.by_model["muse-wonder-1.0"].usd == pytest.approx(0.4)
    assert summary.total_usd == pytest.approx(0.5)
