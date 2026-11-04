"""The drawing review: the facts each drawing must show, one strict Muse Spark answer per
drawing (replayed here from its stub), the run's own cost guard, the dry run, and a correction
carried from the review into the set file and into the next drawing's request."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from app.config import Settings
from app.demo.schema import DemoItem, DemoPropose, DemoSet
from app.inventory import FieldCreate, Inventory, ItemCreate
from app.model_api import CostLedger, ModelApiClient, NoRecordingError
from app.picture import finished_prompt, prompt_for
from app.picture.briefs import SetBrief, apply
from app.picture.review import (
    OP,
    Budget,
    Drawing,
    Facts,
    Options,
    PicturesOnlyClient,
    Report,
    Review,
    ReviewAnswer,
    Services,
    ceiling_usd,
    chosen_briefs,
    collect,
    describe,
    main,
    markdown,
    parse,
    review_all,
    run_review,
    selected,
    set_briefs,
    view_of,
)
from app.picture.service import TAIL, Picture
from tests.conftest import RECORDED_FIXTURES, SAMPLE_VALUE

pytestmark = pytest.mark.anyio

SET_TEXT = """\
title: a small set
items:
  # the mirror's screen
  - key: monitor
    name: Dell 1800FP monitor, 18 inch
    item_type: monitor
    picture: a smart mirror on a hall wall
    decide: true
    reuse_picture: true
    decision: keep_build

  - key: board
    name: a board
    item_type: motherboard

propose:
  count: 3
  pictures: true
  views:
    - from above, as it is used
