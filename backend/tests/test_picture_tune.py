"""The drawing parameters and their tuning: the file read and validated, the prompt builder
saying sizes first and leaving lettering and condition out, the review gate, the aggregation
of a review into proposed edits, the edits applied with the version one up, and each version
scored and compared."""

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.inventory import FieldCreate, Inventory, ItemCreate
from app.inventory.schema import Item
from app.model_api.client import IMAGES, picture_body
from app.model_api.fixtures import request_key
from app.picture import gate as gate_module
from app.picture import params as params_module
from app.picture import tune
from app.picture.gate import PictureGate, needs_redraw, second_is_better
from app.picture.params import (
    PARAMS_FILE,
    ClosingRules,
    DrawingParams,
    ParamsError,
    dump,
    name_sizes,
    parse,
)
from app.picture.review import Facts, Issue, Options, Report, Review, ReviewAnswer
from app.picture.review import parse as parse_args
from app.picture.service import PictureCheck, Pictures, finished_prompt, part_of, prompt_for
from app.projects.templates import Templates
from tests.conftest import RECORDED_FIXTURES, V1_TAIL, params_v1_text

pytestmark = pytest.mark.anyio

V2 = """\
version: 2
facts:
  part_values: 6
  first: [size]
  left_out: [brand, model, part number, certification, condition, fault, voltage]
  from_name: true
  condition: false
kinds:
  Monitor:
    looks: a computer monitor, far smaller than a television
    size: screen size
projects:
  smart_mirror:
    match: [smart mirror]
    correction: a framed two-way mirror at eye level, the display behind the glass; never a TV
views:
  from above: seen straight down from above
negatives: [no lettering on any part]
rules:
  item: on a plain background, no people
  use: finished and in use in a home, no people
  card: finished and in use in a home, no people
  project: finished and in use in a home, no people
"""


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


def monitor(settings: Settings, **extra: str) -> Item:
    inventory = Inventory(settings)
    item = inventory.create(
        ItemCreate(
            name="Dell 1800FP monitor, 18 inch",
            item_type="monitor",
            condition=extra.get("condition", ""),
        )
    )
    for field, value, unit in (
        ("brand", "DELL", ""),
        ("model_number", "1800FP", ""),
        ("input_voltage", "100-240", "V"),
        ("certifications", "FCC, CE", ""),
        ("condition_notes", "dusty housing, label blacked out", ""),
        ("aspect_ratio", "5:4", ""),
        ("serial_number", "CN0ABC", ""),
    ):
        inventory.add_field(
            item.id, FieldCreate(field=field, value=value, unit=unit, provenance="tested")
        )
    return inventory.get(item.id)


# --- the file ------------------------------------------------------------------------------


def test_the_shipped_parameters_read_and_round_trip() -> None:
    params = params_module.load(PARAMS_FILE)
    assert params.version >= 2
    assert parse(dump(params)) == params
    assert PARAMS_FILE.read_text(encoding="utf-8") == dump(params)


def test_the_parameters_are_validated() -> None:
    with pytest.raises(ParamsError, match="not YAML"):
        parse("version: [1")
    with pytest.raises(ParamsError, match="a map"):
        parse("- 1")
    with pytest.raises(ParamsError, match="version"):
        parse(V2.replace("version: 2", "version: 0"))
    with pytest.raises(ParamsError, match=r"(?i)extra"):
        parse(V2 + "color: red\n")
    with pytest.raises(ParamsError):
        parse(V2.replace("part_values: 6", "part_values: 99"))
    long = "x" * 500
    with pytest.raises(ParamsError):
        parse(V2.replace("correction: a framed", f"correction: {long} a framed"))
    params = parse(V2)
    # keys and words lower case, negatives once each
    assert params.kind("MONITOR") is not None
    assert parse(V2.replace("[no lettering on any part]", "[a, A]")).negatives == ["a"]


def test_the_parameters_are_read_again_when_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "params.yaml"
    path.write_text(V2, encoding="utf-8")
    assert params_module.load(path).version == 2
    import os

    path.write_text(V2.replace("version: 2", "version: 3"), encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 5))
    assert params_module.load(path).version == 3


