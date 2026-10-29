import pytest

from app.match import Reading, evaluate
from app.match.rules import allowance, normal, number, unit_of
from app.profiles import Rule


def rule(kind: str = "within", **over: object) -> Rule:
    spec: dict[str, object] = {"key": "output_voltage", "label": "Output voltage", "kind": kind}
    spec.update(over)
    return Rule.model_validate(spec)


def test_number_reads_the_first_number_with_either_decimal_mark() -> None:
    assert number("19.5 V") == 19.5
    assert number("19,5V") == 19.5
    assert number("centre positive") is None


def test_unit_of_reads_the_recorded_unit_or_the_one_written_after_the_number() -> None:
    assert unit_of(Reading("19.5", unit="V")) == "V"
    assert unit_of(Reading("19.5 V")) == "V"
    assert unit_of(Reading("3300mA")) == "mA"
    assert unit_of(Reading("4.5 mm (caliper)")) == "mm"
    assert unit_of(Reading("4.5")) == ""
    assert unit_of(Reading("35 (about)")) == ""


def test_a_value_in_another_unit_on_either_side_is_not_compared() -> None:
    amps = rule("at_least", key="output_current", label="Output current", unit="A")
    # 3300 mA would pass as 3300 A; it must not
    written = evaluate(amps, Reading("3.33 A"), Reading("3300 mA"))
    assert written.status == "unknown"
    assert "in mA" in written.basis and "enter it in A" in written.basis
    recorded = evaluate(amps, Reading("3.33"), Reading("3300", unit="mA"))
    assert recorded.status == "unknown"
    needed = evaluate(amps, Reading("3330 mA"), Reading("4.62"))
    assert needed.status == "unknown" and "required value is in mA" in needed.basis
    # the rule's own unit, in any case, is fine; so is no unit at all
    assert evaluate(amps, Reading("3.33 a"), Reading("4.62A")).status == "pass"
    assert evaluate(amps, Reading("3.33"), Reading("4.62")).status == "pass"
    # a rule without a unit compares bare numbers whatever is written after them
    bare = rule("at_least", key="count", label="Count", unit="")
    assert evaluate(bare, Reading("2 pcs"), Reading("3 pcs")).status == "pass"


def test_normal_uses_the_field_normaliser_and_lower_case() -> None:
    assert normal("polarity", "Centre positive") == normal("polarity", "center positive (+)")
    assert normal("connector", "5.5x2.5mm barrel") == normal("connector", "barrel 5.5 x 2.5 mm")
    assert normal("colour", "  Dark   Grey ") == "dark grey"


def test_allowance_takes_the_larger_of_absolute_and_relative() -> None:
    assert allowance(rule(tolerance=0.5), 19.5) == 0.5
    assert allowance(rule(tolerance_pct=5), 20.0) == pytest.approx(1.0)
    assert allowance(rule(tolerance=0.5, tolerance_pct=5), 20.0) == pytest.approx(1.0)


def test_missing_values_are_unknown_not_a_pass() -> None:
    assert evaluate(rule(), None, Reading("19.5")).status == "unknown"
    assert evaluate(rule(), Reading("19.5"), None).status == "unknown"
    check = evaluate(rule(), Reading("19.5"), None)
    assert check.needed == "19.5" and check.observed == ""


def test_within_passes_fails_or_stays_unknown_with_uncertainty() -> None:
    r = rule(tolerance_pct=5, unit="V")
    assert evaluate(r, Reading("19.5 V"), Reading("19.5")).status == "pass"
    assert evaluate(r, Reading("19.5 V"), Reading("20")).status == "pass"
    failed = evaluate(r, Reading("19.5 V"), Reading("12 V"))
    assert failed.status == "fail"
    assert "off by 7.5 V" in failed.basis
    # a measured value: the uncertainty straddles the tolerance, so nobody can say
    mm = rule(key="plug_outer_diameter", label="Plug outer diameter", tolerance=0.1, unit="mm")
    assert evaluate(mm, Reading("4.5"), Reading("4.5", uncertainty=0.05)).status == "pass"
    on_edge = evaluate(mm, Reading("4.5"), Reading("4.55", uncertainty=0.3))
    assert on_edge.status == "unknown"
    assert "not precise enough" in on_edge.basis
    assert evaluate(mm, Reading("4.5"), Reading("5.5", uncertainty=0.3)).status == "fail"


def test_at_least_and_at_most_use_the_tolerance_as_slack() -> None:
    amps = rule("at_least", key="output_current", label="Output current", unit="A")
    assert evaluate(amps, Reading("3.33 A"), Reading("4.62")).status == "pass"
    assert evaluate(amps, Reading("3.33 A"), Reading("3.33")).status == "pass"
    assert evaluate(amps, Reading("3.33 A"), Reading("2.5")).status == "fail"
    assert evaluate(amps, Reading("3.33 A"), Reading("3.3", uncertainty=0.1)).status == "unknown"
    width = rule("at_most", key="width", label="Width", unit="mm", tolerance=2)
    assert evaluate(width, Reading("100"), Reading("101.5")).status == "pass"
    assert evaluate(width, Reading("100"), Reading("103")).status == "fail"


def test_equal_compares_normalised_text() -> None:
    pol = rule("equal", key="polarity", label="Polarity")
    assert evaluate(pol, Reading("center positive"), Reading("Centre positive")).status == "pass"
    failed = evaluate(pol, Reading("center positive"), Reading("center negative"))
    assert failed.status == "fail"
    assert "is not" in failed.basis
    assert evaluate(pol, Reading("   "), Reading("center positive")).status == "unknown"


def test_numbers_missing_from_text_are_unknown() -> None:
    r = rule(tolerance=1)
    assert evaluate(r, Reading("unknown"), Reading("19.5")).status == "unknown"
    assert evaluate(r, Reading("19.5"), Reading("see label")).status == "unknown"
