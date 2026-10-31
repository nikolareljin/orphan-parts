"""Reading the samples: the same flow the web app runs on an upload (SAM 3.1 finds the label
on the first photo, Muse Spark reads the photos with the label crops), on the exact files of
the demo set, so the recording made of each one answers. Only an exact recording answers in
fixture mode: a selection with none says so instead of passing an operation's stub off as a
reading. The recorder runs the same code, so what it keeps is what a click asks for."""

import base64
import logging

from pydantic import BaseModel, Field

from app.config import Settings
from app.extract import Extraction, Extractor
from app.model_api import NoRecordingError, exact_replay
from app.samples.catalog import MISSING_LINE, Samples, UnknownSampleError
from app.segment import Segmentation, Segmenter

log = logging.getLogger("app.samples")


class SampleReadRequest(BaseModel):
    sample_ids: list[str] = Field(
        min_length=1,
        max_length=64,
        description="sample photo ids from GET /api/samples; an item's every photo is read"
        " together, any other photo alone",
    )
    find_label: bool = Field(
        default=True, description="find the label with SAM 3.1 first and read its crops too"
    )


class SampleResult(BaseModel):
    """One reading: an item's whole photo group, or one photo."""

    sample_ids: list[str]
    item_key: str
    item_name: str
    whole_item: bool = Field(description="every photo of the item, read together")
    segmentation: Segmentation | None = None
    extraction: Extraction | None = None
    missing: bool = Field(default=False, description="no recording answers this selection")
    note: str = Field(default="", description="said in place of a reading, when there is none")


class SampleRead(BaseModel):
    results: list[SampleResult]


Unit = tuple[str, str, list[str], bool]  # item key, item name, photo ids, the whole item


def label_crops(segmentation: Segmentation, limit: int) -> list[bytes]:
    """The label regions' crops as bytes, as the web app sends them back after a segment."""
    out: list[bytes] = []
    for region in segmentation.regions:
        if region.concept != "label":
            continue
        out.append(base64.b64decode(region.crop.split(",", 1)[1]))
    return out[:limit]


class SampleReader:
    def __init__(
        self, settings: Settings, samples: Samples, extractor: Extractor, segmenter: Segmenter
    ) -> None:
        self.settings = settings
        self.samples = samples
        self.extractor = extractor
        self.segmenter = segmenter

    def units(self, sample_ids: list[str]) -> list[Unit]:
        """The selection as readings, in the catalog's order: an item whose every photo is
        chosen is one reading of them all; any other chosen photo is a reading of its own.
        An unknown id is refused before anything is read."""
        chosen = list(dict.fromkeys(sample_ids))
        for sid in chosen:
            self.samples.item_of(sid)  # raises UnknownSampleError
        picked = set(chosen)
        out: list[Unit] = []
        for item in self.samples.catalog().items:
            ids = [p.id for p in item.photos]
            if all(i in picked for i in ids):
                out.append((item.key, item.name, ids, True))
                continue
            out += [(item.key, item.name, [i], False) for i in ids if i in picked]
        return out

    async def read_photos(
        self, photos: list[bytes], find_label: bool
    ) -> tuple[Segmentation | None, Extraction]:
        """What the web app does with these photos: the label found on the first, then the
        photos read with its crops (or whole, when SAM found no label or was not asked)."""
        segmentation: Segmentation | None = None
        crops: list[bytes] = []
        if find_label:
            segmentation = await self.segmenter.segment(photos[0])
            crops = label_crops(segmentation, self.settings.max_photos)
        return segmentation, await self.extractor.extract(photos, crops)

    async def read(self, sample_ids: list[str], find_label: bool = True) -> SampleRead:
        results: list[SampleResult] = []
        for key, name, ids, whole in self.units(sample_ids):
            result = SampleResult(sample_ids=ids, item_key=key, item_name=name, whole_item=whole)
            token = exact_replay.set(True)
            try:
                photos = [self.samples.photo(i) for i in ids]
                segmentation, extraction = await self.read_photos(photos, find_label)
            except NoRecordingError as exc:
                log.info("sample without a recording", extra={"samples": ids, "op": exc.op})
                result = result.model_copy(update={"missing": True, "note": MISSING_LINE})
            else:
                result = result.model_copy(
                    update={"segmentation": segmentation, "extraction": extraction}
                )
            finally:
                exact_replay.reset(token)
            results.append(result)
        return SampleRead(results=results)


__all__ = [
    "SampleRead",
    "SampleReadRequest",
    "SampleReader",
    "SampleResult",
    "UnknownSampleError",
    "label_crops",
]