def test_sizes_are_read_from_the_name_and_nothing_else() -> None:
    params = parse(V2)
    assert name_sizes("Dell 1800FP monitor, 18 inch", "monitor", params) == [
        "screen size 18 inch, about 46 cm across the diagonal"
    ]
    assert name_sizes("Kingston A400 480 GB SSD", "SSD", params) == ["size 480 GB"]
    assert name_sizes("Toshiba 2.5 inch hard drive", "hard drive", params) == ["size 2.5 inch"]
    assert name_sizes("ThinkPad T510", "laptop", params) == []
    assert name_sizes("in a case", "board", params) == []
    v1 = parse(params_v1_text())
    assert name_sizes("Dell 1800FP monitor, 18 inch", "monitor", v1) == []


# --- the prompt ----------------------------------------------------------------------------


def test_the_request_says_the_size_first_and_leaves_lettering_and_condition_out(
    settings: Settings,
) -> None:
    params = parse(V2)
    item = monitor(settings, condition="still in its plastic wrap")
    prompt = prompt_for(item, "a smart mirror on a hall wall", params=params)
    assert "monitor (screen size 18 inch, about 46 cm across the diagonal, aspect ratio 5:4" in (
        prompt
    )
    for gone in ("DELL", "1800FP", "FCC", "dusty", "plastic wrap", "100-240", "CN0ABC"):
        assert gone not in prompt
    assert "far smaller than a television" in prompt
    # the kind of project the use names carries its correction, before the negatives and rules
    assert prompt.index("never a TV") < prompt.index("no lettering") < prompt.index("in a home")
    assert prompt.endswith("finished and in use in a home, no people")
    # the item as itself keeps its plain background
    assert prompt_for(item, "", params=params).endswith("on a plain background, no people")


def test_a_part_carries_every_size_fact_not_three_alphabetical(settings: Settings) -> None:
    item = monitor(settings)
    v1 = parse(params_v1_text())
    # version 1: the first three values, by name: the size is never reached
    assert part_of(item, as_built=True, params=v1) == (
        "monitor (aspect ratio 5:4, brand DELL, input voltage 100-240 V)"
    )
    said = part_of(item, as_built=True, params=parse(V2))
    assert said.startswith("monitor (screen size 18 inch, about 46 cm across the diagonal")
    assert "DELL" not in said


def test_a_view_adds_its_preset_and_a_brief_said_twice_is_said_once() -> None:
    params = parse(V2)
    prompt = finished_prompt(
        "Arcade table",
        ["monitor"],
        "a table",
        "from above, as it is used",
        "in a home",
        "glass top",
        correction="glass top",
        params=params,
    )
    assert "; shown from above, as it is used; seen straight down from above; glass top;" in (
        prompt
    )
    assert prompt.count("glass top") == 1


def test_version_one_asks_exactly_what_the_builder_asked_before(settings: Settings) -> None:
    item = monitor(settings, condition="scuffed")
    v1 = parse(params_v1_text())
    prompt = prompt_for(item, "a smart mirror", "slim frame", params=v1)
    assert prompt == (
        "a semi-realistic illustration of a smart mirror built from monitor (aspect ratio 5:4,"
        " brand DELL, certifications FCC, CE, condition notes dusty housing, label blacked out,"
        " input voltage 100-240 V, model number 1800FP); condition: scuffed; slim frame, " + V1_TAIL
    )


# --- the gate ------------------------------------------------------------------------------


def answer(verdict: str, *cats: str, brief: str = "a computer monitor, not a TV") -> ReviewAnswer:
    return ReviewAnswer(
        verdict=verdict,  # type: ignore[arg-type]
        confidence=0.9,
        issues=[Issue(category=c, detail=f"{c} found") for c in cats],  # type: ignore[arg-type]
        brief=brief if verdict != "matches" else "",
        summary="a drawing",
    )


def test_a_drawing_is_drawn_again_only_when_it_misleads() -> None:
    assert needs_redraw(answer("wrong", "missing_part"))
    assert needs_redraw(answer("partly", "text", "scale"))
    assert needs_redraw(answer("partly", "wrong_device"))
    assert not needs_redraw(answer("partly", "text"))
    assert not needs_redraw(answer("matches"))
    assert not needs_redraw(answer("wrong", "scale", brief=" "))


def test_the_better_drawing_is_shown() -> None:
    def check(verdict: str, issues: int = 0) -> PictureCheck:
        return PictureCheck(verdict=verdict, issues=["x"] * issues)

    assert second_is_better(check("wrong"), check("partly"))
    assert not second_is_better(check("partly"), check("wrong"))
    assert second_is_better(check("partly", 2), check("partly", 2))
    assert not second_is_better(check("partly", 1), check("partly", 2))
    assert not second_is_better(check("partly"), None)
    assert second_is_better(None, check("wrong"))


