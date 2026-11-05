"""Likes and dislikes of what the app generated: the owner votes, changes and takes back a vote;
a judge's code votes on what it can see, tagged with its code and counting its own vote alone;
the demo visitor is refused and reads nothing of them; the review tools read the votes as a
person's signal (disliked drawings selected and counted by --tune, liked ones kept)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.feedback import Feedback, VoteCreate, read_votes
from app.feedback.signals import People, expand, tally
from app.main import create_app
from app.ops.door import judge_code
from app.ops.gate import DEMO_LINE
from app.picture import tune
from app.picture.params import load as load_params
from app.picture.review import (
    Budget,
    Facts,
    Options,
    Report,
    Review,
    chosen_briefs,
    decide_all,
    markdown,
    run_review,
)
from app.textparams import TextParams
from app.textparams import tune as tt
from tests.conftest import RECORDED_FIXTURES
from tests.test_gate import CODE, gated_settings
from tests.test_picture_review import a_monitor, services
from tests.test_picture_review import drawing_settings as drawing_settings
from tests.test_saved_results import _saved_item

pytestmark = pytest.mark.usefixtures("v1_params")


@pytest.fixture
def gated(tmp_path: Path) -> Iterator[TestClient]:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES, picture_enabled=True)
    with TestClient(create_app(settings)) as c:
        yield c


def _sign_in(c: TestClient, code: str) -> None:
    c.cookies.clear()
    assert c.post("/api/access", json={"code": code}).json()["granted"] is True


def _picture(c: TestClient, item: int) -> dict[str, object]:
    drawn = c.post(f"/api/items/{item}/picture", json={})
    assert drawn.status_code == 201, drawn.text
    return {"target_kind": "item_picture", "target_id": item, "target_ref": str(drawn.json()["n"])}


def _vote(
    c: TestClient, target: dict[str, object], vote: str, reason: str = ""
) -> dict[str, object]:
    res = c.post("/api/feedback", json={**target, "vote": vote, "reason": reason})
    assert res.status_code == 200, res.text
    return dict(res.json())


def test_the_owner_votes_changes_the_vote_and_takes_it_back(gated: TestClient) -> None:
    item = _saved_item(gated)
    target = _picture(gated, item)
    assert gated.get("/api/feedback", params=target).json() == {
        **target,
        "likes": 0,
        "dislikes": 0,
        "mine": None,
        "reason": "",
    }
    liked = _vote(gated, target, "like")
    assert (liked["likes"], liked["dislikes"], liked["mine"]) == (1, 0, "like")
    # a second vote replaces the first: one per person
    disliked = _vote(gated, target, "dislike", "  drawn as\na TV,\tnot a monitor ")
    assert (disliked["likes"], disliked["dislikes"], disliked["mine"]) == (0, 1, "dislike")
    assert disliked["reason"] == "drawn as a TV, not a monitor"
    assert gated.get("/api/feedback", params=target).json()["mine"] == "dislike"
    gone = gated.delete("/api/feedback", params=target)
    assert gone.status_code == 200 and gone.json()["mine"] is None
    assert gone.json()["dislikes"] == 0
    # nothing was asked of a model by any of it
    spend = gated.get("/api/spend").json()
    assert all("feedback" not in str(k) for k in spend.get("by_op", {}))


def test_every_kind_of_target_is_found_and_kept(gated: TestClient) -> None:
    item = _saved_item(gated)
    inventory = gated.app.state.inventory  # type: ignore[attr-defined]
    scenarios = inventory.scenarios(item)[-1]["id"]
    uses = inventory.uses(item)[-1]["id"]
    guidance = gated.get(f"/api/items/{item}/price").json()[-1]["id"]
    draft = gated.get(f"/api/items/{item}/drafts").json()[-1]["id"]
    card = gated.post(f"/api/items/{item}/scenarios/{scenarios}/reuse/0/picture")
    assert card.status_code == 201, card.text
    targets = [
        ("scenarios", item, str(scenarios)),
        ("uses", item, str(uses)),
        ("price_guidance", item, str(guidance)),
        ("draft", draft, ""),
        ("card_picture", item, f"{scenarios}/0/{card.json()['n']}"),
    ]
    for kind, tid, ref in targets:
        target = {"target_kind": kind, "target_id": tid, "target_ref": ref}
        assert _vote(gated, target, "like")["likes"] == 1, kind
    kept = read_votes(gated.app.state.settings.inventory_db_path)  # type: ignore[attr-defined]
    assert [(v.target_kind, v.owner_code) for v in kept] == [(k, None) for k, _, _ in targets]
    # a drawing's vote keeps its bytes' digest; any other vote none
    assert [bool(v.digest) for v in kept] == [False, False, False, False, True]


@pytest.mark.parametrize(
    ("spec", "status"),
    [
        ({"target_kind": "photo", "target_id": 1, "target_ref": "1"}, 422),
        ({"target_kind": "item_picture", "target_id": 1, "target_ref": ""}, 422),
        ({"target_kind": "item_picture", "target_id": 1, "target_ref": "1/2"}, 422),
        ({"target_kind": "item_picture", "target_id": 1, "target_ref": "01"}, 422),
        ({"target_kind": "draft", "target_id": 1, "target_ref": "3"}, 422),
        ({"target_kind": "item_picture", "target_id": 0, "target_ref": "1"}, 422),
        ({"target_kind": "item_picture", "target_id": 1, "target_ref": "9"}, 404),
        ({"target_kind": "scenarios", "target_id": 999, "target_ref": "1"}, 404),
        ({"target_kind": "candidate", "target_id": 5, "target_ref": ""}, 404),
    ],
)
def test_a_vote_on_nothing_or_of_the_wrong_shape_is_refused(
    gated: TestClient, spec: dict[str, object], status: int
) -> None:
    _sign_in(gated, CODE)
    gated.post("/api/items", json={"item_type": "monitor"})
    res = gated.post("/api/feedback", json={**spec, "vote": "like"})
    assert res.status_code == status, res.text
    if status == 422 and spec["target_kind"] != "photo" and spec["target_id"] != 0:
        assert gated.get("/api/feedback", params=spec).status_code == 422


def test_a_reason_is_one_short_line_and_a_vote_is_like_or_dislike(gated: TestClient) -> None:
    item = _saved_item(gated)
    target = _picture(gated, item)
    long = gated.post("/api/feedback", json={**target, "vote": "dislike", "reason": "x" * 201})
    assert long.status_code == 422
    odd = gated.post("/api/feedback", json={**target, "vote": "meh"})
    assert odd.status_code == 422
    assert _vote(gated, target, "dislike", "y" * 200)["reason"] == "y" * 200


def test_the_demo_visitor_can_neither_vote_nor_read_the_votes(gated: TestClient) -> None:
    item = _saved_item(gated)
    target = _picture(gated, item)
    _vote(gated, target, "dislike", "the owner's reason")
    gated.cookies.clear()
    for method in ("GET", "POST", "DELETE"):
        if method == "POST":
            res = gated.post("/api/feedback", json={**target, "vote": "like"})
        else:
            res = gated.request(method, "/api/feedback", params=target)
        assert res.status_code == 403 and res.json()["detail"] == DEMO_LINE, method
        assert "the owner's reason" not in res.text
    # the item it is about reads as before, and says nothing of the votes
    seen = gated.get(f"/api/items/{item}")
    assert seen.status_code == 200 and "reason" not in seen.text


def test_a_judge_votes_in_a_sandbox_of_its_own(gated: TestClient) -> None:
    item = _saved_item(gated)
    target = _picture(gated, item)
    private = _saved_item(gated, public=False)
    hidden = _picture(gated, private)
    _vote(gated, target, "like")
    keys = gated.app.state.gate.keys  # type: ignore[attr-defined]
    jury, record = keys.issue("jury", scope="judge")
    other, other_record = keys.issue("other", scope="judge")
    _sign_in(gated, jury)
    # the owner's vote is not counted for the judge, and not shown as theirs
    seen = gated.get("/api/feedback", params=target).json()
    assert (seen["likes"], seen["dislikes"], seen["mine"]) == (0, 0, None)
    mine = _vote(gated, target, "dislike", "a judge's reason")
    assert (mine["likes"], mine["dislikes"], mine["mine"]) == (0, 1, "dislike")
    # what the owner keeps private is not there for it
    assert gated.post("/api/feedback", json={**hidden, "vote": "like"}).status_code == 404
    assert gated.get("/api/feedback", params=hidden).status_code == 404
    # its own item: voted on as its own
    own = gated.post("/api/items", json={"item_type": "toaster"}).json()["id"]
    drafted = gated.app.state.inventory.add_draft(own, "sell", "{}", "[]")["id"]  # type: ignore[attr-defined]
    own_target = {"target_kind": "draft", "target_id": drafted, "target_ref": ""}
    assert _vote(gated, own_target, "like")["mine"] == "like"
    # another judge sees neither the first one's vote nor its item
    _sign_in(gated, other)
    assert gated.get("/api/feedback", params=target).json()["dislikes"] == 0
    assert gated.post("/api/feedback", json={**own_target, "vote": "like"}).status_code == 404
    assert gated.delete("/api/feedback", params=own_target).status_code == 404
    # taking back its own vote leaves the first judge's alone
    assert gated.delete("/api/feedback", params=target).json()["mine"] is None
    # the owner counts every vote; the judge's is tagged with its code
    _sign_in(gated, CODE)
    counted = gated.get("/api/feedback", params=target).json()
    assert (counted["likes"], counted["dislikes"], counted["mine"]) == (1, 1, "like")
    kept = read_votes(gated.app.state.settings.inventory_db_path)  # type: ignore[attr-defined]
    assert {v.owner_code for v in kept} == {None, record.id}
    assert other_record.id not in {v.owner_code for v in kept}


def test_the_votes_go_with_the_inventory_and_an_older_file_has_none(tmp_path: Path) -> None:
    assert read_votes(tmp_path / "none.sqlite3") == []
    settings = gated_settings(tmp_path)
    with TestClient(create_app(settings)):
        pass
    assert read_votes(settings.inventory_db_path) == []


# --- the review tools ---------------------------------------------------------------------


def _review(rid: str, verdict: str, people: People, subject: str = "smart_mirror") -> Review:
    return Review(
        id=rid,
        title=rid,
        kind=rid.split(":")[0],
        subject=subject,
        kinds=["monitor"],
        facts=Facts(title=rid),
        verdict=verdict,
        brief=f"brief for {rid}",
        people=people,
    )


def test_disliked_and_liked_stand_for_the_drawings_people_voted_on() -> None:
    people = {
        "item:a#1": People(dislikes=1, reasons=["owner: a TV"]),
        "item:b#1": People(likes=2),
        "item:c#1": People(likes=1, dislikes=1, reasons=["judge code 3: no"]),
        "item:d#1": People(),
    }
    assert expand(["disliked"], people) == ["item:a#1", "item:c#1"]
    assert expand(["liked", "project:2"], people) == ["item:b#1", "project:2"]
    assert expand(["disliked"], {}) == []


def test_all_wrong_keeps_a_liked_drawing_and_disliked_names_the_flagged() -> None:
    report = Report(
        at="",
        source="",
        mode="",
        reviews=[
            _review("project:1#1", "wrong", People(likes=1)),
            _review("project:2#1", "wrong", People()),
            _review("project:3#1", "matches", People(dislikes=1, reasons=["owner: too big"])),
        ],
    )
    assert chosen_briefs(report, ["all-wrong"], "", None) == {
        "project:2#1": "brief for project:2#1"
    }
    assert list(chosen_briefs(report, ["disliked"], "", None)) == ["project:3#1"]
    # nobody voted: nothing to redraw, and it says so
    with pytest.raises(ValueError, match="vote"):
        chosen_briefs(Report(at="", source="", mode="", reviews=[]), ["disliked"], "", None)


def test_tune_counts_a_dislike_with_its_reason_and_keeps_a_liked_drawing() -> None:
    report = Report(
        at="2026-11-04T00:00:00+00:00",
        source="demo/set.yaml",
        mode="demo set",
        params_version=1,
        reviews=[
            _review(
                "project:2#1",
                "matches",
                People(dislikes=1, reasons=["owner: the monitor is drawn as a TV"]),
            ),
            _review("project:7#1", "matches", People(likes=1), subject="arcade_table"),
        ],
    )
    agg = tune.aggregate(report, 1)
    assert agg.disliked == {"project:2#1": ["owner: the monitor is drawn as a TV"]}
    assert agg.liked == ["project:7#1"]
    mirror = agg.subjects["smart_mirror"]
    assert mirror.people == ["flagged by a person: owner: the monitor is drawn as a TV"]
    assert mirror.issues[0].startswith("flagged by a person")
    # a reviewer's match does not hide a person's flag: the subject is up for a correction
    assert tune.needs_correction(mirror) and not tune.needs_correction(agg.subjects["arcade_table"])
    params = load_params()
    text = tune.phrase_input(agg, params, {"smart_mirror": "Smart mirror"})
    assert "flagged by a person: owner: the monitor is drawn as a TV" in text
    # without a brief of the reviewer's, the correction is the phrasing call's, from the reason
    assert tune.correction_edits(agg, params, None, {"smart_mirror": "Smart mirror"}) == []
    phrased = tune.Phrased(
        corrections=[
            tune.Phrased.Correction(subject="smart_mirror", text="a slim monitor, not a TV")
        ],
        looks=[],
    )
    edits = tune.correction_edits(agg, params, phrased, {"smart_mirror": "Smart mirror"})
    assert len(edits) == 1 and "1 disliked by a person" in edits[0].why
    shown = tune.proposal_markdown(
        tune.Proposal(
            at="", from_version=1, to_version=2, report_at="", edits=edits, aggregate=agg
        ),
        params,
    )
    assert "## People's votes" in shown and "`project:7#1` liked" in shown


def test_decide_tune_takes_a_dislike_as_a_flag_a_person_raised() -> None:
    from app.picture.review import DecideReview

    checked = tt.Report(
        at="",
        source="",
        mode="demo set",
        decide=[
            DecideReview(
                id="cards:ram",
                title="t",
                sound=True,
                people=People(dislikes=1, reasons=["owner: needs a processor I do not own"]),
            ),
            DecideReview(id="ideas:uno", title="t", sound=True, people=People(likes=1)),
        ],
    )
    flags = tt.flags_by_section(checked)
    assert [f.claim for f in flags["scenarios"]] == ["needs a processor I do not own"]
    assert flags["uses"] == []
    assert "Section: scenarios" in tt.phrase_input(checked, TextParams(version=1))
    assert "## People's votes" in tt.markdown(checked)


@pytest.mark.anyio
async def test_a_review_reads_the_votes_and_selects_the_disliked(
    tmp_path: Path, drawing_settings: Settings
) -> None:
    sv, client = services(drawing_settings)
    item = a_monitor(sv.inventory)
    await sv.pictures.draw(item, "a smart mirror")
    await sv.pictures.draw(item, "a kitchen screen")
    await sv.decider.scenarios(item)
    await client.aclose()
    feedback = Feedback(sv.inventory)
    feedback.vote(
        VoteCreate(target_kind="item_picture", target_id=item, target_ref="2", vote="dislike"),
        tally_digest(sv, item, 2),
    )
    token = judge_code.set(7)
    try:
        feedback.vote(
            VoteCreate(
                target_kind="item_picture",
                target_id=item,
                target_ref="2",
                vote="dislike",
                reason="not a kitchen",
            ),
            tally_digest(sv, item, 2),
        )
    finally:
        judge_code.reset(token)
    # a vote cast on other bytes under number 1: a drawing since redrawn
    feedback.vote(
        VoteCreate(target_kind="item_picture", target_id=item, target_ref="1", vote="like"),
        "0" * 16,
    )
    cards = sv.decider.latest_scenarios(item)
    assert cards is not None
    feedback.vote(
        VoteCreate(
            target_kind="scenarios",
            target_id=item,
            target_ref=str(cards.id),
            vote="dislike",
            reason="wrong socket",
        )
    )
    opts = Options(
        set_file=tmp_path / "none.yaml",
        out=tmp_path / "out",
        data=True,
        dry_run=True,
        only=["disliked"],
    )
    report = await run_review(drawing_settings, opts)
    assert [r.id for r in report.reviews] == [f"item:{item}#2"]
    people = report.reviews[0].people
    assert (people.likes, people.dislikes) == (0, 2)
    assert people.reasons == ["owner: disliked, no reason given", "judge code 7: not a kitchen"]
    assert "## People's votes" in markdown(report)
    # nobody liked a drawing as it is now: liked names none
    opts.only = ["liked"]
    assert (await run_review(drawing_settings, opts)).reviews == []
    opts.only = []
    every = {r.id: r.people for r in (await run_review(drawing_settings, opts)).reviews}
    assert every[f"item:{item}#1"].stale == 1 and every[f"item:{item}#1"].likes == 0
    # the recommendation check keeps the dislike beside the cards it was cast on
    sv2, client2 = services(drawing_settings)
    checked = await decide_all(
        client2, sv2, Budget(1.0), [], votes=read_votes(drawing_settings.inventory_db_path)
    )
    await client2.aclose()
    by_id = {d.id: d for d in checked}
    assert by_id[f"cards:{item}"].people.reasons == ["owner: wrong socket"]


def tally_digest(sv: object, item: int, n: int) -> str:
    """The digest the API keeps with a vote on the item's picture ``n``."""
    from app.feedback.signals import digest_of

    folder = sv.pictures.folder(item)  # type: ignore[attr-defined]
    return digest_of(folder / f"picture-{n}.jpg")


def test_a_tally_reads_only_its_own_target() -> None:
    from app.feedback import Cast

    votes = [
        Cast(
            target_kind="uses",
            target_id=1,
            target_ref="2",
            vote="dislike",
            reason="",
            digest="",
            owner_code=None,
            created_at="",
        ),
        Cast(
            target_kind="uses",
            target_id=1,
            target_ref="3",
            vote="like",
            reason="",
            digest="",
            owner_code=4,
            created_at="",
        ),
    ]
    assert tally(votes, "uses", 1, "2").dislikes == 1
    assert tally(votes, "uses", 1, "3").likes == 1
    assert tally(votes, "scenarios", 1, "2") == People()
