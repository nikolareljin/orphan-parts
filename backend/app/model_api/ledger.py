"""Spend ledger: one line per Model API call, a running total and a hard cap."""

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.model_api.errors import SpendCapError
from app.model_api.pricing import Usage

log = logging.getLogger("app.model_api.ledger")


class LedgerEntry(BaseModel):
    ts: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat(timespec="seconds"))
    request_id: str = "-"
    op: str
    model: str
    endpoint: str
    usage: Usage = Field(default_factory=Usage)
    usd: float = 0.0
    fixture: bool = False
    attempts: int = 1
    ms: float = 0.0


class ModelTotals(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0


class LedgerSummary(BaseModel):
    total_usd: float
    cap_usd: float
    remaining_usd: float
    paused: bool
    calls: int
    live_calls: int
    fixture_calls: int
    by_model: dict[str, ModelTotals]


class CostLedger:
    """Thread-safe running total, kept by one process. Entries are appended to a JSON-lines file
    when a path is set and read back once at startup; the file is the record, the total is not
    shared between processes, so the service runs one."""

    def __init__(self, cap_usd: float, path: Path | None = None) -> None:
        self.cap_usd = cap_usd
        self.path = path
        self._lock = threading.Lock()
        self._entries: list[LedgerEntry] = []
        self._total = 0.0
        if path is not None:
            self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            return
        bad = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = LedgerEntry.model_validate_json(line)
            except ValueError:
                bad += 1
                continue
            self._entries.append(entry)
            self._total += entry.usd
        if bad:
            log.warning("ledger %s: skipped %d unreadable lines", path, bad)

    @property
    def total_usd(self) -> float:
        return round(self._total, 6)

    @property
    def remaining_usd(self) -> float:
        return round(max(self.cap_usd - self._total, 0.0), 6)

    @property
    def paused(self) -> bool:
        return self._total >= self.cap_usd

    def require_budget(self) -> None:
        if self.paused:
            raise SpendCapError(self.total_usd, self.cap_usd)

    def record(self, entry: LedgerEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            self._total += entry.usd
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry.model_dump(), separators=(",", ":")) + "\n")
        if self.paused:
            log.warning(
                "spend cap reached", extra={"total_usd": self.total_usd, "cap_usd": self.cap_usd}
            )

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def summary(self) -> LedgerSummary:
        by_model: dict[str, ModelTotals] = {}
        live = 0
        for e in self._entries:
            t = by_model.setdefault(e.model, ModelTotals())
            t.calls += 1
            t.input_tokens += e.usage.input_tokens
            t.output_tokens += e.usage.output_tokens
            t.usd = round(t.usd + e.usd, 6)
            if not e.fixture:
                live += 1
        return LedgerSummary(
            total_usd=self.total_usd,
            cap_usd=self.cap_usd,
            remaining_usd=self.remaining_usd,
            paused=self.paused,
            calls=len(self._entries),
            live_calls=live,
            fixture_calls=len(self._entries) - live,
            by_model=by_model,
        )
