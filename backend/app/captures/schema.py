"""A capture: what the phone sent in one go (photos, a clip, a spoken note, a line of text),
kept until it is processed into an item, and after, until the owner deletes it."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["received", "processed", "failed"]
TEXT_MAX = 2000


class CaptureCreate(BaseModel):
    """The text part of the bundle; the files travel beside it."""

    note: str = Field(default="", max_length=TEXT_MAX, description="a line typed on the phone")
    name: str = Field(default="", max_length=200, description="what to call it, if known")
    find_label: bool = Field(default=True, description="look for the label first, as the web does")


class Capture(BaseModel):
    id: int
    status: Status
    note: str
    name: str
    find_label: bool
    photos: int
    clip: bool
    clip_bytes: int
    audio: bool
    audio_seconds: float
    item_id: int | None
    error: str
    model: str
    cost_usd: float
    created_at: str
    processed_at: str
    public: bool = False


class CaptureList(BaseModel):
    captures: list[Capture]
