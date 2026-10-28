from io import BytesIO

from PIL import Image

from app.extract.imaging import dimensions
from app.segment.render import clip, colour_for, crop, data_url, mask_image, overlay, scale_box
from app.segment.schema import Box
from tests.conftest import make_photo


def test_overlay_keeps_the_photo_size_and_tints_the_mask() -> None:
    photo = make_photo(200, 100)
    box = Box(left=20, top=10, right=60, bottom=40)
    mask = mask_image(bytes([1]) * (40 * 30), 40, 30)

    out = overlay(photo, [("label", box, mask)])

    assert dimensions(out) == (200, 100)
    with Image.open(BytesIO(out)) as img:
        inside = img.getpixel((40, 25))
        outside = img.getpixel((150, 80))
    assert inside != outside
    assert outside == (200, 200, 200)


def test_overlay_skips_an_empty_box() -> None:
    photo = make_photo(50, 50)
    empty = Box(left=10, top=10, right=10, bottom=30)
    out = overlay(photo, [("item", empty, mask_image(b"", 0, 0))])
    assert dimensions(out) == (50, 50)


def test_crop_adds_a_margin_and_clips_to_the_photo() -> None:
    photo = make_photo(200, 100)
    assert dimensions(crop(photo, Box(left=50, top=20, right=150, bottom=70))) == (116, 58)
    assert dimensions(crop(photo, Box(left=0, top=0, right=200, bottom=100))) == (200, 100)


def test_clip_and_scale() -> None:
    assert clip(Box(left=-5, top=10, right=700, bottom=20), 640, 480) == Box(
        left=0, top=10, right=640, bottom=20
    )
    assert scale_box(Box(left=10, top=10, right=20, bottom=30), 0.5, 2.0) == Box(
        left=5, top=20, right=10, bottom=60
    )


def test_colours_are_stable_per_concept_and_cycle_for_the_rest() -> None:
    assert colour_for("label", 7) == colour_for("label", 0)
    assert colour_for("hinge", 0) != colour_for("hinge", 1)


def test_data_url_has_the_mime_and_base64_body() -> None:
    assert data_url(b"\x00\x01", "image/jpeg") == "data:image/jpeg;base64,AAE="
