"""Access codes as records: issued once, matched by hash, ended by expiry or by hand."""

import hashlib
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.inventory.store import Store
from app.keys import PREFIX, AccessKeyError, AccessKeys, master_tag, new_code
from app.keys.__main__ import main


def keys_in(tmp_path: Path) -> AccessKeys:
    return AccessKeys(Store(tmp_path / "inventory.sqlite3"))


def test_a_code_is_issued_once_and_kept_as_a_hash(tmp_path: Path) -> None:
    keys = keys_in(tmp_path)
    code, key = keys.issue("judges", 7)
    assert code.startswith(PREFIX) and len(code) > 30
    assert key.label == "judges" and key.state() == "current"
    assert key.expires_at is not None and key.revoked_at is None
    with Store(tmp_path / "inventory.sqlite3").connect() as conn:
        row = conn.execute("SELECT hash FROM access_keys").fetchone()
    assert code not in row["hash"] and len(row["hash"]) == 64
    assert keys.match(code) is not None and keys.match(code).label == "judges"  # type: ignore[union-attr]
    assert keys.match(code + "x") is None
    assert keys.match("not-ours") is None
    assert keys.match(new_code()) is None


def test_expiry_and_revocation_end_a_code(tmp_path: Path) -> None:
    keys = keys_in(tmp_path)
    forever, kept = keys.issue("family")
    assert kept.expires_at is None
    short, soon = keys.issue("visitor", 1)
    assert keys.match(short) is not None
    # a day later the short one is gone, the other stands
    later = datetime.now(UTC) + timedelta(days=2)
    assert soon.state(later) == "expired" and kept.state(later) == "current"
    with Store(tmp_path / "inventory.sqlite3").connect() as conn:
        conn.execute(
            "UPDATE access_keys SET expires_at = ? WHERE label = 'visitor'",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    assert keys.match(short) is None
    gone = keys.revoke("family")
    assert gone.state() == "revoked" and gone.revoked_at is not None
    assert keys.match(forever) is None
    assert [k.state() for k in keys.all()] == ["revoked", "expired"]


def test_labels_are_checked_and_unique_among_current_codes(tmp_path: Path) -> None:
    keys = keys_in(tmp_path)
    with pytest.raises(AccessKeyError, match="blank"):
        keys.issue("  ")
    with pytest.raises(AccessKeyError, match="longer"):
        keys.issue("x" * 61)
    with pytest.raises(AccessKeyError, match="at least 1"):
        keys.issue("judges", 0)
    keys.issue("judges", 7)
    with pytest.raises(AccessKeyError, match="revoke it first"):
        keys.issue("judges", 7)
    keys.revoke("judges")
    keys.issue("judges", 7)  # the label is free again once the old one is revoked
    with Store(tmp_path / "inventory.sqlite3").connect() as conn:
        conn.execute(
            "UPDATE access_keys SET expires_at = ? WHERE label = 'judges' AND revoked_at IS NULL",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
    reissued, _ = keys.issue("judges", 7)  # and once it has expired
    kept = keys.match(reissued)
    assert kept is not None and keys.stamp(kept.id) == kept.created_at
    assert keys.stamp(9999) is None  # no such record
    keys.revoke("judges")  # the newest record with the label, not the expired one
    assert keys.match(reissued) is None
    with pytest.raises(AccessKeyError, match="no current code"):
        keys.revoke("nobody")


def test_the_command_issues_lists_and_revokes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    keys = keys_in(tmp_path)
    assert main(["issue", "--label", "judges", "--days", "7"], keys) == 0
    out, err = capsys.readouterr()
    label, code = out.strip().split(": ")
    assert label == "judges" and code.startswith(PREFIX)
    assert "shown once" in err
    assert keys.match(code) is not None
    assert main(["list"], keys) == 0
    out, _ = capsys.readouterr()
    assert "judges\tcurrent" in out
    assert main(["revoke", "judges"], keys) == 0
    assert "revoked at" in capsys.readouterr()[0]
    assert main(["revoke", "judges"], keys) == 2
    assert "no current code" in capsys.readouterr()[1]
    assert main(["list"], keys) == 0
    assert "revoked" in capsys.readouterr()[0]


def test_the_master_tag_is_a_slow_salted_digest() -> None:
    tag = master_tag("the-master-code")
    slow = hashlib.pbkdf2_hmac("sha256", b"the-master-code", b"opl-phone-master", 200_000)
    assert tag == slow[:8].hex() and len(tag) == 16
    assert tag != hashlib.sha256(b"the-master-code").hexdigest()[:16]
    assert master_tag("a-new-master-code") != tag and master_tag("") == ""


def test_a_revoke_on_another_connection_lands_before_the_claim_reads_its_parent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inventory.sqlite3"
    keys = AccessKeys(Store(path))
    _, guest = keys.issue("guest", 2)
    other = sqlite3.connect(path, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    ended: list[str] = []

    def claim() -> None:
        try:
            keys.issue_child("phone racing1", 30, parent=guest.id, stamp=guest.created_at)
        except AccessKeyError as exc:
            ended.append(str(exc))

    worker = threading.Thread(target=claim)
    worker.start()
    time.sleep(0.3)
    # the claim waits for the write lock the revoke holds, and reads the parent after it
    assert worker.is_alive()
    other.execute("UPDATE access_keys SET revoked_at = ? WHERE id = ?", ("2026-01-01", guest.id))
    other.execute("COMMIT")
    other.close()
    worker.join(10)
    assert ended == ["the code that paired this phone has ended"]
    assert [k.label for k in keys.all()] == ["guest"]


def test_a_phone_code_is_claimed_once_and_stands_with_its_parent(tmp_path: Path) -> None:
    keys = AccessKeys(Store(tmp_path / "inventory.sqlite3"), master_tag("the-master-code"))
    _, guest = keys.issue("guest", 2)
    code, phone = keys.issue_child("phone abcd1234", 30, parent=guest.id, stamp=guest.created_at)
    assert phone.expires_at == guest.expires_at and phone.parent_id == guest.id
    assert keys.match(code) == phone and keys.stamp(phone.id) == phone.created_at
    with pytest.raises(AccessKeyError, match="already"):
        keys.issue_child("phone abcd1234", 30, parent=guest.id, stamp=guest.created_at)
    # a stamp that is not the parent's (a reset reused the id) is a parent that has ended
    with pytest.raises(AccessKeyError, match="has ended"):
        keys.issue_child("phone other", 30, parent=guest.id, stamp="2026-01-01T00:00:00+00:00")
    with pytest.raises(AccessKeyError, match="another phone"):
        keys.issue_child("phone grand", 30, parent=phone.id, stamp=phone.created_at)
    # a parent that runs out ends the phone's record with it
    _, aging = keys.issue("aging", 2)
    _, child = keys.issue_child("phone aging1", 30, parent=aging.id, stamp=aging.created_at)
    assert keys.stamp(child.id) == child.created_at
    past = (datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=0).isoformat()
    with keys.store.connect() as conn:
        conn.execute("UPDATE access_keys SET expires_at = ? WHERE id = ?", (past, aging.id))
    assert keys.stamp(child.id) is None
    keys.revoke("guest")
    assert keys.match(code) is None and keys.stamp(phone.id) is None
    with pytest.raises(AccessKeyError, match="has ended"):
        keys.issue_child("phone late", 30, parent=guest.id, stamp=guest.created_at)
    # under the master code: tagged with it, and gone once the tag is another
    code, phone = keys.issue_child("phone master1", 5, parent=0)
    assert phone.master and phone.parent_id is None and keys.match(code) == phone
    rotated = AccessKeys(keys.store, master_tag("a-new-master-code"))
    assert rotated.match(code) is None and rotated.stamp(phone.id) is None
    with pytest.raises(AccessKeyError, match="no master code"):
        AccessKeys(keys.store).issue_child("phone none", 5)
    # the label is taken for good, revoked or not; a plain issue sees only current codes
    keys.revoke("phone master1")
    with pytest.raises(AccessKeyError, match="already"):
        keys.issue_child("phone master1", 5)
    keys.issue("phone master1", 1)
