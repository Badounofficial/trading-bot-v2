"""
Tests for directional engine and trend following strategy.

Run with: python tests/test_trend.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from backtest.directional_engine import run_directional_backtest
from strategies.trend_following import generate_trend_position, compute_atr


# ============================================================================
# ENGINE TESTS
# ============================================================================

def test_directional_zero_position_no_pnl():
    """Never in position → no P&L."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    prices = pd.Series(np.linspace(100, 120, 100), index=idx)  # uptrend
    position = pd.Series(0, index=idx)
    result = run_directional_backtest(prices, position, capital=10_000,
                                       entry_cost_bps=0, exit_cost_bps=0)
    assert abs(result['metrics']['total_pnl_usd']) < 0.01
    print("✓ test_directional_zero_position_no_pnl")


def test_long_captures_uptrend():
    """Long all the way on uptrend should profit."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    # Price goes from 100 to 110 = +10%
    prices = pd.Series(np.linspace(100, 110, 100), index=idx)
    position = pd.Series(1, index=idx)
    result = run_directional_backtest(prices, position, capital=10_000,
                                       entry_cost_bps=0, exit_cost_bps=0)
    # Should profit ~10% = $1000
    pnl = result['metrics']['total_pnl_usd']
    assert 950 < pnl < 1050, f"Expected ~$1000, got ${pnl:.2f}"
    print(f"✓ test_long_captures_uptrend (got ${pnl:.2f}, expected ~$1000)")


def test_short_captures_downtrend():
    """Short all the way on downtrend should profit."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    prices = pd.Series(np.linspace(110, 100, 100), index=idx)  # -9.09%
    position = pd.Series(-1, index=idx)
    result = run_directional_backtest(prices, position, capital=10_000,
                                       entry_cost_bps=0, exit_cost_bps=0)
    pnl = result['metrics']['total_pnl_usd']
    # The engine computes period-by-period compound P&L (position * pct_change × capital,
    # summed each period). For a -1 position throughout, the cumulative P&L on linear
    # price decline 110→100 ≈ +$952 (slightly more than naive 9.09% because of compounding
    # the relative returns each period).
    assert 900 < pnl < 1000, f"Expected ~$950, got ${pnl:.2f}"
    print(f"✓ test_short_captures_downtrend (got ${pnl:.2f}, expected ~$950)")


def test_long_loses_on_downtrend():
    """Long during a downtrend should lose."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    prices = pd.Series(np.linspace(100, 90, 100), index=idx)
    position = pd.Series(1, index=idx)
    result = run_directional_backtest(prices, position, capital=10_000,
                                       entry_cost_bps=0, exit_cost_bps=0)
    pnl = result['metrics']['total_pnl_usd']
    assert pnl < -800, f"Expected loss ~$1000, got ${pnl:.2f}"
    print(f"✓ test_long_loses_on_downtrend (got ${pnl:.2f})")


def test_costs_charged_on_entry_exit():
    """Round-trip cost should match (entry+exit) bps."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    prices = pd.Series(100.0, index=idx)  # flat price, no P&L from moves
    position = pd.Series(0, index=idx)
    position.iloc[10:90] = 1  # enter at bar 10, exit at bar 90
    result = run_directional_backtest(prices, position, capital=10_000,
                                       entry_cost_bps=10, exit_cost_bps=10)
    # No price movement → P&L should be -$20 (just costs)
    pnl = result['metrics']['total_pnl_usd']
    expected = -(10 + 10) / 10_000 * 10_000  # = -$20
    assert abs(pnl - expected) < 0.5, f"Expected -$20, got ${pnl:.2f}"
    print(f"✓ test_costs_charged_on_entry_exit (got ${pnl:.2f}, expected -$20)")


# ============================================================================
# STRATEGY TESTS
# ============================================================================

def test_atr_basic():
    """ATR computation on simple known case."""
    n = 30
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    df = pd.DataFrame({
        'high': [102.0] * n,
        'low': [98.0] * n,
        'close': [100.0] * n,
    }, index=idx)
    atr = compute_atr(df, period_days=20)
    # TR = max(high-low, ...) = 4 always (because |102-100|=2, |98-100|=2 are smaller than 4)
    # ATR = mean of TR over 20 days = 4
    last_atr = atr.dropna().iloc[-1]
    assert abs(last_atr - 4.0) < 0.1, f"Expected ATR ~4, got {last_atr}"
    print(f"✓ test_atr_basic (ATR = {last_atr:.2f})")


def test_trend_position_enters_long_on_breakout():
    """Strategy should enter long when price breaks above N-day high."""
    n = 50
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # Flat at 100 for 30 bars, then breakout to 120
    prices = [100.0] * 30 + list(np.linspace(100, 120, 20))
    df = pd.DataFrame({
        'high': [p + 0.5 for p in prices],
        'low':  [p - 0.5 for p in prices],
        'close': prices,
    }, index=idx)
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    mode='long_only')
    # After breakout, we should be long for most of the rising period
    # The exact bar of entry depends on when close > prior_max
    in_long_at_end = pos.iloc[-1] == 1
    assert in_long_at_end, f"Expected long at end (price 120 vs prior max 100), got {pos.iloc[-1]}"
    print(f"✓ test_trend_position_enters_long_on_breakout")


def test_trend_position_enters_short_on_breakdown():
    """Strategy should enter short when price breaks below N-day low."""
    n = 50
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = [100.0] * 30 + list(np.linspace(100, 80, 20))  # downtrend
    df = pd.DataFrame({
        'high': [p + 0.5 for p in prices],
        'low':  [p - 0.5 for p in prices],
        'close': prices,
    }, index=idx)
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    mode='long_short')
    in_short_at_end = pos.iloc[-1] == -1
    assert in_short_at_end, f"Expected short at end, got {pos.iloc[-1]}"
    print(f"✓ test_trend_position_enters_short_on_breakdown")


