"""Best of N: the candidates' briefs, the pick, the review gate drawing several candidates, the
reviewer's facts as built, and the evaluations kept by stage."""

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.decide.schema import ReuseScenario
from app.inventory import FieldCreate, Inventory, ItemCreate
from app.inventory.schema import Item
from app.picture import best, tune
from app.picture import gate as gate_module
from app.picture.gate import PictureGate
from app.picture.review import (
    Drawing,
    Facts,
    Issue,
    Report,
    Review,
    ReviewAnswer,
    build_needs,
    card_facts,
    item_facts,
)
from app.picture.review import parse as parse_args
from app.picture.service import Pictures
from app.projects.templates import Templates
from tests.conftest import RECORDED_FIXTURES

pytestmark = pytest.mark.anyio


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        picture_enabled=True,
        log_format="text",
        _env_file=None,
    )


def review(verdict: str, confidence: float = 0.9, issues: int = 0, rid: str = "x#1") -> Review:
    return Review(
        id=rid,
        title="t",
        kind="item",
        facts=Facts(title="t"),
        verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,
        issues=[Issue(category="text", detail="d") for _ in range(issues)],
    )


# --- briefs and the pick -------------------------------------------------------------------


def test_a_candidate_brief_keeps_its_variant_whole_and_fits_the_bound() -> None:
    base = "a 24 inch monitor flat under the glass " * 20
    said = best.compose(base, "seen from above")
    assert len(said) <= best.BRIEF_MAX and said.endswith("; seen from above")
    assert best.compose("one monitor", "") == "one monitor"
    assert best.compose("", "seen from above") == "seen from above"


def test_the_candidates_differ_from_each_other_and_from_the_brief_asked_with() -> None:
    briefs = best.candidate_briefs("one monitor", "", 3, view=False)
    assert len(briefs) == 3 and len(set(briefs)) == 3
    assert "one monitor" not in briefs and all(b.startswith("one monitor; ") for b in briefs)
    corrected = best.candidate_briefs("old", "a small mirror, not a TV", 2, view=True)
    assert corrected[0] == "a small mirror, not a TV"
    assert corrected[1].endswith(best.SCENES[1])
    # with no brief at all, the variants alone
    assert best.candidate_briefs("", "", 2, view=False) == [best.FRAMINGS[1], best.FRAMINGS[2]]


def test_the_best_candidate_wins_by_verdict_then_confidence_then_fewer_issues() -> None:
    assert best.pick(review("partly"), [review("wrong"), review("matches", 0.6)]) == 1
    assert best.pick(review("matches", 0.8), [review("matches", 0.9)]) == 0
    assert best.pick(review("matches", 0.9, 1), [review("matches", 0.9, 0)]) == 0
    # a tie keeps the drawing as it stands
    assert best.pick(review("matches", 0.9), [review("matches", 0.9)]) is None
    assert best.pick(None, [review("wrong")]) == 0
    assert best.pick(review("partly"), []) is None


def test_the_targets_are_named_or_every_drawing_not_matching() -> None:
    def d(rid: str) -> Drawing:
        return Drawing(id=rid, kind="item", n=1, file="f", use="u", facts=Facts(title="t"))

    drawings = [d("item:a#1"), d("item:b#1"), d("project:2#1")]
    last = Report(
        at="now",
        source="set",
        mode="demo set",
        reviews=[review("matches", rid="item:a#1"), review("wrong", rid="item:b#1")],
    )
    assert [x.id for x in best.targets(drawings, last, [])] == ["item:b#1"]
    assert [x.id for x in best.targets(drawings, last, ["project:2"])] == ["project:2#1"]
    assert [x.id for x in best.targets(drawings, last, ["item"])] == ["item:a#1", "item:b#1"]


