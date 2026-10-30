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
    out = BytesIO()
    rgb.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


def dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
        return int(width), int(height)


# A 3x3 Laplacian; edges push it off the 128 offset, blur flattens it.
_LAPLACIAN = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
SHARPNESS_PX = 512


def sharpness(data: bytes) -> float:
    """How much edge there is in a photo: the variance of its Laplacian on a copy at most
    SHARPNESS_PX wide. Printed text scores in the hundreds and above; a blurred label, or a
    patch with nothing on it, in the tens."""
    with Image.open(BytesIO(data)) as img:
        gray = img.convert("L")
        gray.thumbnail((SHARPNESS_PX, SHARPNESS_PX))
        return float(ImageStat.Stat(gray.filter(_LAPLACIAN)).var[0])


def enhance(data: bytes) -> bytes:
    """The same photo with its contrast stretched (the darkest and lightest half-percent
    clipped) and its edges sharpened a little, so faint print on a label reads better. Only
    what goes to the model is changed; what is kept is the photo as taken."""
    with Image.open(BytesIO(data)) as img:
        rgb = img.convert("RGB")
        stretched = ImageOps.autocontrast(rgb, cutoff=0.5, preserve_tone=True)
        sharper = stretched.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
        out = BytesIO()
        sharper.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()
