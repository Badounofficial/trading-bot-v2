"""
validate_backup_integration.py — Targeted test of the FULL backup path.

WHAT THIS DOES
==============
Exercises the EXACT production path that runs at every cycle:
    paper_trader.run_one_cycle()
        → ... cycle work ...
        → _post_cycle_backup(ts)
            → backup_manager.snapshot()
            → backup_manager.maybe_send_to_telegram()

Unlike manual_backup_to_telegram.py which calls BackupManager directly,
this script goes through PaperTrader so we validate:
1. The hook _post_cycle_backup is reached
2. snapshot() creates a real file
3. maybe_send_to_telegram() sends because timestamp = 12:00 UTC (scheduled)
4. NEW LOGS (INFO/WARNING) from May 15 fix appear in terminal output

WHY THIS IS DIFFERENT FROM live_test_3_cycles.py
=================================================
This is a "single cycle, fake timestamp" test — runs in ~10 seconds total.
live_test_3_cycles.py is the "real" 3h test that waits for actual UTC hours.

USAGE
=====
    python -m scripts.validate_backup_integration

EXPECTED OUTPUT
===============
Logs you SHOULD see:
- "Snapshot created: state_2026-05-15T12-00-00.db.gz (XXX bytes)"
- "Telegram backup sent: state_XXX.db.gz (X.X KB)"

What you should see ON TELEGRAM
================================
A .db.gz file should arrive on your phone within seconds.
"""
from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from paper_trading import config
from paper_trading.backup import (
    BackupManager,
    _read_last_telegram_backup_ts,
)
from paper_trading.monitoring import Monitor, JsonLineLogger, TelegramAlerter
from paper_trading.paper_trader import PaperTrader
from paper_trading.state_manager import StateManager, EquitySnapshot


def _make_fake_h1(n_bars: int = 720) -> pd.DataFrame:
    """Build a synthetic H1 DataFrame just to satisfy the cycle path.

    Strategy will likely find no setup on synthetic data, which is fine:
    we only care that the cycle runs and reaches _post_cycle_backup.
    """
    end = pd.Timestamp("2026-05-15T11:00:00Z", tz="UTC")
    idx = pd.date_range(end=end, periods=n_bars, freq="1h", tz="UTC")
    base = 80000.0
    # Simple synthetic price walk
    closes = pd.Series(
        [base + i * 0.1 for i in range(n_bars)], index=idx,
    )
    df = pd.DataFrame({
        "open": closes,
        "high": closes + 50,
        "low": closes - 50,
        "close": closes,
        "volume": 1000.0,
    }, index=idx)
    df.index.name = "timestamp"
    return df


def main():
    print("=" * 72)
    print("  VALIDATE BACKUP INTEGRATION — full prod path test")
    print("=" * 72)

    # ── 1. Setup temp workspace ──
    workdir = Path(tempfile.mkdtemp(prefix="validate_backup_"))
    db_path = workdir / "state.db"
    backup_dir = workdir / "backups"
    logs_dir = workdir / "logs"
    backup_dir.mkdir()
    logs_dir.mkdir()
    print(f"\nTemp workspace: {workdir}")

    # Clear the production tracker so we don't get false dedup
    if config.LAST_TELEGRAM_BACKUP_FILE.exists():
        backup_ts = _read_last_telegram_backup_ts()
        print(f"\nClearing production tracker (was: {backup_ts})")
        config.LAST_TELEGRAM_BACKUP_FILE.unlink()
    else:
        print("\nProduction tracker is empty — clean state.")

    # ── 2. Setup PaperTrader with mocked data_fetcher ──
    # We don't want to actually fetch from Kraken (we want to focus on
    # the backup path, not the data fetch). Provide synthetic data.
    sm = StateManager(db_path=db_path)
    json_logger = JsonLineLogger(logs_dir=logs_dir)
    alerter = TelegramAlerter()  # Real Telegram from .env
    monitor = Monitor(json_logger=json_logger, alerter=alerter)
    backup_manager = BackupManager(
        db_path=db_path,
        backup_dir=backup_dir,
        telegram_enabled=True,
    )

    print(f"\nTelegram enabled: {alerter.enabled}")
    if not alerter.enabled:
        print("⚠ Telegram is DISABLED — Telegram step will skip.")

    # Synthetic data fetcher: same dataset for all assets
    fake_h1 = _make_fake_h1(n_bars=720)
    fake_fetcher = lambda: {asset: fake_h1.copy() for asset in config.ASSETS}

    # Real adapter is fine — synthetic data is unlikely to produce trades
    trader = PaperTrader(
        state_manager=sm,
        monitor=monitor,
        data_fetcher=fake_fetcher,
        backup_manager=backup_manager,
    )

    # ── 3. Pre-record an equity snapshot to avoid HALT on first cycle ──
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-15T11:00:00Z",
            cash=1000.0,
            open_positions_value=0.0,
            equity=1000.0,
            peak_equity=1000.0,
            drawdown_pct=0.0,
        ))

    # ── 4. Run ONE cycle with a forced timestamp at 12:00 UTC ──
    # This is the key: timestamp_iso="...T12:00:10Z" → hour 12
    # → IN TELEGRAM_BACKUP_HOURS_UTC = [0, 6, 12, 18]
    # → backup should be sent.
    forced_ts = "2026-05-15T12:00:10Z"
    print(f"\nRunning one cycle with forced ts = {forced_ts}")
    print("(hour 12 is in TELEGRAM_BACKUP_HOURS_UTC → backup should be sent)\n")
    print("─" * 72)

    result = trader.run_one_cycle(timestamp_iso=forced_ts)

    print("─" * 72)
    print(f"\nCycle result:")
    print(f"  success           : {result.success}")
    print(f"  halt_triggered    : {result.halt_triggered}")
    print(f"  opened            : {result.n_trades_opened}")
    print(f"  closed            : {result.n_trades_closed}")
    print(f"  skipped           : {result.n_trades_skipped}")

    # ── 5. Verify backup artifacts ──
    print(f"\n── Backup artifacts ──")
    snapshots = sorted(backup_dir.glob("state_*.db.gz"))
    print(f"Local snapshots created: {len(snapshots)}")
    for s in snapshots:
        size_kb = s.stat().st_size / 1024
        print(f"  {s.name} ({size_kb:.2f} KB)")

    # Telegram tracker
    tracker_ts = _read_last_telegram_backup_ts()
    print(f"\nTelegram tracker (.last_telegram_backup):")
    print(f"  last_backup_ts = {tracker_ts}")

    # ── 6. Verdict ──
    print(f"\n{'=' * 72}")
    snapshot_ok = len(snapshots) >= 1
    telegram_ok = tracker_ts is not None

    if snapshot_ok and telegram_ok:
        print(f"  ✅ FULL PROD PATH VALIDATED")
        print(f"  → Snapshot created: yes")
        print(f"  → Telegram backup sent: yes (tracker updated)")
        print(f"  → Check your phone for the .db.gz file!")
    elif snapshot_ok and not telegram_ok:
        print(f"  ⚠️  Snapshot OK but Telegram failed/skipped")
        print(f"  → Check terminal logs above for WARNING/INFO Telegram lines")
    else:
        print(f"  ❌ Snapshot creation failed")
        print(f"  → Check terminal logs above")
    print(f"{'=' * 72}\n")

    print(f"Temp workspace remains at: {workdir}")
    print(f"(rm -rf to clean up after inspection)")


if __name__ == "__main__":
    main()