def test_the_report_says_what_each_candidate_scored_and_which_was_kept() -> None:
    run = best.Run(
        outcomes=[
            best.Outcome(
                id="item:a#1",
                title="A",
                before=review("wrong", 0.9, 2),
                candidates=[
                    best.Candidate(brief="b1", review=review("partly")),
                    best.Candidate(brief="b2", review=review("matches")),
                    best.Candidate(brief="b3", error="not drawn"),
                ],
                winner=1,
            )
        ],
        cost_usd=0.05,
    )
    said = best.markdown(run, 3)
    assert "# Best of 3" in said and "candidate 2" in said and "**kept**" in said
    assert "error: not drawn" in said


def test_candidates_are_a_mode_of_their_own() -> None:
    opts = parse_args(["--candidates", "3", "--only", "project:7"])
    assert not isinstance(opts, str) and opts.candidates == 3
    assert isinstance(parse_args(["--candidates", "9"]), str)
    assert isinstance(parse_args(["--candidates", "2", "--redraw-set"]), str)
    assert isinstance(parse_args(["--candidates", "2", "--dry-run"]), str)
    assert isinstance(parse_args(["--stage", "best3"]), str)
    staged = parse_args(["--evaluate", "--stage", "Best3"])
    assert not isinstance(staged, str) and staged.stage == "best3"
    assert isinstance(parse_args(["--evaluate", "--stage", "no spaces"]), str)


# --- the review gate with candidates -------------------------------------------------------


def answer(verdict: str, *cats: str, confidence: float = 0.9) -> ReviewAnswer:
    return ReviewAnswer(
        verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,
        issues=[Issue(category=c, detail=f"{c} found") for c in cats],  # type: ignore[arg-type]
        brief="a computer monitor, not a TV" if verdict != "matches" else "",
        summary="a drawing",
    )


def monitor(settings: Settings) -> Item:
    inventory = Inventory(settings)
    item = inventory.create(ItemCreate(name="Dell 1800FP monitor, 18 inch", item_type="monitor"))
    inventory.add_field(
        item.id,
        FieldCreate(field="condition_notes", value="dusty", unit="", provenance="tested"),
    )
    return inventory.get(item.id)


async def gated(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[ReviewAnswer],
    candidates: int,
    cap: float = 10.0,
) -> tuple[Pictures, int, list[str]]:
    from app.model_api import CostLedger, ModelApiClient

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    on = settings.model_copy(update={"picture_review_gate": True, "picture_candidates": candidates})
    inventory = Inventory(on)
    item_id = monitor(on).id
    client = ModelApiClient(on, CostLedger(cap))
    pictures = Pictures(on, client, inventory, Templates())
    asked: list[str] = []
    real = client.picture

    async def picture(prompt: str, *, op: str = "picture") -> Any:
        asked.append(prompt)
        return await real(prompt, op=op)

    client.picture = picture  # type: ignore[method-assign]
    queue = list(answers)

    async def check(*_: Any, **__: Any) -> tuple[ReviewAnswer, float]:
        return queue.pop(0), 0.008

    monkeypatch.setattr(gate_module, "review_one", check)
    return pictures, item_id, asked


