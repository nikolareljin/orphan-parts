import pytest

from app.extract import FIELDS, field_guide, normalize


@pytest.mark.parametrize(
    ("kind", "text", "expected"),
    [
        ("volts", "19.5V", ("19.5", "V")),
        ("volts", "DC 19,5 V", ("19.5", "V")),
        ("volts", "OUTPUT: 20.0V 3.25A", ("20", "V")),
        ("volts_range", "100-240V~ 50/60Hz", ("100-240", "V")),
        ("volts_range", "100 ~ 240 V", ("100-240", "V")),
        ("volts_range", "100 to 240 V", ("100-240", "V")),
        ("volts_range", "230V", ("230", "V")),
        ("volts_range", "12V 1.5A", ("12", "V")),
        ("amps", "3.33A", ("3.33", "A")),
        ("amps", "3330mA", ("3.33", "A")),
        ("amps", "1.5 A max", ("1.5", "A")),
        ("watts", "65W", ("65", "W")),
        ("watts", "65.0 Watt", ("65", "W")),
        ("code", "P/N: OP065-19-333", ("OP065-19-333", "")),
        ("code", "model no. op-65n", ("OP-65N", "")),
        ("code", "ADP 65DB", ("ADP65DB", "")),
        ("code", "P/N ADP_65DB", ("ADP_65DB", "")),
        ("connector", "barrel 4.5x3.0mm", ("barrel 4.5 x 3 mm", "")),
        ("connector", "5.5 X 2.5", ("barrel 5.5 x 2.5 mm", "")),
        ("connector", f"5.5{chr(0xD7)}2.1mm", ("barrel 5.5 x 2.1 mm", "")),
        ("connector", "5,5x2,5", ("barrel 5.5 x 2.5 mm", "")),
        ("connector", "USB Type-C", ("usb-c", "")),
        ("connector", "USB-C", ("usb-c", "")),
        ("connector", "magsafe 2", ("magsafe 2", "")),
        ("polarity", "Center positive", ("center positive", "")),
        ("polarity", "centre negative", ("center negative", "")),
        ("polarity", "inner +", ("inner +", "")),
        ("list", "UL CE FCC", ("UL, CE, FCC", "")),
        ("list", "ul, ce; fcc / ul", ("UL, CE, FCC", "")),
        ("text", "  light  scuffs on the  case ", ("light scuffs on the case", "")),
        ("material", "Stainless steel, all-metal", ("metal", "")),
        ("material", "ABS plastic", ("plastic", "")),
        ("material", "metal rod, plastic head", ("metal rod, plastic head", "")),
        ("material", "wood", ("wood", "")),
    ],
)
def test_normalizers(kind: str, text: str, expected: tuple[str, str]) -> None:
    assert normalize(kind, text) == expected


def test_unparseable_number_keeps_the_text_and_the_unit() -> None:
    assert normalize("volts", "see label") == ("see label", "V")


def test_default_unit_fills_a_missing_one() -> None:
    assert normalize("text", "19.5", default_unit="V") == ("19.5", "V")
    assert normalize("volts", "19.5V", default_unit="mV") == ("19.5", "V")


def test_unknown_normalizer_falls_back_to_text() -> None:
    assert normalize("no-such-kind", " a  b ") == ("a b", "")


def test_field_guide_lists_every_field_with_its_unit() -> None:
    guide = field_guide()
    for spec in FIELDS:
        assert f"- {spec.name}:" in guide
    assert "(unit: V)" in guide
