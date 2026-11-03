"""Shapes of an extraction: what the model returns and what the API serves."""

from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from app.ops.door import for_visitor
from app.privacy.text import mask_text

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
    "listing_text",
    "screenshot",
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
    enhanced: bool = Field(default=False, description="contrast and edges lifted before the read")
    model: str
    from_fixture: bool
    cost_usd: float

    # what the demo visitor reads of a label: a product key, a MAC address, a serial number or
    # a password on it masked, in the transcription and in every value
    @field_serializer("label_text")
    def _shown_label(self, value: str) -> str:
        return mask_text(value) if for_visitor() else value

    @field_serializer("fields")
    def _shown_fields(self, value: dict[str, Evidence]) -> dict[str, Evidence]:
        if not for_visitor():
            return value
        return {
            k: e.model_copy(update={"value": mask_text(e.value), "raw": mask_text(e.raw)})
            for k, e in value.items()
        }
