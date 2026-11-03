"""Shapes of a photo check: what the model returns, what is kept beside a photo, and what the
API serves about it."""

from typing import Literal

from pydantic import BaseModel, Field

from app.privacy.text import Kind

# clear: checked, nothing private found; found: checked, areas to black out; failed: the check
# did not finish or its answer could not be placed, so the photo is not shared; unchecked: no
# check has run on this photo yet, which is not shared either
Status = Literal["clear", "found", "failed", "unchecked"]


class FoundArea(BaseModel):
    """One area as the model reports it: a box on a 0 to 1000 scale of the image's width and
    height. Strict output schema: every property required, no extras."""

    kind: Kind
    what: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int


class SensitiveReading(BaseModel):
    areas: list[FoundArea]


class Area(BaseModel):
    """One area blacked out on every shared copy, unless the owner chose to show it. The box is
    a fraction of the image's width and height, already padded, so it covers the same part of
    the photo at any size."""

    id: int
    kind: Kind
    label: str = Field(description="what it is, in plain words; never the value")
    what: str = Field(default="", description="where the model saw it, without the value")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)
    hidden: bool = Field(default=True, description="blacked out on shared copies")


class PhotoCheck(BaseModel):
    """What is kept for one photo, by the digest of its stored bytes: the same photo is the same
    check wherever it is kept (an item's, a capture's, a sample of the demo set)."""

    digest: str
    status: Status
    areas: list[Area] = []
    reason: str = Field(default="", description="why a check failed")
    model: str = ""
    from_fixture: bool = False
    cost_usd: float = 0.0
    checked_at: str = ""


class PhotoPrivacy(BaseModel):
    """One photo's check as the API serves it, with the line the app shows under it."""

    n: int
    status: Status
    areas: list[Area] = []
    note: str
    shared: bool = Field(description="a copy may leave the owner's view (checked)")
    reason: str = ""


class AreaChoice(BaseModel):
    hidden: bool = Field(description="black the area out on shared copies (true) or show it")
