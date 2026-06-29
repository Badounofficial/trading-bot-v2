"""
live_test_3_cycles.py — Test B : LIVE paper trading on Kraken for 3 cycles.

WHAT THIS DOES
==============
Runs paper_trader.run_forever(max_cycles=3) against the REAL Kraken API,
on a TEMPORARY database (no impact on future production state).

This is the production-like validation: the same code that will run forever
in production, but bounded to 3 cycles for observation.

Each cycle takes the bot ~10-30s of actual work but waits ~1 hour between
cycles (synced to XX:00 UTC + POST_BAR_DELAY_SECONDS).

→ Total duration ≈ 2h-3h depending on when you launch.

DIFFERENCES vs dry_run_48h.py
=============================
- Real Kraken fetch at each cycle (not pre-fetched historical)
- Real Telegram alerter (you'll get heartbeats/halts on your phone)
- Real scheduler (sleep until XX:00 UTC + 10s)
- Bounded by max_cycles=3 (terminates cleanly)

USAGE
=====
    python -m scripts.live_test_3_cycles

EXPECTED OBSERVATIONS
=====================
- Cycle 1: bot wakes up at XX:00:10 UTC, fetches 8 assets, processes them.
  Logs show cycle_start → trade_opened/skipped/etc → cycle_end with equity.
- Cycle 2-3: same pattern, validating the scheduler loop.
- If a cycle hits the HEARTBEAT_HOUR_UTC (default 12h UTC), Telegram pings you.
- If no trades happen (likely in 3 hours), that's normal — ICC is patient.

ABORT
=====
Ctrl+C at any time. The temp DB and logs remain on disk for inspection.
"""
from __future__ import annotations

import logging
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Configure logging to show what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from paper_trading import config
from paper_trading.paper_trader import PaperTrader
from paper_trading.state_manager import StateManager
from paper_trading.monitoring import Monitor, JsonLineLogger, TelegramAlerter
from paper_trading.backup import BackupManager


# ════════════════════════════════════════════════════════════════
#                    CONFIGURATION
# ════════════════════════════════════════════════════════════════

N_CYCLES = 3  # Number of live cycles to observe


