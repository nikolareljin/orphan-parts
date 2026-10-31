"""What a run prints: one line per operation, a total, and nothing that is a credential."""

import sys
from dataclasses import dataclass, field
from typing import TextIO

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

HEADER = (
    f"{'op':<20} {'model':<26} {'status':<6} {'ms':>7} {'in':>6} {'out':>6} {'reas':>5}"
    f" {'usd':>9}  note"
)


@dataclass
class Result:
    op: str
    model: str = "-"
    status: str = SKIP
    ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    usd: float = 0.0
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def line(self) -> str:
        return (
            f"{self.op:<20} {self.model:<26} {self.status:<6} {self.ms:>7.0f} "
            f"{self.input_tokens:>6} {self.output_tokens:>6} {self.reasoning_tokens:>5} "
            f"{self.usd:>9.6f}  {self.note}"
        )


@dataclass
class Run:
    results: list[Result] = field(default_factory=list)

    @property
    def spent(self) -> float:
        return round(sum(r.usd for r in self.results), 6)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    def total(self) -> str:
        passed = sum(1 for r in self.results if r.status == PASS)
        failed = sum(1 for r in self.results if r.status == FAIL)
        skipped = sum(1 for r in self.results if r.status == SKIP)
        return (
            f"total: {len(self.results)} ops, {passed} passed, {failed} failed, "
            f"{skipped} skipped, spent ${self.spent:.4f}"
        )


class Redacting:
    """A text stream that never lets a credential through: every secret it was given is
    replaced before a line reaches the terminal, whatever wrote it."""

    def __init__(self, inner: TextIO, secrets: list[str]) -> None:
        self._inner = inner
        # the longest first, so a secret that contains another is covered whole
        self._secrets = sorted({s for s in secrets if len(s) >= 4}, key=len, reverse=True)

    def write(self, text: str) -> int:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return self._inner.write(text)

    def flush(self) -> None:
        self._inner.flush()

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return self._inner.encoding


def install_redaction(secrets: list[str]) -> None:
    sys.stdout = Redacting(sys.stdout, secrets)
    sys.stderr = Redacting(sys.stderr, secrets)


class RefusedError(RuntimeError):
    """The run must not start: said once, exit code 2."""


def said(name: str, value: str) -> str:
    """How a credential is reported: whether it is set and how long it is, never what it is."""
    return f"{name}: set ({len(value)} chars)" if value else f"{name}: missing"


def one_line(exc: BaseException) -> str:
    """The exception's own message on one line, cut short; never a request or its body."""
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    return text if len(text) <= 160 else text[:157] + "..."
