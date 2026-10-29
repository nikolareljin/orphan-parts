import json

from app.segment import parse_matches
from app.segment.render import shift_path
from tests.conftest import RECORDED_FIXTURES


def fixture_text(name: str) -> str:
    path = RECORDED_FIXTURES / "responses" / f"{name}.json"
    body = json.loads(path.read_text())
    text: str = body["response"]["output"][0]["content"][0]["text"]
    return text


def test_two_label_matches_come_back_with_boxes_masks_and_confidence() -> None:
    matches, warnings = parse_matches(fixture_text("segment-label"))

    assert warnings == []
    assert [m.object_id for m in matches] == ["0", "1"]
    first = matches[0]
    assert (first.left, first.top, first.right, first.bottom) == (200, 300, 440, 380)
    assert (first.source_width, first.source_height) == (640, 480)
    assert first.confidence == 0.88
    assert (first.mask_width, first.mask_height) == (240, 80)
    assert len(first.raster) == 240 * 80
    assert set(first.raster) == {1}
    assert first.svg_path.startswith("M")
    assert matches[1].confidence == 0.41


def test_an_ellipse_mask_covers_less_than_its_box() -> None:
    (match,), _ = parse_matches(fixture_text("segment-item"))
    coverage = sum(match.raster) / len(match.raster)
    assert 0.7 < coverage < 0.85


def test_empty_output_is_zero_matches() -> None:
    assert parse_matches("") == ([], [])


def test_a_malformed_record_is_reported_not_raised() -> None:
    matches, warnings = parse_matches("<0f>0<|box;x1=1|>")
    assert matches == []
    assert warnings and "malformed_record" in warnings[0]


def test_shift_path_moves_and_scales_every_point() -> None:
    assert shift_path("M 0 0 L 10 0 L 10 5 Z", 100, 50) == "M 100 50 L 110 50 L 110 55 Z"
    assert shift_path("M 1 1 Z", 0, 0, 2, 3) == "M 2 3 Z"
    assert shift_path("", 1, 1) == ""
