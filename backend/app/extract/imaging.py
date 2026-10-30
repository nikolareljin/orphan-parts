"""Photos as they go to the model: bounded in size, upright, JPEG, no metadata."""

from io import BytesIO

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF"})
JPEG_QUALITY = 85
# Decoded size is what costs memory, not the upload size: a well-compressed PNG inside the
# upload limit can still unpack to hundreds of megabytes. 50 MP covers every phone camera.
MAX_PIXELS = 50_000_000
_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1")


class BadImageError(ValueError):
    """The upload is not a usable photo; the message is safe to show to the user."""


def _is_heif(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS


def prepare(data: bytes, *, max_px: int, max_bytes: int) -> bytes:
    """Re-encode one photo: EXIF orientation applied, longest side at most ``max_px``,
    RGB JPEG without any metadata. Raises ``BadImageError`` for anything else."""
    return _encode(_decode(data, max_px=max_px, max_bytes=max_bytes))


def _decode(data: bytes, *, max_px: int, max_bytes: int) -> Image.Image:
    """The photo checked, upright, RGB and bounded, still in memory."""
    if not data:
        raise BadImageError("the photo is empty")
    if len(data) > max_bytes:
        raise BadImageError(f"the photo is larger than {max_bytes // (1024 * 1024)} MB")
    if _is_heif(data):
        raise BadImageError("HEIC photos are not supported yet; export the photo as JPEG")
    try:
        img = Image.open(BytesIO(data))
        width, height = img.size
        if width * height > MAX_PIXELS:
            raise BadImageError("the photo has too many pixels; resize it to 50 megapixels or less")
        if img.format == "JPEG":
            # decode at a reduced scale when the photo is far larger than needed
            img.draft("RGB", (max_px, max_px))
        img.load()
    except Image.DecompressionBombError as exc:
        raise BadImageError("the photo is too large to decode") from exc
    except BadImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BadImageError("the file is not an image") from exc
    if img.format not in ALLOWED_FORMATS:
        raise BadImageError(f"unsupported image format: {img.format or 'unknown'}")
    upright = ImageOps.exif_transpose(img) or img
    rgb = upright.convert("RGB")
    rgb.thumbnail((max_px, max_px))
    return rgb


def _encode(img: Image.Image) -> bytes:
    out = BytesIO()
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def read_copy(data: bytes, *, max_px: int, max_bytes: int, enhance: bool) -> tuple[bytes, float]:
    """The copy the model reads, and the sharpness of the photo before any help: decoded once,
    enhanced in memory when asked, encoded once, so the help is never applied to a copy this
    service encoded (what came in is as it came in)."""
    img = _decode(data, max_px=max_px, max_bytes=max_bytes)
    score = sharpness_of(img)
    return _encode(_enhanced(img) if enhance else img), score


def dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
        return int(width), int(height)


# A 3x3 Laplacian; edges push it off the 128 offset, blur flattens it.
_LAPLACIAN = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
SHARPNESS_PX = 512
SHARPNESS_TILES = 4


def sharpness_of(img: Image.Image) -> float:
    """How much edge there is where the photo has the most: the variance of its Laplacian on a
    copy at most SHARPNESS_PX wide, taken over a grid of tiles, and the third sharpest tile
    counted: a legible label that fills a quarter of the frame covers several tiles and
    scores as the label, not as the frame, while one sharp thing beside a blurred label (a
    finger, a table edge) fills one tile and does not pass for it. The outermost pixel ring
    is left out: the filter copies it unchanged, and a flat frame would score its own border.
    Printed text scores in the hundreds and above; a blurred label, or a patch with nothing
    on it, in the tens."""
    gray = img.convert("L")
    gray.thumbnail((SHARPNESS_PX, SHARPNESS_PX))
    lap = gray.filter(_LAPLACIAN)
    width, height = lap.size
    if width < 4 or height < 4:
        return 0.0
    inner = (1, 1, width - 1, height - 1)
    tiles = SHARPNESS_TILES
    tile_w = max(8, (width - 2) // tiles)
    tile_h = max(8, (height - 2) // tiles)
    scores: list[float] = []
    for top in range(inner[1], inner[3], tile_h):
        for left in range(inner[0], inner[2], tile_w):
            box = (left, top, min(left + tile_w, inner[2]), min(top + tile_h, inner[3]))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            scores.append(float(ImageStat.Stat(lap.crop(box)).var[0]))
    if not scores:
        return 0.0
    scores.sort(reverse=True)
    return scores[min(2, len(scores) - 1)]


def sharpness(data: bytes) -> float:
    with Image.open(BytesIO(data)) as img:
        return sharpness_of(img)


def _enhanced(img: Image.Image) -> Image.Image:
    """The same photo with its contrast stretched (the darkest and lightest half-percent
    clipped) and its edges sharpened a little, so faint print on a label reads better. Only
    what goes to the model is changed; what is kept is the photo as taken."""
    stretched = ImageOps.autocontrast(img.convert("RGB"), cutoff=0.5, preserve_tone=True)
    return stretched.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))


def enhance(data: bytes) -> bytes:
    """``_enhanced`` on an encoded photo, for a caller that holds bytes."""
    with Image.open(BytesIO(data)) as img:
        return _encode(_enhanced(img))
