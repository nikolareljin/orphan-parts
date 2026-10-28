"""Photos as they go to the model: bounded in size, upright, JPEG, no metadata."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
JPEG_QUALITY = 85


class BadImageError(ValueError):
    """The upload is not a usable photo; the message is safe to show to the user."""


def prepare(data: bytes, *, max_px: int, max_bytes: int) -> bytes:
    """Re-encode one photo: EXIF orientation applied, longest side at most ``max_px``,
    RGB JPEG without any metadata. Raises ``BadImageError`` for anything else."""
    if not data:
        raise BadImageError("the photo is empty")
    if len(data) > max_bytes:
        raise BadImageError(f"the photo is larger than {max_bytes // (1024 * 1024)} MB")
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Image.DecompressionBombError as exc:
        raise BadImageError("the photo is too large to decode") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BadImageError("the file is not an image") from exc
    if img.format not in ALLOWED_FORMATS:
        raise BadImageError(f"unsupported image format: {img.format or 'unknown'}")
    upright = ImageOps.exif_transpose(img) or img
    rgb = upright.convert("RGB")
    rgb.thumbnail((max_px, max_px))
    out = BytesIO()
    rgb.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
        return int(width), int(height)
