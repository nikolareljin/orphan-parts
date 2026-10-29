"""Synthetic photos with known geometry for the measurement tests."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

GREY = (200, 200, 200)
INK = (20, 20, 20)

# a ruler: a bar from x=100 to x=500 at y=400, 400 px for 100 mm, so 4 px per mm
RULER_A = (100, 400)
RULER_B = (500, 400)
RULER_MM = 100.0
# an opening: inner edges at x=200 and x=340 on y=200, 140 px, so 35 mm
OPENING_A = (200, 200)
OPENING_B = (340, 200)
# a card: an axis-aligned rectangle, 300 by 190 px, drawn for the homography case
CARD = [(50, 50), (350, 50), (350, 240), (50, 240)]
CARD_MM = (85.6, 53.98)


def ruler_photo(width: int = 640, height: int = 480, *, blur: float = 0.0) -> bytes:
    img = Image.new("RGB", (width, height), GREY)
    draw = ImageDraw.Draw(img)
    draw.line([RULER_A, RULER_B], fill=INK, width=4)
    for x in range(RULER_A[0], RULER_B[0] + 1, 40):
        draw.line([(x, 392), (x, 408)], fill=INK, width=2)
    # the opening: a dark ring seen from the front, inner edges at OPENING_A and OPENING_B
    draw.rectangle([(OPENING_A[0] - 30, 170), (OPENING_B[0] + 30, 230)], fill=INK)
    draw.rectangle([(OPENING_A[0], 180), (OPENING_B[0], 220)], fill=GREY)
    draw.rectangle([CARD[0], CARD[2]], outline=INK, width=3)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    out = BytesIO()
    img.save(out, "PNG")
    return out.getvalue()