async def test_the_gate_draws_the_candidates_asked_for_and_shows_the_best(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pictures, item_id, asked = await gated(
        settings,
        monkeypatch,
        [
            answer("wrong", "wrong_device"),
            answer("partly", "scale"),
            answer("matches", confidence=0.95),
            answer("matches", confidence=0.7),
        ],
        candidates=3,
    )
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    await pictures.client.aclose()
    assert len(asked) == 4 and len(set(asked[1:])) == 3
    assert shown.n == 3 and shown.check is not None and shown.check.redraw_of == 1
    kept = pictures.list(item_id).pictures
    assert [(p.n, p.hidden) for p in kept] == [(1, True), (2, True), (3, False), (4, True)]


async def test_one_candidate_is_the_single_redraw_it_was(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pictures, item_id, asked = await gated(
        settings, monkeypatch, [answer("wrong", "scale"), answer("matches")], candidates=1
    )
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    await pictures.client.aclose()
    assert len(asked) == 2 and asked[1].count("a computer monitor, not a TV") == 1
    assert shown.n == 2


async def test_the_gate_stops_drawing_candidates_at_the_spend_cap(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pictures, item_id, asked = await gated(
        settings,
        monkeypatch,
        [answer("wrong", "scale"), answer("partly", "scale"), answer("matches")],
        candidates=3,
        cap=0.0,
    )
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    await pictures.client.aclose()
    # the first corrected drawing is the gate's own; the next would pass the cap
    assert len(asked) == 2 and shown.n == 2


async def test_a_judges_code_draws_one_corrected_candidate(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pictures, item_id, asked = await gated(
        settings,
        monkeypatch,
        [answer("wrong", "scale"), answer("partly", "scale"), answer("matches")],
        candidates=3,
    )
    # the request is a judge's code (its inventory scoping is tested in test_judge)
    monkeypatch.setattr(gate_module, "sandbox", lambda: 7)
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    await pictures.client.aclose()
    # the first drawing and one corrected candidate, whatever PICTURE_CANDIDATES says
    assert len(asked) == 2 and shown.n == 2


# --- the reviewer's facts, as built --------------------------------------------------------


def test_an_item_drawn_as_a_use_is_described_as_built_with_the_rest_of_its_build(
    settings: Settings,
) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    item = monitor(settings)
    facts = item_facts(
        item,
        "a smart mirror on the hall wall",
        "asked",
        subject="smart_mirror",
        templates=Templates(),
    )
    assert "dusty" not in " ".join(facts.parts)
    assert facts.build_needs and any("mirror" in n.lower() for n in facts.build_needs)
    assert "may appear" in facts.text()
    own = item_facts(item, "monitor", "asked", subject="", templates=Templates())
    assert own.build_needs == []


def test_a_card_lists_its_other_items_extra_parts_and_build(
    settings: Settings,
) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    item = monitor(settings)
    reuse = ReuseScenario.model_construct(
        title="Smart mirror",
        what_it_does="shows the time",
        with_items=["laptop"],
        extra_parts=["two-way film (~$15)"],
    )
    facts = card_facts(item, reuse, "asked", subject="smart_mirror", templates=Templates())
    assert facts.parts[1] == "another item: laptop"
    assert facts.still_to_get == ["two-way film (~$15)"]
    assert facts.build_needs
    assert build_needs("no_such_template", [item], Templates()) == []
    assert build_needs("smart_mirror", [item], None) == []


# --- evaluations by stage ------------------------------------------------------------------


def evaluation(version: int, stage: str, at: str, matches: int) -> tune.Evaluation:
    return tune.Evaluation(
        params_version=version,
        stage=stage,
        at=at,
        report_at=at,
        reviewer="muse-spark",
        image_model="muse-image",
        drawings=matches,
        verdicts={"matches": matches},
        categories={},
        by_kind={},
        review_usd=0.1,
        scored=[],
        params={},
    )


def test_a_later_stage_of_a_version_is_kept_beside_its_first_score(tmp_path: Path) -> None:
    for e in (
        evaluation(3, "best3", "2026-11-04T06:00:00+00:00", 25),
        evaluation(3, "", "2026-11-03T06:00:00+00:00", 21),
        evaluation(3, "asbuilt", "2026-11-04T04:00:00+00:00", 19),
        evaluation(2, "", "2026-11-02T06:00:00+00:00", 20),
    ):
        tune.eval_path(tmp_path, e.params_version, e.stage).write_text(tune.dumps(e), "utf-8")
    assert tune.eval_path(tmp_path, 3, "best3").name == "params-v3-best3.json"
    evals = tune.history(tmp_path)
    assert [tune.label(e) for e in evals] == [
        "params v2",
        "params v3",
        "params v3 asbuilt",
        "params v3 best3",
    ]
    assert "| params v3 best3 |" in tune.table(evals)
