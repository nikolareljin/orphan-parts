"""The most an operation can cost, from its own output limit and the client's price table.

The input side is not known before the call, so each operation carries a token allowance for
it: the most a live call of that kind has read, times 1.5. The output side is what the client
puts on the wire for the service's ``MAX_OUTPUT_TOKENS``: the answer budget plus the reasoning
headroom for the effort the service asks for (``output_cap``), since reasoning counts as
output, times the steps a tool loop may take. Searches and media are priced per unit. The
client retries a failed request up to ``MODEL_API_MAX_ATTEMPTS`` times and a timed-out one may
still be billed, so every ceiling counts each attempt. The guard stops before an operation
whose ceiling would carry the run past ``--max-usd``; what a call then costs is read off the
ledger, not estimated."""

from dataclasses import dataclass

from app.config import Settings
from app.decide.service import MAX_OUTPUT_TOKENS as USES_OUT
from app.extract.service import MAX_OUTPUT_TOKENS as EXTRACT_OUT
from app.find.service import MAX_OUTPUT_TOKENS as LISTING_OUT
from app.listing.service import MAX_OUTPUT_TOKENS as DRAFT_OUT
from app.model_api.client import output_cap
from app.model_api.pricing import Usage, cost_usd
from app.projects.service import MAX_OUTPUT_TOKENS as PROPOSE_OUT
from app.projects.service import MAX_STEPS as PROPOSE_STEPS
from app.value.service import MAX_OUTPUT_TOKENS as PRICE_OUT

# input tokens allowed for: a text brief, and each photo on top of it (a live extract of one
# label photo read 3,311 tokens: 5,000 is that times 1.5)
TEXT_INPUT = 3000
IMAGE_INPUT = 2000
# one step of the propose loop: the brief, the inventory and the tool results so far
PROPOSE_INPUT = 6000
# the price call with web search, held to PRICE_MAX_SEARCHES searches: live calls read 70,000
# to 100,000 input tokens over 11 or 12 unbounded searches, about 10,000 a search; the allowance
# is the brief plus that times 1.5 for each search allowed (63,000 at the default of 4)
PRICE_INPUT_PER_SEARCH = 15_000
# what the text services ask for, but extract, which takes EXTRACT_REASONING_EFFORT
EFFORT = "low"


@dataclass(frozen=True)
class Ceiling:
    model: str
    usd: float
    why: str


def tokens(
    model: str,
    answer: int,
    cap: int,
    *,
    effort: str = EFFORT,
    input_tokens: int = TEXT_INPUT,
    images: int = 0,
    steps: int = 1,
    searches: int = 0,
    attempts: int = 1,
) -> float:
    """``answer`` is the service's budget; what goes on the wire is that plus the headroom for
    ``effort``, under ``cap`` (MODEL_MAX_OUTPUT_TOKENS, 0 = none)."""
    usage = Usage(
        input_tokens=input_tokens + IMAGE_INPUT * images,
        output_tokens=output_cap(answer, effort, cap),
        search_queries=searches,
    )
    return round(cost_usd(model, usage) * steps * attempts, 6)


def media(model: str, *, images: int = 0, audio_seconds: float = 0.0, attempts: int = 1) -> float:
    return round(cost_usd(model, Usage(images=images, audio_seconds=audio_seconds)) * attempts, 6)


def price_terms(settings: Settings) -> tuple[int, int]:
    """The input allowance and the searches of one price call under PRICE_MAX_SEARCHES."""
    searches = settings.price_max_searches
    return TEXT_INPUT + PRICE_INPUT_PER_SEARCH * searches, searches


def ceiling(op: str, settings: Settings, *, audio_seconds: float) -> Ceiling:
    """What one run of ``op`` can cost at most with these settings, and in what terms."""
    spark = settings.model_spark
    cap = settings.model_max_output_tokens
    attempts = settings.model_api_max_attempts
    tries = f", x {attempts} attempts"
    if op == "extract":
        effort = settings.extract_reasoning_effort
        return Ceiling(
            spark,
            tokens(spark, EXTRACT_OUT, cap, effort=effort, images=1, attempts=attempts),
            f"{EXTRACT_OUT} out at effort {effort}, 1 photo{tries}",
        )
    if op == "segment":
        sam = settings.model_sam
        return Ceiling(sam, media(sam, images=1, attempts=attempts), f"1 image, 1 concept{tries}")
    if op == "transcribe":
        voice = settings.model_voice
        return Ceiling(
            voice,
            media(voice, audio_seconds=audio_seconds, attempts=attempts),
            f"{audio_seconds:.1f} s{tries}",
        )
    if op == "listing-text":
        return Ceiling(
            spark, tokens(spark, LISTING_OUT, cap, attempts=attempts), f"{LISTING_OUT} out{tries}"
        )
    if op == "draft":
        return Ceiling(
            spark, tokens(spark, DRAFT_OUT, cap, attempts=attempts), f"{DRAFT_OUT} out{tries}"
        )
    if op == "uses":
        return Ceiling(
            spark, tokens(spark, USES_OUT, cap, attempts=attempts), f"{USES_OUT} out{tries}"
        )
    if op == "propose":
        return Ceiling(
            spark,
            tokens(
                spark,
                PROPOSE_OUT,
                cap,
                input_tokens=PROPOSE_INPUT,
                steps=PROPOSE_STEPS,
                attempts=attempts,
            ),
            f"{PROPOSE_OUT} out x {PROPOSE_STEPS} steps{tries}",
        )
    if op == "price":
        allowance, searches = price_terms(settings)
        return Ceiling(
            spark,
            tokens(
                spark,
                PRICE_OUT,
                cap,
                input_tokens=allowance,
                searches=searches,
                attempts=attempts,
            ),
            f"{PRICE_OUT} out, {allowance} in, {searches} searches{tries}",
        )
    if op == "picture":
        image = settings.model_image
        return Ceiling(image, media(image, images=1, attempts=attempts), f"1 image{tries}")
    raise ValueError(f"no ceiling for {op}")
