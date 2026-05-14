"""
backup.py — Local rotating snapshots + Telegram backup.

PURPOSE
=======
Protect the paper trading state database against data loss:
- Level 1: PERSISTENT path (paper_trading/state.db) — already handled by state_manager
- Level 2: Rotating local snapshots (this module) — after each cycle + each close
- Level 3: Telegram backup (this module) — every N hours via sendDocument

WHY THIS MATTERS
================
The bot will run unattended for 10+ days during the user's trip. A single
hardware failure could wipe out weeks of accumulated paper trading data.
This module provides defense in depth:
1. Even if the live DB corrupts, local snapshots preserve recent state
2. Even if the entire machine fails, Telegram has hourly-ish DB copies

ARCHITECTURE
============
BackupManager is the single entry point. It coordinates:
- create_snapshot(): gzip-compressed copy of state.db with timestamp
- rotate_local(): keep only the N most recent snapshots (configurable)
- maybe_send_to_telegram(): check if it's a scheduled hour, send if so

FAIL-SOFT POLICY
================
ALL operations here are best-effort. A backup failure NEVER raises an
exception that would break the trading bot. Errors are logged but the
bot continues. This mirrors the monitoring module's design.
"""
from __future__ import annotations

import gzip
import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from paper_trading import config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    DATACLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class SnapshotResult:
    """Result of a local snapshot operation."""
    ok: bool
    path: Optional[Path] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


@dataclass
class TelegramBackupResult:
    """Result of a Telegram backup send."""
    ok: bool
    http_status: Optional[int] = None
    error: Optional[str] = None
    skipped: bool = False           # True if we didn't send (e.g. not the right hour)
    skip_reason: Optional[str] = None


# ════════════════════════════════════════════════════════════════
#                    LAST-TELEGRAM-BACKUP TRACKER
# ════════════════════════════════════════════════════════════════

def _read_last_telegram_backup_ts() -> Optional[str]:
    """Read the timestamp of the last successful Telegram backup.

    Returns:
        ISO UTC string of last backup, or None if no record (first run).

    Defensive: if the file is corrupted or unreadable, return None
    (we'll just send a backup at the next scheduled hour, harmless).
    """
    path = config.LAST_TELEGRAM_BACKUP_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("last_backup_ts")
    except Exception as e:
        logger.warning("Failed to read last_telegram_backup_ts: %s", e)
        return None


def _write_last_telegram_backup_ts(ts: str) -> None:
    """Persist the timestamp of the last successful Telegram backup.

    Defensive: if write fails, log but don't raise (worst case = duplicate send).
    """
    path = config.LAST_TELEGRAM_BACKUP_FILE
    try:
        path.write_text(json.dumps({"last_backup_ts": ts}, indent=2))
    except Exception as e:
        logger.warning("Failed to write last_telegram_backup_ts: %s", e)


# ════════════════════════════════════════════════════════════════
#                    LOCAL SNAPSHOT FUNCTIONS
# ════════════════════════════════════════════════════════════════