"""


@pytest.fixture
def drawing_settings(tmp_path: Path) -> Settings:
    return Settings(
        OPL_FAKE_API=True,
        data_dir=tmp_path / "data",
        fixtures_dir=RECORDED_FIXTURES,
        picture_enabled=True,
        log_format="text",
        _env_file=None,
    )


def services(settings: Settings) -> tuple[Services, ModelApiClient]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    from app.demo.__main__ import build_loader

    loader, client = build_loader(settings, ModelApiClient(settings, CostLedger(10.0)))
    assert loader.pictures is not None
    return (
        Services(settings, loader.inventory, loader.pictures, loader.decider, loader.planner),
        client,
    )


def a_monitor(inventory: Inventory) -> int:
    item = inventory.create(ItemCreate(name="Dell 1800FP monitor, 18 inch", item_type="monitor"))
    for field, value, unit in (
        ("screen_size", "18", "in"),
        ("serial_number", "CN0ABC", ""),
        ("price", "40", ""),
    ):
        inventory.add_field(
            item.id, FieldCreate(field=field, value=value, unit=unit, provenance="tested")
        )
    return item.id


# --- the prompt and the set ----------------------------------------------------------------


def test_a_brief_goes_before_the_closing_words_and_nothing_changes_without_one() -> None:
    plain = finished_prompt("Hall smart mirror", ["monitor"], "a mirror in the hall")
    assert finished_prompt("Hall smart mirror", ["monitor"], "a mirror in the hall", brief="") == (
        plain
    )
    said = finished_prompt(
        "Hall smart mirror",
        ["monitor"],
        "a mirror in the hall",
        brief="an 18 inch monitor; not a TV",
    )
    assert said == plain.replace(f", {TAIL}", f"; an 18 inch monitor; not a TV, {TAIL}")
    assert said.endswith(TAIL)


def test_a_brief_is_said_with_an_item_picture(drawing_settings: Settings) -> None:
    sv, _ = services(drawing_settings)
    item = sv.inventory.get(a_monitor(sv.inventory))
    plain = prompt_for(item, "smart mirror")
    assert prompt_for(item, "smart mirror", "   ") == plain
    assert "; slim frame, not a TV, on a plain" in prompt_for(
        item, "smart mirror", "slim frame, not a TV"
    )


def test_a_correction_is_found_by_template_title_and_view() -> None:
    propose = DemoPropose(
        corrections={
            "smart_mirror": "an 18 inch monitor; not a TV",
            "Arcade coffee table / from above, as it is used": "a coffee table seen from above",
        }
    )
    assert propose.correction("smart_mirror", "Hall smart mirror") == "an 18 inch monitor; not a TV"
    # the drawing as built alone: a view has its own key
    assert (
        propose.correction("smart_mirror", "Hall smart mirror", "from above, as it is used") == ""
    )
    assert (
        propose.correction("arcade_table", "Arcade  coffee table", "from above,  as it is used")
        == "a coffee table seen from above"
    )
    assert propose.correction("arcade_table", "Arcade coffee table") == ""
    with pytest.raises(ValueError):
        DemoPropose(corrections={"smart_mirror": " "})


def test_briefs_are_written_into_the_set_file_and_it_still_reads() -> None:
    briefs = [
        SetBrief("an 18 inch monitor, not a TV", item="monitor", field="picture_brief"),
        SetBrief('a "second" screen', item="monitor", field="reuse_picture_brief"),
        SetBrief("a mirror 45 x 40 cm", correction="smart_mirror"),
        SetBrief("seen from above", correction="smart_mirror / from above, as it is used"),
    ]
    text = apply(SET_TEXT, briefs)
    assert "  # the mirror's screen" in text  # comments stay
    lines = text.splitlines()
    picture = lines.index("    picture: a smart mirror on a hall wall")
    assert lines[picture + 1] == '    picture_brief: "an 18 inch monitor, not a TV"'
    reuse = lines.index("    reuse_picture: true")
    assert lines[reuse + 1] == '    reuse_picture_brief: "a \\"second\\" screen"'
    demo = DemoSet.model_validate(yaml.safe_load(text))
    assert demo.items[0].picture_brief == "an 18 inch monitor, not a TV"
    assert demo.items[0].reuse_picture_brief == 'a "second" screen'
    assert demo.items[1].picture_brief == ""
    assert demo.propose is not None
    assert demo.propose.views == ["from above, as it is used"]
    assert demo.propose.corrections == {
        "smart_mirror": "a mirror 45 x 40 cm",
        "smart_mirror / from above, as it is used": "seen from above",
    }
    # a second pass replaces, never repeats
    again = apply(text, [SetBrief("a mirror 50 x 40 cm", correction="smart_mirror")])
    again = apply(again, [SetBrief("only 18 inch", item="monitor", field="picture_brief")])
    demo = DemoSet.model_validate(yaml.safe_load(again))
    assert demo.items[0].picture_brief == "only 18 inch"
    assert demo.propose is not None
    assert demo.propose.corrections["smart_mirror"] == "a mirror 50 x 40 cm"
    assert again.count(" picture_brief:") == 1 and again.count("corrections:") == 1
    with pytest.raises(KeyError):
        apply(SET_TEXT, [SetBrief("x", item="nothing", field="picture_brief")])


def test_the_demo_set_takes_briefs_where_the_tool_writes_them() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "demo" / "set.yaml").read_text(encoding="utf-8")
    written = apply(
        text,
        [
            SetBrief("an 18 inch monitor", item="monitor_1800fp", field="picture_brief"),
            SetBrief("a slim frame", correction="smart_mirror"),
        ],
    )
    demo = DemoSet.model_validate(yaml.safe_load(written))
    by_key = {i.key: i for i in demo.items}
    assert by_key["monitor_1800fp"].picture_brief == "an 18 inch monitor"
    assert demo.propose is not None and demo.propose.corrections["smart_mirror"] == "a slim frame"


async def test_the_loader_says_the_brief_with_the_drawing(drawing_settings: Settings) -> None:
    from app.demo.__main__ import build_loader
    from app.demo.schema import Outcome

    loader, client = build_loader(drawing_settings)
    assert loader.pictures is not None
    asked: list[str] = []
    real = client.picture

    async def picture(prompt: str, *, op: str = "picture") -> Any:
        asked.append(prompt)
        return await real(prompt, op=op)

    client.picture = picture  # type: ignore[method-assign]
    item = DemoItem(
        key="monitor",
        name="Dell 1800FP monitor, 18 inch",
        item_type="monitor",
        picture="a smart mirror",
        picture_brief="an 18 inch monitor behind the glass; not a TV",
    )
    item_id = a_monitor(loader.inventory)
    await loader.draw(item, item_id, Outcome())
    await client.aclose()
    assert asked and "; an 18 inch monitor behind the glass; not a TV, on a plain" in asked[0]


# --- the facts -----------------------------------------------------------------------------


def test_an_item_is_described_by_its_kind_name_and_values_never_a_serial_or_a_price(
    drawing_settings: Settings,
) -> None:
    sv, _ = services(drawing_settings)
    item = sv.inventory.get(a_monitor(sv.inventory))
    said = describe(item)
    assert said.startswith("monitor (Dell 1800FP monitor, 18 inch)")
    assert "screen size 18 in" in said
    assert "CN0ABC" not in said and "40" not in said.replace("1800", "")


def test_a_view_is_read_from_the_drawing_record() -> None:
    picture = Picture(
        n=2, use="Arcade table, from above", model="m", cost_usd=0, from_fixture=True, created_at=""
    )
    assert view_of(picture, "Arcade table") == "from above"
    assert view_of(picture, "Something else") == ""


def test_selectors_pick_a_drawing_or_all_of_one_thing() -> None:
    assert selected("project:2#1", ["project:2"])
    assert selected("project:2#3", ["project:2#3"])
    assert not selected("project:21#1", ["project:2"])
    assert not selected("project:2#1", ["project:2#2"])


async def test_every_drawing_is_collected_with_its_facts(drawing_settings: Settings) -> None:
    sv, client = services(drawing_settings)
    item_id = a_monitor(sv.inventory)
    await sv.pictures.draw(item_id, "a smart mirror")
    sv.keys = {item_id: "monitor"}
    found = collect(sv)
    await client.aclose()
    assert [d.id for d in found] == ["item:monitor#1"]
    facts = found[0].facts
    assert facts.title == "a smart mirror"
    assert "screen size 18 in" in facts.parts[0]
    assert facts.asked.startswith("a semi-realistic illustration of a smart mirror")


# --- the calls and the guard ---------------------------------------------------------------


def test_the_ceiling_counts_every_output_token_the_call_may_write() -> None:
    assert ceiling_usd("muse-spark-1.3", 6000, 1200) > (6000 * 1.25 + 1200 * 4.25) / 1_000_000
    budget = Budget(0.05)
    assert budget.allows(0.05)
    budget.add(0.01)
    assert not budget.allows(0.05)


async def test_a_review_replays_its_stub_and_a_tight_cap_makes_no_call(
    drawing_settings: Settings, tmp_path: Path
) -> None:
    sv, client = services(drawing_settings)
    item_id = a_monitor(sv.inventory)
    await sv.pictures.draw(item_id, "a smart mirror")
    drawings = collect(sv)
    skipped: list[str] = []
    reviews = await review_all(
        client, drawing_settings, drawings, tmp_path / "out", Budget(1.0), skipped=skipped
    )
    assert reviews[0].verdict == "wrong"
    assert reviews[0].issues[0].category == "wrong_device"
    assert "not a TV" in reviews[0].brief
    assert (tmp_path / "out" / reviews[0].picture).is_file()
    calls = len(client.ledger.entries())
    assert client.ledger.entries()[-1].op == OP
    tight = await review_all(
        client, drawing_settings, drawings, tmp_path / "out", Budget(0.001), skipped=skipped
    )
    await client.aclose()
    assert tight[0].verdict == "not reviewed"
    assert skipped and "--max-usd" in skipped[0]
    assert len(client.ledger.entries()) == calls


def test_the_answer_schema_is_strict() -> None:
    from app.model_api import strict_schema

    schema = strict_schema(ReviewAnswer)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"verdict", "confidence", "issues", "brief", "summary"}


async def test_a_redraw_run_buys_drawings_alone(tmp_path: Path) -> None:
    settings = Settings(
        OPL_FAKE_API=False,
        OPL_RECORD_FIXTURES=True,
        OPL_KEY_PROBE=False,
        model_api_key=SAMPLE_VALUE,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        _env_file=None,
    )
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(500)

    client = PicturesOnlyClient(settings, CostLedger(1.0), transport=httpx.MockTransport(answer))
    with pytest.raises(NoRecordingError):
        await client.respond(model="muse-spark-1.3", input="hello", op="scenarios")
    await client.aclose()
    assert sent == []


# --- the runs ------------------------------------------------------------------------------


async def test_a_dry_run_lists_the_drawings_and_spends_nothing(
    drawing_settings: Settings, tmp_path: Path
) -> None:
    sv, client = services(drawing_settings)
    await sv.pictures.draw(a_monitor(sv.inventory), "a smart mirror")
    await client.aclose()
    out = tmp_path / "out"
    opts = Options(set_file=tmp_path / "none.yaml", out=out, data=True, dry_run=True)
    report = await run_review(drawing_settings, opts)
    assert [r.id for r in report.reviews] == ["item:1#1"]
    assert report.reviews[0].verdict == "not reviewed" and report.cost_usd == 0
    assert "dry run" in report.mode
    assert "screen size 18 in" in markdown(report)


async def test_a_data_run_reviews_and_writes_the_report(
    drawing_settings: Settings, tmp_path: Path
) -> None:
    sv, client = services(drawing_settings)
    await sv.pictures.draw(a_monitor(sv.inventory), "a smart mirror")
    await client.aclose()
    opts = Options(set_file=tmp_path / "none.yaml", out=tmp_path / "out", data=True, decide=True)
    report = await run_review(drawing_settings, opts)
    assert report.counts() == {"wrong": 1}
    text = markdown(report)
    assert "| `item:1#1` |" in text and "**wrong_device**" in text


def test_the_briefs_come_from_the_report_or_the_command_line(tmp_path: Path) -> None:
    facts = Facts(title="t")
    report = Report(
        at="",
        source="",
        mode="",
        reviews=[
            Review(
                id="project:2#1", title="", kind="project", facts=facts, verdict="wrong", brief="b2"
            ),
            Review(
                id="project:3#1",
                title="",
                kind="project",
                facts=facts,
                verdict="partly",
                brief="b3",
            ),
            Review(id="item:x#1", title="", kind="item", facts=facts, verdict="matches"),
        ],
    )
    assert chosen_briefs(report, ["all-wrong"], "", None) == {"project:2#1": "b2"}
    assert chosen_briefs(report, ["project:3"], "", None) == {"project:3#1": "b3"}
    assert chosen_briefs(report, ["project:3#1"], "my own", None) == {"project:3#1": "my own"}
    briefs = tmp_path / "briefs.yaml"
    briefs.write_text('"item:x#1": a better one\n', encoding="utf-8")
    assert chosen_briefs(report, ["item:x"], "", briefs) == {"item:x#1": "a better one"}
    with pytest.raises(ValueError):
        chosen_briefs(report, ["item:x"], "", None)


def test_set_briefs_name_the_project_by_template_and_view() -> None:
    def project(n: int, view: str = "") -> Drawing:
        return Drawing(
            id=f"project:2#{n}",
            kind="project",
            n=n,
            file="",
            use="",
            project_id=2,
            template="smart_mirror",
            project_title="Hall mirror",
            view=view,
            facts=Facts(title="t"),
        )

    drawings = [project(1), project(2, "from above")]
    out = set_briefs(drawings, {"project:2#1": "a", "project:2#2": "b"})
    assert [b.correction for b in out] == ["smart_mirror", "smart_mirror / from above"]


def test_the_command_line_is_checked(capsys: pytest.CaptureFixture[str]) -> None:
    assert isinstance(parse(["--max-usd", "x"]), str)
    assert isinstance(parse(["--brief", "x"]), str)
    assert isinstance(parse(["--redraw", "all-wrong", "--dry-run"]), str)
    opts = parse(["--only", "project:2, card:monitor", "--max-usd", "0.5", "--decide"])
    assert isinstance(opts, Options)
    assert opts.only == ["project:2", "card:monitor"] and opts.max_usd == 0.5 and opts.decide
    assert main(["--wat"]) == 2
    assert main(["--help"]) == 0
    assert "--redraw" in capsys.readouterr().out


async def test_the_recommendation_check_replays_its_stub(drawing_settings: Settings) -> None:
    from app.picture.review import decide_all

    sv, client = services(drawing_settings)
    item_id = a_monitor(sv.inventory)
    await sv.decider.scenarios(item_id)
    skipped: list[str] = []
    checked = await decide_all(client, sv, Budget(1.0), skipped)
    await client.aclose()
    assert checked and checked[0].sound is False
    assert checked[0].flags[0].severity == "major"


async def test_the_request_shown_carries_the_correction_it_was_drawn_with(
    drawing_settings: Settings,
) -> None:
    sv, client = services(drawing_settings)
    item_id = a_monitor(sv.inventory)
    await sv.pictures.draw(item_id, "a smart mirror", "an 18 inch monitor; not a TV")
    await client.aclose()
    sv.keys = {item_id: "monitor"}
    sv.demo = DemoSet(
        items=[
            DemoItem(
                key="monitor",
                name="Dell 1800FP monitor, 18 inch",
                picture="a smart mirror",
                picture_brief="an 18 inch monitor; not a TV",
            )
        ]
    )
    asked = collect(sv)[0].facts.asked
    assert "; an 18 inch monitor; not a TV, on a plain background" in asked
    assert sv.item_brief(item_id, "reuse_picture_brief") == ""


def test_a_brief_for_several_drawings_is_refused() -> None:
    facts = Facts(title="t")
    report = Report(
        at="",
        source="",
        mode="",
        reviews=[
            Review(id=f"project:4#{n}", title="", kind="project", facts=facts, brief="b")
            for n in (1, 2)
        ],
    )
    with pytest.raises(ValueError):
        chosen_briefs(report, ["project:4"], "my own", None)


def test_a_wrong_argument_is_named_never_echoed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["MODEL_API_KEY=" + SAMPLE_VALUE]) == 2
    assert main(["--key=" + SAMPLE_VALUE]) == 2
    err = capsys.readouterr().err
    assert SAMPLE_VALUE not in err and "--key" in err


def test_refused_settings_never_show_the_key() -> None:
    from app.picture.review import refused

    with pytest.raises(ValueError) as caught:
        Settings(OPL_FAKE_API=False, model_api_key=SAMPLE_VALUE, CANDIDATE_DAYS=0, _env_file=None)
    assert SAMPLE_VALUE[:6] not in refused(caught.value)
    assert "CANDIDATE_DAYS" in refused(caught.value)


async def test_a_recorded_failure_is_not_bought_again_in_a_redraw_run(tmp_path: Path) -> None:
    settings = Settings(
        OPL_FAKE_API=False,
        OPL_RECORD_FIXTURES=True,
        OPL_KEY_PROBE=False,
        model_api_key=SAMPLE_VALUE,
        data_dir=tmp_path / "data",
        fixtures_dir=tmp_path / "fixtures",
        log_format="text",
        _env_file=None,
    )
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(500)

    client = PicturesOnlyClient(settings, CostLedger(1.0), transport=httpx.MockTransport(answer))
    # a failure kept on disk: the plain record mode would ask again, live
    client.fixtures.save(
        "/v1/responses", {"model": "m", "input": "hi"}, "scenarios", {}, status=500
    )
    with pytest.raises(NoRecordingError):
        await client._post("/v1/responses", {"model": "m", "input": "hi"}, "scenarios")
    await client.aclose()
    assert sent == []


def test_the_record_run_buys_whole_drawings_within_what_is_left() -> None:
    from app.picture.review import drawings_cap

    for left, most in ((0.0, 0), (0.009, 0), (0.025, 2), (0.03, 3)):
        ledger = CostLedger(drawings_cap(left))
        bought = 0
        while not ledger.paused:
            ledger._total += 0.01
            bought += 1
        assert bought == most
