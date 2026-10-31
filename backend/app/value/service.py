"""Price guidance: Muse Spark searches and proposes, the rules keep only what a result backs,
and four quantities stay apart. The owner sets the price; nothing here is a valuation."""

import json
import logging
import statistics
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import Item
from app.model_api import (
    ModelApiClient,
    citations,
    search_results,
    searches,
    text_part,
    user_message,
)
from app.value.schema import (
    Comparable,
    Findings,
    Guidance,
    Kind,
    PartsComparison,
    PriceReport,
    PriceReportCreate,
    PriceRequest,
    Quantity,
    Source,
    Strategy,
)

log = logging.getLogger("app.value")

MAX_OUTPUT_TOKENS = 900
WEAK_BELOW = 3
# what the model writes is shown as it is, so it is cut, not trusted
TEXT_MAX = 200
CAVEAT_MAX = 300
CAVEATS_MAX = 8
DETAIL_KEYS = ("condition", "faults", "tests_done", "accessories")

INSTRUCTIONS = (
    "You find what a used item sells for. Search the web for current listings and completed"
    " sales of the same model in the same condition. Report only prices you saw on a page you"
    " searched, one comparable per page, with its URL; never invent a listing, a sale or a"
    " price. Mark a comparable 'sold' only when the page says the item sold or was bought at"
    " that price; everything else is 'asking'. Give the date on the page when there is one."
    " Then give a low, high and typical estimate in the requested currency with a one-line"
    " basis, and caveats for whatever makes the figures uncertain. Plain words, no hype."
)


def instructions(max_searches: int) -> str:
    """The standing instructions with the search bound said: the model plans its searches
    around the count, and ``max_tool_calls`` on the request holds it there."""
    return (
        f"{INSTRUCTIONS} Search at most {max_searches} time{'s' if max_searches != 1 else ''},"
        " then answer with what those searches found."
    )


LABELS = {
    "asking": "asking prices seen",
    "sold": "sold prices seen",
    "reported": "sales you reported",
    "estimate": "the model's estimate",
}


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def brief(item: Item, known: dict[str, str], request: PriceRequest) -> str:
    """What the model is told: confirmed values and the owner's details, the currency, the place."""
    lines = [f"name: {item.name}", f"item_type: {item.item_type}"]
    for key in DETAIL_KEYS:
        lines.append(f"{key}: {getattr(item, key) or '(not given)'}")
    lines.append(f"currency: {request.currency}")
    where = ", ".join(p for p in (request.city, request.country) if p)
    lines.append(f"market: {where or '(not given)'}")
    lines.append("Confirmed fields (key: value):")
    lines.extend(f"- {k}: {v}" for k, v in known.items())
    if not known:
        lines.append("- (none confirmed yet)")
    return "\n".join(lines)


def _norm_url(url: str) -> str:
    """The page without scheme, www, query, fragment or trailing slash: the same page, however
    the model or the search wrote it."""
    u = url.strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix) :]
    if u.startswith("www."):
        u = u[4:]
    for sep in ("?", "#"):
        u = u.split(sep, 1)[0]
    return u.rstrip("/")


def backed(
    found: list[Comparable], output: list[dict[str, Any]], currency: str
) -> tuple[list[Comparable], int, list[str]]:
    """Keep a comparable only when a search result or a citation carries its page, in the
    requested currency; say how many were dropped and why."""
    pages = {_norm_url(r["url"]) for r in search_results(output)}
    pages |= {_norm_url(c["url"]) for c in citations(output)}
    kept: list[Comparable] = []
    dropped = 0
    caveats: list[str] = []
    other_currency = 0
    no_price = 0
    seen_pages: set[str] = set()
    for c in found:
        if c.price <= 0:
            no_price += 1
            continue
        page = _norm_url(c.source_url)
        if page not in pages:
            dropped += 1
            continue
        if c.currency.upper() != currency:
            other_currency += 1
            continue
        if page in seen_pages:
            dropped += 1  # one comparable per page: a second line from it is the same listing
            continue
        seen_pages.add(page)
        kept.append(
            c.model_copy(
                update={
                    "observed": c.observed or today(),
                    "currency": currency,
                    "title": c.title.strip()[:TEXT_MAX],
                    "condition": c.condition.strip()[:TEXT_MAX],
                    "source_title": c.source_title.strip()[:TEXT_MAX],
                }
            )
        )
    made = searches(output)
    if made == 0 and found:
        caveats.append("the model made no web search, so nothing it wrote can be backed")
    elif not pages and found:
        caveats.append("the search returned no pages, so nothing the model wrote can be backed")
    if dropped:
        caveats.append(
            f"{dropped} line(s) the model wrote rest on no search result and were left out"
        )
    if no_price:
        caveats.append(f"{no_price} line(s) carried no price and were left out")
    if other_currency:
        caveats.append(
            f"{other_currency} comparable(s) in another currency were left out;"
            " nothing is converted"
        )
    return kept, dropped + other_currency + no_price, caveats


