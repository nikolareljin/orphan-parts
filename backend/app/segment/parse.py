"""Turn SAM 3.1 output text into matches.

The model answers in a line grammar: a frame marker, then one record per match with a box
token and a mask token. Meta's parser (``meta-sam-parser``) validates the grammar and decodes
the mask payloads; this module reduces its records to what the service needs.
"""

import re
from dataclasses import dataclass

from meta_sam_parser import (
    CompletedOutcome,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    decode_mask_to_raster,
    decode_mask_to_svg_path,
    image_segmentation_format,
)

# The box token also carries the dimensions the model saw; the parser checks them and drops them.
_SOURCE_DIMS = re.compile(r"<\|box;[^|]*?\bw=(\d+);h=(\d+)")


@dataclass(frozen=True)
class Match:
    object_id: str
    left: int
    top: int
    right: int  # exclusive
    bottom: int  # exclusive
    source_width: int
    source_height: int
    confidence: float | None
    raster: bytes  # row-major 0/1, mask_width * mask_height
    mask_width: int
    mask_height: int
    svg_path: str  # mask-local pixel coordinates


def parse_matches(text: str) -> tuple[list[Match], list[str]]:
    """Matches in output order, and the parser's diagnostics as plain warnings."""
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result

    dims = _SOURCE_DIMS.search(text)
    source_width, source_height = (int(dims.group(1)), int(dims.group(2))) if dims else (0, 0)

    boxes: dict[str, SegmentationBoxRecord] = {}
    masks: dict[str, SegmentationMaskRecord] = {}
    for record in result.records:
        if isinstance(record, SegmentationBoxRecord):
            boxes.setdefault(record.object_id, record)
        elif isinstance(record, SegmentationMaskRecord):
            masks[record.object_id] = record  # a later revision replaces an earlier one

    matches: list[Match] = []
    for object_id, box in boxes.items():
        mask = masks.get(object_id)
        if mask is None:
            continue
        matches.append(
            Match(
                object_id=object_id,
                left=int(box.left),
                top=int(box.top),
                right=int(box.right),
                bottom=int(box.bottom),
                source_width=source_width,
                source_height=source_height,
                confidence=box.confidence if box.confidence is not None else mask.confidence,
                raster=decode_mask_to_raster(mask.mask),
                mask_width=mask.mask.width,
                mask_height=mask.mask.height,
                svg_path=decode_mask_to_svg_path(mask.mask),
            )
        )
    warnings = [f"{d.code}: {d.message}" for d in result.diagnostics if d.severity == "error"]
    return matches, warnings
