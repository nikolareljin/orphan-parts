"""Shapes of an extraction: what the model returns and what the API serves."""

from typing import Literal

from pydantic import BaseModel, Field

# Where a value came from. Segmentation, grounding, voice and video add their own later.
Source = Literal[
    "photo",
    "label_crop",
    "grounding_citation",
    "voice_note",
    "user_edit",
    "video_frame",
    "measurement",
    "document",
]


class ReadField(BaseModel):
    """One field as the model read it. Empty value means nothing on the label supports it."""

    name: str
    value: str
    unit: str
    confidence: float


class LabelReading(BaseModel):
    """Strict output schema of an extraction call: every property required, no extras."""

    item_type: str
    label_text: str
    fields: list[ReadField]


class Evidence(BaseModel):
    """A value with its provenance. Every number the app shows is one of these."""

    value: str
    unit: str = ""
    confidence: float = Field(ge=0, le=1)
    source: Source
    raw: str = ""


class Extraction(BaseModel):
    item_type: str
    label_text: str
    fields: dict[str, Evidence]
    warnings: list[str]
    photos: int
    crops: int = 0
    model: str
    from_fixture: bool
    cost_usd: float
