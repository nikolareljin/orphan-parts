"""Missing items: a search request the owner runs on Marketplace by handoff, candidates brought
back as text, a screenshot or typed values, each assessed by the profile's rules and dated."""

import asyncio
import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.config import Settings
from app.extract.schema import Evidence, Extraction, LabelReading
from app.extract.service import Extractor, assemble
from app.find.plan import (
    DEFAULT_EXCLUSIONS,
    MAX_PHRASINGS,
    MIN_PHRASINGS,
    PHRASING_MAX,
    RANK,
    SCAN_MAX,
    WHY_MAX,
    PatternError,
    Score,
    clean_exclusions,
    score_listing,
    validate_pattern,
)
from app.find.schema import (
    BroughtListing,
    Candidate,
    CandidateCreate,
    Highlight,
    ListingReading,
    ListingsBack,
    ListingScore,
    PatternResult,
    PatternTest,
    Phrasing,
    PlanEdit,
    PlanWriting,
    Search,
    SearchCreate,
    SearchPatch,
    SearchPlan,
    SellerQuestions,
    State,
)
from app.inventory import Inventory, NotFoundError
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


PLAN_OUTPUT_TOKENS = 700
# listings one search keeps for scoring; past it the oldest go first, the ones not yet checked
# before the ones Check fit has read
MAX_LISTINGS = 50
PLAN_INSTRUCTIONS = (
    "You plan a search of second-hand listings for one needed part or device. Write 3 to 6"
    " search phrasings a seller might have put in a listing title: the plain name, synonyms,"
    " the part or model number in the ways it gets written, the devices it is sold for, seller"
    " wording and common misspellings; each with one line on what it finds that the others"
    " miss. A phrasing is a few words for a search box that takes words, not operators or"
    " quotes. Then one match pattern: an RE2 regular expression, applied case-insensitively"
    " to a listing's text, that a listing which fits the need matches, built from the part"
    " number with optional separators or the deciding values with their units. Keep it under"
    " 200 characters; use short gaps such as .{0,20} and classes such as [-\\s]?; no"
    " lookarounds, no backreferences, no comments and no inline flags. Then the words or short"
    " phrases in a listing that rule it out: for parts, broken, not working, and any that name"
    " a variant that does not fit. Never invent a part or model number the need does not give."
)


class FindError(ValueError):
    """The request cannot be served as given (no profile, an unknown profile, a bad candidate)."""


class BusyError(FindError):
    """The same work is already under way (Check fit reading the same listing)."""


# how long a Check fit in progress holds its listing; one older than this was cut off
CHECKING_SECONDS = 300


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def handoff_url(base: str, title: str, max_price: float | None) -> str:
    """The Marketplace search the owner runs. A link, nothing more: no session, no fetch."""
    params: dict[str, str] = {"query": title}
    if max_price is not None and max_price > 0:
        params["maxPrice"] = f"{max_price:g}"
    return f"{base}?{urlencode(params)}"


def stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def score_model(score: Score) -> ListingScore:
    return ListingScore(
        verdict=score.verdict,
        matched=score.matched,
        highlights=[
            Highlight(kind=h.kind, start=h.start, end=h.end, text=h.text) for h in score.hits
        ],
        excluded=score.excluded,
        price=score.price,
        price_ok=score.price_ok,
        reasons=score.reasons,
    )


def compiled_or_none(pattern: str) -> Any:
    """The kept pattern compiled, or None when there is none (or it no longer passes)."""
    if not pattern.strip():
        return None
    try:
        return validate_pattern(pattern)
    except PatternError:
        return None


def ranked(listings: list[BroughtListing]) -> list[BroughtListing]:
    """Fits first, then maybe, then the ones ruled out; cheaper first within each, then newer."""
    return sorted(
        listings,
        key=lambda b: (
            RANK[b.score.verdict],
            b.score.price if b.score.price is not None else float("inf"),
            -b.id,
        ),
    )


def capped(entries: list[dict[str, Any]], fresh: set[int]) -> list[dict[str, Any]]:
    """At most MAX_LISTINGS, in the order they came: past it the oldest go first, the ones not
    yet checked before the ones with a candidate; the ones just brought back stay."""
    over = len(entries) - MAX_LISTINGS
    if over <= 0:
        return entries
    old = [e for e in entries if int(e["id"]) not in fresh]
    order = [e for e in old if e.get("candidate_id") is None]
    order += [e for e in old if e.get("candidate_id") is not None]
    gone = {int(e["id"]) for e in order[:over]}
    return [e for e in entries if int(e["id"]) not in gone]


