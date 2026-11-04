"""The text parameters: the file read and validated, the instructions and briefs they change
(and leave word for word when empty), and their tuning from the recommendation checks: rule
edits, phrased edits, apply, evaluate, the history table and the pruning of unused recordings."""

from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.decide.service import INSTRUCTIONS, SCENARIOS_INSTRUCTIONS, brief, scenarios_brief
from app.inventory.schema import Item
from app.model_api import CostLedger, NoRecordingError
from app.model_api.client import IMAGES
from app.model_api.fixtures import FixtureStore, request_key
from app.picture.review import DecideReview, Flag
from app.projects.schema import Preferences
from app.projects.service import INSTRUCTIONS as PROPOSE_INSTRUCTIONS
from app.projects.service import propose_instructions
from app.textparams import (
    TEXT_PARAMS_FILE,
    TextParams,
    TextSection,
    attrs_line,
    dump,
    load,
    parse,
)
from app.textparams import tune as tt

pytestmark = pytest.mark.anyio


# --- the file ------------------------------------------------------------------------------


def test_the_shipped_file_reads_and_round_trips(tmp_path: Path) -> None:
    params = load()
    assert params.version >= 1
    copy = tmp_path / "params.yaml"
    copy.write_text(TEXT_PARAMS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    dump(params, copy)
    assert load(copy) == params
    assert copy.read_text(encoding="utf-8").startswith("# The text parameters")


def test_the_file_is_validated() -> None:
    with pytest.raises(ValueError):
        parse(["not a mapping"])
    with pytest.raises(ValueError):
        parse({"version": 0})
    with pytest.raises(ValueError):
        parse({"version": 1, "scenarios": {"tone": "warm"}})
    with pytest.raises(ValueError):
        TextSection(corrections=["x" * 400])
    with pytest.raises(ValueError):
        TextSection(banned=[f"phrase {n}" for n in range(20)])
    assert TextSection(banned=[" a  b ", "a b", ""]).banned == ["a b"]


def test_an_empty_section_leaves_the_instructions_word_for_word() -> None:
    v1 = TextParams(version=1)
    assert v1.scenarios.instructions(SCENARIOS_INSTRUCTIONS) == SCENARIOS_INSTRUCTIONS
    assert v1.uses.instructions(INSTRUCTIONS) == INSTRUCTIONS


def test_a_section_adds_its_rules_corrections_and_banned_phrases() -> None:
    section = TextSection(
        constraints=["rest only on owned items"],
        corrections=["say the memory generation."],
        banned=["with the processor you own"],
    )
    said = section.instructions("Base.")
    assert said.startswith("Base. Also: rest only on owned items.")
    assert "Mistakes to avoid, found in earlier answers: say the memory generation." in said
    assert said.endswith('Never write these phrases or their like: "with the processor you own".')


def test_the_proposals_read_their_section(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import app.projects.service as projects

    path = tmp_path / "params.yaml"
    dump(TextParams(version=1), path)
    monkeypatch.setattr(projects, "load_text_params", lambda: load(path))
    assert propose_instructions(PROPOSE_INSTRUCTIONS) == PROPOSE_INSTRUCTIONS
    dump(TextParams(version=2, propose=TextSection(facts_first=True, banned=["x y"])), path)
    said = propose_instructions(PROPOSE_INSTRUCTIONS)
    assert said.startswith(PROPOSE_INSTRUCTIONS + projects.FACTS_FIRST) and '"x y"' in said


def test_the_compatibility_facts_are_one_line() -> None:
    assert attrs_line({"socket": "LGA1155", "memory": ["DDR3", "DIMM"], "x": None, "d": {}}) == (
        "socket LGA1155; memory DDR3, DIMM"
    )


def item() -> Item:
    return Item.model_construct(
        id=1,
        name="ASUS P8Z77-V LX",
        item_type="motherboard",
        condition="",
        faults="",
        tests_done="",
        accessories="",
        intent="build",
    )


def test_facts_first_lead_the_brief_and_move_the_pairings_up() -> None:
    prefs = Preferences()
    fits = ["fail: Slot 1 processor with ASUS: another socket"]
    plain = scenarios_brief(item(), {}, prefs, profiled=False, others=[], fits=fits)
    led = scenarios_brief(
        item(), {}, prefs, profiled=False, others=[], fits=fits, facts="socket LGA1155"
    )
    assert "compatibility facts" not in plain
    assert led.splitlines()[2] == "compatibility facts: socket LGA1155"
    assert led.index("compatibility rules") < led.index("Profile:")
    assert plain.index("compatibility rules") > plain.index("Profile:")
    uses = brief(item(), {}, prefs, [], fits, facts="")
    assert "compatibility facts: (none read)" in uses
    assert uses.index("compatibility rules") < uses.index("interests:")


# --- tuning --------------------------------------------------------------------------------


def report(*checks: DecideReview, version: int = 1) -> tt.Report:
    return tt.Report(
        at="2026-11-04T04:00:00+00:00",
        source="set",
        mode="demo set",
        model="muse-spark",
        params_version=version,
        decide=list(checks),
        cost_usd=0.4,
        used={"responses": ["a" * 24, "b" * 24], "images-generations": ["c" * 24]},
    )


def flag(claim: str, fact: str, severity: str = "major") -> Flag:
    return Flag(where="reuse card 0", claim=claim, fact=fact, severity=severity)  # type: ignore[arg-type]


CHECKS = (
    DecideReview(
        id="cards:ram",
        title="t",
        flags=[flag("with the processor you own", "no owned processor fits the LGA1155 socket")],
    ),
    DecideReview(id="cards:pcb", title="t", flags=[flag("works as it is", "a bare PCB")]),
    DecideReview(id="ideas:uno", title="t", sound=True),
    DecideReview(
        id="project:3", title="t", flags=[flag("fits the DDR3 laptop", "8 GB per slot", "minor")]
    ),
)


def test_the_rules_propose_facts_first_and_the_owned_and_condition_lines() -> None:
    edits = tt.rule_edits(report(*CHECKS), TextParams(version=1))
    by = {(e.section, e.field): e for e in edits}
    assert by[("scenarios", "facts_first")].value is True
    lines = by[("scenarios", "constraints")].value
    assert isinstance(lines, list) and tt.OWN_CONSTRAINT in lines
    assert tt.CONDITION_CONSTRAINT in lines
    assert ("propose", "facts_first") in by
    # what a section already has is not proposed again
    have = TextParams(
        version=1,
        scenarios=TextSection(
            facts_first=True, constraints=[tt.OWN_CONSTRAINT, tt.CONDITION_CONSTRAINT]
        ),
    )
    assert not [e for e in tt.rule_edits(report(*CHECKS), have) if e.section == "scenarios"]


def test_the_phrasing_input_lists_each_flagged_section() -> None:
    text = tt.phrase_input(report(*CHECKS), TextParams(version=1))
    assert "Section: scenarios" in text and "Section: propose" in text
    assert "Section: uses" not in text
    assert tt.phrase_input(report(CHECKS[2]), TextParams(version=1)) == ""


def test_phrased_edits_keep_only_flagged_sections_and_short_lines() -> None:
    phrased = tt.Phrased(
        sections=[
            tt.Sentences(
                section="scenarios",
                corrections=["Say when no owned processor fits the board.", "x" * 300],
                banned=["with the processor you own", "a"],
            ),
            tt.Sentences(section="uses", corrections=["never flagged"], banned=[]),
        ]
    )
    edits = tt.phrased_edits(phrased, report(*CHECKS))
    assert [(e.section, e.field) for e in edits] == [
        ("scenarios", "corrections"),
        ("scenarios", "banned"),
    ]
    assert edits[0].value == ["Say when no owned processor fits the board."]
    assert edits[1].value == ["with the processor you own"]
    assert tt.phrased_edits(None, report(*CHECKS)) == []


def test_applying_bumps_the_version_and_merges_the_lines(tmp_path: Path) -> None:
    path = tmp_path / "params.yaml"
    dump(TextParams(version=1, scenarios=TextSection(banned=["a b"])), path)
    proposal = tt.Proposal(
        at="now",
        from_version=1,
        to_version=2,
        report_at="then",
        edits=[
            tt.Edit(section="scenarios", field="facts_first", value=True, why="w"),
            tt.Edit(section="scenarios", field="banned", value=["a b", "c d"], why="w"),
        ],
    )
    saved = tmp_path / "tune.json"
    saved.write_text(proposal.model_dump_json(), encoding="utf-8")
    new = tt.apply_proposal(saved, path)
    assert new.version == 2 and load(path) == new
    assert new.scenarios.facts_first and new.scenarios.banned == ["a b", "c d"]
    with pytest.raises(ValueError):
        tt.apply_proposal(saved, path)
    assert "| scenarios | banned | a b / c d | w |" in tt.proposal_markdown(proposal)


def test_an_evaluation_counts_by_section_and_the_history_is_a_table(tmp_path: Path) -> None:
    ev = tt.evaluation(report(*CHECKS), TextParams(version=1))
    assert (ev.checked, ev.flagged, ev.flags, ev.major) == (4, 3, 3, 2)
    assert ev.by_section["scenarios"] == {"checked": 2, "flagged": 2, "flags": 2}
    tt.eval_path(tmp_path, 1).write_text(ev.model_dump_json(), encoding="utf-8")
    later = tt.evaluation(report(CHECKS[0], CHECKS[2], version=2), TextParams(version=2))
    later.used = {"responses": ["a" * 24]}
    tt.eval_path(tmp_path, 2).write_text(later.model_dump_json(), encoding="utf-8")
    evals = tt.history(tmp_path)
    table = tt.table(evals)
    assert "| text v1 | text v2 |" in table and "| with flags | 3 | 1 |" in table
    assert "| cards with flags | 2/2 | 1/1 |" in table
    page = tmp_path / "results.md"
    page.write_text(f"# Results\n\n{tt.START}\nold\n{tt.END}\n\nafter\n", encoding="utf-8")
    assert tt.write_history(page, evals)
    text = page.read_text(encoding="utf-8")
    assert "old" not in text and "| text v1 | text v2 |" in text and text.endswith("after\n")
    assert not tt.write_history(tmp_path / "missing.md", evals)
    assert tt.unused(evals[0], evals[1]) == {
        "responses": ["b" * 24],
        "images-generations": ["c" * 24],
    }


def test_pruning_deletes_only_the_unused_recordings_and_their_images(tmp_path: Path) -> None:
    folder = tmp_path / "images-generations"
    folder.mkdir()
    for name in (f"{'c' * 24}.json", f"{'c' * 24}-1.jpg", f"{'d' * 24}.json", "picture.json"):
        (folder / name).write_text("{}", encoding="utf-8")
    removed = tt.prune(tmp_path, {"images-generations": ["c" * 24, "../escape"]})
    assert sorted(p.name for p in removed) == [f"{'c' * 24}-1.jpg", f"{'c' * 24}.json"]
    assert sorted(p.name for p in folder.iterdir()) == [f"{'d' * 24}.json", "picture.json"]


def test_the_replay_remembers_the_recordings_it_answered_from(tmp_path: Path) -> None:
    store = tt.UsedStore(tmp_path)
    body: dict[str, Any] = {"model": "m", "input": "x"}
    store.save("/responses", body, "scenarios", {"output": []})
    assert store.find("/responses", body, "scenarios") is not None
    assert store.find("/responses", {"model": "m", "input": "y"}, "scenarios") is None
    assert store.used == {"responses": {request_key("/responses", body)}}


async def test_a_rerecord_buys_only_the_text_and_the_drawings(tmp_path: Path) -> None:
    settings = Settings(
        OPL_FAKE_API=False,
        OPL_RECORD_FIXTURES=True,
        MODEL_API_KEY="k" * 20,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        _env_file=None,
    )
    client = tt.TextOnlyClient(settings, CostLedger(1.0), FixtureStore(tmp_path / "fixtures"))
    try:
        with pytest.raises(NoRecordingError):
            await client._post("/responses", {"model": "m"}, "extract")
        bought: list[str] = []

        async def request(*args: Any, **_: Any) -> tuple[dict[str, Any], int, float]:
            bought.append(args[1])
            return {"ok": True}, 1, 1.0

        client._request = request  # type: ignore[method-assign]
        await client._post("/responses", {"model": "m"}, "scenarios")
        await client._post(IMAGES, {"model": "m", "prompt": "p"}, "picture")
        assert bought == ["/responses", IMAGES]
    finally:
        await client.aclose()


def test_the_command_line_takes_one_mode_at_a_time() -> None:
    opts = tt.parse(["--tune", "--max-usd", "0.1"])
    assert not isinstance(opts, str) and opts.tune and opts.max_usd == 0.1
    assert isinstance(tt.parse(["--tune", "--rerecord"]), str)
    assert isinstance(tt.parse(["--apply"]), str)
    assert isinstance(tt.parse(["--prune"]), str)
    assert isinstance(tt.parse(["--rerecord", "--dry-run"]), str)
    assert isinstance(tt.parse(["--max-usd", "-1"]), str)
    assert tt.parse(["--max-usd=sk-secret"]) == "unknown argument --max-usd"
    assert tt.parse(["-h"]) == "help"


def test_refused_settings_name_the_reason_never_the_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("MODEL_API_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("PICTURE_CANDIDATES", "sk-also-not-a-number")
    get_settings.cache_clear()
    try:
        # a dry run falls back to fixture settings; refused there too, it says why and stops
        assert tt.main(["--dry-run", "--out", str(tmp_path / "out")]) == 1
    finally:
        get_settings.cache_clear()
    err = capsys.readouterr().err
    assert "the settings are refused" in err and "sk-" not in err


def test_evaluate_from_the_command_line_keeps_the_score(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text(
        report(*CHECKS, version=load().version).model_dump_json(), encoding="utf-8"
    )
    page = tmp_path / "results.md"
    page.write_text(f"{tt.START}\n{tt.END}\n", encoding="utf-8")
    code = tt.main(
        [
            "--evaluate",
            "--out",
            str(out),
            "--eval-dir",
            str(tmp_path / "eval"),
            "--results",
            str(page),
            "--set",
            str(Path(__file__).parents[2] / "demo" / "set.yaml"),
        ]
    )
    assert code == 0
    assert "3 with flags" in capsys.readouterr().out
    assert (tmp_path / "eval" / f"text-v{load().version}.json").is_file()
    assert "| checked | 4 |" in page.read_text(encoding="utf-8")


def test_keeping_an_earlier_version_writes_it_back_and_drops_the_later_recordings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.textparams as textparams

    path = tmp_path / "params.yaml"
    dump(TextParams(version=3, scenarios=TextSection(banned=["later"])), path)
    monkeypatch.setattr(textparams, "TEXT_PARAMS_FILE", path)
    folder = tmp_path / "eval"
    folder.mkdir()
    two = tt.evaluation(report(*CHECKS, version=2), TextParams(version=2))
    three = tt.evaluation(report(*CHECKS, version=3), TextParams(version=3))
    three.used = {"responses": ["a" * 24, "e" * 24]}
    for e in (two, three):
        tt.eval_path(folder, e.params_version).write_text(e.model_dump_json(), "utf-8")
    fixtures = tmp_path / "fixtures" / "responses"
    fixtures.mkdir(parents=True)
    for key in ("a", "b", "e"):
        (fixtures / f"{key * 24}.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        OPL_FAKE_API=True, fixtures_dir=tmp_path / "fixtures", log_format="text", _env_file=None
    )
    opts = tt.parse(["--keep", "2", "--eval-dir", str(folder)])
    assert not isinstance(opts, str)
    kept, removed = tt.run_keep(settings, opts)
    assert kept.version == 2 and load(path).version == 2
    assert [p.name for p in removed] == [f"{'e' * 24}.json"]
    with pytest.raises(ValueError):
        tt.run_keep(settings, tt.Options(set_file=path, out=tmp_path, keep=3, eval_dir=folder))
    assert isinstance(tt.parse(["--keep", "two"]), str)
    assert isinstance(tt.parse(["--keep", "2", "--evaluate"]), str)
