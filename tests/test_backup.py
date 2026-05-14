"""
Tests for paper_trading/backup.py.

Covers:
- create_snapshot: basic creation, missing DB, compression works
- rotate_local_snapshots: keeps N most recent, ignores non-matching files
- BackupManager.snapshot: combined create + rotate
- BackupManager.maybe_send_to_telegram: scheduling, dedup, skip cases
- last_telegram_backup_ts tracker: read/write/missing/corrupted
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from paper_trading.backup import (
    BackupManager,
    SnapshotResult,
    TelegramBackupResult,
    create_snapshot,
    rotate_local_snapshots,
    _read_last_telegram_backup_ts,
    _write_last_telegram_backup_ts,
)


# ─── Helpers ──────────────────────────────────────────────────────

def _make_fake_db(path: Path, n_rows: int = 50) -> None:
    """Create a small SQLite DB at path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE test (id INTEGER, value TEXT)")
    conn.executemany("INSERT INTO test VALUES (?, ?)",
                     [(i, f"row_{i}") for i in range(n_rows)])
    conn.commit()
    conn.close()


# ════════════════════════════════════════════════════════════════
#                    create_snapshot
# ════════════════════════════════════════════════════════════════

def test_create_snapshot_basic(tmp_path):
    """A snapshot is created as a valid gzip file containing the DB."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"

    result = create_snapshot(db, backup_dir, timestamp_iso="2026-05-14T22:00:10Z")

    assert result.ok is True
    assert result.path is not None
    assert result.path.exists()
    assert result.path.suffix == ".gz"
    assert result.path.name.startswith("state_")
    assert ":" not in result.path.name  # colons must be sanitized
    assert result.size_bytes is not None and result.size_bytes > 0

    # The gzip file decompresses back to a valid SQLite DB
    decompressed = tmp_path / "restored.db"
    with gzip.open(result.path, "rb") as f_in:
        decompressed.write_bytes(f_in.read())
    conn = sqlite3.connect(decompressed)
    rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()
    conn.close()
    assert rows[0] == 50


def test_create_snapshot_missing_db(tmp_path):
    """If the DB doesn't exist, snapshot fails gracefully (no raise)."""
    backup_dir = tmp_path / "backups"
    result = create_snapshot(tmp_path / "nonexistent.db", backup_dir,
                             timestamp_iso="2026-05-14T22:00:10Z")
    assert result.ok is False
    assert result.error is not None
    assert "not found" in result.error.lower()


def test_create_snapshot_default_timestamp_uses_now(tmp_path):
    """If timestamp_iso is None, current UTC is used."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"

    result = create_snapshot(db, backup_dir, timestamp_iso=None)
    assert result.ok is True
    # File name should contain "2026" (year of test) — defensive check
    assert "20" in result.path.name


def test_create_snapshot_strips_microseconds_from_filename(tmp_path):
    """Filename should NOT contain microsecond fragments like .988448."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"

    # Pass an ISO timestamp WITH microseconds
    result = create_snapshot(
        db, backup_dir,
        timestamp_iso="2026-05-14T21:58:16.988448Z",
    )
    assert result.ok is True
    # Filename should NOT contain the microsecond part
    assert ".988448" not in result.path.name
    # But the time portion should still be present
    assert "T21-58-16" in result.path.name

    # Default timestamp (None) should also be clean
    result2 = create_snapshot(db, backup_dir, timestamp_iso=None)
    assert result2.ok is True
    # The auto-generated filename should have no decimal point in time portion
    stem = result2.path.name.replace("state_", "").replace(".db.gz", "")
    assert "." not in stem, f"Filename has unexpected '.' in stem: {stem}"


# ════════════════════════════════════════════════════════════════
#                    rotate_local_snapshots
# ════════════════════════════════════════════════════════════════

