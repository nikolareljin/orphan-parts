"""Read a label from photos into typed, evidence-backed fields with Muse Spark."""

from app.extract.fields import FIELD_NAMES, FIELDS, FieldSpec, field_guide
from app.extract.imaging import BadImageError, dimensions, prepare
from app.extract.normalize import normalize
from app.extract.schema import Evidence, Extraction, LabelReading, ReadField, Source
from app.extract.service import Extractor

__all__ = [
    "FIELDS",
    "FIELD_NAMES",
    "BadImageError",
    "Evidence",
    "Extraction",
    "Extractor",
    "FieldSpec",
    "LabelReading",
    "ReadField",
    "Source",
    "dimensions",
    "field_guide",
    "normalize",
    "prepare",
]
