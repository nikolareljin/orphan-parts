"""What a run prints: one line per operation, a total, and nothing that is a credential."""

import atexit
import json
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
    # skipped before the run: its ceiling alone is above --max-usd, said up front
    planned: bool = False

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
        """Every op run passed, and one at least; an op skipped up front by its ceiling was
        named before the run and does not fail it."""
        ran = [r for r in self.results if not r.planned]
        return bool(ran) and all(r.passed for r in ran)

    def total(self) -> str:
        passed = sum(1 for r in self.results if r.status == PASS)
        failed = sum(1 for r in self.results if r.status == FAIL)
        skipped = sum(1 for r in self.results if r.status == SKIP)
        planned = sum(1 for r in self.results if r.planned)
        up_front = f" ({planned} on the ceiling alone, named before the run)" if planned else ""
        return (
            f"total: {len(self.results)} ops, {passed} passed, {failed} failed, "
            f"{skipped} skipped{up_front}, spent ${self.spent:.4f}"
        )


# every credential the run knows of, and the forms it takes when echoed as JSON or a repr;
# filled once by install_redaction
_SECRETS: list[str] = []


def _forms(secrets: list[str]) -> list[str]:
    """Each secret as written, as a JSON string body and as a repr body; the longest first, so
    a secret that contains another is covered whole. Shorter than 4 is no secret."""
    found: set[str] = set()
    for secret in secrets:
        if len(secret) < 4:
            continue
        found.update({secret, json.dumps(secret)[1:-1], repr(secret)[1:-1]})
    return sorted(found, key=len, reverse=True)


def _replace(text: str, forms: list[str]) -> str:
    for secret in forms:
        text = text.replace(secret, "***")
    return text


def redact(text: str) -> str:
    """``text`` with every secret install_redaction was given replaced by ``***``."""
    return _replace(text, _SECRETS)


class Redacting:
    """A text stream that never lets a credential through: every secret it was given is
    replaced before a line reaches the terminal, whatever wrote it. Text is held until its
    line ends, so a secret split over two writes is still caught (no secret holds a line
    break); a line left without one goes out at ``drain``, which runs on exit."""

    def __init__(self, inner: TextIO, secrets: list[str]) -> None:
        self._inner = inner
        self._secrets = _forms(secrets)
        self._pending = ""

    def write(self, text: str) -> int:
        self._pending += text
        if "\n" in self._pending:
            lines, _, self._pending = self._pending.rpartition("\n")
            self._inner.write(_replace(lines + "\n", self._secrets))
        return len(text)

    def drain(self) -> None:
        if self._pending:
            self._inner.write(_replace(self._pending, self._secrets))
            self._pending = ""
        self._inner.flush()

    def flush(self) -> None:
        # a partial line stays held: the rest of a secret may be in the next write
        self._inner.flush()

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return self._inner.encoding


def install_redaction(secrets: list[str]) -> None:
    _SECRETS[:] = _forms(secrets)
    out = Redacting(sys.stdout, secrets)
    err = Redacting(sys.stderr, secrets)
    sys.stdout = out
    sys.stderr = err
    atexit.register(err.drain)
    atexit.register(out.drain)


class RefusedError(RuntimeError):
    """The run must not start: said once, exit code 2."""


def said(name: str, value: str) -> str:
    """How a credential is reported: whether it is set and how long it is, never what it is."""
    return f"{name}: set ({len(value)} chars)" if value else f"{name}: missing"


def one_line(exc: BaseException) -> str:
    """The exception's own message on one line, cut short; never a request or its body."""
    text = redact(" ".join(str(exc).split())) or exc.__class__.__name__
    # redacted before it is cut: a cut would leave a secret's head that no filter recognizes
    return text if len(text) <= 160 else text[:157] + "..."
