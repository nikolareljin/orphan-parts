"""Is this capture good enough to measure from? Each check says what to redo."""

from io import BytesIO

from PIL import Image, ImageFilter, ImageStat

from app.measure.schema import Point

# A 3x3 Laplacian. Edges push it away from the 128 offset; blur flattens it.
_LAPLACIAN = ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=128)
WINDOW_PX = 48


def sharpness_at(photo: bytes, points: list[Point], window: int = WINDOW_PX) -> float:
    """The weakest edge response around any marked point: variance of the Laplacian in a window
    centred on each point, the smallest of them. Blur, and a mark on a featureless patch, both
    score low."""
    with Image.open(BytesIO(photo)) as img:
        gray = img.convert("L")
        lap = gray.filter(_LAPLACIAN)
        scores: list[float] = []
        for p in points:
            left = int(max(0, min(p.x - window // 2, gray.width - window)))
            top = int(max(0, min(p.y - window // 2, gray.height - window)))
            box = (left, top, min(left + window, gray.width), min(top + window, gray.height))
            # the outermost pixel ring is the filter's copy of the photo, not an edge
            box = (
                max(1, box[0]),
                max(1, box[1]),
                min(gray.width - 1, box[2]),
                min(gray.height - 1, box[3]),
            )
            if box[2] - box[0] < 2 or box[3] - box[1] < 2:
                scores.append(0.0)
                continue
            scores.append(float(ImageStat.Stat(lap.crop(box)).var[0]))
    return min(scores) if scores else 0.0


def inside(p: Point, width: int, height: int) -> bool:
    return 0 <= p.x < width and 0 <= p.y < height
