"""Missing items: a search request the owner runs on Marketplace by handoff, candidates brought
back as text, a screenshot or typed values, each assessed by the profile's rules and dated."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.config import Settings
from app.extract.schema import Evidence, Extraction, LabelReading
from app.extract.service import Extractor, assemble
from app.find.schema import (
    Candidate,
    CandidateCreate,
    ListingReading,
    Search,
    SearchCreate,
    SearchPatch,
    SellerQuestions,
    State,
)
from app.inventory import Inventory
from app.match.schema import Assessment, AssessRequest, Side
from app.match.service import Assessor
from app.model_api import ModelApiClient, text_part, user_message
from app.profiles import Profiles, UnknownProfileError

log = logging.getLogger("app.find")

MAX_OUTPUT_TOKENS = 800
LISTING_INSTRUCTIONS = (
    "You read a second-hand listing someone pasted: the title, the asking price with its"
    " currency, the place, and what is included, as written. Then the specification fields the"
    " text supports, from the list given, with a confidence per field; leave out any field the"
    " text does not state, and never infer a value the seller did not write."
)


class FindError(ValueError):
    """The request cannot be served as given (no profile, an unknown profile, a bad candidate)."""


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def handoff_url(base: str, title: str, max_price: float | None) -> str:
    """The Marketplace search the owner runs. A link, nothing more: no session, no fetch."""
    params: dict[str, str] = {"query": title}
    if max_price is not None and max_price > 0:
        params["maxPrice"] = f"{max_price:g}"
    return f"{base}?{urlencode(params)}"


def state_for(assessment: Assessment) -> State:
    """The ladder onto the candidate states. A documented candidate is not an installed part."""
    if assessment.verdict in ("EXACT_MATCH", "COMPATIBLE_LIKELY"):
        return "documented"
    if assessment.verdict == "CONFLICT":
        return "rejected"
    if assessment.verdict == "VISUALLY_SIMILAR":
        soft_failed = any(c.status == "fail" and not c.hard for c in assessment.checks)
        return "conflicting" if soft_failed else "needs_evidence"
    return "needs_evidence"


def listing_prompt(text: str, field_names: list[str]) -> str:
    return f"Listing text, as pasted:\n---\n{text}\n---\nField names you may use: " + ", ".join(
        field_names
    )


def seller_message(candidate: Candidate) -> SellerQuestions:
    """The questions as a message. No model: the rules asked them, the owner sends them."""
    subject = f"About your listing: {candidate.title or 'the item'}"
    lines = ["I am interested in this listing. Before I come by, could you tell me:"]
    if candidate.questions:
        lines.extend(f"{i}. {q}" for i, q in enumerate(candidate.questions, 1))
    else:
        lines = ["I am interested in this listing; it answers everything I needed to check."]
    lines.append("Is it still available, and when could I pick it up?")
    return SellerQuestions(
        candidate_id=candidate.id,
        subject=subject,
        message="\n".join(lines),
        questions=list(candidate.questions),
    )


class Finder:
    def __init__(
        self,
        settings: Settings,
        client: ModelApiClient,
        inventory: Inventory,
        profiles: Profiles,
        extractor: Extractor,
        assessor: Assessor,
    ) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory
        self.profiles = profiles
        self.extractor = extractor
        self.assessor = assessor

    # --- searches ------------------------------------------------------------

    def create(self, spec: SearchCreate) -> Search:
        profile = spec.profile
        if spec.need_item_id is not None:
            # the item's profile decides; a profile in the request fills in when it has none
            item = self.inventory.get(spec.need_item_id)
            profile = item.profile or profile
        if not profile:
            raise FindError("no profile: give one, or a need item that has one")
        try:
            self.profiles.get(profile)
        except UnknownProfileError as exc:
            raise FindError(str(exc)) from exc
        content = {
            "spec": spec.spec,
            "radius_km": spec.radius_km,
            "max_price": spec.max_price,
            "currency": spec.currency,
            "budget_left": spec.budget_left,
            "notes": spec.notes,
        }
        row = self.inventory.add_search(
            need_item_id=spec.need_item_id,
            profile=profile,
            title=spec.title,
            content=json.dumps(content),
            handoff_url=handoff_url(
                self.settings.marketplace_search_url, spec.title, spec.max_price
            ),
        )
        log.info("search", extra={"search_id": int(row["id"]), "profile": profile})
        return self.search_of(row)

    def searches(self) -> list[Search]:
        return [self.search_of(r) for r in self.inventory.searches()]

    def search(self, search_id: int) -> Search:
        return self.search_of(self.inventory.search(search_id))

    def update(self, search_id: int, patch: SearchPatch) -> Search:
        row = self.inventory.search(search_id)
        content = json.loads(row["content"])
        if patch.notes is not None:
            content["notes"] = patch.notes
        status = patch.status or str(row["status"])
        return self.search_of(self.inventory.update_search(search_id, status, json.dumps(content)))

    def search_of(self, row: Any) -> Search:
        content = json.loads(row["content"])
        return Search(
            id=int(row["id"]),
            need_item_id=row["need_item_id"],
            profile=row["profile"],
            title=row["title"],
            status=row["status"],
            handoff_url=row["handoff_url"],
            candidates=int(row["candidate_count"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            **content,
        )

    # --- candidates ----------------------------------------------------------

    async def add_candidate(
        self, search_id: int, spec: CandidateCreate, screenshot: bytes | None = None
    ) -> Candidate:
        search = self.search(search_id)
        if search.status == "closed":
            raise FindError("the search is closed; reopen it to bring a listing back")
        if spec.source_kind == "text" and not spec.text:
            raise FindError("a text candidate needs the listing text")
        if spec.source_kind == "screenshot" and not screenshot:
            raise FindError("a screenshot candidate needs the screenshot")
        if spec.source_kind == "manual" and not spec.values:
            raise FindError("a manual candidate needs at least one value")
        reading: Extraction | None = None
        title = ""
        asking_price, currency = spec.asking_price, spec.currency
        location, included = spec.location, spec.included_parts
        model, from_fixture, cost = "", True, 0.0
        if spec.source_kind == "text":
            rule_keys = [r.key for r in self.profiles.get(search.profile).rules]
            listing, response = await self.read_text(spec.text, rule_keys)
            reading = assemble(
                LabelReading(item_type="", label_text=spec.text, fields=listing.fields),
                response,
                photos=0,
                source="listing_text",
            )
            # a rule's key the label set does not know (a plug diameter, say) is kept as read
            label_names = set(self.extractor.field_names())
            extra: dict[str, Evidence] = {}
            for read in listing.fields:
                name = read.name.strip().lower()
                if name in rule_keys and name not in label_names and read.value.strip():
                    extra[name] = Evidence(
                        value=read.value.strip(),
                        unit=read.unit.strip(),
                        confidence=min(max(read.confidence, 0.0), 1.0),
                        source="listing_text",
                        raw=read.value,
                    )
            reading = reading.model_copy(
                update={
                    "fields": {**reading.fields, **extra},
                    "warnings": [w for w in reading.warnings if "does not know" not in w],
                }
            )
            title = listing.title.strip()[:200]
            asking_price = asking_price or listing.asking_price.strip()[:40]
            currency = (
                currency if spec.asking_price else (listing.currency.strip().upper() or currency)
            )
            location = location or listing.location.strip()[:120]
            included = included or listing.included.strip()[:500]
            model, from_fixture, cost = response.model, response.from_fixture, response.cost_usd
        elif spec.source_kind == "screenshot":
            assert screenshot is not None
            reading = await self.extractor.extract([screenshot])
            reading = reading.model_copy(
                update={
                    "fields": {
                        k: e.model_copy(update={"source": "screenshot"})
                        for k, e in reading.fields.items()
                    }
                }
            )
            title = (
                reading.label_text.strip().splitlines()[0][:200]
                if reading.label_text.strip()
                else ""
            )
            model, from_fixture, cost = reading.model, reading.from_fixture, reading.cost_usd
        fields: dict[str, Evidence] = dict(reading.fields) if reading else {}
        warnings = list(reading.warnings) if reading else []
        # values typed in are the owner's word about the listing: they replace what was read
        for key, value in spec.values.items():
            if value.strip():
                fields[key] = Evidence(value=value.strip(), confidence=1.0, source="user_edit")
        if not fields:
            warnings.append("nothing in the listing supports a specification field")
        observed_on = spec.observed_on or today()
        content: dict[str, Any] = {
            "asking_price": asking_price,
            "currency": currency,
            "location": location,
            "included_parts": included,
            "url": spec.url,
            "title": title,
            "text": spec.text,
            "note": spec.note,
            "fields": {k: e.model_dump() for k, e in fields.items()},
            "warnings": warnings,
            "model": model,
            "from_fixture": from_fixture,
            "cost_usd": cost,
        }
        assessment = self.assess(search, fields)
        content["assessment"] = assessment.model_dump()
        content["questions"] = assessment.questions
        row = self.inventory.add_candidate(
            search_id, spec.source_kind, observed_on, state_for(assessment), json.dumps(content)
        )
        log.info(
            "candidate",
            extra={
                "search_id": search_id,
                "candidate_id": int(row["id"]),
                "source": spec.source_kind,
                "verdict": assessment.verdict,
                "usd": cost,
            },
        )
        return self.candidate_of(row)

    async def read_text(self, text: str, rule_keys: list[str]) -> tuple[ListingReading, Any]:
        names = sorted(set(self.extractor.field_names()) | set(rule_keys))
        result = await self.client.respond_structured(
            ListingReading,
            model=self.settings.model_spark,
            input=[user_message(text_part(listing_prompt(text, names)))],
            instructions=LISTING_INSTRUCTIONS,
            effort="low",
            max_output_tokens=MAX_OUTPUT_TOKENS,
            op="listing-text",
        )
        return result.parsed, result.response

    def assess(self, search: Search, fields: dict[str, Evidence]) -> Assessment:
        values = {k: f"{e.value} {e.unit}".strip() for k, e in fields.items() if e.value.strip()}
        need = (
            Side(item_id=search.need_item_id, profile=search.profile, values=search.spec)
            if search.need_item_id is not None
            else Side(profile=search.profile, values=search.spec)
        )
        return self.assessor.assess(
            AssessRequest(need=need, candidate=Side(profile=search.profile, values=values))
        )

    def candidates(self, search_id: int) -> list[Candidate]:
        self.inventory.search(search_id)
        return [self.candidate_of(r) for r in self.inventory.candidates(search_id)]

    def candidate(self, candidate_id: int) -> Candidate:
        return self.candidate_of(self.inventory.candidate(candidate_id))

    def recheck(self, candidate_id: int) -> Candidate:
        """The same listing against the need as it stands now; the observation date stays."""
        row = self.inventory.candidate(candidate_id)
        if row["state"] == "withdrawn":
            raise FindError("a withdrawn candidate is not rechecked")
        search = self.search(int(row["search_id"]))
        content = json.loads(row["content"])
        fields = {k: Evidence(**e) for k, e in content["fields"].items()}
        assessment = self.assess(search, fields)
        content["assessment"] = assessment.model_dump()
        content["questions"] = assessment.questions
        return self.candidate_of(
            self.inventory.update_candidate(
                candidate_id, state_for(assessment), json.dumps(content)
            )
        )

    def withdraw(self, candidate_id: int) -> Candidate:
        row = self.inventory.candidate(candidate_id)
        return self.candidate_of(
            self.inventory.update_candidate(candidate_id, "withdrawn", row["content"])
        )

    def questions(self, candidate_id: int) -> SellerQuestions:
        return seller_message(self.candidate(candidate_id))

    def candidate_of(self, row: Any) -> Candidate:
        content = json.loads(row["content"])
        observed = date.fromisoformat(row["observed_on"])
        expires = observed + timedelta(days=self.settings.candidate_days)
        return Candidate(
            id=int(row["id"]),
            search_id=int(row["search_id"]),
            source_kind=row["source_kind"],
            observed_on=row["observed_on"],
            expires_on=expires.isoformat(),
            expired=datetime.now(UTC).date() > expires,
            state=row["state"],
            created_at=row["created_at"],
            assessed_at=row["assessed_at"],
            **content,
        )
