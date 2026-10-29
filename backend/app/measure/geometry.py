"""Explicit geometry: distances, a scale from two points, a homography from four corners."""

import math

from app.measure.schema import Point

Matrix = list[list[float]]


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def scale_from_two_points(a: Point, b: Point, length_mm: float) -> float:
    """Pixels per millimetre along a known length."""
    return distance(a, b) / length_mm


def solve(a: Matrix, b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Small systems only."""
    n = len(b)
    m = [[*row, b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("the points do not define a unique transform")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = (m[r][n] - s) / m[r][r]
    return x


def homography(src: list[Point], dst: list[Point]) -> Matrix:
    """The 3x3 projective transform taking each ``src`` point to its ``dst`` point."""
    if len(src) != 4 or len(dst) != 4:
        raise ValueError("a homography needs four point pairs")
    rows: Matrix = []
    rhs: list[float] = []
    for s, d in zip(src, dst, strict=True):
        rows.append([s.x, s.y, 1, 0, 0, 0, -d.x * s.x, -d.x * s.y])
        rhs.append(d.x)
        rows.append([0, 0, 0, s.x, s.y, 1, -d.y * s.x, -d.y * s.y])
        rhs.append(d.y)
    h = solve(rows, rhs)
    return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]]


def apply(h: Matrix, p: Point) -> Point:
    w = h[2][0] * p.x + h[2][1] * p.y + h[2][2]
    if abs(w) < 1e-12:
        raise ValueError("the point maps to infinity under this transform")
    return Point(
        x=(h[0][0] * p.x + h[0][1] * p.y + h[0][2]) / w,
        y=(h[1][0] * p.x + h[1][1] * p.y + h[1][2]) / w,
    )


def rectangle_plane(corners: list[Point], width_mm: float, height_mm: float) -> Matrix:
    """Image pixels to millimetres on the plane of a known rectangle."""
    target = [
        Point(x=0, y=0),
        Point(x=width_mm, y=0),
        Point(x=width_mm, y=height_mm),
        Point(x=0, y=height_mm),
    ]
    return homography(corners, target)


def side_lengths(corners: list[Point]) -> list[float]:
    return [distance(corners[i], corners[(i + 1) % 4]) for i in range(4)]
