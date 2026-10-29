import pytest

from app.measure import geometry
from app.measure.schema import Point


def p(x: float, y: float) -> Point:
    return Point(x=x, y=y)


def test_distance_and_scale() -> None:
    assert geometry.distance(p(0, 0), p(3, 4)) == 5.0
    assert geometry.scale_from_two_points(p(100, 400), p(500, 400), 100.0) == 4.0


def test_homography_recovers_a_known_projective_transform() -> None:
    known = [[1.2, 0.1, 30.0], [0.05, 0.9, -10.0], [0.0005, 0.0002, 1.0]]
    src = [p(0, 0), p(400, 0), p(400, 300), p(0, 300)]
    dst = [geometry.apply(known, s) for s in src]
    found = geometry.homography(src, dst)
    for probe in (p(10, 20), p(200, 150), p(390, 290), p(50, 280)):
        expected = geometry.apply(known, probe)
        got = geometry.apply(found, probe)
        assert got.x == pytest.approx(expected.x, abs=1e-6)
        assert got.y == pytest.approx(expected.y, abs=1e-6)


def test_rectangle_plane_maps_an_oblique_card_back_to_millimetres() -> None:
    width, height = 85.6, 53.98
    # the card as a camera at an angle would see it: a known mm-to-pixel transform
    to_pixels = [[3.5, 0.4, 120.0], [-0.2, 3.1, 80.0], [0.0008, 0.0011, 1.0]]
    card = [p(0, 0), p(width, 0), p(width, height), p(0, height)]
    corners = [geometry.apply(to_pixels, c) for c in card]
    plane = geometry.rectangle_plane(corners, width, height)
    for mm in (p(10, 10), p(42.8, 27), p(80, 50)):
        back = geometry.apply(plane, geometry.apply(to_pixels, mm))
        assert back.x == pytest.approx(mm.x, abs=1e-6)
        assert back.y == pytest.approx(mm.y, abs=1e-6)
    a = geometry.apply(plane, geometry.apply(to_pixels, p(10, 20)))
    b = geometry.apply(plane, geometry.apply(to_pixels, p(45, 20)))
    assert geometry.distance(a, b) == pytest.approx(35.0, abs=1e-6)


def test_degenerate_points_are_refused() -> None:
    same = [p(1, 1)] * 4
    with pytest.raises(ValueError, match="unique transform"):
        geometry.homography(same, same)
    with pytest.raises(ValueError, match="four point pairs"):
        geometry.homography([p(0, 0)], [p(0, 0)])


def test_side_lengths_walk_the_corners_in_order() -> None:
    assert geometry.side_lengths([p(0, 0), p(4, 0), p(4, 3), p(0, 3)]) == [4.0, 3.0, 4.0, 3.0]
