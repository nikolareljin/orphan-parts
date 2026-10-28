"""One segmentation: a photo and a few concepts in, regions with crops and an overlay out."""

import logging
import re
from collections.abc import Sequence

import anyio

from app.config import Settings
from app.extract.imaging import BadImageError, dimensions, prepare
from app.model_api import ModelApiClient, image_part, text_part, user_message
from app.segment.concepts import DEFAULT_CONCEPTS, MAX_CONCEPTS, phrase_for
from app.segment.parse import Match, parse_matches
from app.segment.render import (
    clip,
    crop,
    data_url,
    mask_image,
    overlay,
    scale_box,
    shift_path,
)
from app.segment.schema import Box, Region, Segmentation

log = logging.getLogger("app.segment")

MAX_REGIONS_PER_CONCEPT = 4
MASK_ENCODING = "one_bit"
_SLUG = re.compile(r"[^a-z0-9]+")


def op_for(concept: str) -> str:
    """Operation name per concept: the ledger line and the fixture file are named after it."""
    return "segment-" + (_SLUG.sub("-", concept.lower()).strip("-") or "concept")


class Segmenter:
    def __init__(self, settings: Settings, client: ModelApiClient) -> None:
        self.settings = settings
        self.client = client

    async def segment(self, photo: bytes, concepts: Sequence[str] | None = None) -> Segmentation:
        s = self.settings
        keys = [k.strip() for k in (concepts or DEFAULT_CONCEPTS) if k and k.strip()]
        if not keys:
            raise BadImageError("at least one concept is required")
        if len(keys) > MAX_CONCEPTS:
            raise BadImageError(f"at most {MAX_CONCEPTS} concepts per request")
        max_bytes = s.max_upload_mb * 1024 * 1024
        prepared = await anyio.to_thread.run_sync(
            lambda: prepare(photo, max_px=s.image_max_px, max_bytes=max_bytes)
        )
        width, height = dimensions(prepared)
        # the model sees a smaller copy: masks come back box-sized and decoding them is
        # pure-Python work, so fewer pixels is faster; boxes are scaled back below
        small = await anyio.to_thread.run_sync(
            lambda: prepare(prepared, max_px=s.segment_max_px, max_bytes=max_bytes)
        )

        found: list[tuple[str, str, Match]] = []
        warnings: list[str] = []
        cost = 0.0
        from_fixture = True
        model = s.model_sam
        for key in keys:
            phrase = phrase_for(key)
            response = await self.client.respond(
                model=s.model_sam,
                input=[user_message(text_part(phrase), image_part(small, "image/jpeg"))],
                op=op_for(key),
                metadata={"include_confidence": "true", "mask_encoding": MASK_ENCODING},
            )
            matches, problems = parse_matches(response.text)
            warnings.extend(f"{key}: {p}" for p in problems)
            if not matches:
                warnings.append(f"no {key} found")
            matches.sort(key=lambda m: -(m.confidence if m.confidence is not None else 0.0))
            found.extend((key, phrase, m) for m in matches[:MAX_REGIONS_PER_CONCEPT])
            cost += response.cost_usd
            from_fixture = from_fixture and response.from_fixture
            model = response.model

        def build() -> tuple[list[Region], str]:
            return assemble(prepared, width, height, found)

        regions, overlay_url = await anyio.to_thread.run_sync(build)
        result = Segmentation(
            width=width,
            height=height,
            regions=regions,
            overlay=overlay_url,
            warnings=warnings,
            model=model,
            from_fixture=from_fixture,
            cost_usd=cost,
        )
        log.info(
            "segmented",
            extra={
                "concepts": len(keys),
                "regions": len(regions),
                "warnings": len(warnings),
                "usd": cost,
            },
        )
        return result


def assemble(
    photo: bytes, width: int, height: int, found: list[tuple[str, str, Match]]
) -> tuple[list[Region], str]:
    """Scale every match onto the prepared photo, render its crop and the shared overlay."""
    regions: list[Region] = []
    layers = []
    for concept, phrase, m in found:
        sx = width / m.source_width if m.source_width else 1.0
        sy = height / m.source_height if m.source_height else 1.0
        raw = Box(left=m.left, top=m.top, right=m.right, bottom=m.bottom)
        box = clip(scale_box(raw, sx, sy), width, height)
        if box.width <= 0 or box.height <= 0:
            continue
        mask = mask_image(m.raster, m.mask_width, m.mask_height)
        coverage = sum(m.raster) / max(len(m.raster), 1)
        layers.append((concept, box, mask))
        regions.append(
            Region(
                concept=concept,
                phrase=phrase,
                object_id=m.object_id,
                box=box,
                confidence=m.confidence,
                coverage=round(coverage, 4),
                crop=data_url(crop(photo, box), "image/jpeg"),
                svg_path=shift_path(
                    m.svg_path,
                    box.left,
                    box.top,
                    box.width / max(m.mask_width, 1),
                    box.height / max(m.mask_height, 1),
                ),
            )
        )
    return regions, data_url(overlay(photo, layers), "image/jpeg")
