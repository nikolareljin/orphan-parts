"""The fields a label can yield for the first category, power adapters.

Category profiles as data come with the matcher; until then this one table is the contract
between the prompt, the normalisers and the evidence table.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    description: str
    unit: str = ""
    normalizer: str = "text"


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("brand", "manufacturer or brand name printed on the label"),
    FieldSpec("model_number", "model designation printed on the label", normalizer="code"),
    FieldSpec("part_number", "part number or P/N code, often next to a barcode", normalizer="code"),
    FieldSpec("input_voltage", "mains input range, for example 100-240 V", "V", "volts_range"),
    FieldSpec("output_voltage", "DC output voltage", "V", "volts"),
    FieldSpec("output_current", "DC output current", "A", "amps"),
    FieldSpec("output_power", "rated output power", "W", "watts"),
    FieldSpec(
        "connector",
        "plug type and size, for example barrel 5.5 x 2.5 mm or USB-C",
        normalizer="connector",
    ),
    FieldSpec(
        "polarity", "center positive or center negative, from the symbol", normalizer="polarity"
    ),
    FieldSpec("certifications", "safety marks such as UL, CE or FCC", normalizer="list"),
    FieldSpec("condition_notes", "visible wear, damage or missing parts"),
)

FIELD_BY_NAME: dict[str, FieldSpec] = {f.name: f for f in FIELDS}
FIELD_NAMES: frozenset[str] = frozenset(FIELD_BY_NAME)


def field_guide() -> str:
    """The field list as it goes into the prompt."""
    lines = []
    for f in FIELDS:
        unit = f" (unit: {f.unit})" if f.unit else ""
        lines.append(f"- {f.name}: {f.description}{unit}")
    return "\n".join(lines)
