"""Every reading a sample click can ask for, run once: each photo alone and each item's photos
together, with the label found first and without. In record mode an answer not yet kept is
bought and kept (one already kept is replayed at no cost); in fixture mode the same run says
which readings have no recording, so the gallery and the recordings stay in step."""

import logging

from pydantic import BaseModel

from app.model_api import ModelApiError
from app.samples.service import SampleReader

log = logging.getLogger("app.samples")


class SamplesOutcome(BaseModel):
    readings: int = 0
    missing: list[str] = []
    failed: list[str] = []
    cost_usd: float = 0.0

    def lines(self) -> list[str]:
        out = [f"samples: {self.readings} reading(s) answered; {self.cost_usd:.4f} USD"]
        out += [f"samples: no recording for {m}" for m in self.missing]
        out += [f"samples: {f}" for f in self.failed]
        return out


def selections(reader: SampleReader) -> list[list[str]]:
    """What a click can send: each photo alone, then each item's photos together when it has
    more than one (an item of one photo is the same selection as the photo)."""
    items = reader.samples.catalog().items
    alone = [[p.id] for item in items for p in item.photos]
    together = [[p.id for p in item.photos] for item in items if len(item.photos) > 1]
    return alone + together


async def record_samples(reader: SampleReader) -> SamplesOutcome:
    out = SamplesOutcome()
    for ids in selections(reader):
        for find_label in (True, False):
            what = f"{'+'.join(ids)} ({'label found first' if find_label else 'read whole'})"
            try:
                read = await reader.read(ids, find_label)
            except ModelApiError as exc:
                out.failed.append(f"{what}: {exc}")
                continue
            for result in read.results:
                if result.missing:
                    out.missing.append(what)
                    continue
                out.readings += 1
                if result.segmentation is not None:
                    out.cost_usd += result.segmentation.cost_usd
                if result.extraction is not None:
                    out.cost_usd += result.extraction.cost_usd
    log.info(
        "samples recorded",
        extra={"readings": out.readings, "missing": len(out.missing), "usd": out.cost_usd},
    )
    return out