def test_rotate_keeps_max_n(tmp_path):
    """Rotation deletes oldest files, keeps max_keep most recent."""
    backup_dir = tmp_path / "backups"
    db = tmp_path / "state.db"
    _make_fake_db(db)

    # Create 5 snapshots with controlled timestamps
    paths = []
    for i in range(5):
        result = create_snapshot(db, backup_dir,
                                  timestamp_iso=f"2026-05-14T22:{i:02d}:00Z")
        paths.append(result.path)
        time.sleep(0.01)  # ensure mtime ordering

    assert len(list(backup_dir.glob("state_*.db.gz"))) == 5

    # Rotate to keep only 3
    n_deleted = rotate_local_snapshots(backup_dir, max_keep=3)

    assert n_deleted == 2
    remaining = list(backup_dir.glob("state_*.db.gz"))
    assert len(remaining) == 3
    # The 2 oldest (first created) should be gone
    assert not paths[0].exists()
    assert not paths[1].exists()
    # The 3 newest should remain
    assert paths[2].exists()
    assert paths[3].exists()
    assert paths[4].exists()


def test_rotate_no_op_when_below_max(tmp_path):
    """If fewer files than max_keep, nothing is deleted."""
    backup_dir = tmp_path / "backups"
    db = tmp_path / "state.db"
    _make_fake_db(db)

    for i in range(3):
        create_snapshot(db, backup_dir, timestamp_iso=f"2026-05-14T22:{i:02d}:00Z")
        time.sleep(0.01)

    n_deleted = rotate_local_snapshots(backup_dir, max_keep=10)
    assert n_deleted == 0
    assert len(list(backup_dir.glob("state_*.db.gz"))) == 3


def test_rotate_missing_dir_returns_zero(tmp_path):
    """If backup_dir doesn't exist, rotation is no-op."""
    n_deleted = rotate_local_snapshots(tmp_path / "nonexistent", max_keep=3)
    assert n_deleted == 0


# ════════════════════════════════════════════════════════════════
#                    BackupManager.snapshot (combined)
# ════════════════════════════════════════════════════════════════

def test_manager_snapshot_creates_and_rotates(tmp_path):
    """BackupManager.snapshot() creates a new snapshot AND rotates."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir, max_keep=2,
        telegram_enabled=False,
    )

    for i in range(4):
        bm.snapshot(timestamp_iso=f"2026-05-14T22:{i:02d}:00Z")
        time.sleep(0.01)

    # max_keep=2 → only 2 files should remain after all 4 calls
    remaining = list(backup_dir.glob("state_*.db.gz"))
    assert len(remaining) == 2


# ════════════════════════════════════════════════════════════════
#                    last_telegram_backup_ts tracker
# ════════════════════════════════════════════════════════════════

def test_last_telegram_backup_ts_read_missing(tmp_path, monkeypatch):
    """If the file doesn't exist, _read returns None."""
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )
    assert _read_last_telegram_backup_ts() is None


def test_last_telegram_backup_ts_write_and_read(tmp_path, monkeypatch):
    """Write, then read returns the same timestamp."""
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )
    _write_last_telegram_backup_ts("2026-05-14T12:00:00Z")
    assert _read_last_telegram_backup_ts() == "2026-05-14T12:00:00Z"


def test_last_telegram_backup_ts_corrupted_returns_none(tmp_path, monkeypatch):
    """Corrupted JSON file returns None (defensive)."""
    f = tmp_path / ".last_telegram_backup"
    f.write_text("this is not json {{")
    monkeypatch.setattr("paper_trading.config.LAST_TELEGRAM_BACKUP_FILE", f)
    assert _read_last_telegram_backup_ts() is None


# ════════════════════════════════════════════════════════════════
#                    BackupManager.maybe_send_to_telegram
# ════════════════════════════════════════════════════════════════

def test_telegram_skip_when_disabled(tmp_path):
    """If telegram_enabled=False, skip silently."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    bm = BackupManager(
        db_path=db, backup_dir=tmp_path / "backups",
        telegram_enabled=False,
    )
    result = bm.maybe_send_to_telegram("2026-05-14T12:00:00Z")
    assert result.skipped is True
    assert "disabled" in result.skip_reason


def test_telegram_skip_wrong_hour(tmp_path, monkeypatch):
    """If current hour not in scheduled hours, skip."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    bm = BackupManager(
        db_path=db, backup_dir=tmp_path / "backups",
        telegram_hours_utc=[0, 6, 12, 18],
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )

    # 22:00 is NOT in [0,6,12,18]
    result = bm.maybe_send_to_telegram("2026-05-14T22:00:10Z")
    assert result.skipped is True
    assert "not_scheduled" in result.skip_reason


