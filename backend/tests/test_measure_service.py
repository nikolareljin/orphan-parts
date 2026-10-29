import pytest

from app.config import Settings
from app.measure import Measurer
from app.measure.schema import (
    ImageSize,
    MeasureRequest,
    Point,
    RectangleReference,
    TwoPointReference,
)
from app.profiles import Profiles
from tests.measure_images import (
    CARD,
    CARD_MM,
    OPENING_A,
    OPENING_B,
    RULER_A,
    RULER_B,
    RULER_MM,
    ruler_photo,
)


def pt(xy: tuple[int, int], scale: float = 1.0) -> Point:
    return Point(x=xy[0] * scale, y=xy[1] * scale)


def two_point_request(
    *, straight_on: bool = True, profile: str | None = "vacuum_attachment", scale: float = 1.0
) -> MeasureRequest:
    return MeasureRequest(
        feature="opening_inner_diameter",
        profile=profile,
        image=ImageSize(width=int(640 * scale), height=int(480 * scale)),
        reference=TwoPointReference(
            points=[pt(RULER_A, scale), pt(RULER_B, scale)], length_mm=RULER_MM
        ),
        points=[pt(OPENING_A, scale), pt(OPENING_B, scale)],
        straight_on=straight_on,
    )


@pytest.fixture
def measurer(settings: Settings) -> Measurer:
    return Measurer(settings, Profiles())


def test_two_point_scale_gives_the_known_width_with_its_uncertainty(measurer: Measurer) -> None:
    result = measurer.compute(ruler_photo(), two_point_request())
    assert result.accepted
    assert result.method == "two_point_scale"
    assert result.value_mm == pytest.approx(35.0, abs=0.3)
    assert result.px_per_mm == pytest.approx(4.0, abs=0.01)
    # marks: 2 * 1.5 px over 4 px/mm; scale: 2 * 1.5 px over 400 px plus 0.5 mm over 100 mm
    expected_u = 2 * 1.5 / 4 + 35 * (2 * 1.5 / 400 + 0.5 / 100)
    assert result.uncertainty_mm == pytest.approx(expected_u, abs=0.05)
    assert "two-point scale: 100 mm over 400 px" in result.basis
    assert result.redo is None
    names = [c.name for c in result.checks]
    assert names[:6] == [
        "image_size",
        "points_inside",
        "points_distinct",
        "reference_length",
        "view",
        "sharpness",
    ]
    assert all(c.passed for c in result.checks if c.blocking)


def test_a_tolerance_tighter_than_the_capture_asks_for_a_direct_reading(
    measurer: Measurer,
) -> None:
    result = measurer.compute(ruler_photo(), two_point_request())
    assert result.tolerance_mm == 0.5
    assert result.needs_direct_reading is True
    tolerance = result.checks[-1]
    assert (tolerance.name, tolerance.passed, tolerance.blocking) == ("tolerance", False, False)
    assert "caliper" in tolerance.detail
    loose = measurer.compute(
        ruler_photo(),
        two_point_request(profile="generic_item").model_copy(update={"feature": "width"}),
    )
    assert loose.needs_direct_reading is False
    unknown = measurer.compute(ruler_photo(), two_point_request(profile=None))
    assert unknown.tolerance_mm is None
    assert unknown.needs_direct_reading is None


def test_marks_made_on_a_larger_copy_are_scaled_onto_the_stored_photo(
    measurer: Measurer,
) -> None:
    result = measurer.compute(ruler_photo(), two_point_request(scale=2.0))
    assert result.accepted
    assert result.value_mm == pytest.approx(35.0, abs=0.3)
    assert result.image == ImageSize(width=640, height=480)
    assert result.points[0].x == pytest.approx(OPENING_A[0])


def test_not_straight_on_is_refused_without_a_number(measurer: Measurer) -> None:
    result = measurer.compute(ruler_photo(), two_point_request(straight_on=False))
    assert not result.accepted
    assert result.value_mm is None
    assert result.uncertainty_mm is None
    assert result.redo is not None
    assert result.redo.startswith("view:")
    assert "four corners" in result.redo
    assert result.basis == "no number: the capture was refused"


def test_a_short_reference_is_refused(measurer: Measurer) -> None:
    request = two_point_request().model_copy(
        update={
            "reference": TwoPointReference(
                points=[Point(x=100, y=400), Point(x=150, y=400)], length_mm=12.5
            )
        }
    )
    result = measurer.compute(ruler_photo(), request)
    assert not result.accepted
    assert "reference_length" in (result.redo or "")


