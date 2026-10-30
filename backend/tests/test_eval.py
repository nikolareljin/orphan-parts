import json
from pathlib import Path

import pytest

from app.config import Settings
from app.demo import DemoItem, DemoSet, Outcome, load_set
from app.demo.__main__ import build_loader
from app.eval import score, write_report
from app.eval.__main__ import main
from app.eval.service import compare, diff, markdown, training_lines
from app.inventory.schema import FieldCreate, ItemCreate
from app.match import Assessor
from app.profiles import Profiles
from tests.conftest import make_photo

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parents[2]
SET = ROOT / "demo" / "set.yaml"

# What the committed fixtures answer for the committed set: the set's photos and the voice
# note are not in the repository, so no label is read, and every answer that is given (three
# drafts, two price guidances, four listing reads, the two steps of the proposal loop) comes
# from an operation's stub rather than a recording of this set. Recording the set with its
# photos brings this to 0; the assertion pins the number the fixtures give today.
STUB_ANSWERS_ON_THE_COMMITTED_SET = 11


async def test_the_run_scores_the_committed_set_and_writes_the_files(
    recorded_settings: Settings, tmp_path: Path
) -> None:
    demo = load_set(SET)
    loader, client = build_loader(recorded_settings)
    try:
        outcome = await loader.run(demo, SET.parent)
    finally:
        await client.aclose()
    report = score(
        demo,
        outcome,
        loader.inventory,
        Assessor(Profiles(), loader.inventory),
        loader.planner,
        loader.ids,
        str(SET),
    )
    s = report.summary
    assert s.mode == "fixture" and s.cost_usd == 0.0
    assert s.items == s.items_loaded == 10 and s.photos == 0 and s.fields_read == 0
    assert s.stub_answers == STUB_ANSWERS_ON_THE_COMMITTED_SET
    # the fit verdicts come from the rules and the owner values: right without any recording
    assert (s.fits_right, s.fits_total) == (2, 2)
    by_key = {i.key: i for i in report.items}
    assert by_key["tool_fits"].fit is not None
    assert by_key["tool_fits"].fit.verdict == "COMPATIBLE_LIKELY"
    assert by_key["tool_near"].fit is not None and by_key["tool_near"].fit.verdict == "CONFLICT"
    # the adapter's expected values are the stub's; its photo is not here, so nothing was read
    assert {f.result for f in by_key["adapter"].expected_fields} == {"not_read"}
    assert s.expected == 5 and s.matches == 0
    # the proposal stub writes three, the rules keep the two the inventory backs
    assert (s.proposals_proposed, s.proposals_kept, s.proposals_dropped) == (3, 2, 1)
    assert by_key["laptop_old"].proposals_in == 1 and by_key["vacuum"].proposals_in == 1
    out = tmp_path / "eval"
    written = write_report(report, out)
    assert [p.name for p in written] == ["report.json", "report.md", "fields.png", "proposals.png"]
    assert all(p.is_file() and p.stat().st_size > 0 for p in written)
    saved = json.loads((out / "report.json").read_text())
    assert saved["summary"]["stub_answers"] == STUB_ANSWERS_ON_THE_COMMITTED_SET
    text = (out / "report.md").read_text()
    assert "| Fit verdicts right | 2 of 2 |" in text and "operation's stub" in text
    assert "| tool_near | 0 | 0 | 1 |  |  | CONFLICT vs vacuum, expected conflict: right |" in text


def test_expected_values_compare_by_number_or_by_the_field_normaliser() -> None:
    assert compare("output_voltage", "19.5 V", "19.5 V")
    assert compare("output_voltage", "19.5 V", "20 V")  # within 5 %
    assert not compare("output_voltage", "19.5 V", "21 V")
    assert not compare("output_voltage", "19.5 V", "19500 mV")  # another unit is not compared
    assert compare("brand", "Orbital  Power", "orbital power")
    assert compare("model_number", "Model OP-65N", "OP-65N")
    assert not compare("brand", "Orbital Power", "Orbital")
    assert compare("opening_inner_diameter", "32 mm", "32.5 mm")  # a profile key: numeric
    assert not compare("opening_inner_diameter", "32 mm", "35 mm")