# ════════════════════════════════════════════════════════════════
#                    MAIN
# ════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print(f"  LIVE TEST B — {N_CYCLES} real cycles on Kraken")
    print("=" * 70)
    print(f"\nAssets:    {', '.join(config.ASSETS)}")
    print(f"Capital:   ${config.INITIAL_CAPITAL:,.2f}")
    print(f"Cycles:    {N_CYCLES} (will terminate after)")
    print(f"Telegram:  REAL (you'll get pings if HEARTBEAT_HOUR_UTC hits)")

    # ── 1. Setup temp workspace ──
    workdir = Path(tempfile.mkdtemp(prefix="live_test_"))
    db_path = workdir / "state.db"
    logs_dir = workdir / "logs"
    backup_dir = workdir / "backups"
    logs_dir.mkdir()
    backup_dir.mkdir()
    print(f"\nTemp workspace: {workdir}")
    print(f"  DB:      {db_path}")
    print(f"  Logs:    {logs_dir}")
    print(f"  Backups: {backup_dir}")

    # ── 2. Setup state manager, monitor, backup manager, trader ──
    sm = StateManager(db_path=db_path)
    json_logger = JsonLineLogger(logs_dir=logs_dir)
    alerter = TelegramAlerter()  # Real Telegram from .env
    monitor = Monitor(json_logger=json_logger, alerter=alerter)

    # IMPORTANT: align BackupManager with the SAME temp DB used by StateManager.
    # Without this, BackupManager defaults to config.STATE_DB_PATH which may
    # not exist (it didn't during yesterday's test) → snapshots fail silently
    # → no Telegram backup sent. Bug discovered May 15, 2026.
    backup_manager = BackupManager(
        db_path=db_path,
        backup_dir=backup_dir,
        telegram_enabled=True,  # Real Telegram active for end-to-end validation
    )

    print(f"\nTelegram enabled: {alerter.enabled}")
    if not alerter.enabled:
        print("⚠ Telegram is DISABLED — check .env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        print("  Bot will still run, but you won't get phone notifications.")

    trader = PaperTrader(
        state_manager=sm,
        monitor=monitor,
        backup_manager=backup_manager,
    )
    # NB: trader.adapter = real IccStrategyAdapter
    # NB: trader.data_fetcher = real live Kraken fetch
    # NB: trader.backup_manager = aligned with temp DB (fix May 15, 2026)

    # ── 3. Schedule info ──
    now = datetime.now(timezone.utc)
    print(f"\nCurrent time UTC: {now.isoformat()}")

    # Approximate wait until next cycle
    seconds_until_next = PaperTrader._seconds_until_next_cycle()
    next_cycle_at = now.timestamp() + seconds_until_next
    next_cycle_dt = datetime.fromtimestamp(next_cycle_at, tz=timezone.utc)
    print(f"Next cycle at:    {next_cycle_dt.isoformat()}  (in {seconds_until_next:.0f}s)")

    expected_end = next_cycle_at + (N_CYCLES - 1) * 3600
    expected_end_dt = datetime.fromtimestamp(expected_end, tz=timezone.utc)
    print(f"Expected end at:  ~{expected_end_dt.isoformat()}  (in ~{(expected_end - now.timestamp())/3600:.1f}h)")

    print("\n" + "─" * 70)
    print(f"  Starting bot in {N_CYCLES} cycles, max_cycles mode...")
    print("─" * 70)
    print()

    # ── 4. Run for N cycles ──
    try:
        trader.run_forever(max_cycles=N_CYCLES)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting.")
        sys.exit(130)
    except Exception as e:
        import traceback
        print(f"\n\n❌ LIVE TEST CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)

    # ── 5. Final summary ──
    print("\n" + "=" * 70)
    print("  LIVE TEST B SUMMARY")
    print("=" * 70)

    closed_trades = sm.get_closed_trades()
    open_positions = sm.get_open_positions()
    latest = sm.get_latest_equity_snapshot()
    bot_state = sm.get_bot_state()

    print(f"\nBot status     : {bot_state.status}")
    if bot_state.halt_reason:
        print(f"Halt reason    : {bot_state.halt_reason}")
    print(f"Cycles run     : {N_CYCLES} (max reached)")
    print(f"Open positions : {len(open_positions)}")
    print(f"Closed trades  : {len(closed_trades)}")

    if latest:
        pnl = latest.equity - config.INITIAL_CAPITAL
        pnl_pct = pnl / config.INITIAL_CAPITAL * 100
        print(f"Final equity   : ${latest.equity:.2f}")
        print(f"  Cash         : ${latest.cash:.2f}")
        print(f"  Open value   : ${latest.open_positions_value:.2f}")
        print(f"PnL            : {'+' if pnl >= 0 else ''}${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"Drawdown       : {latest.drawdown_pct*100:.2f}%")

        # Invariant check
        invariant_diff = abs(latest.equity - (latest.cash + latest.open_positions_value))
        print(f"\nInvariant check (equity == cash + open_value):")
        print(f"  Diff: ${invariant_diff:.6f}  {'✅' if invariant_diff < 0.01 else '❌ BROKEN'}")

    if closed_trades:
        print(f"\nClosed trades:")
        for t in closed_trades:
            sign = "+" if t.pnl_dollars >= 0 else ""
            print(f"  {t.asset:5s} | {t.exit_reason:15s} | "
                  f"PnL {sign}${t.pnl_dollars:7.2f} ({sign}{t.pnl_pct*100:5.2f}%)")

    print(f"\nArtifacts:")
    print(f"  DB:      {workdir}/state.db")
    print(f"  Logs:    {workdir}/logs/")
    print(f"  Backups: {workdir}/backups/")

    # Show what was backed up
    snapshots = sorted(backup_dir.glob("state_*.db.gz"))
    print(f"\nBackup snapshots created: {len(snapshots)}")
    for s in snapshots:
        size_kb = s.stat().st_size / 1024
        print(f"  {s.name} ({size_kb:.1f} KB)")
    print(f"  Inspect: cat {workdir}/logs/*.jsonl | head -20")

    print("\n" + "=" * 70)
    if bot_state.status == "RUNNING":
        print(f"  ✅ LIVE TEST B COMPLETED — {N_CYCLES} cycles, bot still RUNNING")
        print(f"  → Ready for production launch (run_forever without max_cycles)")
    else:
        print(f"  ⚠ Bot was HALTED — investigate reason: {bot_state.halt_reason}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
