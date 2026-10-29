"""One rule, two readings, one of three answers. Nothing here calls a model."""

import re
from dataclasses import dataclass

from app.extract.fields import FIELD_BY_NAME
from app.extract.normalize import normalize
from app.match.schema import Backing, Check, Status
from app.profiles import Rule

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
# the unit written right after the first number: "19.5 V", "3300mA", "4.5 mm (caliper)"
_UNIT_AFTER = re.compile(r"[-+]?\d+(?:[.,]\d+)?\s*([A-Za-zµΩ°%]+)")


@dataclass(frozen=True)
class Reading:
    """A value on one side of the comparison, with how precise it is when that is known."""

    value: str
    unit: str = ""
    uncertainty: float | None = None
    backing: Backing | None = None


def number(text: str) -> float | None:
    """The first number in the text, or None."""
    m = _NUMBER.search(text)
    return float(m.group(0).replace(",", ".")) if m else None


def unit_of(reading: Reading) -> str:
    """The unit the reading is in: the one recorded with it, else the one written in the text."""
    if reading.unit.strip():
        return reading.unit.strip()
    m = _UNIT_AFTER.search(reading.value)
    return m.group(1) if m else ""


def normal(key: str, text: str) -> str:
    """Text as the label normaliser for the field would write it, lower case, one space."""
    spec = FIELD_BY_NAME.get(key)
    value, _ = normalize(spec.normalizer if spec else "text", text)
    return " ".join(value.lower().split())


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def allowance(rule: Rule, needed: float) -> float:
    """The slack a numeric rule allows around the needed value, in its unit."""
    absolute = rule.tolerance or 0.0
    relative = abs(needed) * (rule.tolerance_pct or 0.0) / 100.0
    return max(absolute, relative)


def evaluate(rule: Rule, need: Reading | None, cand: Reading | None) -> Check:
    """Apply one rule. A missing value on either side is unknown, never a pass."""
    base = {
        "key": rule.key,
        "label": rule.label,
        "kind": rule.kind,
        "hard": rule.hard,
        "identity": rule.identity,
        "unit": rule.unit,
        "needed": need.value if need else "",
        "observed": cand.value if cand else "",
        "backing": cand.backing if cand else None,
    }
    if need is None:
        return Check(**base, status="unknown", basis="no required value was given")
    if cand is None:
        return Check(**base, status="unknown", basis="the candidate's value is not known")
    if rule.kind == "equal":
        return Check(**base, **_equal(rule, need, cand))
    return Check(**base, **_numeric(rule, need, cand))


def _equal(rule: Rule, need: Reading, cand: Reading) -> dict[str, str]:
    a, b = normal(rule.key, need.value), normal(rule.key, cand.value)
    if not a or not b:
        return {"status": "unknown", "basis": "one side is empty after normalisation"}
    if a == b:
        return {"status": "pass", "basis": f"both read {a!r}"}
    return {"status": "fail", "basis": f"{b!r} is not {a!r}"}


def _numeric(rule: Rule, need: Reading, cand: Reading) -> dict[str, str]:
    # a number in another unit is not compared: 19500 mV is not 19500 V
    for side, reading in (("required", need), ("candidate's", cand)):
        unit = unit_of(reading)
        if rule.unit and unit and unit.lower() != rule.unit.lower():
            return {
                "status": "unknown",
                "basis": f"the {side} value is in {unit}, the rule compares {rule.unit};"
                f" enter it in {rule.unit}",
            }
    n, c = number(need.value), number(cand.value)
    if n is None:
        return {"status": "unknown", "basis": f"no number in the required value {need.value!r}"}
    if c is None:
        return {"status": "unknown", "basis": f"no number in the candidate's {cand.value!r}"}
    u = cand.uncertainty or 0.0
    unit = f" {rule.unit}".rstrip()
    about = f"±{_fmt(u)}{unit}" if u else "as stated"
    if rule.kind == "within":
        t = allowance(rule, n)
        d = abs(c - n)
        if d + u <= t:
            status: Status = "pass"
        elif d - u > t:
            status = "fail"
        else:
            status = "unknown"
        basis = (
            f"{_fmt(c)}{unit} ({about}) against {_fmt(n)}{unit} ±{_fmt(t)}{unit}:"
            f" off by {_fmt(d)}{unit}"
        )
    else:
        slack = allowance(rule, n)
        if rule.kind == "at_least":
            floor = n - slack
            status = "pass" if c - u >= floor else "fail" if c + u < floor else "unknown"
            basis = f"{_fmt(c)}{unit} ({about}) must be at least {_fmt(floor)}{unit}"
        else:
            ceiling = n + slack
            status = "pass" if c + u <= ceiling else "fail" if c - u > ceiling else "unknown"
            basis = f"{_fmt(c)}{unit} ({about}) must be at most {_fmt(ceiling)}{unit}"
    if status == "unknown":
        basis += "; the capture is not precise enough to decide, take a caliper reading"
    return {"status": status, "basis": basis}
