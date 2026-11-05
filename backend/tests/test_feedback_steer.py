"""A dislike steers the next drawing of the same thing: its reasons become what the drawing
avoids, a liked drawing's correction what it keeps, and other projects of the same kind add a
few of theirs. Without votes the request is word for word what it was (so every recording still
answers); a judge's votes steer that judge's own drawings alone, the owner's the owner's, the
demo visitor's none; and an older file at schema version 15 opens with every row kept."""

import sqlite3
from pathlib import Path

import pytest

from app.config import Settings
from app.feedback import Feedback, VoteCreate
from app.feedback.steer import AVOID_MAX, KIND_MAX, NO_REASON, Steer, assemble, clean
from app.inventory import Inventory, ItemCreate
from app.inventory.store import MIGRATIONS, SCHEMA_VERSION, Store
from app.model_api import CostLedger, ModelApiClient
from app.ops.door import judge_code, live_request
from app.picture.service import Pictures, prompt_for
from app.projects.templates import Templates
from tests.conftest import RECORDED_FIXTURES

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("v1_params")]

FAKE_KEY = "-".join(("ABCDE", "12345", "FGHIJ", "67890", "KLMNO"))


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


# --- the prompt's added segments ------------------------------------------------------------


def test_no_votes_add_nothing() -> None:
    assert assemble([]).segments() == []
    assert Steer().segments() == []


def test_reasons_are_deduped_cut_and_limited_newest_first() -> None:
    steer = assemble(["Too dark", "too  dark", "no\nscreen", "x" * 500, "fourth", "fifth"])
    assert steer.avoid[:2] == ["Too dark", "no screen"]
    assert len(steer.avoid) == AVOID_MAX
    assert len(steer.avoid[2]) == 200
    assert steer.segments() == ["Avoid: " + "; ".join(steer.avoid)]


def test_a_dislike_without_a_reason_asks_for_another_composition() -> None:
    assert assemble(["", ""]).avoid == [NO_REASON]
    assert assemble(["", "too dark"]).avoid == [NO_REASON, "too dark"]


def test_the_kind_adds_a_smaller_set_and_a_liked_correction_is_kept() -> None:
    steer = assemble(
        ["too dark"], ["Too dark", "no joystick", "wrong cabinet", "too tall"], ["", "show a lid"]
    )
    assert steer.avoid == ["too dark", "no joystick", "wrong cabinet"]
    assert len(steer.avoid) == 1 + KIND_MAX
    assert steer.keep == "show a lid"
    assert steer.segments() == [
        "Avoid: too dark; no joystick; wrong cabinet",
        "Keep: show a lid",
    ]
    # a kind's reason without an own dislike still steers; a kind's empty reason does not
    assert assemble([], ["", "no joystick"]).avoid == ["no joystick"]


def test_a_private_value_in_a_reason_is_masked() -> None:
    said = clean(f"it shows the key {FAKE_KEY}")
    assert FAKE_KEY not in said and said.startswith("it shows the key")


# --- the drawing asked for ------------------------------------------------------------------


class _Spy:
    """The model client, with every prompt it was asked to draw kept."""

    def __init__(self, client: ModelApiClient) -> None:
        self.client = client
        self.prompts: list[str] = []

    async def picture(self, prompt: str) -> object:
        self.prompts.append(prompt)
        return await self.client.picture(prompt)


def _pictures(settings: Settings) -> tuple[Pictures, Inventory, Feedback, _Spy, ModelApiClient]:
    inventory = Inventory(settings)
    feedback = Feedback(inventory)
    client = ModelApiClient(settings, CostLedger(cap_usd=25.0))
    spy = _Spy(client)
    pictures = Pictures(settings, client, inventory, Templates(), feedback)
    pictures.client = spy  # type: ignore[assignment]
    return pictures, inventory, feedback, spy, client


def _vote(feedback: Feedback, item: int, n: int, vote: str, reason: str = "") -> None:
    feedback.vote(
        VoteCreate(
            target_kind="item_picture",
            target_id=item,
            target_ref=str(n),
            vote=vote,
            reason=reason,
        )
    )


async def test_without_votes_the_request_is_word_for_word_what_it_was(
    drawing_settings: Settings,
) -> None:
    pictures, inventory, _, spy, client = _pictures(drawing_settings)
    item = inventory.create(ItemCreate(item_type="laptop", condition="scuffed lid"))
    plain = Pictures(drawing_settings, client, inventory, Templates())
    plain.client = spy  # type: ignore[assignment]
    first = await pictures.draw(item.id, "a lamp")
    await plain.draw(item.id, "a lamp")
    expected = prompt_for(inventory.get(item.id), "a lamp")
    assert spy.prompts == [expected, expected]
    assert (first.avoided, first.kept, first.brief) == ([], "", "")
    await client.aclose()


