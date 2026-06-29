"""
Walk-Forward Validation for Trend Following
=============================================
Splits the 209-day trading period into TRAIN (first half) and TEST (second half).
For each half, tests all MA windows independently.

Question: does MA147 (or its neighbors MA100-180) stay optimal across both halves?
  - If YES → genuine edge, not overfit
  - If NO  → results from compare_regimes.py are partly noise

Usage:
    python walkforward_trend.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_prices
from data.fetch_extended import fetch_btc_extended_daily
from strategies.trend_following import (
    generate_trend_position, compute_regime_filter
)
from backtest.directional_engine import run_directional_backtest


MA_WINDOWS = [None, 50, 100, 147, 180, 200, 250]

DEFAULT_PARAMS = {
    'lookback_days': 20,
    'exit_lookback_days': 10,
    'atr_period_days': 20,
    'atr_stop_multiplier': 2.0,
    'mode': 'long_short',
}


def to_daily(prices_hourly: pd.DataFrame) -> pd.DataFrame:
    return prices_hourly.resample('1D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna()


def get_costs():
    f_cfg = cfg()['friction']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    return fee + f_cfg['slippage_median_bps']


def run_window(
    prices_daily_by_symbol: dict,
    ma_days,
    btc_for_regime: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    capital_per_symbol=10_000,
) -> dict:
    """Run backtest restricted to [start, end] window with given MA."""
    regime_filter = None
    if ma_days is not None:
        if len(btc_for_regime) < ma_days + 5:
            return {'error': f'Need {ma_days}+ bars'}
        regime_filter = compute_regime_filter(btc_for_regime, ma_days=ma_days)

    cost = get_costs()
    per_symbol = []

    for sym, prices_daily_full in prices_daily_by_symbol.items():
        # Restrict to the window
        prices_daily = prices_daily_full[
            (prices_daily_full.index >= start) & (prices_daily_full.index <= end)
        ]
        if len(prices_daily) < DEFAULT_PARAMS['lookback_days'] + 30:
            continue

        position = generate_trend_position(
            prices_daily,
            lookback_days=DEFAULT_PARAMS['lookback_days'],
            exit_lookback_days=DEFAULT_PARAMS['exit_lookback_days'],
            atr_period_days=DEFAULT_PARAMS['atr_period_days'],
            atr_stop_multiplier=DEFAULT_PARAMS['atr_stop_multiplier'],
            mode=DEFAULT_PARAMS['mode'],
            regime_filter=regime_filter,
        )
        result = run_directional_backtest(
            prices_daily['close'], position,
            capital=capital_per_symbol,
            entry_cost_bps=cost, exit_cost_bps=cost,
        )
        per_symbol.append(result['metrics'])

    if not per_symbol:
        return {'error': 'no data'}

    total_capital = capital_per_symbol * len(per_symbol)
    total_pnl = sum(m['total_pnl_usd'] for m in per_symbol)
    total_long_pnl = sum(m['long_pnl_usd'] for m in per_symbol)
    total_short_pnl = sum(m['short_pnl_usd'] for m in per_symbol)
    n_trades = sum(m['n_trades'] for m in per_symbol)
    avg_sharpe = float(np.mean([m['sharpe'] for m in per_symbol]))
    worst_dd = float(min(m['max_dd_pct'] for m in per_symbol))
    total_return_pct = total_pnl / total_capital * 100

    span_days = max((end - start).days, 1)
    years = span_days / 365.25
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    return {
        'ma_days': ma_days,
        'cagr_pct': cagr,
        'sharpe': avg_sharpe,
        'max_dd_pct': worst_dd,
        'n_trades': n_trades,
        'long_pnl_usd': total_long_pnl,
        'short_pnl_usd': total_short_pnl,
        'total_pnl_usd': total_pnl,
        'span_days': span_days,
    }


def print_table(label: str, results: list):
    print(f"\n{'='*100}")
    print(f"{label}")
    print(f"{'='*100}")
    print(f"{'MA':<10} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>9} {'#Trades':>8} "
          f"{'Long P&L':>12} {'Short P&L':>12} {'Total':>10}")
    print('-' * 100)

    for r in results:
        ma = r.get('ma_days')
        label = 'No filter' if ma is None else f"MA{ma}"
        if 'error' in r:
            print(f"{label:<10} ⚠ {r['error']}")
            continue
        print(f"{label:<10} {r['cagr_pct']:>8.2f}% {r['sharpe']:>8.2f} "
              f"{r['max_dd_pct']:>8.2f}% {r['n_trades']:>8} "
              f"${r['long_pnl_usd']:>10,.0f} ${r['short_pnl_usd']:>10,.0f} "
              f"${r['total_pnl_usd']:>8,.0f}")


def main():
    print("\n=== WALK-FORWARD VALIDATION FOR TREND FOLLOWING ===\n")
    print("Loading data...")

    prices_daily_by_symbol = {}
    for sym in cfg()['exchange']['symbols']:
        prices_hourly = fetch_prices(sym)
        if not prices_hourly.empty:
            prices_daily_by_symbol[sym] = to_daily(prices_hourly)

    btc_extended = fetch_btc_extended_daily(years_back=3)
    if btc_extended.empty:
        print("⚠ Cannot fetch extended BTC")
        return

    # Determine split
    hl_btc = prices_daily_by_symbol['BTC/USDC:USDC']
    full_start = hl_btc.index[0]
    full_end = hl_btc.index[-1]
    mid = full_start + (full_end - full_start) / 2

    print(f"\nFull trading period: {full_start.date()} → {full_end.date()} "
          f"({(full_end - full_start).days} days)")
    print(f"  TRAIN: {full_start.date()} → {mid.date()} ({(mid - full_start).days} days)")
    print(f"  TEST:  {mid.date()} → {full_end.date()} ({(full_end - mid).days} days)")

    # Train results
    print("\nRunning TRAIN window...")
    train_results = []
    for ma in MA_WINDOWS:
        r = run_window(prices_daily_by_symbol, ma, btc_extended, full_start, mid)
        train_results.append(r)

    # Test results
    print("Running TEST window...")
    test_results = []
    for ma in MA_WINDOWS:
        r = run_window(prices_daily_by_symbol, ma, btc_extended, mid, full_end)
        test_results.append(r)

    # Print tables
    print_table("TRAIN PERIOD (first half — used to find 'best' MA)", train_results)
    print_table("TEST PERIOD (second half — true out-of-sample)", test_results)

    # Analysis
    print(f"\n{'='*100}")
    print("CROSS-PERIOD ANALYSIS")
    print(f"{'='*100}\n")

    print(f"{'MA':<10} {'Train CAGR':>13} {'Test CAGR':>13} {'Degradation':>14} {'Verdict':<30}")
    print('-' * 100)

    # Find best MA on train
    valid_train = [r for r in train_results if 'error' not in r and r.get('ma_days') is not None]
    valid_test = [r for r in test_results if 'error' not in r and r.get('ma_days') is not None]

    if not valid_train or not valid_test:
        print("⚠ Insufficient data")
        return

    best_on_train = max(valid_train, key=lambda x: x['cagr_pct'])

    test_by_ma = {r.get('ma_days'): r for r in test_results}
    for tr in train_results:
        ma = tr.get('ma_days')
        label = 'No filter' if ma is None else f"MA{ma}"
        te = test_by_ma.get(ma, {})
        if 'error' in tr or 'error' in te:
            print(f"{label:<10} (skipped)")
            continue
        train_cagr = tr['cagr_pct']
        test_cagr = te['cagr_pct']
        degradation = train_cagr - test_cagr

        if test_cagr > 5:
            verdict = "✓ profitable in OOS"
        elif test_cagr > 0:
            verdict = "~ marginally positive OOS"
        else:
            verdict = "✗ negative OOS"

        marker = ""
        if ma == best_on_train.get('ma_days'):
            marker = " ← best train"
        if ma == 147:
            marker = " ← MA147"

        print(f"{label:<10} {train_cagr:>12.2f}% {test_cagr:>12.2f}% "
              f"{degradation:>+13.2f}pp {verdict}{marker}")

    print()
    print(f"Best MA on TRAIN: MA{best_on_train.get('ma_days')} → "
          f"train CAGR {best_on_train['cagr_pct']:.2f}%")

    # Apply best train config to test
    same_in_test = next((r for r in test_results
                        if r.get('ma_days') == best_on_train.get('ma_days')), None)
    if same_in_test and 'error' not in same_in_test:
        print(f"Same config applied to TEST: CAGR {same_in_test['cagr_pct']:.2f}% "
              f"(degradation: {best_on_train['cagr_pct'] - same_in_test['cagr_pct']:+.2f}pp)")

    # MA147 specific
    ma147_train = next((r for r in train_results if r.get('ma_days') == 147), None)
    ma147_test = next((r for r in test_results if r.get('ma_days') == 147), None)
    if ma147_train and ma147_test and 'error' not in ma147_train and 'error' not in ma147_test:
        print(f"\nMA147 specifically:")
        print(f"  Train CAGR: {ma147_train['cagr_pct']:.2f}%")
        print(f"  Test CAGR:  {ma147_test['cagr_pct']:.2f}%")
        diff = ma147_train['cagr_pct'] - ma147_test['cagr_pct']
        print(f"  Degradation: {diff:+.2f}pp")
        if ma147_test['cagr_pct'] > 15:
            print("  ✅ MA147 PASSES the out-of-sample test (Test CAGR > 15%)")
        elif ma147_test['cagr_pct'] > 0:
            print("  ⚠ MA147 PARTIALLY passes (positive OOS but degraded)")
        else:
            print("  ❌ MA147 FAILS out-of-sample — overfit to first half")

    print(f"\n{'='*100}")
    print("FINAL VERDICT")
    print(f"{'='*100}")
    print("""
  Read the cross-period table above:

  - If MA147 (or MA100-180 range) stays profitable on TEST → genuine edge ✓
  - If best-train degrades a lot on test → overfit warning
  - If most MAs are profitable on TEST → trend following itself is robust ✓
  - If most MAs negative on TEST → bad period or strategy doesn't work
""")


if __name__ == '__main__':
    main()