def create_snapshot(
    db_path: Path,
    backup_dir: Path,
    timestamp_iso: Optional[str] = None,
) -> SnapshotResult:
    """Create a gzip-compressed copy of the SQLite DB.

    Args:
        db_path: path to the live state.db
        backup_dir: directory where snapshots are stored
        timestamp_iso: optional, defaults to now in UTC

    Returns:
        SnapshotResult with the path of the created snapshot.

    File format: state_2026-05-14T22-00-10.db.gz
    (':' replaced by '-' for filesystem compatibility)
    """
    if not db_path.exists():
        return SnapshotResult(ok=False, error=f"DB not found: {db_path}")

    if timestamp_iso is None:
        # Strip microseconds for clean filename (e.g. .988448 → nothing)
        timestamp_iso = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    # Sanitize timestamp for filesystem (": → -")
    ts_safe = timestamp_iso.replace(":", "-").replace("+00-00Z", "Z").rstrip("Z")
    # Also strip any leftover microsecond fragment "T21-58-16.988448" → "T21-58-16"
    if "." in ts_safe:
        ts_safe = ts_safe.split(".")[0]
    out_path = backup_dir / f"state_{ts_safe}.db.gz"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        # Use shutil + gzip for atomic-like behavior
        with open(db_path, "rb") as f_in:
            with gzip.open(out_path, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
        size = out_path.stat().st_size
        logger.info("Snapshot created: %s (%d bytes)", out_path.name, size)
        return SnapshotResult(ok=True, path=out_path, size_bytes=size)
    except Exception as e:
        logger.exception("Failed to create snapshot")
        return SnapshotResult(ok=False, error=str(e))


def rotate_local_snapshots(
    backup_dir: Path,
    max_keep: int = 24,
) -> int:
    """Delete oldest snapshots, keep only the `max_keep` most recent.

    Args:
        backup_dir: directory containing snapshots
        max_keep: number of recent snapshots to keep

    Returns:
        Number of snapshots deleted (0 if nothing to do).

    Defensive: failures are logged but don't raise.
    """
    if not backup_dir.exists():
        return 0
    try:
        snapshots = sorted(
            backup_dir.glob("state_*.db.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,  # most recent first
        )
        to_delete = snapshots[max_keep:]
        n_deleted = 0
        for p in to_delete:
            try:
                p.unlink()
                n_deleted += 1
            except Exception as e:
                logger.warning("Failed to delete %s: %s", p.name, e)
        if n_deleted:
            logger.info("Rotated %d old snapshots (kept %d most recent)",
                        n_deleted, max_keep)
        return n_deleted
    except Exception as e:
        logger.exception("Failed to rotate snapshots: %s", e)
        return 0


# ════════════════════════════════════════════════════════════════
#                    TELEGRAM BACKUP
# ════════════════════════════════════════════════════════════════

def _telegram_send_document(
    token: str,
    chat_id: str,
    file_path: Path,
    caption: Optional[str] = None,
    timeout: float = 30.0,
) -> TelegramBackupResult:
    """Send a file as document to a Telegram chat (best-effort, never raises).

    Telegram limit: 50 MB per file via sendDocument API.
    Our gzipped DB should be << 1 MB even after months of trading.
    """
    if not token or not chat_id:
        return TelegramBackupResult(ok=False, error="not_configured")
    if not file_path.exists():
        return TelegramBackupResult(ok=False, error=f"file_not_found: {file_path}")

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": (file_path.name, f)}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            resp = requests.post(url, files=files, data=data, timeout=timeout)
        if resp.status_code == 200:
            return TelegramBackupResult(ok=True, http_status=200)
        return TelegramBackupResult(
            ok=False,
            http_status=resp.status_code,
            error=f"http_{resp.status_code}: {resp.text[:200]}",
        )
    except Exception as e:
        return TelegramBackupResult(ok=False, error=f"exception: {e}")


# ════════════════════════════════════════════════════════════════
#                    BACKUP MANAGER (main entry point)
# ════════════════════════════════════════════════════════════════

class BackupManager:
    """Coordinates local snapshots and Telegram backups for state.db.

    Usage:
        bm = BackupManager()
        bm.snapshot()                              # local snapshot + rotate
        bm.maybe_send_to_telegram(timestamp_iso)   # send if scheduled hour
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
        max_keep: Optional[int] = None,
        telegram_hours_utc: Optional[list[int]] = None,
        telegram_enabled: Optional[bool] = None,
    ):
        self.db_path = db_path or config.STATE_DB_PATH
        self.backup_dir = backup_dir or config.BACKUPS_DIR
        self.max_keep = max_keep if max_keep is not None else config.BACKUP_MAX_KEEP
        self.telegram_hours_utc = (
            telegram_hours_utc if telegram_hours_utc is not None
            else config.TELEGRAM_BACKUP_HOURS_UTC
        )
        self.telegram_enabled = (
            telegram_enabled if telegram_enabled is not None
            else config.TELEGRAM_BACKUP_ENABLED
        )
        # Lazy resolve token / chat_id (read at send time so tests can patch)
        self._telegram_token: Optional[str] = None
        self._telegram_chat_id: Optional[str] = None

    @property
    def telegram_token(self) -> Optional[str]:
        if self._telegram_token is None:
            self._telegram_token = config.TELEGRAM_BOT_TOKEN
        return self._telegram_token

    @property
    def telegram_chat_id(self) -> Optional[str]:
        if self._telegram_chat_id is None:
            self._telegram_chat_id = config.TELEGRAM_CHAT_ID
        return self._telegram_chat_id

    # ─── Local snapshot ───────────────────────────────────────────

    def snapshot(self, timestamp_iso: Optional[str] = None) -> SnapshotResult:
        """Create a local snapshot of state.db and rotate old backups.

        This is the primary entry point called from paper_trader after
        each cycle (and optionally after each close).
        """
        result = create_snapshot(self.db_path, self.backup_dir, timestamp_iso)
        if result.ok:
            rotate_local_snapshots(self.backup_dir, max_keep=self.max_keep)
        return result

    # ─── Telegram backup ──────────────────────────────────────────

    def maybe_send_to_telegram(
        self, timestamp_iso: str,
        force: bool = False,
    ) -> TelegramBackupResult:
        """Check if it's a scheduled hour and send the latest snapshot.

        Args:
            timestamp_iso: current time in ISO UTC format
            force: if True, send regardless of hour or duplicate check

        Returns:
            TelegramBackupResult with skipped=True if not scheduled.

        Logic:
        1. Skip if telegram backup is disabled
        2. Skip if current hour not in TELEGRAM_BACKUP_HOURS_UTC
        3. Skip if we already sent at this hour today (deduplication)
        4. Find the most recent local snapshot
        5. Send it via sendDocument
        6. On success, update last_telegram_backup_ts
        """
        if not self.telegram_enabled and not force:
            return TelegramBackupResult(
                ok=False, skipped=True, skip_reason="telegram_backup_disabled",
            )

        if not self.telegram_token or not self.telegram_chat_id:
            return TelegramBackupResult(
                ok=False, skipped=True, skip_reason="telegram_not_configured",
            )

        try:
            now = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        except Exception as e:
            return TelegramBackupResult(ok=False, error=f"bad_timestamp: {e}")

        current_hour = now.hour

        if not force and current_hour not in self.telegram_hours_utc:
            return TelegramBackupResult(
                ok=True, skipped=True,
                skip_reason=f"hour_{current_hour}_not_scheduled",
            )

        # Deduplication: did we already send at this hour today?
        if not force:
            last_ts = _read_last_telegram_backup_ts()
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    # If last backup was less than 1 hour ago in same hour slot, skip
                    if (now - last_dt).total_seconds() < 3600:
                        return TelegramBackupResult(
                            ok=True, skipped=True,
                            skip_reason="already_sent_recently",
                        )
                except Exception:
                    pass  # corrupted timestamp, proceed with send

        # Find the most recent snapshot
        snapshots = sorted(
            self.backup_dir.glob("state_*.db.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not snapshots:
            return TelegramBackupResult(
                ok=False, error="no_local_snapshot_available",
            )
        latest = snapshots[0]

        # Build caption
        size_kb = latest.stat().st_size / 1024
        caption = (
            f"📦 *Trading bot DB backup*\n"
            f"Snapshot: `{latest.name}`\n"
            f"Size: {size_kb:.1f} KB\n"
            f"Time: {timestamp_iso}"
        )

        # Send
        result = _telegram_send_document(
            token=self.telegram_token,
            chat_id=self.telegram_chat_id,
            file_path=latest,
            caption=caption,
        )

        if result.ok:
            _write_last_telegram_backup_ts(timestamp_iso)
            logger.info("Telegram backup sent: %s (%.1f KB)", latest.name, size_kb)
        else:
            logger.warning("Telegram backup failed: %s", result.error)

        return result


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : self-test
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    import sqlite3

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print("=" * 64)
    print("  backup.py — démo")
    print("=" * 64)

    tmpdir = Path(tempfile.mkdtemp())
    db_path = tmpdir / "state.db"
    backup_dir = tmpdir / "backups"

    # Create a fake DB
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER, value TEXT)")
    conn.executemany("INSERT INTO test VALUES (?, ?)",
                     [(i, f"row_{i}") for i in range(100)])
    conn.commit()
    conn.close()
    db_size = db_path.stat().st_size
    print(f"\nFake DB created: {db_path} ({db_size} bytes)")

    # Test snapshot
    bm = BackupManager(
        db_path=db_path,
        backup_dir=backup_dir,
        max_keep=3,
        telegram_enabled=False,  # No real Telegram in demo
    )

    print("\n[1] Create 5 snapshots (should rotate to keep 3)...")
    for i in range(5):
        ts = f"2026-05-14T22-{i:02d}-00Z".replace("-", ":", 2)[:-1] + "Z"
        # Reformulate cleanly
        ts = f"2026-05-14T22:{i:02d}:00Z"
        result = bm.snapshot(timestamp_iso=ts)
        print(f"  Snapshot {i+1}: ok={result.ok}, size={result.size_bytes}b")
        time.sleep(0.01)  # ensure mtime ordering

    remaining = list(backup_dir.glob("state_*.db.gz"))
    print(f"\n  Snapshots remaining: {len(remaining)} (expected 3)")
    for p in sorted(remaining, key=lambda x: x.stat().st_mtime):
        print(f"    {p.name}")

    # Test Telegram skip (no token in demo)
    print("\n[2] Telegram send attempt (should skip):")
    result = bm.maybe_send_to_telegram("2026-05-14T22:00:00Z")
    print(f"  ok={result.ok}, skipped={result.skipped}, reason={result.skip_reason}")

    print("\n" + "=" * 64)
    print("  backup.py OK (full tests in tests/test_backup.py)")
    print("=" * 64)