async def test_a_dislike_steers_the_next_drawing_of_the_same_item(
    drawing_settings: Settings,
) -> None:
    pictures, inventory, feedback, spy, client = _pictures(drawing_settings)
    item = inventory.create(ItemCreate(item_type="laptop"))
    other = inventory.create(ItemCreate(item_type="laptop"))
    first = await pictures.draw(item.id, "a lamp", "show the hinge")
    _vote(feedback, item.id, first.n, "like")
    second = await pictures.draw(item.id, "a lamp")
    _vote(feedback, item.id, second.n, "dislike", "the shade is too dark")
    third = await pictures.draw(item.id, "a lamp")
    base = prompt_for(inventory.get(item.id), "a lamp")
    assert "Keep: show the hinge" in spy.prompts[1]
    assert "Avoid: the shade is too dark" in spy.prompts[2]
    assert spy.prompts[2] == prompt_for(
        inventory.get(item.id),
        "a lamp",
        steer=["Avoid: the shade is too dark", "Keep: show the hinge"],
    )
    assert spy.prompts[2] != base
    assert third.avoided == ["the shade is too dark"] and third.kept == "show the hinge"
    # the record says it, and another item is not steered by it
    assert pictures.list(item.id).pictures[-1].avoided == ["the shade is too dark"]
    await pictures.draw(other.id, "a lamp")
    assert spy.prompts[3] == prompt_for(inventory.get(other.id), "a lamp")
    await client.aclose()


async def test_a_judges_votes_steer_its_own_drawings_alone_and_the_visitor_none(
    drawing_settings: Settings,
) -> None:
    pictures, inventory, feedback, spy, client = _pictures(drawing_settings)
    item = inventory.create(ItemCreate(item_type="laptop"))
    drawn = await pictures.draw(item.id, "a lamp")
    token = judge_code.set(7)
    try:
        _vote(feedback, item.id, drawn.n, "dislike", "a judge's reason")
        assert [v[2] for v in feedback.drawing_votes("item_picture", item.id)] == [
            "a judge's reason"
        ]
    finally:
        judge_code.reset(token)
    # the owner's next drawing is not steered by the judge's vote
    await pictures.draw(item.id, "a lamp")
    assert "a judge's reason" not in spy.prompts[-1]
    _vote(feedback, item.id, drawn.n, "dislike", "the owner's reason")
    door = live_request.set(False)
    try:
        assert feedback.drawing_votes("item_picture", item.id) == []
        shown = pictures.list(item.id).pictures[0].model_dump()
    finally:
        live_request.reset(door)
    assert shown["avoided"] == [] and shown["kept"] == ""
    await client.aclose()


def test_a_card_and_a_kind_of_project_read_their_own_votes(drawing_settings: Settings) -> None:
    inventory = Inventory(drawing_settings)
    feedback = Feedback(inventory)
    with inventory.store.connect() as conn:
        for pid, template in ((1, "arcade_table"), (2, "arcade_table"), (3, "smart_mirror")):
            conn.execute(
                "INSERT INTO projects (id, template, title, status, version, content,"
                " created_at, updated_at) VALUES (?, ?, 't', 'proposed', 1, '{}', 'x', 'x')",
                (pid, template),
            )

    def cast(kind: str, tid: int, ref: str, reason: str) -> None:
        feedback.vote(
            VoteCreate(
                target_kind=kind,
                target_id=tid,
                target_ref=ref,
                vote="dislike",
                reason=reason,
            )
        )

    cast("card_picture", 4, "9/0/1", "card zero")
    cast("card_picture", 4, "9/1/1", "card one")
    assert [v[2] for v in feedback.drawing_votes("card_picture", 4, "9/0/")] == ["card zero"]
    cast("project_picture", 2, "1", "no joystick")
    cast("project_picture", 3, "1", "no frame")
    assert feedback.kind_reasons("arcade_table", 1) == ["no joystick"]
    assert feedback.kind_reasons("arcade_table", 2) == []
    assert feedback.kind_reasons("", 1) == []


# --- the file the votes are kept in ---------------------------------------------------------


def test_a_version_15_file_with_data_opens_at_16_with_every_row_kept(tmp_path: Path) -> None:
    """The hosted volume holds a version 15 file: the step adds the votes' table and nothing
    else, a second start finds nothing to do, and every row reads as before."""
    db = tmp_path / "inventory.sqlite3"
    Store(db, migrations={v: MIGRATIONS[v] for v in range(1, 16)})
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO items (name, item_type, created_at, updated_at)"
        " VALUES ('old laptop', 'laptop', 'x', 'x')"
    )
    conn.commit()
    before = {
        t: conn.execute(f"SELECT * FROM {t}").fetchall()
        for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 15
    conn.close()
    assert SCHEMA_VERSION == 16
    for _ in range(2):
        Store(db)
        conn = sqlite3.connect(db)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
        for table, rows in before.items():
            assert conn.execute(f"SELECT * FROM {table}").fetchall() == rows
        assert conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 0
        conn.close()
