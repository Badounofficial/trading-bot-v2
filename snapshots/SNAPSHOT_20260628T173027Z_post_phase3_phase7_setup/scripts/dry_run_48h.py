"""
dry_run_48h.py — Test E2E : replay 48 cycles H1 sur de la vraie data Kraken.

WHAT THIS DOES
==============
1. Fetches ~30 days of H1 OHLCV for the 8 ICC assets from Kraken.
2. Builds 48 successive "snapshots" — each snapshot is what the bot would see
   at a given hour if it were running live. Snapshot[i] = last 720 H1 bars
   as of hour (now - 48 + i).
3. Runs paper_trader.run_dev_fast() over these 48 snapshots in a TEMP database
   (no impact on production state).
4. Prints a summary: equity progression, trades, anomalies.

WHY THIS MATTERS
================
This is the FIRST end-to-end test of the bot against real Kraken data, real
ICC strategy decisions, real (simulated) order execution. No mocks.
If anything is wrong with the integration between modules, we'll see it here
BEFORE we go live with run_forever().

USAGE
=====
    python -m scripts.dry_run_48h

OUTPUT
======
- Prints summary to stdout
- Writes JSON logs in /tmp/dry_run_<timestamp>/logs/
- Writes SQLite DB in /tmp/dry_run_<timestamp>/state.db (kept for inspection)
"""
from __future__ import annotations

import logging
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

