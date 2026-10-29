"""An assessment: the profile's rules applied to a need and a candidate, then the ladder."""

from app.inventory import Inventory
from app.inventory.service import current_fields
from app.match.rules import Reading, evaluate
from app.match.schema import Assessment, AssessRequest, Backing, Check, Side, Verdict
from app.profiles import Profiles, Rule


class AssessError(ValueError):
    """The request cannot be assessed as given (no profile, an unknown profile)."""


def verdict_for(checks: list[Check]) -> tuple[Verdict, str]:
    """The ladder. Rules decide; nothing moves a conflict up."""
    hard = [c for c in checks if c.hard]
    failed = [c for c in hard if c.status == "fail"]
    if failed:
        names = ", ".join(c.label.lower() for c in failed)
        return "CONFLICT", f"a hard rule fails: {names}"
    exact = [c for c in checks if c.identity and c.status == "pass"]
    if exact:
        return "EXACT_MATCH", f"same {exact[0].label.lower()}"
    passed = [c for c in hard if c.status == "pass"]
    unknown = [c for c in hard if c.status == "unknown"]
    if hard and not unknown:
        soft_failed = [c for c in checks if not c.hard and c.status == "fail"]
        tail = (
            "; a soft rule differs: " + ", ".join(c.label.lower() for c in soft_failed)
            if soft_failed
            else ""
        )
        return "COMPATIBLE_LIKELY", f"every hard rule passes ({len(passed)}){tail}"
    if passed:
        names = ", ".join(c.label.lower() for c in unknown)
        return "VISUALLY_SIMILAR", f"{len(passed)} hard rule(s) pass, still unknown: {names}"
    if not hard:
        soft = [c for c in checks if c.status != "unknown"]
        if soft and all(c.status == "pass" for c in soft):
            return "COMPATIBLE_LIKELY", "no hard rules for this profile; every known value fits"
        if any(c.status == "fail" for c in soft):
            return "VISUALLY_SIMILAR", "no hard rules for this profile; a known value differs"
    return "INSUFFICIENT_INFO", "no hard rule could be decided"


class Assessor:
    def __init__(self, profiles: Profiles, inventory: Inventory) -> None:
        self.profiles = profiles
        self.inventory = inventory

    def assess(self, request: AssessRequest) -> Assessment:
        need, need_profile = self._readings(request.need)
        cand, cand_profile = self._readings(request.candidate)
        profile_id = (
            request.need.profile or need_profile or request.candidate.profile or cand_profile
        )
        if not profile_id:
            raise AssessError("no profile: give one, or use an item that has one")
        try:
            profile = self.profiles.get(profile_id)
        except LookupError as exc:
            raise AssessError(str(exc)) from exc
        checks = [evaluate(rule, need.get(rule.key), cand.get(rule.key)) for rule in profile.rules]
        verdict, summary = verdict_for(checks)
        return Assessment(
            profile=profile.id,
            verdict=verdict,
            summary=summary,
            checks=checks,
            questions=questions_for(profile.rules, checks, cand),
            missing=[c.label for c in checks if not c.needed],
            to_confirm=[
                c.label for c in checks if c.backing is not None and c.backing.review == "proposed"
            ],
            need_item=request.need.item_id,
            candidate_item=request.candidate.item_id,
        )

    def _readings(self, side: Side) -> tuple[dict[str, Reading], str]:
        """What one side knows, keyed by rule key, and the profile it carries."""
        readings = {k: Reading(value=v) for k, v in side.values.items() if v.strip()}
        if side.item_id is None:
            return readings, ""
        item = self.inventory.get(side.item_id)
        uncertainty: dict[int, float] = {}
        for m in self.inventory.measurements(side.item_id):
            if m.assertion_id is not None and m.uncertainty_mm is not None:
                uncertainty[m.assertion_id] = m.uncertainty_mm
        # a value written in beside an item is the owner's explicit word: it wins
        for key, a in current_fields(item.assertions).items():
            if key in readings:
                continue
            readings[key] = Reading(
                value=a.value,
                unit=a.unit,
                uncertainty=uncertainty.get(a.id),
                backing=Backing(
                    provenance=a.provenance,
                    review=a.review,
                    source=a.source,
                    uncertainty=uncertainty.get(a.id),
                    at=a.at,
                ),
            )
        return readings, item.profile


def questions_for(rules: list[Rule], checks: list[Check], cand: dict[str, Reading]) -> list[str]:
    """What to ask about the candidate: one question per rule its evidence cannot answer."""
    out: list[str] = []
    by_key = {r.key: r for r in rules}
    for c in checks:
        if c.status != "unknown" or not c.needed:
            continue
        rule = by_key[c.key]
        if c.key in cand and "not precise enough" in c.basis:
            out.append(
                f"{rule.label}: a caliper or ruler reading, the photo gives"
                f" ±{cand[c.key].uncertainty:g} {rule.unit}".rstrip()
            )
        elif rule.question:
            out.append(rule.question)
    return out
