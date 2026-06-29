"""
Period-by-Period Forensic Analysis
====================================
Why does the strategy degrade in 2026? Let's look at the raw funding data
month by month and answer:

  1. Is the OVERALL funding lower in 2026? (mean / median)
  2. Are HIGH-funding episodes (>10% APR) rarer or shorter in 2026?
  3. Has volatility / regime changed?
  4. Did Hyperliquid funding mechanics change?

The goal: decide if the degradation is structural (strategy permanently broken)
or cyclical (will rebound) or fixable (different threshold/exchange).
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_funding


PERIODS = [
    ('2024-H1',  '2024-01-01', '2024-07-01'),
    ('2024-H2',  '2024-07-01', '2025-01-01'),
    ('2025-H1',  '2025-01-01', '2025-07-01'),
    ('2025-H2',  '2025-07-01', '2026-01-01'),
    ('2026 YTD', '2026-01-01', '2026-04-30'),
]

THRESHOLDS_APR = [0.02, 0.05, 0.10, 0.15, 0.20]  # 2%, 5%, 10%, 15%, 20%


def analyze_period(funding_df: pd.DataFrame, start: str, end: str) -> dict:
    """Compute funding stats for one sub-period."""
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    window = funding_df[(funding_df.index >= start_ts) & (funding_df.index < end_ts)]
    if len(window) < 100:
        return {}

    # Smooth over 72h (matching our best strategy config)
    smoothed = window['annualized'].rolling(72, min_periods=72).mean().dropna()

    stats = {
        'n_bars': len(window),
        'mean_apr_raw': float(window['annualized'].mean() * 100),
        'median_apr_raw': float(window['annualized'].median() * 100),
        'mean_apr_smooth': float(smoothed.mean() * 100),
        'median_apr_smooth': float(smoothed.median() * 100),
        'pct_negative_raw': float((window['fundingRate'] < 0).mean() * 100),
        'std_apr': float(window['annualized'].std() * 100),
        'p95_apr': float(window['annualized'].quantile(0.95) * 100),
        'max_apr': float(window['annualized'].max() * 100),
    }

    # Threshold crossings on smoothed funding
    for thr in THRESHOLDS_APR:
        above = smoothed > thr
        pct_time = above.mean() * 100
        transitions = above.astype(int).diff()
        n_episodes = (transitions == 1).sum()
        avg_dur_h = above.sum() / max(1, n_episodes) if n_episodes > 0 else 0
        stats[f'thr_{int(thr*100)}_pct_time'] = float(pct_time)
        stats[f'thr_{int(thr*100)}_n_episodes'] = int(n_episodes)
        stats[f'thr_{int(thr*100)}_avg_dur_h'] = float(avg_dur_h)

    return stats


def print_table(all_results: dict, symbol: str):
    """Print stats table for one symbol across all periods."""
    print(f"\n{'=' * 100}")
    print(f"DETAILED FUNDING STATS — {symbol}")
    print(f"{'=' * 100}")
    periods = [p[0] for p in PERIODS]

    # Basic stats
    print(f"\n{'Metric':<32}", end='')
    for p in periods:
        print(f"{p:>13}", end='')
    print()
    print('-' * (32 + 13 * len(periods)))

    metrics_to_show = [
        ('Raw funding median (% APR)', 'median_apr_raw', '{:>12.2f}%'),
        ('Raw funding mean (% APR)',   'mean_apr_raw',   '{:>12.2f}%'),
        ('Smoothed-72h mean (% APR)',  'mean_apr_smooth', '{:>12.2f}%'),
        ('% time funding negative',    'pct_negative_raw', '{:>12.1f}%'),
        ('Std deviation (APR)',        'std_apr',        '{:>12.2f}'),
        ('P95 funding (% APR)',        'p95_apr',        '{:>12.2f}%'),
        ('Max funding (% APR)',        'max_apr',        '{:>12.2f}%'),
    ]
    for label, key, fmt in metrics_to_show:
        print(f"{label:<32}", end='')
        for p in periods:
            r = all_results.get(p, {})
            if r and key in r:
                print(f' {fmt.format(r[key])}', end='')
            else:
                print(f'{"—":>13}', end='')
        print()

    # Threshold crossings
    print(f"\n{'% time above threshold (smoothed 72h)':<32}")
    for thr in THRESHOLDS_APR:
        key = f'thr_{int(thr*100)}_pct_time'
        label = f"  > {int(thr*100)}% APR"
        print(f"{label:<32}", end='')
        for p in periods:
            r = all_results.get(p, {})
            if r and key in r:
                print(f"{r[key]:>12.1f}%", end='')
            else:
                print(f'{"—":>13}', end='')
        print()

    print(f"\n{'# episodes above threshold':<32}")
    for thr in THRESHOLDS_APR:
        key = f'thr_{int(thr*100)}_n_episodes'
        label = f"  > {int(thr*100)}% APR"
        print(f"{label:<32}", end='')
        for p in periods:
            r = all_results.get(p, {})
            if r and key in r:
                print(f"{r[key]:>13}", end='')
            else:
                print(f'{"—":>13}', end='')
        print()

    print(f"\n{'Avg episode duration (hours)':<32}")
    for thr in THRESHOLDS_APR:
        key = f'thr_{int(thr*100)}_avg_dur_h'
        label = f"  > {int(thr*100)}% APR"
        print(f"{label:<32}", end='')
        for p in periods:
            r = all_results.get(p, {})
            if r and key in r:
                print(f"{r[key]:>12.0f}h", end='')
            else:
                print(f'{"—":>13}', end='')
        print()


def diagnose(all_data: dict):
    """Cross-symbol diagnosis: what changed in 2026?"""
    print(f"\n{'=' * 100}")
    print("CROSS-SYMBOL DIAGNOSIS")
    print(f"{'=' * 100}")

    # Compare 2024-H1 (best) vs 2026 YTD (worst) for each symbol
    print("\nKey changes 2024-H1 → 2026 YTD:\n")
    for symbol, periods_data in all_data.items():
        h1_2024 = periods_data.get('2024-H1', {})
        ytd_2026 = periods_data.get('2026 YTD', {})
        if not h1_2024 or not ytd_2026:
            continue
        print(f"  {symbol}:")
        delta_median = ytd_2026.get('median_apr_raw', 0) - h1_2024.get('median_apr_raw', 0)
        delta_thr10 = ytd_2026.get('thr_10_pct_time', 0) - h1_2024.get('thr_10_pct_time', 0)
        delta_thr10_eps = ytd_2026.get('thr_10_n_episodes', 0) - h1_2024.get('thr_10_n_episodes', 0)
        delta_thr10_dur = ytd_2026.get('thr_10_avg_dur_h', 0) - h1_2024.get('thr_10_avg_dur_h', 0)
        print(f"    Median funding APR:        {h1_2024.get('median_apr_raw', 0):.2f}% → "
              f"{ytd_2026.get('median_apr_raw', 0):.2f}% ({delta_median:+.2f}pp)")
        print(f"    % time above 10% APR:      {h1_2024.get('thr_10_pct_time', 0):.1f}% → "
              f"{ytd_2026.get('thr_10_pct_time', 0):.1f}% ({delta_thr10:+.1f}pp)")
        print(f"    # episodes above 10% APR:  {h1_2024.get('thr_10_n_episodes', 0)} → "
              f"{ytd_2026.get('thr_10_n_episodes', 0)} ({delta_thr10_eps:+d})")
        print(f"    Avg duration above 10%:    {h1_2024.get('thr_10_avg_dur_h', 0):.0f}h → "
              f"{ytd_2026.get('thr_10_avg_dur_h', 0):.0f}h ({delta_thr10_dur:+.0f}h)")
        print()

    # Verdict
    print(f"\n{'=' * 100}")
    print("INTERPRETATION GUIDE")
    print(f"{'=' * 100}")
    print("""
  Look at the patterns above:

  CASE A — Median APR has dropped significantly (e.g. 11% → 4%):
      → Funding is structurally lower across the board
      → Hyperliquid has more liquidity providers compressing funding
      → STRATEGY ADAPTATION: lower entry threshold (5% APR instead of 10%)
      → But the edge will be thinner — expect 3-5% CAGR, not 12%

  CASE B — Median APR similar but % time above 10% dropped a lot:
      → Funding is still positive on average, but spikes are rarer
      → SPECIFIC: market makers compete more on Hyperliquid
      → STRATEGY ADAPTATION: be in position more often at lower thresholds

  CASE C — % time negative has increased:
      → Bear regime or risk-off; more shorts than longs
      → STRATEGY ADAPTATION: maybe trade the SHORT side of funding arb
        (long perp + short spot, but spot shorting is harder)

  CASE D — Only SOL changed but BTC/ETH stable:
      → Symbol-specific issue (SOL had a regime change)
      → STRATEGY ADAPTATION: drop SOL or use per-symbol thresholds

  CASE E — Everything similar but recent months are temporarily soft:
      → Likely cyclical, not structural
      → WAIT 1-3 months and re-evaluate before deploying
""")


def main():
    print("\n=== PERIOD-BY-PERIOD FORENSIC ANALYSIS ===\n")
    print("Loading data...")
    all_data = {}
    for sym in cfg()['exchange']['symbols']:
        funding_df = fetch_funding(sym)
        period_results = {}
        for label, start, end in PERIODS:
            stats = analyze_period(funding_df, start, end)
            if stats:
                period_results[label] = stats
        all_data[sym] = period_results
        print_table(period_results, sym)

    diagnose(all_data)


if __name__ == '__main__':
    main()