def clean_phrasings(
    written: list[Phrasing], title: str, base: str, max_price: float | None
) -> list[Phrasing]:
    """One line each, one of each, at most six; the title fills in when fewer than three."""
    kept: list[Phrasing] = []
    seen: set[str] = set()
    for p in written:
        text = " ".join(p.text.split())[:PHRASING_MAX]
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        kept.append(Phrasing(text=text, why=" ".join(p.why.split())[:WHY_MAX], url=""))
        if len(kept) >= MAX_PHRASINGS:
            break
    if len(kept) < MIN_PHRASINGS and title.lower() not in seen:
        kept.append(Phrasing(text=title[:PHRASING_MAX], why="the need as written", url=""))
    return [p.model_copy(update={"url": handoff_url(base, p.text, max_price)}) for p in kept]


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
        # one lock per search around every read-modify-write of its plan and listings, so a
        # pattern saved while listings come in loses neither
        self._locks: dict[int, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    @contextmanager
    def held(self, search_id: int) -> Iterator[None]:
        with self._locks_guard:
            lock = self._locks.setdefault(search_id, threading.RLock())
        with lock:
            yield

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
        with self.held(search_id):
            row = self.inventory.search(search_id)
            content = json.loads(row["content"])
            if patch.notes is not None:
                content["notes"] = patch.notes
            status = patch.status or str(row["status"])
            row = self.inventory.update_search(search_id, status, json.dumps(content))
        return self.search_of(row)

    def search_of(self, row: Any) -> Search:
        # the head is the content without the listings, so a list of searches parses no listing
        content = json.loads(row["head"])
        plan = content.pop("plan", None)
        for kept_apart in ("listings", "checking", "next_listing_id"):
            content.pop(kept_apart, None)
        return Search(
            plan=SearchPlan(**plan) if plan else None,
            listings=int(row["listing_count"]),
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

    # --- search plan ---------------------------------------------------------

    def plan_brief(self, search: Search) -> str:
        profile = self.profiles.get(search.profile)
        lines = [f"Needed: {search.title}", f"Kind of part: {profile.label}"]
        if search.spec:
            lines.append(
                "Needed values: "
                + "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in search.spec.items())
            )
        if search.need_item_id is not None:
            # imported here: app.projects imports this module
            from app.projects.pack import private_field

            item = self.inventory.get(search.need_item_id)
            lines.append(f"Needed by: {item.name or item.item_type}")
            # nothing that identifies the item or its owner (a serial, an address, an account)
            values = [
                f"{k.replace('_', ' ')} {a.value} {a.unit}".strip()
                for k, a in item.fields.items()
                if a.value.strip() and a.review != "rejected" and not private_field(k)
            ]
            if values:
                lines.append("What it states: " + "; ".join(values[:30]))
        if search.notes:
            lines.append(f"Notes: {search.notes}")
        if search.max_price:
            lines.append(f"Top price: {search.max_price:g} {search.currency}")
        return "\n".join(lines)

    async def plan(self, search_id: int) -> Search:
        """One Muse Spark call: the phrasings, the pattern and the exclusion words. A pattern
        that fails the checks is not kept; the plan says why. Planned again, the pattern and the
        words the owner saved stay, the written pattern offered beside them, and a refused one
        never empties a pattern already kept."""
        search = self.search(search_id)
        result = await self.client.respond_structured(
            PlanWriting,
            model=self.settings.model_spark,
            input=[user_message(text_part(self.plan_brief(search)))],
            instructions=PLAN_INSTRUCTIONS,
            effort="low",
            max_output_tokens=PLAN_OUTPUT_TOKENS,
            op="search-plan",
        )
        written, response = result.parsed, result.response
        pattern, error = written.pattern.strip(), ""
        try:
            validate_pattern(pattern)
        except PatternError as exc:
            pattern, error = (
                "",
                f"the written pattern {written.pattern.strip()[:80]!r} was refused: {exc}",
            )
        exclusions = clean_exclusions([*DEFAULT_EXCLUSIONS, *written.exclusions])
        before, suggested, edited_at = search.plan, "", ""
        if before is not None and before.edited_at:
            # the owner's own pattern and words stay; the written pattern is offered
            suggested = pattern if pattern != before.pattern else ""
            pattern, exclusions, edited_at = before.pattern, before.exclusions, before.edited_at
        elif before is not None and not pattern:
            pattern = before.pattern
        plan = SearchPlan(
            phrasings=clean_phrasings(
                written.phrasings,
                search.title,
                self.settings.marketplace_search_url,
                search.max_price,
            ),
            pattern=pattern,
            pattern_error=error,
            suggested_pattern=suggested,
            # the usual words first, then the ones written for this need; the owner prunes
            exclusions=exclusions,
            edited_at=edited_at,
            max_price=search.max_price,
            radius_km=search.radius_km,
            model=response.model,
            from_fixture=response.from_fixture,
            cost_usd=response.cost_usd,
            planned_at=stamp(),
        )
        log.info(
            "search plan",
            extra={"search_id": search_id, "usd": response.cost_usd, "refused": bool(error)},
        )
        # scoring every listing again, and the lock, stay off the event loop
        return await asyncio.to_thread(self._keep_plan, search_id, plan)

    def edit_plan(self, search_id: int, edit: PlanEdit) -> Search:
        """The owner's pattern and words. A search with no plan yet gets one here, with the
        title as its one phrasing, so a pattern can be written without a model call."""
        if edit.pattern is not None and edit.pattern.strip():
            try:
                validate_pattern(edit.pattern)
            except PatternError as exc:
                raise FindError(str(exc)) from exc
        with self.held(search_id):
            return self._edit_plan(search_id, edit)

    def _edit_plan(self, search_id: int, edit: PlanEdit) -> Search:
        search = self.search(search_id)
        plan = search.plan or SearchPlan(
            phrasings=clean_phrasings(
                [], search.title, self.settings.marketplace_search_url, search.max_price
            ),
            pattern="",
            exclusions=list(DEFAULT_EXCLUSIONS),
            max_price=search.max_price,
            radius_km=search.radius_km,
            model="",
            from_fixture=False,
            cost_usd=0.0,
            planned_at=stamp(),
        )
        update: dict[str, Any] = {"edited_at": stamp()}
        if edit.pattern is not None:
            update |= {
                "pattern": edit.pattern.strip(),
                "pattern_error": "",
                "suggested_pattern": "",
            }
        if edit.exclusions is not None:
            update["exclusions"] = clean_exclusions(edit.exclusions)
        return self._keep_plan(search_id, plan.model_copy(update=update))

    def _keep_plan(self, search_id: int, plan: SearchPlan) -> Search:
        """Store the plan and score every listing brought back again by it."""
        compiled = compiled_or_none(plan.pattern)
        with self.held(search_id):
            row = self.inventory.search(search_id)
            content = json.loads(row["content"])
            content["plan"] = plan.model_dump()
            for entry in content.get("listings", []):
                entry["score"] = self._score(entry["text"], compiled, plan).model_dump()
            row = self.inventory.update_search(search_id, str(row["status"]), json.dumps(content))
        return self.search_of(row)

    def _score(self, text: str, compiled: Any, plan: SearchPlan | None) -> ListingScore:
        exclusions = plan.exclusions if plan else list(DEFAULT_EXCLUSIONS)
        max_price = plan.max_price if plan else None
        return score_model(score_listing(text, compiled, exclusions, max_price))

    def test_pattern(self, spec: PatternTest) -> PatternResult:
        """A pattern tried on a line: the error it is refused with, or the score it gives."""
        compiled = None
        if spec.pattern.strip():
            try:
                compiled = validate_pattern(spec.pattern)
            except PatternError as exc:
                return PatternResult(error=str(exc), score=None)
        score = score_listing(
            spec.text, compiled, clean_exclusions(spec.exclusions), spec.max_price
        )
        return PatternResult(error="", score=score_model(score))

    # --- listings brought back -----------------------------------------------

    def _add_listings(
        self, search_id: int, texts: list[tuple[str, str]], observed_on: str
    ) -> list[BroughtListing]:
        """Kept as far as the pattern reads them (SCAN_MAX), scored, at most MAX_LISTINGS."""
        with self.held(search_id):
            row = self.inventory.search(search_id)
            if row["status"] == "closed":
                raise FindError("the search is closed; reopen it to bring listings back")
            content = json.loads(row["content"])
            plan = SearchPlan(**content["plan"]) if content.get("plan") else None
            compiled = compiled_or_none(plan.pattern) if plan else None
            entries: list[dict[str, Any]] = content.setdefault("listings", [])
            # ids only go up, so one removed is never given to another listing
            next_id = max(
                int(content.get("next_listing_id", 1)),
                max((int(e["id"]) for e in entries), default=0) + 1,
            )
            content["next_listing_id"] = next_id + len(texts)
            added_at = stamp()
            for i, (kind, whole) in enumerate(texts):
                text = whole.strip()[:SCAN_MAX]
                entries.append(
                    {
                        "id": next_id + i,
                        "source_kind": kind,
                        "text": text,
                        "observed_on": observed_on or today(),
                        "added_at": added_at,
                        "candidate_id": None,
                        "score": self._score(text, compiled, plan).model_dump(),
                    }
                )
            fresh = set(range(next_id, next_id + len(texts)))
            content["listings"] = capped(entries, fresh)
            self.inventory.update_search(search_id, str(row["status"]), json.dumps(content))
            return self.listings(search_id)

    def add_listings(self, search_id: int, back: ListingsBack) -> list[BroughtListing]:
        """Pasted listings, scored where they stand; nothing is read by a model."""
        return self._add_listings(search_id, [("text", t) for t in back.texts], back.observed_on)

    async def add_screenshots(
        self, search_id: int, shots: list[bytes], observed_on: str
    ) -> list[BroughtListing]:
        """Screenshots of listings: the extractor reads each into text (one call each), and each
        is kept and scored like a pasted listing as soon as it is read, so a request cut off
        part way keeps the readings it paid for."""
        if self.search(search_id).status == "closed":
            raise FindError("the search is closed; reopen it to bring listings back")
        kept: list[BroughtListing] | None = None
        for shot in shots:
            reading = await self.extractor.extract([shot])
            text = reading.label_text.strip()
            if not text:
                values = [f"{k} {e.value} {e.unit}".strip() for k, e in reading.fields.items()]
                text = "; ".join(values)
            if text:
                # scoring, and the lock, stay off the event loop
                kept = await asyncio.to_thread(
                    self._add_listings, search_id, [("screenshot", text)], observed_on
                )
        if kept is None:
            raise FindError("no text could be read from the screenshots")
        return kept

    def listings(self, search_id: int) -> list[BroughtListing]:
        content = json.loads(self.inventory.search(search_id)["content"])
        return ranked([BroughtListing(**e) for e in content.get("listings", [])])

    def remove_listing(self, search_id: int, listing_id: int) -> list[BroughtListing]:
        with self.held(search_id):
            row = self.inventory.search(search_id)
            content = json.loads(row["content"])
            entries = content.get("listings", [])
            kept = [e for e in entries if int(e["id"]) != listing_id]
            if len(kept) == len(entries):
                raise NotFoundError(f"no listing {listing_id} on search {search_id}")
            content["listings"] = kept
            self.inventory.update_search(search_id, str(row["status"]), json.dumps(content))
            return self.listings(search_id)

    async def check_listing(self, search_id: int, listing_id: int) -> Candidate:
        """Check fit: the listing becomes a candidate, read by Muse Spark and assessed by the
        profile's rules, with the seller questions; the listing remembers which candidate."""
        found = await asyncio.to_thread(self._start_check, search_id, listing_id)
        if found.candidate_id is not None:
            return self.candidate(found.candidate_id)
        try:
            candidate = await self.add_candidate(
                search_id, CandidateCreate(text=found.text, observed_on=found.observed_on)
            )
        except BaseException:
            await asyncio.to_thread(self._remember_candidate, search_id, listing_id, None)
            raise
        await asyncio.to_thread(self._remember_candidate, search_id, listing_id, candidate.id)
        return candidate

    def _start_check(self, search_id: int, listing_id: int) -> BroughtListing:
        """The listing to check, marked as being read so a second Check fit on it is refused
        rather than paid for twice; a listing already checked comes back as it is."""
        with self.held(search_id):
            row = self.inventory.search(search_id)
            content = json.loads(row["content"])
            entry = next(
                (e for e in content.get("listings", []) if int(e["id"]) == listing_id), None
            )
            if entry is None:
                raise NotFoundError(f"no listing {listing_id} on search {search_id}")
            listing = BroughtListing(**entry)
            if listing.candidate_id is not None:
                return listing
            checking: dict[str, str] = content.setdefault("checking", {})
            since = checking.get(str(listing_id))
            if since and datetime.now(UTC) - datetime.fromisoformat(since) < timedelta(
                seconds=CHECKING_SECONDS
            ):
                raise BusyError("Check fit is already reading this listing")
            checking[str(listing_id)] = stamp()
            self.inventory.update_search(search_id, str(row["status"]), json.dumps(content))
            return listing

    def _remember_candidate(
        self, search_id: int, listing_id: int, candidate_id: int | None
    ) -> None:
        """The candidate a listing became (None when the reading failed); either way the
        listing is no longer being read."""
        with self.held(search_id):
            row = self.inventory.search(search_id)
            content = json.loads(row["content"])
            content.get("checking", {}).pop(str(listing_id), None)
            for entry in content.get("listings", []):
                if int(entry["id"]) == listing_id and candidate_id is not None:
                    entry["candidate_id"] = candidate_id
            self.inventory.update_search(search_id, str(row["status"]), json.dumps(content))

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
