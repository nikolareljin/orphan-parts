from io import BytesIO

import pytest
from PIL import Image

from app.extract import BadImageError, dimensions, imaging, prepare
from tests.conftest import make_photo

MB = 1024 * 1024


def test_large_photo_is_downscaled_to_the_longest_side() -> None:
    out = prepare(make_photo(4000, 3000), max_px=1280, max_bytes=12 * MB)
    assert dimensions(out) == (1280, 960)


def test_small_photo_keeps_its_size() -> None:
    out = prepare(make_photo(300, 200), max_px=1280, max_bytes=12 * MB)
    assert dimensions(out) == (300, 200)


def test_png_becomes_jpeg() -> None:
    out = prepare(make_photo(100, 100, "PNG"), max_px=1280, max_bytes=12 * MB)
    with Image.open(BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.mode == "RGB"


def test_exif_is_dropped_and_orientation_applied() -> None:
    img = Image.new("RGB", (200, 100), (10, 20, 30))
    exif = Image.Exif()
    exif[0x010F] = "CameraCo"  # Make
    exif[0x0110] = "Model X"  # Model
    exif[0x0112] = 6  # orientation: rotate 90 degrees
    buf = BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())

    out = prepare(buf.getvalue(), max_px=1280, max_bytes=12 * MB)

    assert dimensions(out) == (100, 200)
    with Image.open(BytesIO(out)) as cleaned:
        assert dict(cleaned.getexif()) == {}


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(BadImageError, match="empty"):
        prepare(b"", max_px=1280, max_bytes=12 * MB)


def test_oversized_upload_is_rejected_before_decoding() -> None:
    with pytest.raises(BadImageError, match="larger than 1 MB"):
        prepare(b"x" * (MB + 1), max_px=1280, max_bytes=MB)


def test_non_image_is_rejected() -> None:
    with pytest.raises(BadImageError, match="not an image"):
        prepare(b"%PDF-1.4 not a photo", max_px=1280, max_bytes=12 * MB)


def test_unsupported_format_is_rejected() -> None:
    img = Image.new("RGB", (10, 10))
    buf = BytesIO()
    img.save(buf, "BMP")
    with pytest.raises(BadImageError, match="unsupported image format: BMP"):
        prepare(buf.getvalue(), max_px=1280, max_bytes=12 * MB)


def test_huge_pixel_count_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(BadImageError, match="too large to decode"):
        prepare(make_photo(640, 480), max_px=1280, max_bytes=12 * MB)


def test_pixel_cap_is_checked_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    photo = make_photo(640, 480)
    monkeypatch.setattr(imaging, "MAX_PIXELS", 1000)
    loaded = []
    monkeypatch.setattr(Image.Image, "load", lambda self: loaded.append(self))
    with pytest.raises(BadImageError, match="too many pixels"):
        prepare(photo, max_px=1280, max_bytes=12 * MB)
    assert loaded == []


def test_heic_is_refused_with_advice() -> None:
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"
    with pytest.raises(BadImageError, match="HEIC photos are not supported yet"):
        prepare(heic, max_px=1280, max_bytes=12 * MB)


def test_big_jpeg_is_still_downscaled_exactly() -> None:
    # the reduced-scale decode must not change the final size
    out = prepare(make_photo(6000, 4000), max_px=1280, max_bytes=12 * MB)
    assert dimensions(out) == (1280, 853)


def test_enhance_keeps_the_size_and_sharpness_tells_text_from_blur() -> None:
    from PIL import Image, ImageDraw, ImageFilter

    from app.extract.imaging import dimensions, enhance, sharpness

    img = Image.new("RGB", (640, 480), (230, 230, 230))
    draw = ImageDraw.Draw(img)
    for i in range(12):
        draw.text((20, 20 + i * 35), "OUTPUT 19.5V 3.33A MODEL OP065-19-333", fill=(20, 20, 20))
    sharp = BytesIO()
    img.save(sharp, "JPEG")
    blurred = BytesIO()
    img.filter(ImageFilter.GaussianBlur(4)).save(blurred, "JPEG")
    assert sharpness(sharp.getvalue()) > 300 > sharpness(blurred.getvalue())
    flat = BytesIO()
    Image.new("RGB", (300, 200), (200, 200, 200)).save(flat, "JPEG")
    assert sharpness(flat.getvalue()) < 150
    better = enhance(sharp.getvalue())
    assert dimensions(better) == (640, 480)
    assert better[:2] == b"\xff\xd8"  # a JPEG
    assert better != sharp.getvalue()