def test_the_gate_is_on_for_live_calls_and_off_in_fixture_mode(settings: Settings) -> None:
    assert not settings.picture_gate_on
    assert settings.model_copy(update={"picture_review_gate": True}).picture_gate_on
    live = settings.model_copy(update={"fake_api": False})
    assert live.picture_gate_on
    assert not live.model_copy(update={"picture_review_gate": False}).picture_gate_on


async def gated(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, answers: list[ReviewAnswer]
) -> tuple[Pictures, int, list[str]]:
    from app.model_api import CostLedger, ModelApiClient

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    on = settings.model_copy(update={"picture_review_gate": True})
    inventory = Inventory(on)
    item_id = monitor(on).id
    client = ModelApiClient(on, CostLedger(10.0))
    pictures = Pictures(on, client, inventory, Templates())
    asked: list[str] = []
    real = client.picture

    async def picture(prompt: str, *, op: str = "picture") -> Any:
        asked.append(prompt)
        return await real(prompt, op=op)

    client.picture = picture  # type: ignore[method-assign]
    queue = list(answers)

    async def review(*_: Any, **__: Any) -> tuple[ReviewAnswer, float]:
        return queue.pop(0), 0.008

    monkeypatch.setattr(gate_module, "review_one", review)
    return pictures, item_id, asked


