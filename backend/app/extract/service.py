"""One extraction: photos in, typed fields with confidence and provenance out."""

import logging

import anyio

from app.config import Settings
from app.extract.fields import FIELD_BY_NAME, field_guide
from app.extract.imaging import BadImageError, prepare
from app.extract.normalize import normalize
from app.extract.schema import Evidence, Extraction, LabelReading, Source
from app.model_api import ModelApiClient, ModelResponse, image_part, text_part, user_message

log = logging.getLogger("app.extract")

LOW_CONFIDENCE = 0.5
MAX_OUTPUT_TOKENS = 800

INSTRUCTIONS = (
    "You read labels on used items and spare parts from photos. Report only what is printed "
    "or clearly visible; never infer a value from the brand or the item type. Give each field "
    "a confidence between 0 and 1 that reflects how legible it is. Leave out any field the "
    "photos do not support. Copy values as printed and put units in the unit property. "
    "label_text is a line by line transcription of the label. item_type is a short noun phrase "
    "such as 'laptop power adapter'."
)


def prompt(crops: int = 0) -> str:
    text = "Read the label on this item. Fields to look for:\n" + field_guide()
    if crops:
        text += f"\nThe last {crops} image(s) are close-up crops of the label found on the item."
    return text


class Extractor:
    def __init__(self, settings: Settings, client: ModelApiClient) -> None:
        self.settings = settings
        self.client = client

    async def extract(self, photos: list[bytes], crops: list[bytes] | None = None) -> Extraction:
        """``crops`` are label crops from segmentation; with them, evidence is sourced
        ``label_crop`` instead of ``photo``."""
        s = self.settings
        crops = crops or []
        if not photos:
            raise BadImageError("at least one photo is required")
        if len(photos) > s.max_photos:
            raise BadImageError(f"at most {s.max_photos} photos per request")
        if len(crops) > s.max_photos:
            raise BadImageError(f"at most {s.max_photos} crops per request")
        max_bytes = s.max_upload_mb * 1024 * 1024

        def prepare_all() -> list[bytes]:
            return [
                prepare(p, max_px=s.image_max_px, max_bytes=max_bytes) for p in [*photos, *crops]
            ]

        # decoding and re-encoding is CPU work; keep it off the event loop
        prepared = await anyio.to_thread.run_sync(prepare_all)
        parts = [
            text_part(prompt(len(crops))),
            *(image_part(p, "image/jpeg") for p in prepared),
        ]
        result = await self.client.respond_structured(
            LabelReading,
            model=s.model_spark,
            input=[user_message(*parts)],
            instructions=INSTRUCTIONS,
            effort=s.extract_reasoning_effort,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            op="extract",
        )
        extraction = assemble(
            result.parsed,
            result.response,
            len(photos),
            crops=len(crops),
            source="label_crop" if crops else "photo",
        )
        log.info(
            "extracted",
            extra={
                "fields": len(extraction.fields),
                "warnings": len(extraction.warnings),
                "photos": len(photos),
                "usd": extraction.cost_usd,
            },
        )
        return extraction


def assemble(
    reading: LabelReading,
    response: ModelResponse,
    photos: int,
    *,
    crops: int = 0,
    source: Source = "photo",
) -> Extraction:
    """Keep known fields, normalise them, and say what is weak or missing."""
    fields: dict[str, Evidence] = {}
    warnings: list[str] = []
    for read in reading.fields:
        name = read.name.strip().lower()
        spec = FIELD_BY_NAME.get(name)
        if spec is None:
            warnings.append(f"ignored a field the label set does not know: {read.name!r}")
            continue
        if not read.value.strip():
            continue
        confidence = min(max(read.confidence, 0.0), 1.0)
        if name in fields and fields[name].confidence >= confidence:
            continue
        value, unit = normalize(spec.normalizer, read.value, default_unit=spec.unit or read.unit)
        fields[name] = Evidence(
            value=value, unit=unit, confidence=confidence, source=source, raw=read.value
        )
    if "part_number" not in fields and "model_number" not in fields:
        warnings.append("no part or model number was read; add a sharper photo of the label")
    low = sorted(n for n, e in fields.items() if e.confidence < LOW_CONFIDENCE)
    if low:
        warnings.append("low confidence: " + ", ".join(low))
    return Extraction(
        item_type=reading.item_type.strip() or "unknown item",
        label_text=reading.label_text.strip(),
        fields=fields,
        warnings=warnings,
        photos=photos,
        crops=crops,
        model=response.model,
        from_fixture=response.from_fixture,
        cost_usd=response.cost_usd,
    )
