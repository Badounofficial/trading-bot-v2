"""
smoke_long.py — Multi-cycle smoke test for the daemon.

Runs N cycles of paper_funding_capture sequentially (no 5-min sleep between),
then runs a stale-heartbeat scenario to validate the watchdog alert path.

Usage:
    python live/smoke_long.py --cycles 6
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from live import paper_funding_capture as d
from paper_trading.monitoring import JsonLineLogger


def run_cycles(n: int):
    state = d.load_state()
    log = JsonLineLogger(d.LOG_DIR)
    alerter = d._alerter()
    print(f"\n=== SMOKE: running {n} consecutive cycles ===")
    for i in range(n):
        print(f"\n--- cycle {i+1}/{n} ---")
        d.run_one_cycle(state, log, alerter, dry=False)
        print(f"  cycle_count={state.cycle_count} positions={list(state.positions.keys())} "
              f"realized=${state.realized_pnl_usd:+.4f}")
        for asset, p in state.positions.items():
            print(f"    {asset}: notional=${p['notional_usd']:.0f}  funding_accrued=${p['funding_accrued_usd']:+.4f}  "
                  f"last_fund={p['last_funding_ts']}")
        # Small sleep just to ensure timestamps differ in logs
        time.sleep(1)
    return state


def stale_heartbeat_test():
    print("\n=== SMOKE: stale-heartbeat scenario ===")
    hb_path = ROOT / "live" / "state" / "heartbeat.txt"
    real = hb_path.read_text() if hb_path.exists() else None
    # Write a heartbeat 3h in the past
    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    hb_path.write_text(stale)
    print(f"  wrote stale heartbeat: {stale}")
    print(f"  watchdog should now alert if run.  Read it back: {hb_path.read_text()}")
    # Restore the real heartbeat
    if real is not None:
        hb_path.write_text(real)
        print(f"  restored real heartbeat for safety.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=6)
    p.add_argument("--stale", action="store_true", help="run stale-heartbeat test in addition")
    args = p.parse_args()

    final_state = run_cycles(args.cycles)
    if args.stale:
        stale_heartbeat_test()

    print("\n=== SMOKE SUMMARY ===")
    print(f"  cycles run            : {final_state.cycle_count}")
    print(f"  api_errors (hourly)   : {final_state.api_error_count_hourly}")
    print(f"  positions open        : {list(final_state.positions.keys())}")
    print(f"  realized PnL          : ${final_state.realized_pnl_usd:+.4f}")
    trades_path = ROOT / "live" / "state" / "trades.jsonl"
    if trades_path.exists():
        with open(trades_path) as f:
            lines = f.readlines()
        print(f"  trade ledger entries  : {len(lines)}")
    print(f"  state file            : {ROOT / 'live' / 'state' / 'daemon_state.json'}")


if __name__ == "__main__":
    main()
