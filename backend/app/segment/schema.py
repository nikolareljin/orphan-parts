"""Shapes of a segmentation: regions with boxes, masks rendered to crops, and the overlay."""

from pydantic import BaseModel, Field


class Box(BaseModel):
    """Half-open pixel bounds on the prepared photo: ``right`` and ``bottom`` are exclusive."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class Region(BaseModel):
    """One match for one concept."""

    concept: str
    phrase: str
    object_id: str
    box: Box
    confidence: float | None = Field(default=None, ge=0, le=1)
    coverage: float = Field(ge=0, le=1, description="mask pixels over box pixels")
    crop: str = Field(description="JPEG data URL of the box with a small margin")
    svg_path: str = Field(description="mask outline in prepared-photo pixels, or empty")


class Segmentation(BaseModel):
    width: int
    height: int
    regions: list[Region]
    overlay: str = Field(description="JPEG data URL of the photo with the masks drawn over it")
    warnings: list[str]
    model: str
    from_fixture: bool
    cost_usd: float
