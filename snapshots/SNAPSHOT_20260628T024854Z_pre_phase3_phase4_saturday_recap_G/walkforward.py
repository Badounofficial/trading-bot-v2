"""
Walk-Forward Analysis
=====================
Tests strategy robustness by running it independently on multiple sub-periods.
If a config works on 2024 but fails on 2025, it's overfitted.

Three tests:

  TEST 1: FIXED CONFIG across sub-periods
    Apply the "best" config (from tune.py) to each year separately.
    Check if performance is consistent.

  TEST 2: PER-PERIOD RE-OPTIMIZATION
    Find the best config IN each sub-period independently.
    If the best config differs wildly between periods → fragile strategy.

  TEST 3: OUT-OF-SAMPLE VALIDATION
    Optimize on first half, test on second half.
    This is the cleanest overfit test.

Usage:
    python walkforward.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import itertools

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_funding
from strategies.funding_capture import generate_position
from backtest.engine import run_backtest


# ============================================================================
# CONFIG TO TEST (from tune.py recommendation)
# ============================================================================

BEST_CONFIG = {
    'smooth_hours': 72,
    'min_hold_hours': 24,
    'entry_threshold_apr': 0.10,
    'exit_threshold_apr': -0.005,
    'min_flat_hours': 24,
}

# Sub-periods (define your walk-forward windows here)
PERIODS = [
    ('2024-01-01', '2024-12-31', '2024'),
    ('2025-01-01', '2025-12-31', '2025'),
    ('2026-01-01', '2026-04-30', '2026 YTD'),
]

# Smaller grid for per-period re-optimization (keep fast)
PARAM_GRID = {
    'smooth_hours':         [24, 48, 72],
    'min_hold_hours':       [24, 72, 168],
    'entry_threshold_apr':  [0.02, 0.05, 0.10],
}


# ============================================================================
# CORE: RUN ONE CONFIG ON ONE PERIOD
# ============================================================================

def run_period(funding_data: dict, start, end, params: dict) -> dict:
    """Run backtest on a subperiod with given params. Returns aggregate metrics."""
    s_cfg = cfg()['strategy']
    f_cfg = cfg()['friction']
    capital = s_cfg['capital_per_symbol_usd']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    cost_per_leg_bps = fee + f_cfg['slippage_median_bps']
    cost_bps = 2 * cost_per_leg_bps

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    per_symbol = []
    for sym, funding_df in funding_data.items():
        window = funding_df[(funding_df.index >= start_ts) & (funding_df.index < end_ts)]
        if len(window) < 100:
            continue
        position = generate_position(
            window['fundingRate'],
            smooth_hours=params['smooth_hours'],
            entry_threshold_apr=params['entry_threshold_apr'],
            exit_threshold_apr=params.get('exit_threshold_apr', -0.005),
            min_hold_hours=params['min_hold_hours'],
            min_flat_hours=params.get('min_flat_hours', 24),
        )
        result = run_backtest(
            window['fundingRate'], position,
            capital=capital,
            entry_cost_bps=cost_bps, exit_cost_bps=cost_bps,
        )
        per_symbol.append(result['metrics'])

    if not per_symbol:
        return {}

    total_capital = capital * len(per_symbol)
    total_pnl = sum(m['total_pnl_usd'] for m in per_symbol)
    total_costs = sum(m['total_costs_usd'] for m in per_symbol)
    total_trades = sum(m['n_trades'] for m in per_symbol)
    total_return_pct = total_pnl / total_capital * 100
    avg_sharpe = float(np.mean([m['sharpe'] for m in per_symbol]))
    worst_dd = float(min(m['max_dd_pct'] for m in per_symbol))
    avg_time_in_pos = float(np.mean([m['time_in_position_pct'] for m in per_symbol]))

    span_days = (end_ts - start_ts).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100 if total_return_pct > -100 else -100

    return {
        'n_trades': int(total_trades),
        'cagr_pct': float(cagr),
        'sharpe': avg_sharpe,
        'max_dd_pct': worst_dd,
        'cost_drag_pct': total_costs / total_capital * 100,
        'time_in_pos_pct': avg_time_in_pos,
        'total_pnl_usd': float(total_pnl),
    }


# ============================================================================
# TEST 1: FIXED CONFIG ACROSS PERIODS
# ============================================================================

def test_fixed_config(funding_data: dict):
    print("\n" + "=" * 90)
    print("TEST 1: FIXED CONFIG ACROSS PERIODS")
    print(f"Config: smooth={BEST_CONFIG['smooth_hours']}h, "
          f"hold={BEST_CONFIG['min_hold_hours']}h, "
          f"entry={BEST_CONFIG['entry_threshold_apr']*100:.1f}% APR")
    print("=" * 90)
    print(f"{'Period':<15} {'Trades':>8} {'CAGR':>9} {'Sharpe':>9} {'MaxDD':>9} "
          f"{'Cost':>8} {'TimeIn':>8}")
    print("-" * 90)

    results = []
    for start, end, label in PERIODS:
        m = run_period(funding_data, start, end, BEST_CONFIG)
        if m:
            print(f"{label:<15} {m['n_trades']:>8} {m['cagr_pct']:>8.2f}% "
                  f"{m['sharpe']:>9.2f} {m['max_dd_pct']:>8.2f}% "
                  f"{m['cost_drag_pct']:>7.2f}% {m['time_in_pos_pct']:>7.1f}%")
            results.append((label, m))

    if len(results) < 2:
        print("\n⚠ Not enough sub-periods to assess robustness")
        return

    cagrs = [r[1]['cagr_pct'] for r in results]
    cagr_min = min(cagrs)
    cagr_max = max(cagrs)
    cagr_std = float(np.std(cagrs))

    print()
    print(f"  CAGR range: {cagr_min:.2f}% → {cagr_max:.2f}% (spread {cagr_max-cagr_min:.2f}%)")
    print(f"  CAGR std:   {cagr_std:.2f}%")

    print()
    if cagr_min > 0 and cagr_max - cagr_min < 10:
        print("  ✅ ROBUST: positive CAGR across all periods, low spread")
    elif cagr_min > 0:
        print("  ⚠ PARTIALLY ROBUST: positive everywhere but high variability")
    else:
        print("  ❌ FRAGILE: negative CAGR in at least one period")


# ============================================================================
# TEST 2: BEST CONFIG PER PERIOD (does optimal config drift?)
# ============================================================================

def find_best_in_period(funding_data: dict, start, end, label: str) -> dict:
    """Find best config for this specific period by grid search."""
    keys = list(PARAM_GRID.keys())
    values = [PARAM_GRID[k] for k in keys]
    best = None
    best_score = -np.inf
    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        m = run_period(funding_data, start, end, params)
        if not m:
            continue
        # Composite: CAGR / |MaxDD|
        dd = max(0.5, abs(m['max_dd_pct']))
        score = m['cagr_pct'] / dd
        if score > best_score:
            best_score = score
            best = {**params, **m, 'period': label}
    return best


def test_per_period_optimum(funding_data: dict):
    print("\n" + "=" * 90)
    print("TEST 2: BEST CONFIG IN EACH PERIOD (does the optimum drift?)")
    print("=" * 90)
    print(f"{'Period':<12} {'Smooth':>7} {'Hold':>7} {'Entry':>8} "
          f"{'CAGR':>9} {'Sharpe':>9} {'MaxDD':>9}")
    print("-" * 90)

    bests = []
    for start, end, label in PERIODS:
        b = find_best_in_period(funding_data, start, end, label)
        if b:
            print(f"{label:<12} {b['smooth_hours']:>5}h "
                  f"{b['min_hold_hours']:>5}h "
                  f"{b['entry_threshold_apr']*100:>6.1f}% "
                  f"{b['cagr_pct']:>8.2f}% "
                  f"{b['sharpe']:>9.2f} "
                  f"{b['max_dd_pct']:>8.2f}%")
            bests.append(b)

    print()
    if len(bests) >= 2:
        # Check if same config wins every period
        smooths = [b['smooth_hours'] for b in bests]
        holds = [b['min_hold_hours'] for b in bests]
        thresholds = [b['entry_threshold_apr'] for b in bests]

        same_smooth = len(set(smooths)) == 1
        same_hold = len(set(holds)) == 1
        same_thr = len(set(thresholds)) == 1

        if same_smooth and same_hold and same_thr:
            print("  ✅ SAME BEST CONFIG across all periods → very robust")
        elif sum([same_smooth, same_hold, same_thr]) >= 2:
            print("  ⚠ PARTIAL STABILITY: 2/3 parameters consistent")
        else:
            print("  ❌ OPTIMUM DRIFTS: different best config per period → likely overfit")


# ============================================================================
# TEST 3: TRUE OUT-OF-SAMPLE
# ============================================================================

def test_out_of_sample(funding_data: dict):
    """
    Find best config on first half (training), apply blindly to second half (test).
    The clean overfit detector.
    """
    print("\n" + "=" * 90)
    print("TEST 3: TRUE OUT-OF-SAMPLE (train on first half, test on second)")
    print("=" * 90)

    # Determine split: first half = 2024-01 to 2025-04, second half = 2025-05 onwards
    train_start = '2024-01-01'
    train_end = '2025-04-30'
    test_start = '2025-05-01'
    test_end = '2026-04-30'

    print(f"  Train: {train_start} → {train_end}")
    print(f"  Test:  {test_start} → {test_end}")
    print()

    # 1. Find best config on training period
    print("  Finding best config on training period...")
    best = find_best_in_period(funding_data, train_start, train_end, 'train')
    if not best:
        print("  ⚠ Could not find best on training period")
        return

    print(f"  Best train config: smooth={best['smooth_hours']}h, "
          f"hold={best['min_hold_hours']}h, "
          f"entry={best['entry_threshold_apr']*100:.1f}% APR")
    print(f"  Train CAGR: {best['cagr_pct']:.2f}%, Sharpe: {best['sharpe']:.2f}")

    # 2. Apply same config to test period (no peeking, no re-tuning)
    test_params = {
        'smooth_hours': best['smooth_hours'],
        'min_hold_hours': best['min_hold_hours'],
        'entry_threshold_apr': best['entry_threshold_apr'],
        'exit_threshold_apr': -0.005,
        'min_flat_hours': 24,
    }
    test_result = run_period(funding_data, test_start, test_end, test_params)

    if not test_result:
        print("  ⚠ Test period failed")
        return

    print(f"\n  Test CAGR (same config, unseen period): {test_result['cagr_pct']:.2f}%")
    print(f"  Test Sharpe: {test_result['sharpe']:.2f}")
    print(f"  Test MaxDD:  {test_result['max_dd_pct']:.2f}%")

    # Verdict
    degradation = best['cagr_pct'] - test_result['cagr_pct']
    print()
    print(f"  Performance degradation: {degradation:.2f} points")

    if test_result['cagr_pct'] > 0 and degradation < 5:
        print("  ✅ NO OVERFITTING: test performance close to training")
    elif test_result['cagr_pct'] > 0:
        print(f"  ⚠ MILD OVERFITTING: train {best['cagr_pct']:.2f}% vs "
              f"test {test_result['cagr_pct']:.2f}%, but still profitable")
    else:
        print("  ❌ SEVERE OVERFITTING: strategy collapses out-of-sample")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n=== WALK-FORWARD ANALYSIS ===")
    print(f"\nLoading data...")
    funding_data = {sym: fetch_funding(sym) for sym in cfg()['exchange']['symbols']}

    test_fixed_config(funding_data)
    test_per_period_optimum(funding_data)
    test_out_of_sample(funding_data)

    print("\n" + "=" * 90)
    print("FINAL VERDICT")
    print("=" * 90)
    print("""
Read all 3 tests above:
  - If all ✅: strategy is genuinely robust, safe to consider for dry-run
  - If mix of ✅ and ⚠: usable but expect 20-40% performance degradation live
  - If any ❌: strategy is overfitted, don't trust it
""")


if __name__ == '__main__':
    main()