def _small_set(expect_voltage: str) -> DemoSet:
    return DemoSet.model_validate(
        {
            "items": [
                {
                    "key": "a",
                    "name": "Adapter",
                    "profile": "power_adapter",
                    "expect": {
                        "fields": {
                            "output_voltage": expect_voltage,
                            "brand": "Orbital Power",
                            "connector": "USB-C",
                        }
                    },
                },
                {"key": "b", "name": "Never loaded", "expect": {"fields": {"brand": "x"}}},
            ]
        }
    )


def test_expect_scoring_on_an_inline_set(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True)
    loader, _ = build_loader(settings)
    item = loader.inventory.create(ItemCreate(name="Adapter", item_type="adapter"))
    loader.inventory.add_field(item.id, FieldCreate(field="output_voltage", value="19.6", unit="V"))
    loader.inventory.add_field(item.id, FieldCreate(field="brand", value="Orbital Power"))
    demo = _small_set("19.5 V")
    report = score(
        demo,
        Outcome(mode="fixture", items=1),
        loader.inventory,
        Assessor(Profiles(), loader.inventory),
        loader.planner,
        {"a": item.id},
    )
    a, b = report.items
    assert {f.field: f.result for f in a.expected_fields} == {
        "output_voltage": "match",
        "brand": "match",
        "connector": "not_read",
    }
    assert not b.loaded and [f.result for f in b.expected_fields] == ["not_read"]
    assert (report.summary.matches, report.summary.expected) == (2, 4)
    report2 = score(
        _small_set("12 V"),
        Outcome(mode="fixture", items=1),
        loader.inventory,
        Assessor(Profiles(), loader.inventory),
        loader.planner,
        {"a": item.id},
    )
    volts = report2.items[0].expected_fields[0]
    assert volts.result == "mismatch" and volts.actual == "19.6 V"
    assert "output_voltage mismatch ('19.6 V')" in markdown(report2)
    lines = diff(report, report2)
    assert any(line.startswith("matches") and line.endswith("-1") for line in lines)
    assert "a.output_voltage: match -> mismatch" in lines


def test_fit_scoring_follows_the_rules(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True)
    loader, _ = build_loader(settings)
    inv = loader.inventory
    vac = inv.create(ItemCreate(name="Vacuum", item_type="vacuum", profile="vacuum_attachment"))
    fits = inv.create(ItemCreate(name="Tool", item_type="tool", profile="vacuum_attachment"))
    near = inv.create(ItemCreate(name="Near", item_type="tool", profile="vacuum_attachment"))
    inv.add_field(fits.id, FieldCreate(field="opening_inner_diameter", value="32.2"))
    inv.add_field(near.id, FieldCreate(field="opening_inner_diameter", value="35"))
    demo = DemoSet.model_validate(
        {
            "items": [
                {"key": "vac", "name": "Vacuum", "profile": "vacuum_attachment"},
                {
                    "key": "fits",
                    "name": "Tool",
                    "profile": "vacuum_attachment",
                    "expect": {"fit": {"against": "vac", "verdict": "fits", "values": {}}},
                },
                {
                    "key": "near",
                    "name": "Near",
                    "profile": "vacuum_attachment",
                    "expect": {
                        "fit": {
                            "against": "vac",
                            "verdict": "fits",
                            "values": {"opening_inner_diameter": "32"},
                        }
                    },
                },
                {
                    "key": "gone",
                    "name": "Gone",
                    "expect": {"fit": {"against": "vac", "verdict": "conflict"}},
                },
            ]
        }
    )
    ids = {"vac": vac.id, "fits": fits.id, "near": near.id}
    report = score(
        demo, Outcome(mode="fixture", items=3), inv, Assessor(Profiles(), inv), loader.planner, ids
    )
    by_key = {i.key: i for i in report.items}
    # no needed value on the vacuum: the rules ask for evidence, which is not a fit
    assert by_key["fits"].fit is not None and by_key["fits"].fit.verdict == "INSUFFICIENT_INFO"
    assert by_key["fits"].fit.right is False
    # 35 against 32 ±0.5: a conflict, and the expectation of a fit is wrong
    assert by_key["near"].fit is not None and by_key["near"].fit.verdict == "CONFLICT"
    assert by_key["near"].fit.right is False
    assert by_key["gone"].fit is not None and by_key["gone"].fit.right is None
    assert (report.summary.fits_right, report.summary.fits_total) == (0, 3)
    for against, message in (("z", "is not an item"), ("a", "against itself")):
        fit = {"against": against, "verdict": "fits"}
        with pytest.raises(ValueError, match=message):
            DemoSet.model_validate(
                {"items": [{"key": "a", "name": "A", "expect": {"fit": fit}}]}
            ).check()
    assert DemoItem(key="k", name="K").expect is None