def test_a_blurred_photo_is_refused(measurer: Measurer) -> None:
    result = measurer.compute(ruler_photo(blur=4.0), two_point_request())
    assert not result.accepted
    assert "sharpness" in (result.redo or "")


def test_marks_off_the_photo_are_refused(measurer: Measurer) -> None:
    request = two_point_request().model_copy(update={"points": [Point(x=700, y=10), pt(OPENING_B)]})
    result = measurer.compute(ruler_photo(), request)
    assert not result.accepted
    assert "points_inside" in (result.redo or "")


def test_a_small_photo_is_refused(measurer: Measurer) -> None:
    request = two_point_request().model_copy(update={"image": ImageSize(width=320, height=240)})
    request = request.model_copy(
        update={
            "reference": TwoPointReference(
                points=[Point(x=50, y=200), Point(x=250, y=200)], length_mm=100
            ),
            "points": [Point(x=100, y=100), Point(x=170, y=100)],
        }
    )
    result = measurer.compute(ruler_photo(320, 240), request)
    assert not result.accepted
    assert "image_size" in (result.redo or "")


def test_homography_from_a_known_rectangle(measurer: Measurer) -> None:
    request = MeasureRequest(
        feature="width",
        profile="generic_item",
        image=ImageSize(width=640, height=480),
        reference=RectangleReference(
            corners=[Point(x=x, y=y) for x, y in CARD],
            width_mm=CARD_MM[0],
            height_mm=CARD_MM[1],
        ),
        points=[pt(OPENING_A), pt(OPENING_B)],
        straight_on=False,
    )
    result = measurer.compute(ruler_photo(), request)
    assert result.accepted, result.redo
    assert result.method == "homography"
    # the card spans 300 px for 85.6 mm along x; the opening's inner edges are 140 px apart
    expected = 140 * CARD_MM[0] / 300
    assert result.value_mm == pytest.approx(expected, abs=0.2)
    assert "homography from a 85.6 by 53.98 mm rectangle" in result.basis


def test_a_steep_rectangle_is_refused(measurer: Measurer) -> None:
    steep = [Point(x=50, y=50), Point(x=350, y=50), Point(x=350, y=130), Point(x=50, y=130)]
    request = MeasureRequest(
        feature="width",
        profile=None,
        image=ImageSize(width=640, height=480),
        reference=RectangleReference(corners=steep, width_mm=85.6, height_mm=53.98),
        points=[Point(x=80, y=120), Point(x=220, y=120)],
    )
    result = measurer.compute(ruler_photo(), request)
    assert not result.accepted
    assert "view:" in (result.redo or "")
    assert "too steep" in (result.redo or "")


@pytest.mark.anyio
async def test_measure_prepares_the_photo_and_returns_it(measurer: Measurer) -> None:
    result, prepared = await measurer.measure(ruler_photo(), two_point_request())
    assert result.accepted
    assert prepared[:2] == b"\xff\xd8"


def test_corners_on_one_line_are_refused_not_crashed(measurer: Measurer) -> None:
    # four sharp marks along the ruler, equal sides, but all on one line
    flat = [{"x": x, "y": 400} for x in (100, 300, 500, 300)]
    request = MeasureRequest.model_validate(
        {
            "feature": "width",
            "image": {"width": 640, "height": 480},
            "reference": {
                "kind": "rectangle",
                "corners": flat,
                "width_mm": 85.6,
                "height_mm": 53.98,
            },
            "points": [{"x": 200, "y": 200}, {"x": 340, "y": 200}],
        }
    )
    result = measurer.compute(ruler_photo(), request)
    assert result.accepted is False and result.value_mm is None
    geometry_check = next(c for c in result.checks if c.name == "geometry")
    assert geometry_check.passed is False
    assert "unique transform" in result.redo


def test_marks_and_lengths_must_be_finite() -> None:
    def body(points: str, length: str) -> str:
        return (
            '{"feature":"w","image":{"width":640,"height":480},'
            '"reference":{"kind":"two_point","points":' + points + ',"length_mm":' + length + "},"
            '"points":[{"x":1,"y":1},{"x":2,"y":2}],"straight_on":true}'
        )

    with pytest.raises(ValueError):
        MeasureRequest.model_validate_json(body('[{"x":NaN,"y":1},{"x":2,"y":2}]', "100"))
    with pytest.raises(ValueError):
        MeasureRequest.model_validate_json(body('[{"x":1,"y":1},{"x":2,"y":2}]', "Infinity"))
