"""
Critical Tests
==============
These tests validate the backtest engine and strategy on cases where we know
the right answer manually. If any test fails, do NOT trust backtest results.

Run with: pytest tests/test_engine.py -v
Or:       python tests/test_engine.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from backtest.engine import run_backtest
from strategies.funding_capture import generate_position


# ============================================================================
# TEST 1: Engine math basics
# ============================================================================

def test_zero_funding_zero_position_returns_capital():
    """If funding is zero everywhere and we never enter, equity = capital."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(0.0, index=idx)
    position = pd.Series(0, index=idx)
    result = run_backtest(funding, position, capital=10_000)
    assert abs(result['equity'].iloc[-1] - 10_000) < 0.01, \
        f"Expected equity ~10000, got {result['equity'].iloc[-1]}"
    assert result['metrics']['total_pnl_usd'] == 0.0
    print("✓ test_zero_funding_zero_position_returns_capital")


def test_constant_positive_funding_no_position_no_pnl():
    """Even with positive funding, if we don't enter, P&L = 0."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(0.0001, index=idx)  # 0.01% per hour = 87.6% APR
    position = pd.Series(0, index=idx)
    result = run_backtest(funding, position, capital=10_000)
    assert result['metrics']['total_pnl_usd'] == 0.0
    print("✓ test_constant_positive_funding_no_position_no_pnl")


def test_constant_funding_always_in_position():
    """
    Sanity: 0.0001 funding/hour × 100 hours × $10,000 capital = $100 gross
    No costs (we set them to 0 in this test).
    """
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(0.0001, index=idx)
    position = pd.Series(1, index=idx)
    result = run_backtest(funding, position, capital=10_000,
                          entry_cost_bps=0, exit_cost_bps=0)
    expected_gross = 0.0001 * 100 * 10_000  # $100
    actual = result['metrics']['gross_funding_usd']
    assert abs(actual - expected_gross) < 0.01, \
        f"Expected ${expected_gross}, got ${actual}"
    print("✓ test_constant_funding_always_in_position")


def test_one_trade_with_costs():
    """
    Single trade: enter at hour 1, exit at hour 51 (50 hours in position).
    Funding 0.0001/h for 50 hours on $10,000 = $50 gross.
    Entry+exit cost: 10 bps total = $10.
    Net P&L should be $40.
    """
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(0.0001, index=idx)
    position = pd.Series(0, index=idx)
    position.iloc[1:51] = 1  # in position for bars 1..50 (50 bars)

    result = run_backtest(funding, position, capital=10_000,
                          entry_cost_bps=5, exit_cost_bps=5)
    # Gross funding: 0.0001 × 50 × 10000 = $50
    # Costs: 10 bps × 10000 = $10
    # Net: $40
    expected_net = 50.0 - 10.0
    actual_net = result['metrics']['total_pnl_usd']
    assert abs(actual_net - expected_net) < 0.5, \
        f"Expected net ~${expected_net}, got ${actual_net}"
    assert result['metrics']['n_entries'] == 1
    assert result['metrics']['n_exits'] == 1
    assert len(result['trades']) == 1
    print(f"✓ test_one_trade_with_costs (expected ${expected_net}, got ${actual_net:.2f})")


def test_negative_funding_in_position_loses_money():
    """If funding goes negative while in position, we lose money."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(-0.0001, index=idx)  # negative funding
    position = pd.Series(1, index=idx)
    result = run_backtest(funding, position, capital=10_000,
                          entry_cost_bps=0, exit_cost_bps=0)
    # 100 hours of -0.0001 × $10000 = -$100
    expected = -100.0
    actual = result['metrics']['gross_funding_usd']
    assert abs(actual - expected) < 0.01
    assert result['metrics']['total_pnl_usd'] < 0
    print("✓ test_negative_funding_in_position_loses_money")


# ============================================================================
# TEST 2: Sanity check vs MANUAL calculation on real data
# ============================================================================