async def test_the_export_writes_one_line_per_item_with_accepted_reads(
    recorded_settings: Settings, tmp_path: Path
) -> None:
    loader, client = build_loader(recorded_settings)
    inv = loader.inventory
    try:
        extraction = await loader.extractor.extract([make_photo()])  # the extract stub
    finally:
        await client.aclose()
    item = inv.create(ItemCreate(name="Adapter", item_type="adapter", extraction=extraction))
    bare = inv.create(ItemCreate(name="Bare", item_type="thing"))
    inv.add_field(bare.id, FieldCreate(field="brand", value="Owner's word"))
    assert training_lines(inv) == []  # nothing accepted yet
    accepted = [a for a in item.assertions if a.field in ("brand", "output_voltage")]
    for a in accepted:
        inv.review(item.id, a.id, "accepted")
    lines = training_lines(inv)
    assert len(lines) == 1
    record = json.loads(lines[0])
    roles = [m["role"] for m in record["messages"]]
    assert roles == ["system", "user", "assistant"] and record["item_id"] == item.id
    assert record["messages"][0]["content"].startswith("You read labels")
    assert f"/api/items/{item.id}/photos" in record["messages"][1]["content"]
    answer = json.loads(record["messages"][2]["content"])
    assert answer["fields"] == {
        "brand": {"value": "Orbital Power", "unit": ""},
        "output_voltage": {"value": "19.5", "unit": "V"},
    }
    out = tmp_path / "eval"
    assert main(["export", "--out", str(out)]) in (0, 1)  # the settings are the environment's


def test_the_command_line(
    tmp_path: Path,
    recorded_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import app.eval.__main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: recorded_settings)
    assert main([]) == 2
    assert main(["fly"]) == 2
    assert main(["run", "--what"]) == 2
    assert main(["diff", "a"]) == 2
    assert main(["diff", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 1
    assert main(["run", "--set", str(tmp_path / "nowhere.yaml")]) == 1
    bad = tmp_path / "bad.yaml"
    bad.write_text("items:\n  - {key: a}\n")
    assert main(["run", "--set", str(bad)]) == 1
    out = tmp_path / "eval"
    recorded_settings.data_dir.mkdir(parents=True, exist_ok=True)
    recorded_settings.inventory_db_path.write_bytes(b"")
    assert main(["run", "--set", str(SET), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "removed inventory.sqlite3" in printed and "2/2 fit verdict(s) right" in printed
    assert (out / "charts" / "proposals.png").is_file()
    assert main(["export", "--out", str(out)]) == 0
    assert (out / "train.jsonl").read_text() == ""  # nothing observed was read for this set
    (out / "a.json").write_bytes((out / "report.json").read_bytes())
    assert main(["diff", str(out / "a.json"), str(out / "report.json")]) == 0
    assert "stub_answers" in capsys.readouterr().out
    # --keep leaves the inventory as it is, so the set is loaded twice over
    assert main(["run", "--set", str(SET), "--out", str(out), "--keep"]) == 0
    assert "removed" not in capsys.readouterr().out
