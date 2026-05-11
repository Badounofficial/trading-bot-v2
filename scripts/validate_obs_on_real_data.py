"""
Validate ICC Order Block detection on real Kraken data.

Usage:
    python scripts/validate_obs_on_real_data.py BTC daily
    python scripts/validate_obs_on_real_data.py ETH daily
    python scripts/validate_obs_on_real_data.py BTC h4
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
)
from strategies.icc_orderblocks import (
    detect_order_blocks, summarize_order_blocks,
    classify_discount_premium, get_active_obs, get_obs_by_strength,
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
        print("Usage: python scripts/validate_obs_on_real_data.py <SYMBOL> <TF>")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    tf = sys.argv[2].lower()

    print(f"\n{'='*78}")
    print(f"ICC ORDER BLOCKS VALIDATION ON REAL DATA — {symbol} {tf}")
    print(f"{'='*78}\n")

    df = load_data(symbol, tf)
    print(f"Loaded {len(df)} bars from {df.index.min().date()} to {df.index.max().date()}")
    span = (df.index.max() - df.index.min()).days
    print(f"Span: {span} days ({span/365.25:.1f} years)\n")

    # Run detection
    W = 5 if tf in ('daily', '1d') else 3
    print(f"Detecting structures (W={W})...")
    structures = detect_structures(df, swing_lookback=W)
    sstats = summarize_structures(structures)
    print(f"  → {sstats['n_total']} structures detected")
    n_breaks = sum(1 for s in structures if s.type in ('NEW_HIGH', 'NEW_LOW', 'HH', 'LL'))
    print(f"  → {n_breaks} break-type structures (potential OB triggers)")

    print(f"\nDetecting Order Blocks...")
    obs = detect_order_blocks(df, structures=structures)
    classify_discount_premium(obs, structures)
    osum = summarize_order_blocks(obs)

    print(f"  → {osum['n_total']} valid OBs (after strength filter)")
    rejection_rate = (n_breaks - osum['n_total']) / max(n_breaks, 1) * 100
    print(f"  → Rejection rate: {rejection_rate:.1f}% of breaks rejected")

    if osum['n_total'] == 0:
        print("\n⚠ No OBs detected — algorithm too strict for this data")
        return

    # Detailed stats
    print(f"\n{'─'*78}")
    print(f"DISTRIBUTION:")
    print(f"{'─'*78}")
    print(f"  By type:")
    for t, c in sorted(osum['by_type'].items()):
        print(f"    {t}: {c}")
    print(f"  By strength:")
    for s, c in sorted(osum['by_strength'].items()):
        print(f"    {s}: {c}")
    print(f"  With FVG: {osum['n_with_fvg']}/{osum['n_total']} "
          f"({100*osum['n_with_fvg']/osum['n_total']:.0f}%)")
    print(f"  Active: {osum['n_active']}, Consumed: {osum['n_consumed']} "
          f"({100*osum['n_consumed']/osum['n_total']:.0f}% consumption rate)")

    # Discount/Premium classification
    in_favorable = sum(1 for ob in obs if ob.in_discount)
    print(f"  In favorable zone (OB+ discount / OB- premium): {in_favorable}/{osum['n_total']} "
          f"({100*in_favorable/osum['n_total']:.0f}%)")

    # Sanity checks
    print(f"\n{'─'*78}")
    print(f"SANITY CHECKS:")
    print(f"{'─'*78}")

    # 1. OB bar always before detection bar
    bad_timing = sum(1 for ob in obs if ob.bar_index >= ob.detected_at_bar)
    print(f"  {'✓' if bad_timing == 0 else '✗'} OB bar < detection bar: {bad_timing} violations")

    # 2. Zone valid (low < high)
    bad_zones = sum(1 for ob in obs if ob.zone_low >= ob.zone_high)
    print(f"  {'✓' if bad_zones == 0 else '✗'} Zone valid (low<high): {bad_zones} violations")

    # 3. Type-OB consistency
    bad_types = 0
    for ob in obs:
        s = ob.structure_broken
        if ob.type == 'OB+' and s.type not in ('NEW_HIGH', 'HH'):
            bad_types += 1
        elif ob.type == 'OB-' and s.type not in ('NEW_LOW', 'LL'):
            bad_types += 1
    print(f"  {'✓' if bad_types == 0 else '✗'} OB type matches break direction: {bad_types} violations")

    # 4. Balance OB+ / OB-
    n_plus = osum['by_type'].get('OB+', 0)
    n_minus = osum['by_type'].get('OB-', 0)
    if n_plus == 0 or n_minus == 0:
        ratio_str = "∞ (degenerate)"
    else:
        ratio = max(n_plus, n_minus) / min(n_plus, n_minus)
        ratio_str = f"{ratio:.2f}"
    print(f"  {'⚠' if (n_plus == 0 or n_minus == 0) else '✓'} OB+/OB- balance: {n_plus}/{n_minus} (ratio {ratio_str})")

    # 5. Consumption rate (we expect most OBs to be eventually consumed)
    if osum['n_consumed'] / osum['n_total'] < 0.5:
        print(f"  ⚠ Low consumption rate ({osum['n_consumed']}/{osum['n_total']}) — many OBs untested")
    else:
        print(f"  ✓ Consumption rate OK")

    # Recent OBs
    print(f"\n{'─'*78}")
    print(f"MOST RECENT 10 OBs:")
    print(f"{'─'*78}")
    for ob in obs[-10:]:
        consumed = '✗consumed' if ob.consumed else '✓active'
        dp = '' if ob.in_discount is None else (' [favorable]' if ob.in_discount else ' [unfavorable]')
        print(f"  {ob.timestamp.date()}  {ob.type}  {ob.strength:<12}{dp}  "
              f"zone=[${ob.zone_low:.2f}, ${ob.zone_high:.2f}]  {consumed}")

    # Active OBs (the tradable ones for future signals)
    active = get_active_obs(obs)
    if active:
        print(f"\n{'─'*78}")
        print(f"CURRENTLY ACTIVE OBs ({len(active)} total) — most recent 10:")
        print(f"{'─'*78}")
        for ob in active[-10:]:
            dp = '' if ob.in_discount is None else (' [favorable]' if ob.in_discount else ' [unfavorable]')
            print(f"  {ob.timestamp.date()}  {ob.type}  {ob.strength:<12}{dp}  "
                  f"zone=[${ob.zone_low:.2f}, ${ob.zone_high:.2f}]")

    print()


if __name__ == '__main__':
    main()
