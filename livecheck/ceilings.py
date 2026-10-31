"""The most an operation can cost, from its own output limit and the client's price table.

The input side is not known before the call, so each operation carries a generous token
allowance for it; the output side is what the client puts on the wire for the service's
``MAX_OUTPUT_TOKENS``: the answer budget plus the reasoning headroom for the effort
(``output_cap``), since reasoning counts as output, times the steps a tool loop may take.
Searches and media are priced per unit. The guard stops before an operation whose ceiling
would carry the run past ``--max-usd``; what a call then costs is read off the ledger, not
estimated."""

from dataclasses import dataclass

from app.decide.service import MAX_OUTPUT_TOKENS as USES_OUT
from app.extract.service import MAX_OUTPUT_TOKENS as EXTRACT_OUT
from app.find.service import MAX_OUTPUT_TOKENS as LISTING_OUT
from app.listing.service import MAX_OUTPUT_TOKENS as DRAFT_OUT
from app.model_api.client import output_cap
from app.model_api.pricing import Usage, cost_usd
from app.projects.service import MAX_OUTPUT_TOKENS as PROPOSE_OUT
from app.projects.service import MAX_STEPS as PROPOSE_STEPS
from app.value.service import MAX_OUTPUT_TOKENS as PRICE_OUT

# input tokens allowed for: a text brief, and each photo on top of it
TEXT_INPUT = 3000
IMAGE_INPUT = 2000
# web searches the price call is allowed before the ceiling is wrong
PRICE_SEARCHES = 4
# every text call of the product asks for this effort
EFFORT = "low"


@dataclass(frozen=True)
class Ceiling:
    model: str
    usd: float
    why: str


def tokens(
    model: str, answer: int, cap: int, *, images: int = 0, steps: int = 1, searches: int = 0
) -> float:
    """``answer`` is the service's budget; what goes on the wire is that plus the headroom."""
    usage = Usage(
        input_tokens=TEXT_INPUT + IMAGE_INPUT * images,
        output_tokens=output_cap(answer, EFFORT, cap),
        search_queries=searches,
    )
    return round(cost_usd(model, usage) * steps, 6)


def media(model: str, *, images: int = 0, audio_seconds: float = 0.0) -> float:
    return cost_usd(model, Usage(images=images, audio_seconds=audio_seconds))


def ceiling(
    op: str,
    *,
    spark: str,
    sam: str,
    voice: str,
    image: str,
    audio_seconds: float,
    cap: int = 0,
) -> Ceiling:
    """What one run of ``op`` can cost at most, and in what terms; ``cap`` is the settings'
    MODEL_MAX_OUTPUT_TOKENS (0 = none)."""
    if op == "extract":
        return Ceiling(
            spark, tokens(spark, EXTRACT_OUT, cap, images=1), f"{EXTRACT_OUT} out, 1 photo"
        )
    if op == "segment":
        return Ceiling(sam, media(sam, images=1), "1 image, 1 concept")
    if op == "transcribe":
        return Ceiling(voice, media(voice, audio_seconds=audio_seconds), f"{audio_seconds:.1f} s")
    if op == "listing-text":
        return Ceiling(spark, tokens(spark, LISTING_OUT, cap), f"{LISTING_OUT} out")
    if op == "draft":
        return Ceiling(spark, tokens(spark, DRAFT_OUT, cap), f"{DRAFT_OUT} out")
    if op == "uses":
        return Ceiling(spark, tokens(spark, USES_OUT, cap), f"{USES_OUT} out")
    if op == "propose":
        return Ceiling(
            spark,
            tokens(spark, PROPOSE_OUT, cap, steps=PROPOSE_STEPS),
            f"{PROPOSE_OUT} out x {PROPOSE_STEPS} steps",
        )
    if op == "price":
        return Ceiling(
            spark,
            tokens(spark, PRICE_OUT, cap, searches=PRICE_SEARCHES),
            f"{PRICE_OUT} out, {PRICE_SEARCHES} searches",
        )
    if op == "picture":
        return Ceiling(image, media(image, images=1), "1 image")
    raise ValueError(f"no ceiling for {op}")
