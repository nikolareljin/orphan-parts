"""The votes, kept in the inventory's file: one per person per target, changed or taken back
at will. A judge's code votes under its own id and counts its own vote alone; the owner
counts every vote. Nothing here calls a model; the reasons a person gave with dislikes of a
drawing are read for that person's next drawing of the same thing (``drawing_votes``)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.feedback.schema import Cast, Tally, Target, VoteCreate
from app.inventory import Inventory
from app.inventory.service import now
from app.ops.door import for_visitor, sandbox

log = logging.getLogger("app.feedback")


class Feedback:
    def __init__(self, inventory: Inventory) -> None:
        self.store = inventory.store

    @staticmethod
    def _where(t: Target) -> tuple[str, tuple[object, ...]]:
        return (
            "target_kind = ? AND target_id = ? AND target_ref = ?",
            (t.target_kind, t.target_id, t.target_ref),
        )

    @staticmethod
    def _voter() -> tuple[str, tuple[object, ...]]:
        judge = sandbox()
        return ("owner_code = ?", (judge,)) if judge else ("owner_code IS NULL", ())

    def tally(self, t: Target) -> Tally:
        """The counts and the caller's own vote: the owner counts everyone's, a judge's code
        its own alone (another judge's vote is never read for it)."""
        where, args = self._where(t)
        voter, who = self._voter()
        # the owner counts every vote; a judge's code its own
        counted, cargs = (f"{where} AND {voter}", (*args, *who)) if sandbox() else (where, args)
        with self.store.connect() as conn:
            rows = conn.execute(
                f"SELECT vote, COUNT(*) AS n FROM feedback WHERE {counted} GROUP BY vote", cargs
            ).fetchall()
            mine = conn.execute(
                f"SELECT vote, reason FROM feedback WHERE {where} AND {voter}", (*args, *who)
            ).fetchone()
        n = {r["vote"]: int(r["n"]) for r in rows}
        return Tally(
            **t.model_dump(include={"target_kind", "target_id", "target_ref"}),
            likes=n.get("like", 0),
            dislikes=n.get("dislike", 0),
            mine=mine["vote"] if mine else None,
            reason=mine["reason"] if mine else "",
        )

    def vote(self, spec: VoteCreate, digest: str = "") -> Tally:
        """The caller's vote on the target, in place of any they cast before."""
        where, args = self._where(spec)
        voter, who = self._voter()
        with self.store.connect() as conn:
            conn.execute(f"DELETE FROM feedback WHERE {where} AND {voter}", (*args, *who))
            conn.execute(
                "INSERT INTO feedback (target_kind, target_id, target_ref, vote, reason, digest,"
                " owner_code, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (*args, spec.vote, spec.reason, digest, sandbox() or None, now()),
            )
        log.info("feedback", extra={"kind": spec.target_kind, "vote": spec.vote})
        return self.tally(spec)

    def withdraw(self, t: Target) -> Tally:
        """The caller's vote taken back; nothing happens when there is none."""
        where, args = self._where(t)
        voter, who = self._voter()
        with self.store.connect() as conn:
            conn.execute(f"DELETE FROM feedback WHERE {where} AND {voter}", (*args, *who))
        return self.tally(t)

    def drawing_votes(
        self, kind: str, target_id: int, ref_prefix: str = ""
    ) -> list[tuple[str, str, str]]:
        """The caller's own votes on the drawings of one target, newest first, as (ref, vote,
        reason): what steers the next drawing of it. ``ref_prefix`` narrows a card's drawings
        to the card ("<scenarios id>/<card>/"). A judge's code reads its own votes, the owner
        the owner's alone (a judge's vote never steers the owner's drawings); the demo visitor
        none."""
        if for_visitor():
            return []
        voter, who = self._voter()
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT target_ref, vote, reason FROM feedback WHERE target_kind = ?"
                f" AND target_id = ? AND substr(target_ref, 1, ?) = ? AND {voter}"
                " ORDER BY id DESC",
                (kind, target_id, len(ref_prefix), ref_prefix, *who),
            ).fetchall()
        return [(r["target_ref"], r["vote"], r["reason"]) for r in rows]

    def kind_reasons(self, template: str, project_id: int) -> list[str]:
        """The reasons the caller gave with dislikes of drawings of other projects of the same
        kind (template), newest first; the same voter rule as ``drawing_votes``."""
        if for_visitor() or not template:
            return []
        voter, who = self._voter()
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT f.reason FROM feedback f JOIN projects p ON p.id = f.target_id"
                " WHERE f.target_kind = 'project_picture' AND f.vote = 'dislike'"
                f" AND f.reason != '' AND p.template = ? AND p.id != ? AND f.{voter}"
                " ORDER BY f.id DESC LIMIT 20",
                (template, project_id, *who),
            ).fetchall()
        return [r["reason"] for r in rows]


def read_votes(db: Path) -> list[Cast]:
    """Every vote in an inventory file, read-only, oldest first: what the review tools take as
    a person's signal. A file without the table (an older build's) has none."""
    if not db.is_file():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT target_kind, target_id, target_ref, vote, reason, digest, owner_code,"
            " created_at FROM feedback ORDER BY id"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [Cast(**dict(r)) for r in rows]