def test_sanity_vs_manual_calculation_btc_feb2024():
    """
    Reproduce the manual sanity check from earlier:
    BTC Feb 1-15 2024, always-in delta neutral, ~$87 gross funding.

    Loads real data from cache. SKIPS if cache not present.
    """
    cache_path = Path(__file__).parent.parent / 'cache' / 'funding_hyperliquid_BTC_USDC_USDC.parquet'
    if not cache_path.exists():
        print(f"⚠ SKIP test_sanity_vs_manual: no cache at {cache_path}")
        return

    btc = pd.read_parquet(cache_path)
    start = pd.Timestamp('2024-02-01')
    end = pd.Timestamp('2024-02-15')
    window = btc[(btc.index >= start) & (btc.index < end)]
    assert len(window) > 100, f"Expected ~336 hourly fundings, got {len(window)}"

    # Always in position over the window
    position = pd.Series(1, index=window.index)

    result = run_backtest(window['fundingRate'], position, capital=10_000,
                          entry_cost_bps=10, exit_cost_bps=10)

    # Manual calculation (matches sanity_check.py):
    # gross = sum(fundingRate × 10000)
    # costs = 20 bps × 10000 = $20
    expected_gross = (window['fundingRate'] * 10_000).sum()
    expected_net = expected_gross - 20.0
    actual_net = result['metrics']['total_pnl_usd']

    print(f"  Manual:    gross=${expected_gross:.2f}, net=${expected_net:.2f}")
    print(f"  Engine:    gross=${result['metrics']['gross_funding_usd']:.2f}, "
          f"net=${actual_net:.2f}")
    assert abs(actual_net - expected_net) < 1.0, \
        f"Engine says ${actual_net}, manual says ${expected_net}"
    print(f"✓ test_sanity_vs_manual_calculation_btc_feb2024")


# ============================================================================
# TEST 3: Strategy logic
# ============================================================================

def test_strategy_enters_on_positive_smoothed_funding():
    """If funding is consistently positive, strategy should be in position."""
    idx = pd.date_range('2024-01-01', periods=100, freq='1h')
    funding = pd.Series(0.0001, index=idx)  # ~87% APR
    position = generate_position(funding, smooth_hours=24,
                                  entry_threshold_apr=0.005,
                                  exit_threshold_apr=-0.005,
                                  min_hold_hours=24, min_flat_hours=24)
    # First 24 bars are warmup (NaN smooth), then we should be in
    # position for the remaining bars
    in_position_after_warmup = position.iloc[30:].mean()
    assert in_position_after_warmup > 0.95, \
        f"Expected mostly in position after warmup, got {in_position_after_warmup}"
    print(f"✓ test_strategy_enters_on_positive_smoothed_funding "
          f"(time in position after warmup: {in_position_after_warmup*100:.0f}%)")


def test_strategy_exits_on_negative_smoothed_funding():
    """If funding turns negative for long enough, strategy exits."""
    idx = pd.date_range('2024-01-01', periods=200, freq='1h')
    funding = pd.Series(0.0001, index=idx)
    funding.iloc[100:] = -0.0001  # second half negative
    position = generate_position(funding, smooth_hours=24,
                                  entry_threshold_apr=0.005,
                                  exit_threshold_apr=-0.005,
                                  min_hold_hours=24, min_flat_hours=24)
    # By the end (after smoothing has caught up), we should be flat
    flat_at_end = (position.iloc[-20:] == 0).all()
    assert flat_at_end, "Expected to be flat after sustained negative funding"
    print("✓ test_strategy_exits_on_negative_smoothed_funding")


def test_strategy_respects_min_hold():
    """Once entered, must hold for at least min_hold_hours bars."""
    idx = pd.date_range('2024-01-01', periods=200, freq='1h')
    # Funding goes positive, then crashes negative immediately
    funding = pd.Series(0.0001, index=idx)
    funding.iloc[40:] = -0.001  # very negative
    position = generate_position(funding, smooth_hours=4,
                                  entry_threshold_apr=0.005,
                                  exit_threshold_apr=-0.005,
                                  min_hold_hours=24, min_flat_hours=24)
    # After warmup (~4h smoothing), we enter, then should hold for 24h minimum
    entry_indices = np.where(position.diff() == 1)[0]
    if len(entry_indices) > 0:
        first_entry = entry_indices[0]
        # Check we stay in for at least 24 hours
        for i in range(first_entry, min(first_entry + 24, len(position))):
            assert position.iloc[i] == 1, \
                f"Bar {i} should still be in position (min_hold violated)"
    print("✓ test_strategy_respects_min_hold")


# ============================================================================
# RUN ALL
# ============================================================================

def run_all():
    tests = [
        test_zero_funding_zero_position_returns_capital,
        test_constant_positive_funding_no_position_no_pnl,
        test_constant_funding_always_in_position,
        test_one_trade_with_costs,
        test_negative_funding_in_position_loses_money,
        test_sanity_vs_manual_calculation_btc_feb2024,
        test_strategy_enters_on_positive_smoothed_funding,
        test_strategy_exits_on_negative_smoothed_funding,
        test_strategy_respects_min_hold,
    ]
    print("=" * 70)
    print("RUNNING ALL TESTS")
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
        print("\nFailures:")
        for name, err in failures:
            print(f"  - {name}: {err}")
        print("\n⚠ DO NOT TRUST BACKTEST RESULTS UNTIL ALL TESTS PASS")
    else:
        print("✅ All tests pass — engine and strategy validated.")
    print("=" * 70)
    return n_fail == 0


if __name__ == '__main__':
    success = run_all()
    sys.exit(0 if success else 1)