def test_telegram_skip_recently_sent(tmp_path, monkeypatch):
    """Dedup: if last backup < 1h ago, skip even on scheduled hour."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"
    create_snapshot(db, backup_dir, timestamp_iso="2026-05-14T11:55:00Z")

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir,
        telegram_hours_utc=[12],
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )
    # Pre-mark a recent backup
    _write_last_telegram_backup_ts("2026-05-14T12:00:00Z")

    # 30 minutes later, scheduled hour but recent backup
    result = bm.maybe_send_to_telegram("2026-05-14T12:30:00Z")
    assert result.skipped is True
    assert "already_sent_recently" in result.skip_reason


def test_telegram_no_snapshots_available(tmp_path, monkeypatch):
    """If no local snapshot exists, return error (nothing to send)."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir,
        telegram_hours_utc=[12],
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )

    result = bm.maybe_send_to_telegram("2026-05-14T12:00:00Z")
    assert result.ok is False
    assert "no_local_snapshot" in result.error


def test_telegram_send_success_updates_tracker(tmp_path, monkeypatch):
    """On successful send, last_telegram_backup_ts is updated."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"
    create_snapshot(db, backup_dir, timestamp_iso="2026-05-14T11:55:00Z")
    tracker_path = tmp_path / ".last_telegram_backup"

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir,
        telegram_hours_utc=[12],
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE", tracker_path,
    )

    # Mock requests.post to simulate Telegram success
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("paper_trading.backup.requests.post", return_value=mock_response) as mock_post:
        result = bm.maybe_send_to_telegram("2026-05-14T12:00:00Z")

    assert result.ok is True
    assert result.http_status == 200
    mock_post.assert_called_once()
    # Tracker updated
    assert tracker_path.exists()
    assert _read_last_telegram_backup_ts() == "2026-05-14T12:00:00Z"


def test_telegram_send_failure_does_not_update_tracker(tmp_path, monkeypatch):
    """On Telegram API failure, tracker is NOT updated (retry next time)."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"
    create_snapshot(db, backup_dir, timestamp_iso="2026-05-14T11:55:00Z")
    tracker_path = tmp_path / ".last_telegram_backup"

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir,
        telegram_hours_utc=[12],
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE", tracker_path,
    )

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Server error"
    with patch("paper_trading.backup.requests.post", return_value=mock_response):
        result = bm.maybe_send_to_telegram("2026-05-14T12:00:00Z")

    assert result.ok is False
    assert result.http_status == 500
    # Tracker NOT updated → next cycle will retry
    assert not tracker_path.exists()


def test_telegram_force_sends_regardless_of_hour(tmp_path, monkeypatch):
    """force=True bypasses hour/dedup checks (for manual triggers)."""
    db = tmp_path / "state.db"
    _make_fake_db(db)
    backup_dir = tmp_path / "backups"
    create_snapshot(db, backup_dir, timestamp_iso="2026-05-14T11:55:00Z")

    bm = BackupManager(
        db_path=db, backup_dir=backup_dir,
        telegram_hours_utc=[0],  # NOT 22
        telegram_enabled=True,
    )
    bm._telegram_token = "fake_token"
    bm._telegram_chat_id = "fake_chat"
    monkeypatch.setattr(
        "paper_trading.config.LAST_TELEGRAM_BACKUP_FILE",
        tmp_path / ".last_telegram_backup",
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("paper_trading.backup.requests.post", return_value=mock_response):
        result = bm.maybe_send_to_telegram("2026-05-14T22:00:00Z", force=True)

    assert result.ok is True
    assert result.skipped is False
