"""Masks and boxes as pixels: the overlay the UI shows, the crops the next step reads."""

import base64
import re
from io import BytesIO

from PIL import Image, ImageDraw

from app.segment.schema import Box

CROP_MARGIN = 0.08
JPEG_QUALITY = 85
MASK_ALPHA = 110
OUTLINE_WIDTH = 3
# one colour per concept, the rest cycle through the spare ones
COLOURS: dict[str, tuple[int, int, int]] = {
    "item": (46, 134, 222),
    "label": (235, 87, 87),
    "connector": (39, 174, 96),
    "opening": (241, 196, 15),
}
_SPARE = ((155, 89, 182), (230, 126, 34), (26, 188, 156))
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def colour_for(concept: str, index: int) -> tuple[int, int, int]:
    return COLOURS.get(concept) or _SPARE[index % len(_SPARE)]


def mask_image(raster: bytes, width: int, height: int) -> Image.Image:
    """A mode L image: 255 inside the mask, 0 outside."""
    return Image.frombytes("L", (width, height), bytes(255 if b else 0 for b in raster))


def clip(box: Box, width: int, height: int) -> Box:
    return Box(
        left=min(max(box.left, 0), width),
        top=min(max(box.top, 0), height),
        right=min(max(box.right, 0), width),
        bottom=min(max(box.bottom, 0), height),
    )


def scale_box(box: Box, sx: float, sy: float) -> Box:
    return Box(
        left=round(box.left * sx),
        top=round(box.top * sy),
        right=round(box.right * sx),
        bottom=round(box.bottom * sy),
    )


def overlay(photo: bytes, layers: list[tuple[str, Box, Image.Image]]) -> bytes:
    """The photo with every mask tinted and its box outlined. ``layers`` carry the concept,
    the box on this photo and the mask image at the box's size."""
    base = Image.open(BytesIO(photo)).convert("RGBA")
    for index, (concept, box, mask) in enumerate(layers):
        if box.width <= 0 or box.height <= 0:
            continue
        colour = colour_for(concept, index)
        tint = Image.new("RGBA", (box.width, box.height), (*colour, MASK_ALPHA))
        alpha = mask.resize((box.width, box.height), Image.Resampling.NEAREST)
        tint.putalpha(alpha.point(lambda v: MASK_ALPHA if v else 0))
        base.alpha_composite(tint, (box.left, box.top))
        ImageDraw.Draw(base).rectangle(
            (box.left, box.top, box.right - 1, box.bottom - 1), outline=colour, width=OUTLINE_WIDTH
        )
    out = BytesIO()
    base.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def crop(photo: bytes, box: Box, *, margin: float = CROP_MARGIN) -> bytes:
    """The box with a margin on every side, clipped to the photo, as JPEG."""
    with Image.open(BytesIO(photo)) as img:
        dx = round(box.width * margin)
        dy = round(box.height * margin)
        grown = clip(
            Box(left=box.left - dx, top=box.top - dy, right=box.right + dx, bottom=box.bottom + dy),
            img.width,
            img.height,
        )
        region = img.crop((grown.left, grown.top, grown.right, grown.bottom)).convert("RGB")
        out = BytesIO()
        region.save(out, "JPEG", quality=JPEG_QUALITY)
        return out.getvalue()


def shift_path(path: str, dx: float, dy: float, sx: float = 1.0, sy: float = 1.0) -> str:
    """Move a mask-local ``M x y L x y ... Z`` path into photo coordinates."""
    if not path:
        return ""
    numbers = _NUMBER.findall(path)
    letters = re.findall(r"[MLZ]", path)
    out: list[str] = []
    it = iter(numbers)
    for letter in letters:
        if letter == "Z":
            out.append("Z")
            continue
        x = float(next(it)) * sx + dx
        y = float(next(it)) * sy + dy
        out.append(f"{letter} {x:g} {y:g}")
    return " ".join(out)


def data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