async def test_the_gate_redraws_a_wrong_drawing_once_and_shows_the_better(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pictures, item_id, asked = await gated(
        settings, monkeypatch, [answer("wrong", "wrong_device"), answer("matches")]
    )
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    await pictures.client.aclose()
    assert len(asked) == 2 and "a computer monitor, not a TV" in asked[1]
    assert shown.n == 2 and shown.check is not None and shown.check.verdict == "matches"
    assert shown.check.redraw_of == 1
    kept = pictures.list(item_id).pictures
    assert [(p.n, p.hidden, p.check.verdict if p.check else "") for p in kept] == [
        (1, True, "wrong"),
        (2, False, "matches"),
    ]


async def test_the_gate_keeps_the_first_when_the_redraw_is_worse_and_stops_on_a_match(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pictures, item_id, _ = await gated(
        settings, monkeypatch, [answer("partly", "scale"), answer("wrong", "scale", "text")]
    )
    shown = await PictureGate(pictures).item(item_id, "a smart mirror")
    assert shown.n == 1 and [p.hidden for p in pictures.list(item_id).pictures] == [False, True]
    pictures2, item2, asked2 = await gated(settings, monkeypatch, [answer("matches")])
    first = await PictureGate(pictures2).item(item2, "a smart mirror")
    await pictures.client.aclose()
    await pictures2.client.aclose()
    assert len(asked2) == 1 and first.check is not None and first.check.cost_usd == 0.008


async def test_the_gate_is_skipped_when_off(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pictures, item_id, asked = await gated(settings, monkeypatch, [answer("wrong", "scale")])
    pictures.settings = pictures.settings.model_copy(update={"picture_review_gate": False})
    gate = PictureGate(pictures)
    shown = await gate.item(item_id, "a smart mirror")
    await pictures.client.aclose()
    assert len(asked) == 1 and shown.check is None


# --- the tuning ----------------------------------------------------------------------------


def review(
    rid: str,
    verdict: str,
    *cats: str,
    subject: str = "",
    kinds: tuple[str, ...] = (),
    asked: str = "",
    view: str = "",
    brief: str = "",
) -> Review:
    kind = rid.split(":")[0]
    return Review(
        id=rid,
        title=rid,
        kind=kind,  # type: ignore[arg-type]
        subject=subject,
        kinds=list(kinds),
        facts=Facts(title=rid, view=view, asked=asked),
        verdict=verdict,  # type: ignore[arg-type]
        issues=[Issue(category=c, detail=f"{c} here") for c in cats],  # type: ignore[arg-type]
        brief=brief,
    )


def a_report() -> Report:
    lettered = "a mirror built from monitor (brand DELL, model number 1800FP), no text"
    return Report(
        at="2026-11-03T00:00:00+00:00",
        source="demo/set.yaml",
        mode="demo set",
        model="muse-spark-1.3",
        params_version=1,
        cost_usd=0.02,
        reviews=[
            review(
                "project:2#1",
                "wrong",
                "scale",
                "text",
                subject="smart_mirror",
                kinds=("monitor",),
                asked=lettered,
                brief="a small framed mirror, not a TV",
            ),
            review(
                "project:7#3",
                "partly",
                "text",
                subject="arcade_table",
                kinds=("monitor", "laptop"),
                asked=lettered.replace("a mirror", "a table"),
                view="from above, as it is used",
            ),
            review(
                "item:monitor#1",
                "partly",
                "missing_part",
                kinds=("monitor",),
                asked="a kitchen screen built from monitor (condition notes dusty)",
            ),
            review("item:board#1", "matches", kinds=("motherboard",)),
            review("card:board#1", "error"),
        ],
    )


def test_a_review_is_counted_by_category_kind_and_subject() -> None:
    agg = tune.aggregate(a_report(), 1)
    assert agg.drawings == 4
    assert agg.verdicts == {"matches": 1, "partly": 2, "wrong": 1}
    assert agg.categories == {"missing_part": 1, "scale": 1, "text": 2}
    assert agg.by_kind["project"] == {"partly": 1, "wrong": 1}
    assert agg.subjects["smart_mirror"].briefs == ["a small framed mirror, not a TV"]
    assert set(agg.subjects) == {"smart_mirror", "arcade_table", "kind:monitor", "kind:motherboard"}
    assert agg.lettered_requests == ["project:2#1", "project:7#3"]
    assert agg.condition_requests == ["item:monitor#1"]
    assert agg.size_kinds == {"monitor": ["project:2#1"]}
    assert agg.setting_issues == ["item:monitor#1"]


def test_the_rules_propose_what_the_counts_call_for() -> None:
    v1 = parse(params_v1_text())
    agg = tune.aggregate(a_report(), 1)
    edits = {(e.path, str(e.value)) for e in tune.rule_edits(agg, v1)}
    paths = [p for p, _ in edits]
    assert ("facts.condition", "False") in edits and ("facts.from_name", "True") in edits
    assert "negatives" in paths and "kinds.monitor.size" in paths
    assert "rules.use" in paths and "rules.card" in paths
    assert "views.from above" not in paths  # the view's issues were lettering only
    left = [e for e in tune.rule_edits(agg, v1) if e.path == "facts.left_out"]
    assert "brand" in left[0].value and "condition" in left[1].value
    # nothing left to propose once they are in
    applied = tune.apply_edits(v1, tune.rule_edits(agg, v1))
    assert tune.rule_edits(agg, applied) == []


def test_the_corrections_come_from_the_phrasing_else_the_shortest_brief() -> None:
    v1 = parse(params_v1_text())
    agg = tune.aggregate(a_report(), 1)
    labels = {"smart_mirror": "Smart mirror", "arcade_table": "Arcade coffee table"}
    plain = tune.correction_edits(agg, v1, None, labels)
    assert [(e.path, e.value["correction"]) for e in plain] == [
        ("projects.smart_mirror", "a small framed mirror, not a TV")
    ]
    assert plain[0].value["match"] == ["smart mirror"]
    phrased = tune.Phrased(
        corrections=[tune.Phrased.Correction(subject="smart_mirror", text="a 46 cm mirror")],
        looks=[tune.Phrased.Looks(kind="monitor", text="a computer monitor, not a TV")],
    )
    said = {e.path: e.value for e in tune.correction_edits(agg, v1, phrased, labels)}
    assert said["projects.smart_mirror"]["correction"] == "a 46 cm mirror"
    assert said["kinds.monitor.looks"] == "a computer monitor, not a TV"
    assert "Subject: smart_mirror (Smart mirror)" in tune.phrase_input(agg, v1, labels)


def test_an_approved_set_correction_becomes_its_kind_of_project() -> None:
    v1 = parse(params_v1_text())
    agg = tune.aggregate(a_report(), 1)
    labels = {"smart_mirror": "Smart mirror", "home_server": "Home server and backup"}
    approved = {
        "home_server": "an opened laptop on a desk",
        "smart_mirror": "a framed mirror",
        "arcade_table / from above": "seen from above",
    }
    edits = tune.promoted_edits(agg, v1, approved, labels, {"smart_mirror"})
    assert [(e.path, e.value["correction"]) for e in edits] == [
        ("projects.home_server", "an opened laptop on a desk")
    ]


def test_applying_bumps_the_version_and_writes_a_valid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "params.yaml"
    path.write_text(params_v1_text(), encoding="utf-8")
    v1 = parse(params_v1_text())
    agg = tune.aggregate(a_report(), 1)
    edits = tune.rule_edits(agg, v1) + tune.correction_edits(agg, v1, None, {})
    proposal = tune.Proposal(
        at="now", from_version=1, to_version=2, report_at=agg.report_at, edits=edits, aggregate=agg
    )
    md = tune.proposal_markdown(proposal, v1)
    assert "version 1 to 2" in md and "+version: 2" in md and "`facts.condition`" in md
    saved = tmp_path / "tune.json"
    saved.write_text(tune.dumps(proposal), encoding="utf-8")
    new = tune.apply_proposal(saved, path)
    assert new.version == 2 and not new.facts.condition and new.facts.from_name
    assert params_module.load(path) == new
    assert new.projects["smart_mirror"].correction == "a small framed mirror, not a TV"
    with pytest.raises(ValueError, match="version 1, the file is at 2"):
        tune.apply_proposal(saved, path)


def test_each_version_is_scored_compared_and_its_unused_recordings_listed(
    tmp_path: Path,
) -> None:
    v1 = parse(params_v1_text())
    v2 = v1.model_copy(update={"version": 2})
    first = tune.evaluation(a_report(), v1, "muse-image-1.0")
    better = a_report()
    better.reviews[0].verdict = "matches"
    better.reviews[0].issues = []
    better.reviews[0].facts.asked = "a mirror, no lettering"
    second = tune.evaluation(better, v2, "muse-image-1.0")
    assert first.scored[0].recording == request_key(
        IMAGES, picture_body("muse-image-1.0", a_report().reviews[0].facts.asked)
    )
    folder = tmp_path / "eval"
    folder.mkdir()
    for ev in (second, first):
        tune.eval_path(folder, ev.params_version).write_text(tune.dumps(ev), encoding="utf-8")
    evals = tune.history(folder)
    assert [e.params_version for e in evals] == [1, 2]
    table = tune.table(evals)
    assert "| | params v1 | params v2 |" in table and "| wrong | 1 | 0 |" in table
    assert tune.changes(first, second) == ["`project:2#1`: wrong to matches"]
    page = tmp_path / "results.md"
    page.write_text(f"# Results\n\n{tune.START}\nold\n{tune.END}\n\nafter\n", encoding="utf-8")
    assert tune.write_history(page, evals)
    text = page.read_text(encoding="utf-8")
    assert "old" not in text and "wrong to matches" in text and text.endswith("after\n")
    assert not tune.write_history(tmp_path / "none.md", evals)
    unused = tune.unused_recordings(first, second)
    assert unused == [first.scored[0].recording]
    fixtures = tmp_path / "fixtures"
    images = fixtures / "images-generations"
    images.mkdir(parents=True)
    for name in (f"{unused[0]}.json", f"{unused[0]}-1.jpg", "keep.json"):
        (images / name).write_text("x", encoding="utf-8")
    removed = tune.prune(fixtures, [*unused, "../keep"])
    assert sorted(p.name for p in removed) == [f"{unused[0]}-1.jpg", f"{unused[0]}.json"]
    assert (images / "keep.json").is_file()


def test_the_command_line_takes_the_tuning_steps_one_at_a_time() -> None:
    opts = parse_args(["--tune", "--apply"])
    assert isinstance(opts, Options) and opts.tune and opts.apply
    opts = parse_args(["--evaluate", "--prune", "--eval-dir", "e", "--results", "r.md"])
    assert isinstance(opts, Options) and opts.prune and opts.eval_dir == Path("e")
    assert parse_args(["--apply"]) == "--apply goes with --tune"
    assert parse_args(["--prune"]) == "--prune goes with --evaluate"
    assert "one at a time" in str(parse_args(["--tune", "--evaluate"]))
    assert "no dry run" in str(parse_args(["--redraw-set", "--dry-run"]))
    assert "demo set" in str(parse_args(["--tune", "--data"]))


def test_closing_rules_are_required() -> None:
    with pytest.raises(ParamsError, match="rules"):
        parse("version: 2\n")
    assert (
        DrawingParams(
            version=1, rules=ClosingRules(item="a", use="b", card="c", project="d")
        ).facts.part_values
        == 3
    )


def test_a_whole_redraw_keeps_room_for_a_review_of_each_drawing(tmp_path: Path) -> None:
    from app.picture.review import SET_DRAWINGS, set_size

    assert set_size(tmp_path) == SET_DRAWINGS
    (tmp_path / "report.json").write_text(a_report().model_dump_json(), encoding="utf-8")
    assert set_size(tmp_path) == 5
