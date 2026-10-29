import pytest

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, ItemCreate
from app.match import AssessError, Assessor, AssessRequest, Check, Side, verdict_for
from app.measure import Measurer
from app.profiles import Profiles
from tests.measure_images import OPENING_A, OPENING_B, RULER_A, RULER_B, RULER_MM, ruler_photo

pytestmark = pytest.mark.anyio


def check(key: str, status: str, *, hard: bool = True, identity: bool = False) -> Check:
    return Check(
        key=key,
        label=key.replace("_", " ").capitalize(),
        kind="equal",
        hard=hard,
        identity=identity,
        status=status,  # type: ignore[arg-type]
        needed="x",
        observed="y",
        unit="",
        basis="",
    )


def test_the_ladder_from_the_checks_alone() -> None:
    assert verdict_for([check("a", "pass"), check("b", "fail")])[0] == "CONFLICT"
    assert (
        verdict_for([check("a", "fail"), check("pn", "pass", hard=False, identity=True)])[0]
        == "CONFLICT"
    )
    assert (
        verdict_for([check("pn", "pass", hard=False, identity=True), check("a", "unknown")])[0]
        == "EXACT_MATCH"
    )
    assert verdict_for([check("a", "pass"), check("b", "pass")])[0] == "COMPATIBLE_LIKELY"
    likely, why = verdict_for([check("a", "pass"), check("c", "fail", hard=False)])
    assert likely == "COMPATIBLE_LIKELY" and "soft rule differs: c" in why
    assert verdict_for([check("a", "pass"), check("b", "unknown")])[0] == "VISUALLY_SIMILAR"
    assert verdict_for([check("a", "unknown"), check("b", "unknown")])[0] == "INSUFFICIENT_INFO"
    assert verdict_for([])[0] == "INSUFFICIENT_INFO"
    # a profile without hard rules reports, it does not rule
    assert verdict_for([check("w", "pass", hard=False)])[0] == "COMPATIBLE_LIKELY"
    assert verdict_for([check("w", "fail", hard=False)])[0] == "VISUALLY_SIMILAR"
    assert verdict_for([check("w", "unknown", hard=False)])[0] == "INSUFFICIENT_INFO"


@pytest.fixture
def assessor(settings: Settings) -> Assessor:
    return Assessor(Profiles(), Inventory(settings))


def laptop(inventory: Inventory) -> int:
    item = inventory.create(ItemCreate(item_type="laptop", name="Laptop", profile="power_adapter"))
    for field, value, unit in [
        ("output_voltage", "19.5", "V"),
        ("output_current", "3.33", "A"),
        ("polarity", "center positive", ""),
        ("plug_outer_diameter", "4.5", "mm"),
        ("plug_inner_diameter", "3.0", "mm"),
    ]:
        inventory.add_field(
            item.id, FieldCreate(field=field, value=value, unit=unit, provenance="documented")
        )
    return item.id


def test_values_written_in_against_an_item(assessor: Assessor) -> None:
    need = laptop(assessor.inventory)
    result = assessor.assess(
        AssessRequest(
            need=Side(item_id=need),
            candidate=Side(
                values={
                    "output_voltage": "19.5 V",
                    "output_current": "4.62 A",
                    "polarity": "centre positive",
                    "plug_outer_diameter": "4.5 mm",
                    "plug_inner_diameter": "3.0",
                }
            ),
        )
    )
    assert result.profile == "power_adapter"
    assert result.verdict == "COMPATIBLE_LIKELY"
    by_key = {c.key: c for c in result.checks}
    assert by_key["output_voltage"].status == "pass"
    assert by_key["output_current"].status == "pass"
    assert by_key["polarity"].status == "pass"
    assert by_key["part_number"].status == "unknown"
    assert "Part number" in result.missing  # the laptop names no part number
    assert result.questions == []  # nothing is asked for a rule the need does not state
    assert result.need_item == need and result.candidate_item is None


