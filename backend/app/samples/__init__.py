"""The demo samples: the demo set's photos the visitor clicks instead of uploading."""

from app.samples.catalog import (
    MISSING_LINE,
    VISITOR_UPLOAD_LINE,
    SampleCatalog,
    SampleItem,
    SampleListing,
    SampleNote,
    SamplePhoto,
    Samples,
    UnknownSampleError,
)
from app.samples.record import SamplesOutcome, record_samples, selections
from app.samples.service import (
    SampleRead,
    SampleReader,
    SampleReadRequest,
    SampleResult,
    label_crops,
)

__all__ = [
    "MISSING_LINE",
    "VISITOR_UPLOAD_LINE",
    "SampleCatalog",
    "SampleItem",
    "SampleListing",
    "SampleNote",
    "SamplePhoto",
    "SampleRead",
    "SampleReadRequest",
    "SampleReader",
    "SampleResult",
    "Samples",
    "SamplesOutcome",
    "UnknownSampleError",
    "label_crops",
    "record_samples",
    "selections",
]
