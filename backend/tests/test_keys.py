"""Access codes as records: issued once, matched by hash, ended by expiry or by hand."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.inventory.store import Store
from app.keys import PREFIX, AccessKeyError, AccessKeys, new_code
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


def test_a_code_claimed_once_takes_its_label_for_good(tmp_path: Path) -> None:
    keys = keys_in(tmp_path)
    until = datetime.now(UTC) + timedelta(days=2)
    code, key = keys.issue("phone abcd1234", until=until, once=True)
    assert key.expires_at == until.replace(microsecond=0).isoformat()
    assert keys.get(key.id) == key and keys.get(9999) is None
    with pytest.raises(AccessKeyError, match="already"):
        keys.issue("phone abcd1234", until=until, once=True)
    keys.revoke("phone abcd1234")
    with pytest.raises(AccessKeyError, match="already"):
        keys.issue("phone abcd1234", until=until, once=True)
    keys.issue("phone abcd1234", 1)  # a plain issue sees only current codes, as before
    with pytest.raises(AccessKeyError, match="passed"):
        keys.issue("late", until=datetime.now(UTC) - timedelta(seconds=1))
    assert keys.match(code) is None