def quantity(kind: Kind, prices: list[float], currency: str, basis: str) -> Quantity:
    if not prices:
        return Quantity(
            kind=kind,
            label=LABELS[kind],
            count=0,
            low=None,
            high=None,
            typical=None,
            currency=currency,
            basis=basis,
        )
    return Quantity(
        kind=kind,
        label=LABELS[kind],
        count=len(prices),
        low=min(prices),
        high=max(prices),
        typical=round(statistics.median(prices), 2),
        currency=currency,
        basis=basis,
    )


def strategies(asking: Quantity, estimate: Quantity, weak: bool) -> list[Strategy]:
    """Three ways to price, each from a figure that exists; the owner picks."""
    tail = " (weak evidence: your call)" if weak else ""
    lows = [v for v in (asking.low, estimate.low) if v is not None]
    highs = [v for v in (asking.high, estimate.high) if v is not None]
    quick = min(lows) if lows else None
    typical = asking.typical if asking.typical is not None else estimate.typical
    patient = max(highs) if highs else None
    return [
        Strategy(
            name="quick_sale",
            label="Quick sale",
            price=quick,
            note="the lowest figure, asked or estimated; expect the first serious buyer" + tail,
        ),
        Strategy(
            name="typical",
            label="Typical",
            price=typical,
            note="the middle of what is asked; expect a week or two" + tail,
        ),
        Strategy(
            name="patient",
            label="Patient",
            price=patient,
            note="the top of the range; expect to wait and to field questions" + tail,
        ),
    ]


