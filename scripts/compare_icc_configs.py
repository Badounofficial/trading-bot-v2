"""
Compare 3 configurations of the ICC cycle:
  CONFIG A : SWING (Daily filter) + measured move 1:2 (BASELINE — your previous results)
  CONFIG B : SWING (Daily filter) + TP=OB opposed (RR>=2.5) + fallback 1:3
  CONFIG C : INTRADAY (no Daily filter, H4 bias only) + TP=OB opposed + fallback 1:3

This helps you decide which version performs best on real Kraken data.

Usage:
    python scripts/compare_icc_configs.py BTC
    python scripts/compare_icc_configs.py ETH
    python scripts/compare_icc_configs.py SOL
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
    run_icc_cycle, summarize_setups, TradeMode,
)


def load_data(symbol: str, tf: str) -> pd.DataFrame:
    tf_map = {'daily': '1d', 'h4': '4h', 'h1': '1h'}
    cache_file = ROOT / 'cache' / f'kraken_{tf_map[tf]}_{symbol}_USD.parquet'
    if not cache_file.exists():
        raise FileNotFoundError(f"No data at {cache_file}")
    return pd.read_parquet(cache_file)


def run_config(label: str, asset, daily, h4, h1, **kwargs):
    """Run one config and return summary."""
    print(f"\n  Running {label}...")
    t0 = time.time()
    setups = run_icc_cycle(
        asset=asset, daily_prices=daily, h4_prices=h4, h1_prices=h1,
        verbose=False, **kwargs,
    )
    elapsed = time.time() - t0
    summary = summarize_setups(setups)
    summary['_elapsed'] = elapsed
    summary['_n_executed'] = sum(1 for s in setups if s.entry_price is not None)
    
    # TP source distribution
    tp_sources = {}
    for s in setups:
        if s.tp_source:
            tp_sources[s.tp_source] = tp_sources.get(s.tp_source, 0) + 1
    summary['_tp_sources'] = tp_sources
    
    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/compare_icc_configs.py <SYMBOL>")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    
    print(f"\n{'='*78}")
    print(f"ICC CONFIG COMPARISON — {symbol}")
    print(f"{'='*78}")
    
    daily = load_data(symbol, 'daily')
    h4 = load_data(symbol, 'h4')
    h1 = load_data(symbol, 'h1')
    
    start = max(daily.index.min(), h4.index.min(), h1.index.min())
    end = min(daily.index.max(), h4.index.max(), h1.index.max())
    daily = daily[(daily.index >= start) & (daily.index <= end)]
    h4 = h4[(h4.index >= start) & (h4.index <= end)]
    h1 = h1[(h1.index >= start) & (h1.index <= end)]
    
    print(f"\nData: {(end-start).days} days ({(end-start).days/365.25:.1f} years)")
    print(f"  Daily: {len(daily)} bars, H4: {len(h4)} bars, H1: {len(h1)} bars")
    
    # CONFIG A : original baseline (need to simulate by using old TP)
    # We approximate by using measured_move_rr=2.0 and very high min_rr_for_ob (effectively disabling OB TP)
    config_a = run_config(
        "CONFIG A (baseline: Daily + measured 1:2)",
        symbol, daily, h4, h1,
        skip_daily_filter=False,
        min_rr_for_ob_tp=999,  # effectively disable OB-based TP
        measured_move_rr=2.0,
    )
    
    # CONFIG B : Daily filter + TP=OB (RR>=2.5) + fallback 1:3
    config_b = run_config(
        "CONFIG B (Daily + TP=OB RR>=2.5 + measured 1:3)",
        symbol, daily, h4, h1,
        skip_daily_filter=False,
        min_rr_for_ob_tp=2.5,
        measured_move_rr=3.0,
    )
    
    # CONFIG C : no Daily filter (H4 bias only) + TP=OB + fallback 1:3
    config_c = run_config(
        "CONFIG C (H4 only + TP=OB RR>=2.5 + measured 1:3)",
        symbol, daily, h4, h1,
        skip_daily_filter=True,
        min_rr_for_ob_tp=2.5,
        measured_move_rr=3.0,
    )
    
    # Print comparison table
    print(f"\n{'='*78}")
    print(f"RESULTS — {symbol}")
    print(f"{'='*78}\n")
    
    def fmt_pct(v, default='—'):
        return f"{v*100:+.2f}%" if isinstance(v, (int, float)) else default
    
    def row(label, ka, kb, kc, fmt=str):
        va = ka if isinstance(ka, str) else fmt(ka)
        vb = kb if isinstance(kb, str) else fmt(kb)
        vc = kc if isinstance(kc, str) else fmt(kc)
        print(f"  {label:<32} {va:>20} {vb:>20} {vc:>20}")
    
    print(f"  {'':32} {'CONFIG A':>20} {'CONFIG B':>20} {'CONFIG C':>20}")
    print(f"  {'':32} {'(Daily, 1:2)':>20} {'(Daily, OB+1:3)':>20} {'(H4 only, OB+1:3)':>20}")
    print(f"  {'-'*32} {'-'*20:>20} {'-'*20:>20} {'-'*20:>20}")
    
    row("Total setups", config_a['n_total'], config_b['n_total'], config_c['n_total'])
    row("Trades executed", config_a['_n_executed'], config_b['_n_executed'], config_c['_n_executed'])
    row("Closed", config_a['n_closed'], config_b['n_closed'], config_c['n_closed'])
    
    # Per year estimation
    years = (end - start).days / 365.25
    
    def trades_per_year(c):
        return f"{c['_n_executed']/years:.1f}"
    row("Trades / year", trades_per_year(config_a), trades_per_year(config_b), trades_per_year(config_c))
    
    if config_a.get('n_closed', 0) > 0:
        row("Win rate", config_a.get('win_rate', 0), config_b.get('win_rate', 0), config_c.get('win_rate', 0),
            fmt=lambda v: f"{v*100:.1f}%")
        row("Avg PnL/trade", config_a.get('avg_pnl_pct', 0), config_b.get('avg_pnl_pct', 0),
            config_c.get('avg_pnl_pct', 0), fmt=fmt_pct)
        row("Total PnL (sum)", config_a.get('total_pnl_pct', 0), config_b.get('total_pnl_pct', 0),
            config_c.get('total_pnl_pct', 0), fmt=fmt_pct)
        row("Avg win", config_a.get('avg_win_pct', 0), config_b.get('avg_win_pct', 0),
            config_c.get('avg_win_pct', 0), fmt=fmt_pct)
        row("Avg loss", config_a.get('avg_loss_pct', 0), config_b.get('avg_loss_pct', 0),
            config_c.get('avg_loss_pct', 0), fmt=fmt_pct)
    
    print()
    print(f"  TP sources:")
    for label, c in [('CONFIG A', config_a), ('CONFIG B', config_b), ('CONFIG C', config_c)]:
        srcs = c.get('_tp_sources', {})
        if srcs:
            top = sorted(srcs.items(), key=lambda x: -x[1])[:2]
            srcs_str = ", ".join(f"{k}={v}" for k, v in top)
            print(f"    {label:<10}: {srcs_str}")
    
    print(f"\n  Exit reasons (CONFIG B vs C):")
    for label, c in [('CONFIG B', config_b), ('CONFIG C', config_c)]:
        reasons = c.get('by_exit_reason', {})
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:3])
        print(f"    {label:<10}: {reasons_str}")
    
    print()


if __name__ == '__main__':
    main()
