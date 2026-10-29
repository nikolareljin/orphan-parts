from app.measure.quality import inside, sharpness_at
from app.measure.schema import Point
from tests.measure_images import OPENING_A, RULER_A, ruler_photo


def test_sharp_edges_score_high_and_blur_scores_low() -> None:
    marks = [Point(x=RULER_A[0], y=RULER_A[1]), Point(x=OPENING_A[0], y=OPENING_A[1])]
    sharp = sharpness_at(ruler_photo(), marks)
    blurred = sharpness_at(ruler_photo(blur=4.0), marks)
    assert sharp > 400
    assert blurred < 100
    assert sharp > 5 * blurred


def test_a_mark_on_a_featureless_patch_scores_near_zero() -> None:
    flat = [Point(x=600, y=40)]
    assert sharpness_at(ruler_photo(), flat) < 1


def test_the_weakest_window_decides() -> None:
    marks = [Point(x=RULER_A[0], y=RULER_A[1]), Point(x=600, y=40)]
    assert sharpness_at(ruler_photo(), marks) < 1


def test_inside_is_half_open() -> None:
    assert inside(Point(x=0, y=0), 640, 480)
    assert inside(Point(x=639.9, y=479.9), 640, 480)
    assert not inside(Point(x=640, y=10), 640, 480)
    assert not inside(Point(x=-1, y=10), 640, 480)
