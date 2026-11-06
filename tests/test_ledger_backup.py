import sqlite3
import pytest

from beli_tool.ledger import Ledger


def test_startup_backs_up_the_previous_run(tmp_path):
    db = tmp_path / "ledger.sqlite"
    Ledger(db).mark_added("p1", "Lilia", "been", "loved")
    Ledger(db)  # a second run backs up what the first left behind
    bak = tmp_path / "ledger.sqlite.bak"
    assert bak.exists()
    rows = sqlite3.connect(bak).execute("SELECT place_id FROM handled").fetchall()
    assert rows == [("p1",)]


def test_no_backup_on_first_ever_run(tmp_path):
    db = tmp_path / "ledger.sqlite"
    Ledger(db)  # nothing to back up yet
    assert not (tmp_path / "ledger.sqlite.bak").exists()


def test_in_memory_ledger_does_not_try_to_back_up():
    Ledger(":memory:")  # must not raise or write a ":memory:.bak" file


def test_backup_failure_blocks_launch_without_losing_source(tmp_path, monkeypatch):
    db = tmp_path / "ledger.sqlite"
    Ledger(db).mark_added("p1", "Lilia", "been", None)
    def boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr("beli_tool.ledger.os.replace", boom)
    with pytest.raises(OSError):
        Ledger(db)
    assert sqlite3.connect(db).execute("SELECT place_id FROM handled").fetchall() == [("p1",)]
    assert not list(tmp_path.glob('.ledger-backup-*'))
