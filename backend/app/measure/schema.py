"""Shapes of a measurement: what the user marked, what was computed, and why it was refused."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

FEATURE_KEY = r"^[a-z][a-z0-9_]{0,63}$"


class Point(BaseModel):
    x: float
    y: float


class ImageSize(BaseModel):
    """The raster the points refer to, as the client saw it."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TwoPointReference(BaseModel):
    """A ruler or any object of known length lying in the plane of the feature."""

    kind: Literal["two_point"] = "two_point"
    points: list[Point] = Field(min_length=2, max_length=2)
    length_mm: float = Field(gt=0)
    tolerance_mm: float = Field(ge=0, default=0.5)


class RectangleReference(BaseModel):
    """A rectangle of known size (a card, a printed target) seen from any angle on a flat
    surface: four corners in order, top-left, top-right, bottom-right, bottom-left."""

    kind: Literal["rectangle"] = "rectangle"
    corners: list[Point] = Field(min_length=4, max_length=4)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    tolerance_mm: float = Field(ge=0, default=0.2)


Reference = Annotated[TwoPointReference | RectangleReference, Field(discriminator="kind")]


class MeasureRequest(BaseModel):
    feature: str = Field(pattern=FEATURE_KEY)
    profile: str | None = None
    image: ImageSize
    reference: Reference
    points: list[Point] = Field(min_length=2, max_length=2)
    # the owner's statement; a two-point scale is only valid straight on
    straight_on: bool = False


class Check(BaseModel):
    name: str
    passed: bool
    detail: str
    blocking: bool = True


Method = Literal["two_point_scale", "homography"]


class MeasureResult(BaseModel):
    """Accepted or not, every result says what was checked. A refused capture has no number."""

    accepted: bool
    feature: str
    profile: str | None
    method: Method
    unit: Literal["mm"] = "mm"
    value_mm: float | None
    uncertainty_mm: float | None
    basis: str
    checks: list[Check]
    redo: str | None
    px_per_mm: float | None
    image: ImageSize
    reference: Reference
    points: list[Point]
    tolerance_mm: float | None
    needs_direct_reading: bool | None


class Measurement(MeasureResult):
    """A stored result: on an item, tied to the observed value it proposed."""

    id: int
    item_id: int
    assertion_id: int | None
    at: str
