"""
Validate ICC structure detection on real Kraken data.
This is the "reviewer" step: does the algorithm behave sensibly
on real market data?

Run after Phase 1 data is in cache/.

Usage:
    python scripts/validate_icc_on_real_data.py BTC daily
    python scripts/validate_icc_on_real_data.py BTC h4
    python scripts/validate_icc_on_real_data.py ETH daily
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from strategies.icc_structure import (
    detect_structures, summarize_structures,
    get_active_structures, get_structures_by_type,
)


def load_data(symbol: str, tf: str) -> pd.DataFrame:
    """Load OHLCV from cache."""
    tf_map = {'daily': '1d', '1d': '1d', 'h4': '4h', '4h': '4h', 'h1': '1h', '1h': '1h'}
    tf_norm = tf_map.get(tf, tf)
    cache_file = ROOT / 'cache' / f'kraken_{tf_norm}_{symbol}_USD.parquet'
    if not cache_file.exists():
        raise FileNotFoundError(f"No data at {cache_file}")
    return pd.read_parquet(cache_file)


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/validate_icc_on_real_data.py <SYMBOL> <TF>")
        print("  e.g. python scripts/validate_icc_on_real_data.py BTC daily")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    tf = sys.argv[2].lower()

    print(f"\n{'='*78}")
    print(f"ICC STRUCTURE VALIDATION ON REAL DATA — {symbol} {tf}")
    print(f"{'='*78}\n")

    df = load_data(symbol, tf)
    print(f"Loaded {len(df)} bars from {df.index.min().date()} to {df.index.max().date()}")
    span = (df.index.max() - df.index.min()).days
    print(f"Span: {span} days ({span/365.25:.1f} years)\n")

    # Run detection
    print(f"Running detection (swing_lookback=5 for daily, 3 for intraday)...")
    W = 5 if tf in ('daily', '1d') else 3
    structures = detect_structures(df, swing_lookback=W)

    # Summary
    summary = summarize_structures(structures)
    print(f"\nDetected {summary['n_total']} structures:")
    for t, count in sorted(summary['by_type'].items()):
        print(f"  {t:<15}: {count}")
    print(f"\nActive: {summary['n_active']}, Broken: {summary['n_broken']}")

    # Sanity checks
    print(f"\n{'─'*78}")
    print("SANITY CHECKS:")
    print(f"{'─'*78}")

    # 1. Balance between highs and lows
    n_highs = sum(1 for s in structures if s.is_high())
    n_lows = sum(1 for s in structures if s.is_low())
    ratio = max(n_highs, n_lows) / max(min(n_highs, n_lows), 1)
    status = "✓" if ratio <= 2.0 else "⚠"
    print(f"  {status} High/Low balance: {n_highs} highs vs {n_lows} lows (ratio {ratio:.2f})")

    # 2. Chronological ordering
    bar_indices = [s.bar_index for s in structures]
    is_ordered = bar_indices == sorted(bar_indices)
    print(f"  {'✓' if is_ordered else '✗'} Chronological order: {is_ordered}")

    # 3. Origin always before swing
    bad_origins = sum(1 for s in structures
                       if s.origin_bar_index is not None
                       and s.origin_bar_index >= s.bar_index)
    print(f"  {'✓' if bad_origins == 0 else '✗'} Origins valid: {bad_origins} bad origins")

    # 4. Broken metadata
    bad_broken = sum(1 for s in structures
                      if s.broken and (s.broken_at_bar is None or s.broken_at_bar <= s.bar_index))
    print(f"  {'✓' if bad_broken == 0 else '✗'} Broken metadata: {bad_broken} invalid")

    # 5. Confirmation lag
    bad_lag = sum(1 for s in structures
                   if s.confirmed_at_bar != s.bar_index + W)
    print(f"  {'✓' if bad_lag == 0 else '✗'} Confirmation lag = {W}: {bad_lag} violations")

    # Print most recent 10 structures
    print(f"\n{'─'*78}")
    print("MOST RECENT 10 STRUCTURES:")
    print(f"{'─'*78}")
    for s in structures[-10:]:
        active = '✓active' if not s.broken else '✗broken'
        print(f"  {s.timestamp.date()}  {s.type:<14}  price=${s.price:>10.2f}  {active}")

    # Print active structures
    print(f"\n{'─'*78}")
    print(f"CURRENTLY ACTIVE STRUCTURES ({summary['n_active']} total):")
    print(f"{'─'*78}")
    active = get_active_structures(structures)
    for s in active[-10:]:
        print(f"  {s.timestamp.date()}  {s.type:<14}  price=${s.price:>10.2f}")

    print()


if __name__ == '__main__':
    main()
