"""
Validate the full ICC cycle (TU#4) on real Kraken data.

Usage:
    python scripts/validate_icc_cycle_on_real_data.py BTC
    python scripts/validate_icc_cycle_on_real_data.py ETH
    python scripts/validate_icc_cycle_on_real_data.py SOL

Tests:
    - SWING mode (Daily bias, H4 indication, H1 entry)
    - Sanity checks on resulting setups
    - PnL stats if any trades executed
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from strategies.icc_cycle import (
    run_icc_cycle, summarize_setups,
    TradeMode, TradeState, Direction, ExitReason,
)


def load_data(symbol: str, tf: str) -> pd.DataFrame:
    """Load OHLCV from cache."""
    tf_map = {'daily': '1d', 'h4': '4h', 'h1': '1h'}
    tf_norm = tf_map[tf]
    cache_file = ROOT / 'cache' / f'kraken_{tf_norm}_{symbol}_USD.parquet'
    if not cache_file.exists():
        raise FileNotFoundError(f"No data at {cache_file}")
    return pd.read_parquet(cache_file)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_icc_cycle_on_real_data.py <SYMBOL>")
        print("Example: python scripts/validate_icc_cycle_on_real_data.py BTC")
        sys.exit(1)

    symbol = sys.argv[1].upper()

    print(f"\n{'='*78}")
    print(f"ICC FULL CYCLE VALIDATION — {symbol}")
    print(f"{'='*78}\n")

    # Load all 3 TFs
    print(f"Loading data...")
    daily = load_data(symbol, 'daily')
    h4 = load_data(symbol, 'h4')
    h1 = load_data(symbol, 'h1')

    # Align time ranges: use overlap of H4 (most constrained)
    start = max(daily.index.min(), h4.index.min(), h1.index.min())
    end = min(daily.index.max(), h4.index.max(), h1.index.max())

    daily = daily[(daily.index >= start) & (daily.index <= end)]
    h4 = h4[(h4.index >= start) & (h4.index <= end)]
    h1 = h1[(h1.index >= start) & (h1.index <= end)]

    print(f"  Daily: {len(daily)} bars  ({daily.index.min().date()} → {daily.index.max().date()})")
    print(f"  H4   : {len(h4)} bars")
    print(f"  H1   : {len(h1)} bars")
    print(f"  Common range: {(end - start).days} days ({(end-start).days/365.25:.1f} years)")

    # Run the pipeline
    print(f"\nRunning ICC cycle (SWING mode, Daily→H4→H1)...")
    start_time = time.time()
    setups = run_icc_cycle(
        asset=symbol,
        daily_prices=daily,
        h4_prices=h4,
        h1_prices=h1,
        mode=TradeMode.SWING,
        daily_lookback=5,
        h4_lookback=3,
        h1_lookback=3,
        verbose=True,
    )
    elapsed = time.time() - start_time
    print(f"\nElapsed: {elapsed:.1f}s")

    # Summary
    summary = summarize_setups(setups)
    print(f"\n{'─'*78}")
    print(f"OVERVIEW:")
    print(f"{'─'*78}")
    print(f"  Total setups created      : {summary['n_total']}")
    print(f"  Currently IN_TRADE        : {summary['n_in_trade']}")
    print(f"  Closed (entered then exit): {summary['n_closed']}")

    # State distribution
    print(f"\n  Setups by terminal state:")
    for state, n in sorted(summary['by_state'].items()):
        print(f"    {state:<12}: {n}")

    # Direction distribution
    print(f"\n  Setups by direction:")
    for direction, n in sorted(summary['by_direction'].items()):
        print(f"    {direction:<6}: {n}")

    # Exit reason distribution
    print(f"\n  Setups by exit reason:")
    if summary.get('by_exit_reason'):
        for reason, n in sorted(summary['by_exit_reason'].items(),
                                 key=lambda x: -x[1]):
            print(f"    {reason:<25}: {n}")
    else:
        print(f"    (no exits yet)")

    # Trade stats
    if summary.get('n_closed', 0) > 0:
        print(f"\n{'─'*78}")
        print(f"TRADE STATS (executed trades only):")
        print(f"{'─'*78}")
        print(f"  Wins / Losses     : {summary['n_wins']} / {summary['n_losses']}")
        print(f"  Win rate          : {summary['win_rate']*100:.1f}%")
        print(f"  Avg PnL/trade     : {summary['avg_pnl_pct']*100:.2f}%")
        print(f"  Total PnL (sum)   : {summary['total_pnl_pct']*100:.2f}%")
        if summary['n_wins'] > 0:
            print(f"  Avg winning trade : {summary['avg_win_pct']*100:.2f}%")
        if summary['n_losses'] > 0:
            print(f"  Avg losing trade  : {summary['avg_loss_pct']*100:.2f}%")

    # Sanity checks
    print(f"\n{'─'*78}")
    print(f"SANITY CHECKS:")
    print(f"{'─'*78}")

    # 1. Direction consistency with Daily bias
    bad_direction = 0
    for s in setups:
        if s.direction == Direction.BUY and s.daily_bias.value != 'BULL':
            bad_direction += 1
        if s.direction == Direction.SELL and s.daily_bias.value != 'BEAR':
            bad_direction += 1
    print(f"  {'✓' if bad_direction == 0 else '✗'} Direction matches Daily bias: {bad_direction} violations")

    # 2. Entry bar always after creation
    bad_entry = sum(1 for s in setups
                     if s.entry_bar is not None and s.entry_bar < s.created_at_bar)
    print(f"  {'✓' if bad_entry == 0 else '✗'} Entry bar after creation: {bad_entry} violations")

    # 3. Exit bar always after entry
    bad_exit = sum(1 for s in setups
                    if s.exit_bar is not None and s.entry_bar is not None
                    and s.exit_bar < s.entry_bar)
    print(f"  {'✓' if bad_exit == 0 else '✗'} Exit bar after entry: {bad_exit} violations")

    # 4. PnL consistency with exit reason
    bad_pnl = 0
    for s in setups:
        if s.exit_reason == ExitReason.TP_HIT and s.pnl_pct is not None and s.pnl_pct <= 0:
            bad_pnl += 1
        if s.exit_reason == ExitReason.SL_HIT and s.pnl_pct is not None and s.pnl_pct >= 0.001:
            bad_pnl += 1  # allow tiny rounding
    print(f"  {'✓' if bad_pnl == 0 else '✗'} PnL consistent with exit reason: {bad_pnl} violations")

    # 5. Setups ordered by creation
    bars = [s.created_at_bar for s in setups]
    ordered = bars == sorted(bars)
    print(f"  {'✓' if ordered else '✗'} Setups chronologically ordered: {ordered}")

    # Sample recent setups
    if setups:
        print(f"\n{'─'*78}")
        print(f"LAST 10 SETUPS (most recent):")
        print(f"{'─'*78}")
        for s in setups[-10:]:
            entry_str = f"${s.entry_price:.2f}" if s.entry_price else "—"
            exit_str = f"${s.exit_price:.2f}" if s.exit_price else "—"
            reason_str = s.exit_reason.value if s.exit_reason else "—"
            pnl_str = f"{s.pnl_pct*100:+.2f}%" if s.pnl_pct is not None else "—"
            print(f"  {s.h4_indication.timestamp.date()}  {s.direction.value} "
                  f"state={s.state.value:<10} entry={entry_str:<10} "
                  f"exit={exit_str:<10} reason={reason_str:<22} PnL={pnl_str}")

    # Most recent EXECUTED trades (entry triggered)
    executed = [s for s in setups if s.entry_price is not None]
    if executed:
        print(f"\n{'─'*78}")
        print(f"EXECUTED TRADES ({len(executed)}) — last 10:")
        print(f"{'─'*78}")
        for s in executed[-10:]:
            exit_str = f"${s.exit_price:.2f}" if s.exit_price else "OPEN"
            reason_str = s.exit_reason.value if s.exit_reason else "—"
            pnl_str = f"{s.pnl_pct*100:+.2f}%" if s.pnl_pct is not None else "—"
            print(f"  {s.entry_timestamp.date() if s.entry_timestamp else '?'}  "
                  f"{s.direction.value} entry=${s.entry_price:.2f} → "
                  f"exit={exit_str:<10} ({reason_str:<20}) PnL={pnl_str}")

    print()


if __name__ == '__main__':
    main()
