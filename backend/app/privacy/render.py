"""The shared copy of a photo: every hidden area a solid black box, re-encoded without metadata;
and the copy the photo check sends, with a numbered grid the model reads its boxes off."""

import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.extract.imaging import _encode
from app.privacy.schema import Area


def pixel_box(area: Area, width: int, height: int) -> tuple[int, int, int, int]:
    """The area in pixels, rounded outwards: a box never covers less than it says."""
    left = max(0, math.floor(area.x * width))
    top = max(0, math.floor(area.y * height))
    right = min(width, math.ceil((area.x + area.w) * width))
    bottom = min(height, math.ceil((area.y + area.h) * height))
    return left, top, right, bottom


def redacted(data: bytes, areas: list[Area]) -> bytes:
    """The photo with its hidden areas blacked out. Always re-encoded, so even a photo with
    nothing to hide goes out as pixels only."""
    with Image.open(BytesIO(data)) as source:
        img = source.convert("RGB")
    draw = ImageDraw.Draw(img)
    for area in areas:
        if area.hidden:
            left, top, right, bottom = pixel_box(area, *img.size)
            if right > left and bottom > top:
                draw.rectangle((left, top, right - 1, bottom - 1), fill=(0, 0, 0))
    return _encode(img)


GRID_STEPS = 10
GRID_COLOR = (255, 0, 255)


def gridded(img: Image.Image) -> bytes:
    """The photo with a thin magenta grid every tenth of its width and height, numbered 100 to
    900 along each edge. A box read off a grid lands far closer to its value than one guessed
    on a blank photo: the grid is what the check's boxes are measured against."""
    width, height = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    size = max(12, min(width, height) // 45)
    font = ImageFont.load_default(size=size)
    for k in range(1, GRID_STEPS):
        x, y = k * width / GRID_STEPS, k * height / GRID_STEPS
        draw.line((x, 0, x, height), fill=(*GRID_COLOR, 150), width=1)
        draw.line((0, y, width, y), fill=(*GRID_COLOR, 150), width=1)
        label = str(k * 1000 // GRID_STEPS)
        for at in ((x + 2, 2), (x + 2, height - size - 4), (2, y + 2), (width - 3 * size, y + 2)):
            draw.text(
                at,
                label,
                font=font,
                fill=(*GRID_COLOR, 255),
                stroke_width=2,
                stroke_fill=(255, 255, 255, 255),
            )
    return _encode(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))