# Configure logging BEFORE imports for clean output
logging.basicConfig(
    level=logging.WARNING,  # quiet by default; can be raised to INFO if needed
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from paper_trading import config
from paper_trading import data_source as ds
from paper_trading.paper_trader import PaperTrader
from paper_trading.state_manager import StateManager
from paper_trading.monitoring import Monitor, JsonLineLogger, TelegramAlerter, TelegramResult


# ════════════════════════════════════════════════════════════════
#                    CONFIGURATION
# ════════════════════════════════════════════════════════════════

N_CYCLES = 48          # number of H1 cycles to replay (= last 48 hours)
# Kraken returns max ~720 H1 bars per call. We need history + cycles to fit.
# History 672 = 28 days, still plenty for ICC multi-TF context.
N_BARS_HISTORY = 672


# ════════════════════════════════════════════════════════════════
#                    DATA FETCHING (one-shot)
# ════════════════════════════════════════════════════════════════

def fetch_extended_history() -> dict[str, pd.DataFrame]:
    """Fetch ~30 days + 48h of H1 data for all assets, in one call per asset.

    We need N_BARS_HISTORY + N_CYCLES = 720 + 48 = 768 bars per asset
    so we can build 48 successive snapshots of length 720 each.
    """
    print(f"\nFetching {N_BARS_HISTORY + N_CYCLES} H1 bars per asset from Kraken...")
    fetched = {}
    for asset in config.ASSETS:
        try:
            df = ds.fetch_recent_h1(asset, n_bars=N_BARS_HISTORY + N_CYCLES)
            fetched[asset] = df
            print(f"  ✓ {asset}: {len(df)} bars  "
                  f"({df.index.min()} → {df.index.max()})")
        except Exception as e:
            print(f"  ✗ {asset}: FAILED — {e}")
        # Small pause to be respectful of Kraken rate limits
        time.sleep(0.3)
    return fetched


# ════════════════════════════════════════════════════════════════
#                    BUILD ROLLING SNAPSHOTS
# ════════════════════════════════════════════════════════════════

def build_cycle_snapshots(
    extended_history: dict[str, pd.DataFrame],
    n_cycles: int = N_CYCLES,
    window_size: int = N_BARS_HISTORY,
) -> list[tuple[str, dict[str, pd.DataFrame]]]:
    """Build a list of (timestamp, snapshot) tuples simulating live cycles.

    For cycle i (0..n_cycles-1):
      - The "current time" = last_bar_time - (n_cycles - 1 - i) hours
      - The visible data = bars [end - n_cycles + i - window_size + 1 ... end - n_cycles + i + 1]
      i.e. the bot sees window_size bars ending at the "current time".

    Returns:
        List of (timestamp_iso, {asset: H1_DataFrame_of_window_size_bars}).
    """
    # We use the first asset's index as the master clock (all assets should be aligned)
    if not extended_history:
        raise RuntimeError("No data fetched; can't build snapshots")
    master_asset = next(iter(extended_history.keys()))
    master_index = extended_history[master_asset].index
    if len(master_index) < window_size + n_cycles:
        actual_max_cycles = max(0, len(master_index) - window_size)
        raise RuntimeError(
            f"Not enough bars: have {len(master_index)}, "
            f"need {window_size + n_cycles}.\n"
            f"  → Either reduce N_CYCLES to {actual_max_cycles} "
            f"or reduce N_BARS_HISTORY to {len(master_index) - n_cycles}.\n"
            f"  → Kraken returns max ~720 bars per fetch_ohlcv call."
        )

    snapshots = []
    for i in range(n_cycles):
        # The "current bar" — the last bar visible to the bot for this cycle
        current_bar_idx = len(master_index) - n_cycles + i
        current_ts = master_index[current_bar_idx]
        # Build snapshot dict
        snap = {}
        for asset, df in extended_history.items():
            # We slice to bars [current_bar_idx - window_size + 1 ... current_bar_idx + 1]
            start_idx = max(0, current_bar_idx - window_size + 1)
            end_idx = current_bar_idx + 1
            snap[asset] = df.iloc[start_idx:end_idx].copy()
        ts_iso = current_ts.isoformat().replace("+00:00", "Z")
        snapshots.append((ts_iso, snap))

    return snapshots


# ════════════════════════════════════════════════════════════════
#                    RUN THE DRY RUN
# ════════════════════════════════════════════════════════════════

def run_dry_run() -> dict:
    """Execute the full 48-hour dry run. Returns a summary dict."""
    # ── 0. Setup temp workspace ──
    workdir = Path(tempfile.mkdtemp(prefix="dry_run_"))
    print(f"\nTemp workspace: {workdir}")
    db_path = workdir / "state.db"
    logs_dir = workdir / "logs"
    logs_dir.mkdir()

    # ── 1. Build a paper trader with mock Telegram (no spam during dry run) ──
    sm = StateManager(db_path=db_path)
    json_logger = JsonLineLogger(logs_dir=logs_dir)
    mock_alerter = MagicMock(spec=TelegramAlerter)
    mock_alerter.send.return_value = TelegramResult(ok=True, http_status=200)
    monitor = Monitor(json_logger=json_logger, alerter=mock_alerter)

    trader = PaperTrader(state_manager=sm, monitor=monitor)
    # NB: trader.adapter is the real IccStrategyAdapter (not mocked)

    # ── 2. Fetch extended history ──
    extended = fetch_extended_history()
    if len(extended) < len(config.ASSETS):
        print(f"\n⚠ Only {len(extended)}/{len(config.ASSETS)} assets available — proceeding anyway")

    # ── 3. Build snapshots ──
    print(f"\nBuilding {N_CYCLES} rolling snapshots ({N_BARS_HISTORY} bars each)...")
    snapshots = build_cycle_snapshots(extended, n_cycles=N_CYCLES, window_size=N_BARS_HISTORY)
    print(f"  First cycle: {snapshots[0][0]}")
    print(f"  Last cycle:  {snapshots[-1][0]}")

    # ── 4. Run the dev_fast loop ──
    print(f"\nRunning paper_trader.run_dev_fast() over {len(snapshots)} cycles...")
    t0 = time.time()
    results = trader.run_dev_fast(snapshots)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s ({elapsed/len(results):.2f}s per cycle)")

    # ── 5. Compute summary ──
    summary = _compute_summary(results, trader, workdir)
    return summary


def _compute_summary(
    results: list,
    trader: PaperTrader,
    workdir: Path,
) -> dict:
    """Compute and print a summary of the dry run."""
    print("\n" + "=" * 70)
    print("  DRY RUN SUMMARY")
    print("=" * 70)

    n_cycles_run = len(results)
    n_success = sum(1 for r in results if r.success)
    n_halt = sum(1 for r in results if r.halt_triggered)
    n_opens = sum(r.n_trades_opened for r in results)
    n_closes = sum(r.n_trades_closed for r in results)
    n_skipped = sum(r.n_trades_skipped for r in results)
    n_trails = sum(r.n_trails for r in results)
    n_partials = sum(r.n_partials for r in results)
    n_errors = sum(1 for r in results if not r.success)
    total_failed_assets = sum(len(r.assets_failed) for r in results)

    # State at end
    open_positions = trader.sm.get_open_positions()
    closed_trades = trader.sm.get_closed_trades()
    latest_equity = trader.sm.get_latest_equity_snapshot()
    bot_state = trader.sm.get_bot_state()

    print(f"\nCycles:")
    print(f"  Ran            : {n_cycles_run} / {N_CYCLES}")
    print(f"  Successful     : {n_success}")
    print(f"  With errors    : {n_errors}")
    print(f"  HALT triggered : {n_halt}")
    print(f"  Avg duration   : {sum(r.cycle_duration_seconds for r in results) / max(1, n_cycles_run):.2f}s")

    print(f"\nActions executed:")
    print(f"  Opens          : {n_opens}")
    print(f"  Closes         : {n_closes}")
    print(f"  Trails (SL upd): {n_trails}")
    print(f"  Partials       : {n_partials}")
    print(f"  Skipped opens  : {n_skipped}")

    print(f"\nFinal state:")
    print(f"  Bot status     : {bot_state.status}")
    if bot_state.halt_reason:
        print(f"  Halt reason    : {bot_state.halt_reason}")
    print(f"  Open positions : {len(open_positions)}")
    print(f"  Closed trades  : {len(closed_trades)}")
    if latest_equity:
        starting_capital = config.INITIAL_CAPITAL
        pnl = latest_equity.equity - starting_capital
        pnl_pct = pnl / starting_capital * 100
        print(f"  Final equity   : ${latest_equity.equity:.2f}")
        print(f"  PnL            : {'+' if pnl >= 0 else ''}${pnl:.2f} ({pnl_pct:+.2f}%)")
        print(f"  Peak equity    : ${latest_equity.peak_equity:.2f}")
        print(f"  Drawdown       : {latest_equity.drawdown_pct*100:.2f}%")

    # Show recent trades if any
    if closed_trades:
        print(f"\nClosed trades (last 5):")
        for t in closed_trades[:5]:
            sign = "+" if t.pnl_dollars >= 0 else ""
            print(f"  {t.asset:5s} | {t.exit_reason:15s} | "
                  f"PnL {sign}${t.pnl_dollars:7.2f} ({sign}{t.pnl_pct*100:5.2f}%)")

    # Data failures
    if total_failed_assets:
        print(f"\n⚠ Assets failed to fetch (total across cycles): {total_failed_assets}")

    # Errors
    if n_errors:
        print(f"\n⚠ {n_errors} cycles had errors. First 3:")
        for r in [r for r in results if not r.success][:3]:
            print(f"  {r.timestamp}: {r.error_message}")

    print(f"\nArtifacts:")
    print(f"  DB:   {workdir}/state.db")
    print(f"  Logs: {workdir}/logs/")
    print(f"  Inspect logs: head -5 {workdir}/logs/*.jsonl")

    print("\n" + "=" * 70)
    if n_errors == 0 and n_halt == 0:
        print("  ✅ DRY RUN COMPLETED — no errors, no halts")
    elif n_errors:
        print(f"  ⚠ DRY RUN COMPLETED with {n_errors} cycle errors — investigate logs")
    elif n_halt:
        print(f"  ⚠ DRY RUN HALTED — verify reason is expected (DD/Loss)")
    print("=" * 70 + "\n")

    return {
        "n_cycles_run": n_cycles_run,
        "n_errors": n_errors,
        "n_halt": n_halt,
        "n_opens": n_opens,
        "n_closes": n_closes,
        "workdir": str(workdir),
    }


# ════════════════════════════════════════════════════════════════
#                    MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  DRY RUN — 48 hours of paper trading on real Kraken data")
    print("=" * 70)
    print(f"\nAssets:    {', '.join(config.ASSETS)}")
    print(f"Capital:   ${config.INITIAL_CAPITAL:,.2f}")
    print(f"Cycles:    {N_CYCLES} (= last 48 hours)")
    print(f"History:   {N_BARS_HISTORY} H1 bars per cycle (~30 days)")

    try:
        summary = run_dry_run()
        sys.exit(0 if summary["n_errors"] == 0 else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting.")
        sys.exit(130)
    except Exception as e:
        import traceback
        print(f"\n\n❌ DRY RUN CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
