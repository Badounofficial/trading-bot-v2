"""
Combined Runner: Mean Reversion + Cross-Sectional Momentum
============================================================
Runs both strategies on the multi-asset universe, with built-in walk-forward
validation to avoid overfitting traps.

Usage:
    python run_strategies.py test         # validate all units
    python run_strategies.py fetch        # download universe
    python run_strategies.py mr           # mean reversion only
    python run_strategies.py xsec         # cross-sectional momentum only
    python run_strategies.py all          # both + walk-forward + side-by-side
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch_universe import fetch_universe_daily, align_universe, UNIVERSE_SYMBOLS
from strategies.mean_reversion import generate_mean_reversion_position
from strategies.momentum_xsec import generate_xsec_positions, backtest_xsec
from backtest.directional_engine import run_directional_backtest


def get_costs():
    f_cfg = cfg()['friction']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    return fee + f_cfg['slippage_median_bps']


# ============================================================================
# MEAN REVERSION FULL BACKTEST
# ============================================================================

def backtest_mr(universe: dict, start=None, end=None, params=None) -> dict:
    """Run mean reversion on each asset, aggregate."""
    if params is None:
        params = {
            'bb_period': 20, 'bb_std': 2.0,
            'rsi_period': 14, 'rsi_oversold': 30, 'rsi_overbought': 70,
            'atr_period': 14, 'atr_stop_multiplier': 2.0,
            'mode': 'long_short',
        }

    cost = get_costs()
    capital = 10_000
    per_symbol = []
    detailed = []

    for sym, prices_daily in universe.items():
        # Restrict to window
        df = prices_daily.copy()
        if start is not None:
            df = df[df.index >= start]
        if end is not None:
            df = df[df.index <= end]
        if len(df) < 60:
            continue

        position = generate_mean_reversion_position(df, **params)
        result = run_directional_backtest(
            df['close'], position,
            capital=capital, entry_cost_bps=cost, exit_cost_bps=cost,
        )
        m = result['metrics']
        m['symbol'] = sym
        per_symbol.append(m)
        detailed.append({'sym': sym, 'metrics': m})

    return aggregate_results(per_symbol, capital, universe, start, end)


# ============================================================================
# CROSS-SECTIONAL MOMENTUM FULL BACKTEST
# ============================================================================

def backtest_xsec_wrapper(universe: dict, start=None, end=None, params=None) -> dict:
    """Cross-sectional momentum on aligned universe."""
    if params is None:
        params = {
            'lookback_days': 30, 'rebalance_days': 7,
            'n_long': 3, 'n_short': 3,
        }

    closes = align_universe(universe)
    if start is not None:
        closes = closes[closes.index >= start]
    if end is not None:
        closes = closes[closes.index <= end]
    if len(closes) < 60:
        return {'error': 'insufficient data'}

    cost = get_costs()
    positions = generate_xsec_positions(closes, **params)
    result = backtest_xsec(closes, positions, capital_per_position=10_000,
                            entry_cost_bps=cost, exit_cost_bps=cost)
    m = result['metrics']
    m['strategy'] = 'xsec'
    return m


# ============================================================================
# AGGREGATION
# ============================================================================

def aggregate_results(per_symbol, capital, universe, start, end):
    if not per_symbol:
        return {'error': 'no symbols ran'}
    total_capital = capital * len(per_symbol)
    total_pnl = sum(m['total_pnl_usd'] for m in per_symbol)
    long_pnl = sum(m.get('long_pnl_usd', 0) for m in per_symbol)
    short_pnl = sum(m.get('short_pnl_usd', 0) for m in per_symbol)
    n_trades = sum(m.get('n_trades', 0) for m in per_symbol)
    avg_sharpe = float(np.mean([m['sharpe'] for m in per_symbol]))
    worst_dd = float(min(m['max_dd_pct'] for m in per_symbol))
    total_return_pct = total_pnl / total_capital * 100

    # Span
    sample = next(iter(universe.values()))
    sym_df = sample
    if start is not None:
        sym_df = sym_df[sym_df.index >= start]
    if end is not None:
        sym_df = sym_df[sym_df.index <= end]
    span_days = max((sym_df.index[-1] - sym_df.index[0]).days, 1)
    years = span_days / 365.25
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    return {
        'total_capital_usd': total_capital,
        'total_pnl_usd': total_pnl,
        'long_pnl_usd': long_pnl,
        'short_pnl_usd': short_pnl,
        'n_trades': n_trades,
        'cagr_pct': float(cagr),
        'sharpe': avg_sharpe,
        'max_dd_pct': worst_dd,
        'span_days': span_days,
    }


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_test():
    from tests.test_mr_xsec import run_all
    sys.exit(0 if run_all() else 1)


def cmd_fetch():
    fetch_universe_daily(years_back=3)


def print_metrics(label, m):
    if 'error' in m:
        print(f"  {label}: ⚠ {m['error']}")
        return
    print(f"  {label}:")
    print(f"    Span:         {m.get('span_days', 0)} days")
    print(f"    CAGR:         {m['cagr_pct']:.2f}%")
    print(f"    Sharpe:       {m['sharpe']:.2f}")
    print(f"    Max DD:       {m['max_dd_pct']:.2f}%")
    print(f"    Trades:       {m.get('n_trades', m.get('n_long_entries', 0) + m.get('n_short_entries', 0))}")
    print(f"    Long P&L:     ${m.get('long_pnl_usd', 0):,.2f}")
    print(f"    Short P&L:    ${m.get('short_pnl_usd', 0):,.2f}")
    print(f"    Total P&L:    ${m['total_pnl_usd']:,.2f}")


def cmd_mr():
    print("\n=== MEAN REVERSION FULL PERIOD ===\n")
    universe = fetch_universe_daily(years_back=3)
    if not universe:
        return
    m = backtest_mr(universe)
    print_metrics('Mean Reversion', m)


def cmd_xsec():
    print("\n=== CROSS-SECTIONAL MOMENTUM FULL PERIOD ===\n")
    universe = fetch_universe_daily(years_back=3)
    if not universe:
        return
    m = backtest_xsec_wrapper(universe)
    print_metrics('Cross-Sectional Momentum', m)


def cmd_all():
    """Run both strategies with walk-forward validation."""
    print("\n=== FULL ANALYSIS: MR vs XSEC with Walk-Forward ===\n")
    universe = fetch_universe_daily(years_back=3)
    if not universe:
        print("⚠ No universe data")
        return

    # Determine common period
    closes = align_universe(universe)
    full_start = closes.index[0]
    full_end = closes.index[-1]
    mid = full_start + (full_end - full_start) / 2

    print(f"\nFull period: {full_start.date()} → {full_end.date()} ({(full_end-full_start).days} days)")
    print(f"  TRAIN: {full_start.date()} → {mid.date()}")
    print(f"  TEST:  {mid.date()} → {full_end.date()}")

    print("\n" + "="*80)
    print("MEAN REVERSION")
    print("="*80)
    print("\nFull period:")
    mr_full = backtest_mr(universe)
    print_metrics('MR full', mr_full)
    print("\nTRAIN:")
    mr_train = backtest_mr(universe, end=mid)
    print_metrics('MR train', mr_train)
    print("\nTEST (out-of-sample):")
    mr_test = backtest_mr(universe, start=mid)
    print_metrics('MR test', mr_test)

    print("\n" + "="*80)
    print("CROSS-SECTIONAL MOMENTUM")
    print("="*80)
    print("\nFull period:")
    xs_full = backtest_xsec_wrapper(universe)
    print_metrics('XSec full', xs_full)
    print("\nTRAIN:")
    xs_train = backtest_xsec_wrapper(universe, end=mid)
    print_metrics('XSec train', xs_train)
    print("\nTEST (out-of-sample):")
    xs_test = backtest_xsec_wrapper(universe, start=mid)
    print_metrics('XSec test', xs_test)

    # SIDE-BY-SIDE
    print("\n" + "="*80)
    print("SIDE-BY-SIDE COMPARISON")
    print("="*80)
    print(f"\n{'Strategy':<28} {'Full CAGR':>12} {'Train CAGR':>13} {'Test CAGR':>12} {'Verdict':<30}")
    print("-"*100)

    for name, full_m, train_m, test_m in [
        ('Mean Reversion', mr_full, mr_train, mr_test),
        ('Cross-Sec Momentum', xs_full, xs_train, xs_test),
    ]:
        if 'error' in full_m or 'error' in test_m:
            print(f"{name:<28} ⚠ skipped")
            continue
        full_c = full_m['cagr_pct']
        train_c = train_m['cagr_pct']
        test_c = test_m['cagr_pct']
        degradation = train_c - test_c
        if test_c > 10:
            verdict = "✅ ROBUST (positive OOS)"
        elif test_c > 0:
            verdict = "⚠ PARTIALLY positive OOS"
        else:
            verdict = "❌ NEGATIVE out-of-sample"
        print(f"{name:<28} {full_c:>11.2f}% {train_c:>12.2f}% {test_c:>11.2f}% {verdict}")

    print("\n" + "="*80)
    print("FINAL VERDICT")
    print("="*80)
    candidates = []
    if 'error' not in mr_test and mr_test['cagr_pct'] > 5:
        candidates.append(('Mean Reversion', mr_test['cagr_pct'], mr_test['sharpe'], mr_test['max_dd_pct']))
    if 'error' not in xs_test and xs_test['cagr_pct'] > 5:
        candidates.append(('Cross-Sec Momentum', xs_test['cagr_pct'], xs_test['sharpe'], xs_test['max_dd_pct']))

    if not candidates:
        print("\n  ❌ Neither strategy passes the out-of-sample test (Test CAGR < 5%).")
        print("     Both likely overfit or the period is unfavorable.")
        print("     Recommendation: don't deploy either.")
    else:
        print(f"\n  ✅ {len(candidates)} strategy(s) pass OOS:")
        for name, cagr, sh, dd in candidates:
            print(f"     {name}: CAGR {cagr:.2f}%, Sharpe {sh:.2f}, MaxDD {dd:.2f}%")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd == 'test':
        cmd_test()
    elif cmd == 'fetch':
        cmd_fetch()
    elif cmd == 'mr':
        cmd_mr()
    elif cmd == 'xsec':
        cmd_xsec()
    elif cmd == 'all':
        cmd_all()
    else:
        print(f"Unknown: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
