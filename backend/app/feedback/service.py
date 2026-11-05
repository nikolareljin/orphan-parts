"""The votes, kept in the inventory's file: one per person per target, changed or taken back
at will. A judge's code votes under its own id and counts its own vote alone; the owner
counts every vote. Nothing here is sent to a model."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.feedback.schema import Cast, Tally, Target, VoteCreate
from app.inventory import Inventory
from app.inventory.service import now
from app.ops.door import sandbox

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
