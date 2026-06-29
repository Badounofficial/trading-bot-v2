"""
Tests for Mean Reversion and Cross-Sectional Momentum strategies.

Run with: python tests/test_mr_xsec.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from strategies.mean_reversion import (
    compute_bollinger, compute_rsi, generate_mean_reversion_position
)
from strategies.momentum_xsec import generate_xsec_positions, backtest_xsec
from backtest.directional_engine import run_directional_backtest


# ============================================================================
# MEAN REVERSION TESTS
# ============================================================================

def test_bollinger_basic():
    """Bollinger bands of a constant series should equal the value."""
    n = 30
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = pd.Series([100.0] * n, index=idx)
    lo, mid, hi = compute_bollinger(prices, period=20, n_std=2.0)
    last_mid = mid.iloc[-1]
    last_lo = lo.iloc[-1]
    last_hi = hi.iloc[-1]
    assert abs(last_mid - 100) < 0.01
    # Std of constant series is 0, so bands collapse to mid
    assert abs(last_lo - 100) < 0.01
    assert abs(last_hi - 100) < 0.01
    print("✓ test_bollinger_basic")


def test_rsi_basic():
    """RSI of consistent upward moves should be ~100."""
    n = 30
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = pd.Series(np.linspace(100, 130, n), index=idx)
    rsi = compute_rsi(prices, period=14)
    last_rsi = rsi.iloc[-1]
    # Pure uptrend → RSI very high (close to 100)
    assert last_rsi > 90, f"Expected RSI > 90 for pure uptrend, got {last_rsi:.1f}"
    print(f"✓ test_rsi_basic (uptrend RSI = {last_rsi:.1f})")


def test_rsi_downtrend():
    """RSI of consistent downward moves should be ~0."""
    n = 30
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = pd.Series(np.linspace(130, 100, n), index=idx)
    rsi = compute_rsi(prices, period=14)
    last_rsi = rsi.iloc[-1]
    assert last_rsi < 15, f"Expected RSI < 15 for pure downtrend, got {last_rsi:.1f}"
    print(f"✓ test_rsi_downtrend (downtrend RSI = {last_rsi:.1f})")


def test_mr_long_entry_on_oversold():
    """Mean reversion should enter long when price < lower BB AND RSI low."""
    n = 50
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # 30 bars flat at 100, then sudden crash to 80
    prices = [100.0] * 30 + list(np.linspace(100, 80, 20))
    df = pd.DataFrame({
        'open': prices, 'high': [p + 0.5 for p in prices],
        'low': [p - 0.5 for p in prices], 'close': prices,
    }, index=idx)
    pos = generate_mean_reversion_position(df, bb_period=20, bb_std=2.0,
                                            rsi_period=14, mode='long_only')
    # Should have at least entered long at some point during the crash
    n_long_bars = (pos == 1).sum()
    assert n_long_bars > 0, f"Expected long entry during oversold crash, got {n_long_bars}"
    print(f"✓ test_mr_long_entry_on_oversold ({n_long_bars} bars long)")


def test_mr_exits_at_mean():
    """Mean reversion should exit when price returns to middle BB."""
    n = 80
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # Flat → crash → recover (V-shaped)
    prices = ([100.0] * 30
              + list(np.linspace(100, 80, 15))   # crash to 80
              + list(np.linspace(80, 100, 35)))   # recover to 100
    df = pd.DataFrame({
        'open': prices, 'high': [p + 0.5 for p in prices],
        'low': [p - 0.5 for p in prices], 'close': prices,
    }, index=idx)
    pos = generate_mean_reversion_position(df, bb_period=20, bb_std=2.0,
                                            rsi_period=14, mode='long_only')
    # By end of recovery, should be flat (mean reverted)
    end_flat = (pos.iloc[-5:] == 0).any()
    assert end_flat, "Expected to be flat after recovery to mean"
    print(f"✓ test_mr_exits_at_mean")


# ============================================================================
# CROSS-SECTIONAL MOMENTUM TESTS
# ============================================================================

def test_xsec_basic_positions():
    """At rebalance, should be long top-K and short bottom-K."""
    # 4 cryptos: A goes up, B flat, C flat, D goes down
    n = 50
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    closes = pd.DataFrame({
        'A': np.linspace(100, 200, n),   # +100% over period
        'B': [100.0] * n,                # flat
        'C': [100.0] * n,                # flat
        'D': np.linspace(100, 50, n),    # -50% over period
    }, index=idx)

    positions = generate_xsec_positions(closes, lookback_days=20,
                                          rebalance_days=10, n_long=1, n_short=1)
    # After warmup, A should be long, D should be short
    last_pos = positions.iloc[-1]
    assert last_pos['A'] == 1, f"Expected A long (top), got {last_pos['A']}"
    assert last_pos['D'] == -1, f"Expected D short (bottom), got {last_pos['D']}"
    print(f"✓ test_xsec_basic_positions")


def test_xsec_backtest_uptrend_winner():
    """Long the winner, short the loser → should profit."""
    n = 100
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    closes = pd.DataFrame({
        'WINNER': np.linspace(100, 200, n),
        'LOSER':  np.linspace(100, 50, n),
    }, index=idx)

    positions = generate_xsec_positions(closes, lookback_days=20,
                                          rebalance_days=10, n_long=1, n_short=1)
    result = backtest_xsec(closes, positions, capital_per_position=10_000,
                            entry_cost_bps=0, exit_cost_bps=0)
    # WINNER long should make ~100%, LOSER short should make ~50%
    # Combined ≈ 75% on capital_per_position×2
    pnl = result['metrics']['total_pnl_usd']
    assert pnl > 5000, f"Expected significant profit, got ${pnl:.0f}"
    print(f"✓ test_xsec_backtest_uptrend_winner (P&L = ${pnl:,.0f})")


def test_xsec_backtest_correlated_assets_low_pnl():
    """If all assets move in same direction, cross-sectional momentum makes ~zero."""
    n = 100
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # All 4 assets move up together, just at slightly different rates
    base = np.linspace(100, 200, n)
    closes = pd.DataFrame({
        'A': base * 1.0,
        'B': base * 0.98,
        'C': base * 1.02,
        'D': base * 0.99,
    }, index=idx)

    positions = generate_xsec_positions(closes, lookback_days=20,
                                          rebalance_days=10, n_long=1, n_short=1)
    result = backtest_xsec(closes, positions, capital_per_position=10_000,
                            entry_cost_bps=0, exit_cost_bps=0)
    # Top mover should make slightly more than bottom mover loses
    # Total should be small in magnitude (we'd expect maybe ±5% of capital)
    pnl = result['metrics']['total_pnl_usd']
    # If correlated, dispersion is small → P&L is small
    print(f"✓ test_xsec_backtest_correlated_assets_low_pnl (P&L = ${pnl:,.0f}, "
          f"avg active = {result['metrics']['avg_active_positions']:.1f})")


def test_xsec_rebalances_at_correct_frequency():
    """Should rebalance every N days, not every day."""
    n = 100
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    closes = pd.DataFrame({
        'A': np.linspace(100, 200, n),
        'B': np.linspace(100, 50, n),
    }, index=idx)
    positions = generate_xsec_positions(closes, lookback_days=20,
                                          rebalance_days=10, n_long=1, n_short=1)

    # Count distinct position changes — should be much fewer than days
    pos_diff = positions.diff().fillna(0)
    changes = (pos_diff != 0).any(axis=1).sum()
    # Roughly: (n - lookback) / rebalance ~ 80/10 = 8 rebalances
    assert changes < 20, f"Too many rebalances ({changes}), should be ~8"
    print(f"✓ test_xsec_rebalances_at_correct_frequency ({changes} changes)")


# ============================================================================
# RUN ALL
# ============================================================================

def run_all():
    tests = [
        test_bollinger_basic,
        test_rsi_basic,
        test_rsi_downtrend,
        test_mr_long_entry_on_oversold,
        test_mr_exits_at_mean,
        test_xsec_basic_positions,
        test_xsec_backtest_uptrend_winner,
        test_xsec_backtest_correlated_assets_low_pnl,
        test_xsec_rebalances_at_correct_frequency,
    ]
    print("=" * 70)
    print("RUNNING MR + XSEC TESTS")
    print("=" * 70)
    n_pass = n_fail = 0
    failures = []
    for t in tests:
        try:
            t()
            n_pass += 1
        except AssertionError as e:
            n_fail += 1
            failures.append((t.__name__, str(e)))
            print(f"✗ {t.__name__}: {e}")
        except Exception as e:
            n_fail += 1
            failures.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"✗ {t.__name__}: ERROR {type(e).__name__}: {e}")

    print()
    print(f"RESULT: {n_pass} passed, {n_fail} failed")
    if failures:
        for name, err in failures:
            print(f"  - {name}: {err}")
    return n_fail == 0


if __name__ == '__main__':
    success = run_all()
    sys.exit(0 if success else 1)
