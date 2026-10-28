"""Find the item, its label and its connector in a photo with SAM 3.1."""

from app.segment.concepts import CONCEPTS, DEFAULT_CONCEPTS, phrase_for
from app.segment.parse import Match, parse_matches
from app.segment.schema import Box, Region, Segmentation
from app.segment.service import Segmenter

__all__ = [
    "CONCEPTS",
    "DEFAULT_CONCEPTS",
    "Box",
    "Match",
    "Region",
    "Segmentation",
    "Segmenter",
    "parse_matches",
    "phrase_for",
]