def test_trend_position_stops_out():
    """Stop loss should trigger when price moves 2x ATR against us."""
    n = 60
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # Flat baseline, breakout up, then sharp reversal
    prices = ([100.0] * 25
              + list(np.linspace(100, 120, 10))  # breakout
              + list(np.linspace(120, 100, 5))   # reverse fast
              + [100.0] * 20)
    df = pd.DataFrame({
        'high': [p + 1 for p in prices],
        'low':  [p - 1 for p in prices],
        'close': prices,
    }, index=idx)
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    atr_stop_multiplier=2.0, mode='long_only')
    # We should have been long during the up move, then exited during the sharp reversal
    n_long = int((pos == 1).sum())
    n_flat_after = int((pos.iloc[-15:] == 0).sum())
    assert n_long > 5, f"Expected some long bars during uptrend, got {n_long}"
    assert n_flat_after > 5, f"Expected to be flat after reversal, got {n_flat_after}"
    print(f"✓ test_trend_position_stops_out (was long {n_long} bars, flat {n_flat_after} bars after)")


def test_trend_position_long_only_never_shorts():
    """In long_only mode, position should never be -1."""
    n = 80
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = list(np.linspace(100, 80, n))  # pure downtrend
    df = pd.DataFrame({
        'high': [p + 1 for p in prices],
        'low':  [p - 1 for p in prices],
        'close': prices,
    }, index=idx)
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    mode='long_only')
    assert (pos == -1).sum() == 0, f"long_only should never go short, but got {(pos == -1).sum()} shorts"
    print(f"✓ test_trend_position_long_only_never_shorts")


# ============================================================================
# REGIME FILTER TESTS
# ============================================================================

def test_regime_filter_basic():
    """Regime filter: BTC > MA200 → +1, BTC < MA200 → -1."""
    from strategies.trend_following import compute_regime_filter
    n = 250  # enough for MA200 + warmup
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # Price climbs from 100 to 200 — most of the second half should be bull
    prices = np.linspace(100, 200, n)
    df = pd.DataFrame({
        'high': prices + 1,
        'low':  prices - 1,
        'close': prices,
        'open': prices,
    }, index=idx)
    regime = compute_regime_filter(df, ma_days=200)
    # First ~200 bars: warmup → regime should be 0
    assert (regime.iloc[:199] == 0).all(), "First 200 bars should be warmup (regime=0)"
    # Last bars: price clearly above MA → bull (regime = +1)
    assert regime.iloc[-1] == 1, f"Expected bull at end, got {regime.iloc[-1]}"
    print(f"✓ test_regime_filter_basic")


def test_regime_filter_blocks_longs_in_bear():
    """When regime says -1 (bear), no long should ever be opened."""
    n = 100
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    # Create a flat-then-breakout-up price (should trigger long signal)
    prices = [100.0] * 30 + list(np.linspace(100, 120, 70))
    df = pd.DataFrame({
        'high': [p + 0.5 for p in prices],
        'low':  [p - 0.5 for p in prices],
        'close': prices,
    }, index=idx)
    # But regime is -1 (bear) the whole time → no longs allowed
    regime = pd.Series(-1, index=idx, dtype=int)
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    mode='long_short', regime_filter=regime)
    assert (pos == 1).sum() == 0, \
        f"Bear regime should block longs, but got {(pos == 1).sum()} long bars"
    print(f"✓ test_regime_filter_blocks_longs_in_bear")


def test_regime_filter_blocks_shorts_in_bull():
    """When regime says +1 (bull), no short should ever be opened."""
    n = 100
    idx = pd.date_range('2024-01-01', periods=n, freq='1D')
    prices = [100.0] * 30 + list(np.linspace(100, 80, 70))  # downtrend → would trigger short
    df = pd.DataFrame({
        'high': [p + 0.5 for p in prices],
        'low':  [p - 0.5 for p in prices],
        'close': prices,
    }, index=idx)
    regime = pd.Series(1, index=idx, dtype=int)  # bull the whole time
    pos = generate_trend_position(df, lookback_days=20, exit_lookback_days=10,
                                    mode='long_short', regime_filter=regime)
    assert (pos == -1).sum() == 0, \
        f"Bull regime should block shorts, but got {(pos == -1).sum()} short bars"
    print(f"✓ test_regime_filter_blocks_shorts_in_bull")


# ============================================================================
# RUN ALL
# ============================================================================

def run_all():
    tests = [
        test_directional_zero_position_no_pnl,
        test_long_captures_uptrend,
        test_short_captures_downtrend,
        test_long_loses_on_downtrend,
        test_costs_charged_on_entry_exit,
        test_atr_basic,
        test_trend_position_enters_long_on_breakout,
        test_trend_position_enters_short_on_breakdown,
        test_trend_position_stops_out,
        test_trend_position_long_only_never_shorts,
        test_regime_filter_basic,
        test_regime_filter_blocks_longs_in_bear,
        test_regime_filter_blocks_shorts_in_bull,
    ]
    print("=" * 70)
    print("RUNNING TREND FOLLOWING TESTS")
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
    print("=" * 70)
    print(f"RESULT: {n_pass} passed, {n_fail} failed")
    if failures:
        for name, err in failures:
            print(f"  - {name}: {err}")
    else:
        print("✅ All tests pass — directional engine and trend strategy validated.")
    print("=" * 70)
    return n_fail == 0


if __name__ == '__main__':
    success = run_all()
    sys.exit(0 if success else 1)
