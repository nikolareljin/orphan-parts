"""Published Model API prices, used to keep the spend ledger.

Prices are USD as listed on the pricing page (standard mode). Token prices are per
million tokens; media prices are per unit. An unknown model is charged at the highest
token rate so the ledger never under-counts.
"""

import logging

from pydantic import BaseModel

log = logging.getLogger("app.model_api.pricing")

PER_MILLION = 1_000_000

# (cached input, input, output) per million tokens, matched by model-id prefix
TOKEN_RATES: dict[str, tuple[float, float, float]] = {
    "muse-wonder": (0.20, 4.00, 20.00),
    "muse-spark": (0.15, 1.25, 4.25),
}
CONTRIBUTOR_RATES: tuple[float, float, float] = (0.002, 0.10, 0.20)
HIGHEST_TOKEN_RATES: tuple[float, float, float] = TOKEN_RATES["muse-wonder"]

IMAGE_UNIT_USD: dict[str, float] = {
    "sam": 2.50 / 1000,  # per image segmented
    "muse-image": 0.01,  # per image generated
}
SAM_VIDEO_FRAME_USD = 0.20 / 1000
SAM_VIDEO_MIN_FRAMES = 50
VOICE_USD_PER_HOUR = 0.18
SEARCH_QUERY_USD = 2.50 / 1000


class Usage(BaseModel):
    """Everything a call consumed, in the units the API bills."""

    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    images: int = 0
    video_frames: int = 0
    audio_seconds: float = 0.0
    search_queries: int = 0

    @classmethod
    def from_response(
        cls,
        usage: dict[str, object] | None,
        *,
        search_queries: int = 0,
        audio_seconds: float = 0.0,
    ) -> "Usage":
        if not usage:
            return cls(search_queries=search_queries, audio_seconds=audio_seconds)
        inp = usage.get("input_tokens_details")
        out = usage.get("output_tokens_details")
        return cls(
            input_tokens=_as_int(usage.get("input_tokens")),
            cached_tokens=_as_int(inp.get("cached_tokens") if isinstance(inp, dict) else 0),
            output_tokens=_as_int(usage.get("output_tokens")),
            reasoning_tokens=_as_int(out.get("reasoning_tokens") if isinstance(out, dict) else 0),
            images=_as_int(usage.get("images_processed")),
            video_frames=_as_int(usage.get("video_frames_processed")),
            search_queries=search_queries,
            audio_seconds=audio_seconds,
        )


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def token_rates(model: str) -> tuple[float, float, float]:
    name = model.lower()
    if "contributor" in name:
        return CONTRIBUTOR_RATES
    for prefix, rates in TOKEN_RATES.items():
        if name.startswith(prefix):
            return rates
    log.warning("no price for model %s; charging the highest token rate", model)
    return HIGHEST_TOKEN_RATES


def cost_usd(model: str, usage: Usage) -> float:
    """Price of one call. Rounded to a tenth of a cent's thousandth to keep sums stable."""
    name = model.lower()
    total = 0.0
    if name.startswith("muse-voice"):
        total += usage.audio_seconds / 3600 * VOICE_USD_PER_HOUR
    elif name.startswith("sam"):
        total += usage.images * IMAGE_UNIT_USD["sam"]
        if usage.video_frames:
            total += max(usage.video_frames, SAM_VIDEO_MIN_FRAMES) * SAM_VIDEO_FRAME_USD
    elif name.startswith("muse-image"):
        total += max(usage.images, 1) * IMAGE_UNIT_USD["muse-image"]
    else:
        cached, inp, out = token_rates(model)
        uncached = max(usage.input_tokens - usage.cached_tokens, 0)
        total += (uncached * inp + usage.cached_tokens * cached + usage.output_tokens * out) / (
            PER_MILLION
        )
    total += usage.search_queries * SEARCH_QUERY_USD
    return round(total, 6)
