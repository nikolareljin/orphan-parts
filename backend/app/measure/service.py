"""From marked points to a dimension with its uncertainty, or a refusal that says what to redo."""

import anyio

from app.config import Settings
from app.extract.imaging import dimensions, prepare
from app.measure import geometry
from app.measure.quality import inside, sharpness_at
from app.measure.schema import (
    Check,
    ImageSize,
    MeasureRequest,
    MeasureResult,
    Point,
    RectangleReference,
    TwoPointReference,
)
from app.profiles import Profiles

MAX_SIDE_RATIO = 2.5


def _scaled(p: Point, sx: float, sy: float) -> Point:
    return Point(x=p.x * sx, y=p.y * sy)


class Measurer:
    def __init__(self, settings: Settings, profiles: Profiles) -> None:
        self.settings = settings
        self.profiles = profiles

    async def measure(self, photo: bytes, request: MeasureRequest) -> tuple[MeasureResult, bytes]:
        """The result and the prepared photo the result's coordinates refer to."""
        s = self.settings
        max_bytes = s.max_upload_mb * 1024 * 1024
        prepared = await anyio.to_thread.run_sync(
            lambda: prepare(photo, max_px=s.image_max_px, max_bytes=max_bytes)
        )
        result = await anyio.to_thread.run_sync(lambda: self.compute(prepared, request))
        return result, prepared

    def compute(self, prepared: bytes, request: MeasureRequest) -> MeasureResult:
        s = self.settings
        width, height = dimensions(prepared)
        # the client marked the photo as it saw it; the stored raster may be smaller
        sx = width / request.image.width
        sy = height / request.image.height
        points = [_scaled(p, sx, sy) for p in request.points]
        ref = request.reference
        if isinstance(ref, TwoPointReference):
            ref = ref.model_copy(update={"points": [_scaled(p, sx, sy) for p in ref.points]})
            ref_points = ref.points
            method = "two_point_scale"
        else:
            ref = ref.model_copy(update={"corners": [_scaled(p, sx, sy) for p in ref.corners]})
            ref_points = ref.corners
            method = "homography"

        checks: list[Check] = []
        marked = [*ref_points, *points]
        checks.append(
            Check(
                name="image_size",
                passed=min(width, height) >= s.measure_min_image_px,
                detail=f"{width} by {height} px; at least {s.measure_min_image_px} px"
                " on the short side",
            )
        )
        checks.append(
            Check(
                name="points_inside",
                passed=all(inside(p, width, height) for p in marked),
                detail="every mark lies on the photo",
            )
        )
        feature_px = geometry.distance(points[0], points[1])
        checks.append(
            Check(
                name="points_distinct",
                passed=feature_px >= 2.0
                and all(geometry.distance(a, b) >= 2.0 for a, b in _pairs(ref_points)),
                detail="the two ends of each span are different points",
            )
        )
        if isinstance(ref, TwoPointReference):
            ref_px = geometry.distance(ref.points[0], ref.points[1])
            checks.append(
                Check(
                    name="reference_length",
                    passed=ref_px >= s.measure_min_reference_px,
                    detail=f"the reference spans {ref_px:.0f} px;"
                    f" at least {s.measure_min_reference_px} px",
                )
            )
            checks.append(
                Check(
                    name="view",
                    passed=request.straight_on,
                    detail="a two-point scale needs a straight-on view with the reference in"
                    " the plane of the feature; otherwise mark the four corners of a known"
                    " rectangle",
                )
            )
        else:
            sides = geometry.side_lengths(ref.corners)
            ref_px = sum(sides) / 4
            ratio = max(sides) / max(min(sides), 1e-9)
            checks.append(
                Check(
                    name="reference_length",
                    passed=min(sides) >= s.measure_min_reference_px,
                    detail=f"the shortest side spans {min(sides):.0f} px;"
                    f" at least {s.measure_min_reference_px} px",
                )
            )
            checks.append(
                Check(
                    name="view",
                    passed=ratio <= MAX_SIDE_RATIO,
                    detail=f"the rectangle's sides differ by {ratio:.1f} to 1 in the photo; past"
                    f" {MAX_SIDE_RATIO} to 1 the view is too steep",
                )
            )
        sharp = sharpness_at(prepared, marked) if checks[1].passed else 0.0
        checks.append(
            Check(
                name="sharpness",
                passed=sharp >= s.measure_min_sharpness,
                detail=f"edge response {sharp:.0f} around the marks;"
                f" at least {s.measure_min_sharpness:.0f}",
            )
        )

        accepted = all(c.passed for c in checks if c.blocking)
        value: float | None = None
        uncertainty: float | None = None
        px_per_mm: float | None = None
        basis = "no number: the capture was refused"
        if accepted:
            value, uncertainty, px_per_mm, basis = self._compute(ref, points, ref_px, feature_px)

        feature = self.profiles.feature(request.profile, request.feature)
        tolerance = feature.tolerance_mm if feature else None
        needs_direct: bool | None = None
        if accepted and tolerance is not None and uncertainty is not None:
            needs_direct = uncertainty > tolerance
            checks.append(
                Check(
                    name="tolerance",
                    passed=not needs_direct,
                    detail=(
                        f"the profile allows ±{tolerance:g} mm;"
                        f" this capture gives ±{uncertainty:.2f} mm"
                        + (
                            "; enter a caliper or ruler reading for this feature"
                            if needs_direct
                            else ""
                        )
                    ),
                    blocking=False,
                )
            )

        failed = [c for c in checks if c.blocking and not c.passed]
        redo = None if accepted else "; ".join(f"{c.name}: {c.detail}" for c in failed)
        return MeasureResult(
            accepted=accepted,
            feature=request.feature,
            profile=request.profile,
            method=method,
            value_mm=None if value is None else round(value, 2),
            uncertainty_mm=None if uncertainty is None else round(uncertainty, 2),
            basis=basis,
            checks=checks,
            redo=redo,
            px_per_mm=None if px_per_mm is None else round(px_per_mm, 3),
            image=ImageSize(width=width, height=height),
            reference=ref,
            points=points,
            tolerance_mm=tolerance,
            needs_direct_reading=needs_direct,
        )

    def _compute(
        self,
        ref: TwoPointReference | RectangleReference,
        points: list[Point],
        ref_px: float,
        feature_px: float,
    ) -> tuple[float, float, float, str]:
        mark = self.settings.measure_mark_px
        if isinstance(ref, TwoPointReference):
            px_per_mm = geometry.scale_from_two_points(ref.points[0], ref.points[1], ref.length_mm)
            value = feature_px / px_per_mm
            ref_len = ref.length_mm
            how = f"two-point scale: {ref.length_mm:g} mm over {ref_px:.0f} px"
        else:
            plane = geometry.rectangle_plane(ref.corners, ref.width_mm, ref.height_mm)
            a = geometry.apply(plane, points[0])
            b = geometry.apply(plane, points[1])
            value = geometry.distance(a, b)
            px_per_mm = feature_px / value if value > 0 else ref_px / ref.width_mm
            ref_len = (ref.width_mm + ref.height_mm) / 2
            how = (
                f"homography from a {ref.width_mm:g} by {ref.height_mm:g} mm rectangle,"
                f" sides about {ref_px:.0f} px"
            )
        # marking error at both ends of the feature, plus the scale error from marking both
        # ends of the reference and from the reference's own tolerance
        marking = 2 * mark / px_per_mm
        scale_rel = 2 * mark / ref_px + ref.tolerance_mm / ref_len
        uncertainty = marking + value * scale_rel
        basis = (
            f"{how}; marks ±{mark:g} px at each end; reference ±{ref.tolerance_mm:g} mm;"
            f" feature {feature_px:.0f} px"
        )
        return value, uncertainty, px_per_mm, basis


def _pairs(points: list[Point]) -> list[tuple[Point, Point]]:
    return (
        [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
        if len(points) > 2
        else [(points[0], points[1])]
    )