class Valuer:
    def __init__(self, settings: Settings, client: ModelApiClient, inventory: Inventory) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory

    async def guide(self, item_id: int, request: PriceRequest) -> Guidance:
        item = self.inventory.get(item_id)
        known = {
            k: f"{a.value} {a.unit}".strip()
            for k, a in item.fields.items()
            if a.review == "accepted"
        }
        tool: dict[str, Any] = {
            "type": "web_search",
            "search_context_size": self.settings.price_search_context,
        }
        country = request.country or self.settings.price_country
        if country or request.city:
            location: dict[str, str] = {"type": "approximate"}
            if country:
                location["country"] = country
            if request.city:
                location["city"] = request.city
            tool["user_location"] = location
        result = await self.client.respond_structured(
            Findings,
            model=self.settings.model_spark,
            input=[user_message(text_part(brief(item, known, request)))],
            instructions=instructions(self.settings.price_max_searches),
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tools=[tool],
            max_tool_calls=self.settings.price_max_searches,
            include=["web_search_call.results"],
            op="price",
        )
        findings = result.parsed
        output = result.response.output
        kept, dropped, caveats = backed(findings.comparables, output, request.currency)
        said = [c.strip()[:CAVEAT_MAX] for c in findings.caveats if c.strip()]
        caveats = said[:CAVEATS_MAX] + caveats
        seen = today()
        asking = quantity(
            "asking",
            [c.price for c in kept if c.kind == "asking"],
            request.currency,
            f"listings found by search on {seen}",
        )
        sold = quantity(
            "sold",
            [c.price for c in kept if c.kind == "sold"],
            request.currency,
            f"sales the pages found on {seen} state as completed",
        )
        reports = self.reports(item_id)
        reported = quantity(
            "reported",
            [r.price for r in reports if r.currency == request.currency],
            request.currency,
            "sales you recorded, with their dates",
        )
        estimate_prices = [findings.estimate_low, findings.estimate_typical, findings.estimate_high]
        if findings.currency.upper() != request.currency or any(p <= 0 for p in estimate_prices):
            estimate = quantity("estimate", [], request.currency, "no usable estimate was given")
            caveats.append("the estimate was not in the requested currency, or not positive")
        else:
            estimate = Quantity(
                kind="estimate",
                label=LABELS["estimate"],
                count=1,
                low=findings.estimate_low,
                high=findings.estimate_high,
                typical=findings.estimate_typical,
                currency=request.currency,
                basis=f"the model's estimate, labelled as such: {findings.basis.strip()}",
            )
        evidence = asking.count + sold.count + reported.count
        weak = evidence < WEAK_BELOW
        weak_reason = (
            f"fewer than {WEAK_BELOW} backed comparables or reported sales; set the price yourself"
            if weak
            else ""
        )
        sources = [
            Source(url=c.source_url, title=c.source_title or c.title, observed=c.observed)
            for c in kept
        ]
        content: dict[str, Any] = {
            "currency": request.currency,
            "quantities": [q.model_dump() for q in (asking, sold, reported, estimate)],
            "comparables": [c.model_dump() for c in kept],
            "dropped": dropped,
            "sources": [s.model_dump() for s in sources],
            "estimate_label": "estimate",
            "strategies": [s.model_dump() for s in strategies(asking, estimate, weak)],
            "weak": weak,
            "weak_reason": weak_reason,
            "caveats": caveats,
            "searches": result.response.usage.search_queries,
            "model": result.response.model,
            "from_fixture": result.response.from_fixture,
            "cost_usd": result.response.cost_usd,
        }
        row = self.inventory.add_guidance(item_id, json.dumps(content))
        log.info(
            "priced",
            extra={
                "item_id": item_id,
                "kept": len(kept),
                "dropped": dropped,
                "weak": weak,
                "searches": content["searches"],
                "usd": result.response.cost_usd,
            },
        )
        return self.assemble(row)

    def guidances(self, item_id: int) -> list[Guidance]:
        rows = self.inventory.guidances(item_id)
        if not rows:
            return []
        # the parts comparison is the item's, not each guidance's: computed once, from the latest
        latest = json.loads(rows[-1]["content"])
        parts = self.parts(item_id, latest)
        return [self.assemble(r, parts=parts) for r in rows]

    def report(self, item_id: int, spec: PriceReportCreate) -> PriceReport:
        row = self.inventory.add_price_report(
            item_id,
            price=spec.price,
            currency=spec.currency,
            sold_on=spec.sold_on,
            note=spec.note,
        )
        return PriceReport(**dict(row))

    def reports(self, item_id: int) -> list[PriceReport]:
        return [PriceReport(**dict(r)) for r in self.inventory.price_reports(item_id)]

    def assemble(self, row: Any, *, parts: PartsComparison | None = None) -> Guidance:
        content = json.loads(row["content"])
        if parts is None:
            parts = self.parts(int(row["item_id"]), content)
        return Guidance(
            id=int(row["id"]),
            item_id=int(row["item_id"]),
            version=int(row["version"]),
            item_version=int(row["item_version"]),
            # a decision is no change to what the item is worth
            stale=bool(row["changed_since"]),
            parts=parts,
            at=row["at"],
            **content,
        )

    def parts(self, item_id: int, content: dict[str, Any]) -> PartsComparison | None:
        """Whole against parts, from the parts' own latest guidance; no part is priced by guess."""
        item = self.inventory.get(item_id)
        if not item.components:
            return None
        typical = next((q["typical"] for q in content["quantities"] if q["kind"] == "asking"), None)
        if typical is None:
            typical = next(
                (q["typical"] for q in content["quantities"] if q["kind"] == "estimate"), None
            )
        priced = 0
        total = 0.0
        for component_id in item.components:
            rows = self.inventory.guidances(component_id)
            if not rows:
                continue
            latest = json.loads(rows[-1]["content"])
            if latest["currency"] != content["currency"]:
                continue
            part = next((q["typical"] for q in latest["quantities"] if q["kind"] == "asking"), None)
            if part is None:
                part = next(
                    (q["typical"] for q in latest["quantities"] if q["kind"] == "estimate"), None
                )
            if part is not None:
                priced += 1
                total += part
        count = len(item.components)
        if priced == 0:
            note = f"{count} part(s) recorded, none priced yet: ask for guidance on each to compare"
            return PartsComparison(
                components=count, priced=0, sum_typical=None, whole_typical=typical, note=note
            )
        note = (
            f"{priced} of {count} part(s) priced: their typical prices sum to {total:.2f}"
            f" {content['currency']}; selling them apart means {count} listings, the time for"
            " each, and a remainder nobody wants"
        )
        return PartsComparison(
            components=count,
            priced=priced,
            sum_typical=round(total, 2),
            whole_typical=typical,
            note=note,
        )