def test_a_conflict_on_voltage_outranks_everything(assessor: Assessor) -> None:
    need = laptop(assessor.inventory)
    inv = assessor.inventory
    adapter = inv.create(ItemCreate(item_type="power adapter", name="Orbital 12 V"))
    for field, value in [
        ("output_voltage", "12"),
        ("output_current", "5"),
        ("polarity", "center positive"),
        ("plug_outer_diameter", "4.5"),
        ("plug_inner_diameter", "3.0"),
        ("part_number", "OP065-19-333"),
    ]:
        inv.add_field(adapter.id, FieldCreate(field=field, value=value))
    inv.add_field(need, FieldCreate(field="part_number", value="OP065-19-333"))
    result = assessor.assess(
        AssessRequest(need=Side(item_id=need), candidate=Side(item_id=adapter.id))
    )
    assert result.verdict == "CONFLICT"
    assert "output voltage" in result.summary
    assert {c.key: c.status for c in result.checks}["part_number"] == "pass"
    assert result.candidate_item == adapter.id


def test_unknowns_become_seller_questions_and_proposed_values_are_listed(
    assessor: Assessor,
) -> None:
    need = laptop(assessor.inventory)
    inv = assessor.inventory
    adapter = inv.create(ItemCreate(item_type="power adapter", name="Mystery"))
    inv.add_field(adapter.id, FieldCreate(field="output_voltage", value="19.5"))
    # an observation still to confirm counts, and is listed as such
    inv.add_field(adapter.id, FieldCreate(field="output_current", value="3.42"))
    result = assessor.assess(
        AssessRequest(need=Side(item_id=need), candidate=Side(item_id=adapter.id))
    )
    assert result.verdict == "VISUALLY_SIMILAR"
    assert any(q.startswith("Is the centre of the plug positive") for q in result.questions)
    assert any("outer diameter of the plug" in q for q in result.questions)
    assert result.to_confirm == []
    backing = {c.key: c.backing for c in result.checks}["output_voltage"]
    assert backing is not None and backing.provenance == "owner_reported"


async def test_a_measured_value_carries_its_uncertainty(
    assessor: Assessor, settings: Settings
) -> None:
    inv = assessor.inventory
    tool = inv.create(ItemCreate(item_type="crevice tool", profile="vacuum_attachment"))
    measurer = Measurer(settings, assessor.profiles)
    request = {
        "feature": "opening_inner_diameter",
        "profile": "vacuum_attachment",
        "image": {"width": 640, "height": 480},
        "reference": {
            "kind": "two_point",
            "points": [{"x": RULER_A[0], "y": RULER_A[1]}, {"x": RULER_B[0], "y": RULER_B[1]}],
            "length_mm": RULER_MM,
        },
        "points": [{"x": OPENING_A[0], "y": OPENING_A[1]}, {"x": OPENING_B[0], "y": OPENING_B[1]}],
        "straight_on": True,
    }
    from app.measure import MeasureRequest

    result, prepared = await measurer.measure(ruler_photo(), MeasureRequest.model_validate(request))
    assert result.accepted and result.uncertainty_mm is not None
    inv.add_measurement(tool.id, result, prepared)

    fits = assessor.assess(
        AssessRequest(
            need=Side(profile="vacuum_attachment", values={"opening_inner_diameter": "35"}),
            candidate=Side(item_id=tool.id),
        )
    )
    opening = {c.key: c for c in fits.checks}["opening_inner_diameter"]
    assert opening.backing is not None and opening.backing.uncertainty == result.uncertainty_mm
    assert opening.backing.source == "measurement" and opening.backing.review == "proposed"
    assert "Opening inner diameter" in fits.to_confirm
    # the capture is coarser than the 0.5 mm tolerance: a near miss cannot be decided
    near = assessor.assess(
        AssessRequest(
            need=Side(profile="vacuum_attachment", values={"opening_inner_diameter": "35.6"}),
            candidate=Side(item_id=tool.id),
        )
    )
    near_check = {c.key: c for c in near.checks}["opening_inner_diameter"]
    assert near_check.status == "unknown"
    assert any(q.startswith("Opening inner diameter: a caliper") for q in near.questions)
    far = assessor.assess(
        AssessRequest(
            need=Side(profile="vacuum_attachment", values={"opening_inner_diameter": "32"}),
            candidate=Side(item_id=tool.id),
        )
    )
    assert far.verdict == "CONFLICT"


def test_the_profile_must_come_from_somewhere(assessor: Assessor) -> None:
    with pytest.raises(AssessError, match="no profile"):
        assessor.assess(AssessRequest(need=Side(values={"a": "1"}), candidate=Side()))
    with pytest.raises(AssessError, match="no profile 'toaster'"):
        assessor.assess(AssessRequest(need=Side(profile="toaster"), candidate=Side()))
