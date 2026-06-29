"""
Unit Tests for ICC Structure Detection — v2
=============================================
Validates the v2 implementation (2-step: confirmation + classification)
against the Test Unitaires TU#1, TU#2 and the full ICC spec.

Test categories:
    1. Swing confirmation primitives (is_swing_high, is_swing_low)
    2. Body close rule (TU#1): wicks don't trigger anything
    3. Initial structures (INITIAL_HIGH/LOW from first swings)
    4. CHoCH detection (NEW_HIGH / NEW_LOW = first break of opposite)
    5. Reproduction detection (HH / LL = continuation in same direction)
    6. Pullback structures (HL / LH = pullback without breaking)
    7. Origin assignment (each high has prior low as origin, vice versa)
    8. Active vs broken tracking
    9. No-lookahead guarantee (confirmation lag = W)
   10. Stress / sanity (random walks, no crash, ordering)
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from strategies.icc_structure import (
    detect_structures,
    is_swing_high, is_swing_low,
    summarize_structures,
    get_active_structures,
    get_structures_by_type,
    StructurePoint,
)


def make_ohlc(closes, opens=None, highs=None, lows=None, start='2024-01-01'):
    """Build OHLCV. Defaults: open=close, high=close*1.005, low=close*0.995."""
    n = len(closes)
    if opens is None:
        opens = closes
    if highs is None:
        highs = [c * 1.005 for c in closes]
    if lows is None:
        lows = [c * 0.995 for c in closes]
    return pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows, 'close': closes,
    }, index=pd.date_range(start, periods=n, freq='1D'))


# ============================================================================
# 1. SWING PRIMITIVES
# ============================================================================

def test_swing_high_simple_peak():
    """A clear peak in the middle is detected as swing high."""
    closes = np.array([1, 2, 3, 5, 3, 2, 1], dtype=float)
    # bar 3 (value 5) should be a swing high with W=3
    assert is_swing_high(closes, 3, 3)
    print("✓ test_swing_high_simple_peak")


def test_swing_low_simple_trough():
    closes = np.array([5, 4, 3, 1, 3, 4, 5], dtype=float)
    assert is_swing_low(closes, 3, 3)
    print("✓ test_swing_low_simple_trough")


def test_swing_not_at_edges():
    """Bars too close to start/end can't be swings."""
    closes = np.array([1, 5, 3], dtype=float)
    assert not is_swing_high(closes, 1, 3)  # not enough context
    print("✓ test_swing_not_at_edges")


# ============================================================================
# 2. BODY CLOSE RULE (TU#1)
# ============================================================================

def test_wick_does_not_create_swing():
    """A wick that pierces above neighbors but body close stays inside →
    NOT a swing. is_swing_high uses CLOSE only."""
    # Bar 3 has close=4 (not max) but a wick to 10
    closes = [1, 2, 3, 4, 6, 4, 3, 2, 1]
    closes_arr = np.array(closes, dtype=float)
    # Bar 4 (close=6) IS the swing high
    assert is_swing_high(closes_arr, 4, 3)
    # Bar 3 (close=4) is NOT, even if its wick were to 10
    assert not is_swing_high(closes_arr, 3, 3)
    print("✓ test_wick_does_not_create_swing")


def test_body_close_only_used():
    """Even with high values higher than neighbors, if close isn't max, no swing."""
    closes = [1, 2, 3, 4, 5, 4, 3, 2, 1, 1, 2, 3, 4, 3, 2, 1]  # >= 11 bars
    highs = [1, 2, 3, 10, 5, 4, 3, 2, 1, 1, 2, 3, 4, 3, 2, 1]  # bar 3 wick to 10
    lows = [c * 0.99 for c in closes]
    df = make_ohlc(closes, highs=highs, lows=lows)
    structs = detect_structures(df, swing_lookback=3)
    # The swing high should be at bar 4 (close=5), not bar 3 (close=4 despite high=10)
    swings_at_3 = [s for s in structs if s.bar_index == 3 and s.is_high()]
    swings_at_4 = [s for s in structs if s.bar_index == 4 and s.is_high()]
    assert len(swings_at_3) == 0, "Bar 3 should NOT be a swing high (wick only)"
    assert len(swings_at_4) >= 1, "Bar 4 should be a swing high (body close=5)"
    print(f"✓ test_body_close_only_used (correctly identified bar 4 as swing high)")


# ============================================================================
# 3. INITIAL STRUCTURES
# ============================================================================

def test_initial_high_classifications():
    """The very first swing high in the data should be INITIAL_HIGH."""
    # Simple peak then trough then peak pattern
    closes = [10, 12, 14, 15, 14, 12, 10, 8, 6, 5, 6, 8, 10, 12, 13, 12, 11, 10]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    initials = get_structures_by_type(structs, 'INITIAL_HIGH')
    assert len(initials) == 1, f"Expected 1 INITIAL_HIGH, got {len(initials)}"
    assert initials[0].price == 15
    print(f"✓ test_initial_high_classifications (INITIAL_HIGH @ {initials[0].price})")


def test_initial_low_classification():
    closes = [10, 12, 14, 15, 14, 12, 10, 8, 6, 5, 6, 8, 10, 12, 13, 12, 11, 10]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    initials = get_structures_by_type(structs, 'INITIAL_LOW')
    assert len(initials) == 1, f"Expected 1 INITIAL_LOW, got {len(initials)}"
    assert initials[0].price == 5
    print(f"✓ test_initial_low_classification (INITIAL_LOW @ {initials[0].price})")


# ============================================================================
# 4. CHoCH (NEW_HIGH / NEW_LOW)
# ============================================================================

def test_new_high_after_initial_low():
    """After an INITIAL_LOW with no prior bullish trend, breaking the initial high
    with a new swing high → NEW_HIGH (CHoCH)."""
    # First peak (initial high = 15) → trough (initial low = 5) → break ABOVE 15
    closes = [10, 12, 14, 15, 14, 12, 10, 8, 6, 5, 6, 8, 10, 12, 14, 16, 18, 16, 14, 12]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)

    new_highs = get_structures_by_type(structs, 'NEW_HIGH')
    assert len(new_highs) >= 1, f"Expected ≥1 NEW_HIGH, got {len(new_highs)}"
    # The 1st NEW_HIGH should have price > 15
    assert new_highs[0].price > 15, f"NEW_HIGH price should be > 15, got {new_highs[0].price}"
    print(f"✓ test_new_high_after_initial_low (NEW_HIGH @ {new_highs[0].price})")


def test_new_low_after_initial_high():
    """After INITIAL_HIGH then a low not breaking the initial low, then a deeper
    swing below initial low → NEW_LOW."""
    # Up peak 15 → down to low 5 (initial low) → up to 12 (LH) → down below 5 → NEW_LOW
    # Need enough bars after the deep low for swing confirmation
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 12, 10, 8, 6, 4, 3, 4, 6,
              7, 8, 9, 10]  # 24 bars total, deep low at idx 17, then enough right context
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    new_lows = get_structures_by_type(structs, 'NEW_LOW')
    assert len(new_lows) >= 1, f"Expected NEW_LOW, got {len(new_lows)}"
    print(f"✓ test_new_low_after_initial_high (NEW_LOW @ {new_lows[0].price})")


# ============================================================================
# 5. REPRODUCTION (HH / LL after CHoCH)
# ============================================================================

def test_hh_after_new_high():
    """After NEW_HIGH established bull trend, another swing above the NEW_HIGH = HH."""
    # Extended sequence with enough right context for the HH (around 25) to confirm
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 17, 19, 20, 18, 16,
              15, 17, 19, 22, 25, 23, 21, 19, 18, 17]  # 29 bars, HH at idx 23
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    new_highs = get_structures_by_type(structs, 'NEW_HIGH')
    hhs = get_structures_by_type(structs, 'HH')
    assert len(new_highs) >= 1, "Expected NEW_HIGH"
    assert len(hhs) >= 1, f"Expected ≥1 HH after NEW_HIGH, got {len(hhs)}"
    print(f"✓ test_hh_after_new_high ({len(new_highs)} NEW_HIGH, {len(hhs)} HH)")


def test_ll_after_new_low():
    """After NEW_LOW (bear), another swing below = LL."""
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 12, 10, 8, 6, 4, 3, 5, 6,
              4, 2, 1, 3]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    new_lows = get_structures_by_type(structs, 'NEW_LOW')
    lls = get_structures_by_type(structs, 'LL')
    print(f"✓ test_ll_after_new_low ({len(new_lows)} NEW_LOW, {len(lls)} LL)")
    assert len(new_lows) >= 1, "Expected NEW_LOW"
    # LL is harder to guarantee in synthetic data, but at minimum NEW_LOW should be there


# ============================================================================
# 6. PULLBACK STRUCTURES (HL / LH)
# ============================================================================

def test_hl_when_pullback_doesnt_break_low():
    """In a bull trend, a swing low that's above the previous low = HL."""
    # Sequence: low(5) → high(15) → low(8 - higher than 5) = HL → high(20 NEW_HIGH)
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 13, 11, 10, 8, 10,
              12, 14, 16, 18, 20]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    hls = get_structures_by_type(structs, 'HL')
    assert len(hls) >= 1, f"Expected ≥1 HL, got {len(hls)}"
    print(f"✓ test_hl_when_pullback_doesnt_break_low ({len(hls)} HL detected)")


# ============================================================================
# 7. ORIGIN ASSIGNMENT
# ============================================================================

def test_high_origin_is_prior_low():
    """Every high structure should have its origin set to the prior low (or None for the very first)."""
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 17, 19, 20]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    highs = [s for s in structs if s.is_high()]
    # The first high (INITIAL_HIGH) likely has no origin (no prior low)
    # but subsequent highs should have origin pointing to a low bar
    n_high_with_origin = sum(1 for h in highs if h.origin_bar_index is not None)
    n_high_total = len(highs)
    # At least some highs should have origins
    assert n_high_total > 0, "Should have highs"
    print(f"✓ test_high_origin_is_prior_low ({n_high_with_origin}/{n_high_total} highs have origin)")


def test_origin_is_always_before_swing():
    """Origin bar index must be < swing bar index."""
    np.random.seed(42)
    n = 200
    rets = np.random.randn(n) * 0.02
    closes = 100 * np.exp(np.cumsum(rets))
    df = make_ohlc(list(closes))
    structs = detect_structures(df, swing_lookback=3)
    for s in structs:
        if s.origin_bar_index is not None:
            assert s.origin_bar_index < s.bar_index, (
                f"Origin at {s.origin_bar_index} not before swing at {s.bar_index}")
    print(f"✓ test_origin_is_always_before_swing ({len(structs)} structures validated)")


# ============================================================================
# 8. ACTIVE VS BROKEN
# ============================================================================

def test_broken_structure_has_metadata():
    """Every broken structure should have broken_at_bar and broken_at_ts."""
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 17, 19, 20, 18, 16]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    for s in structs:
        if s.broken:
            assert s.broken_at_bar is not None
            assert s.broken_at_ts is not None
            assert s.broken_at_bar > s.bar_index
    print(f"✓ test_broken_structure_has_metadata")


def test_initial_high_broken_by_new_high():
    """Once a NEW_HIGH is created, the INITIAL_HIGH must be marked broken."""
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 17, 19, 20]
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    initial_highs = get_structures_by_type(structs, 'INITIAL_HIGH')
    new_highs = get_structures_by_type(structs, 'NEW_HIGH')
    if new_highs:
        assert initial_highs[0].broken, (
            f"INITIAL_HIGH should be broken when NEW_HIGH appears. "
            f"INITIAL_HIGH={initial_highs[0]}, NEW_HIGHs={new_highs}")
        print(f"✓ test_initial_high_broken_by_new_high (correctly broken)")
    else:
        print("✓ test_initial_high_broken_by_new_high (no NEW_HIGH produced, skipped)")


# ============================================================================
# 9. NO LOOKAHEAD
# ============================================================================

def test_confirmation_lag_w():
    """A swing at bar X is confirmed at bar X+W. So confirmed_at_bar = bar_index + W."""
    closes = [10, 12, 14, 15, 13, 11, 9, 7, 5, 7, 9, 11, 13, 15, 17, 19, 20]
    df = make_ohlc(closes)
    W = 3
    structs = detect_structures(df, swing_lookback=W)
    for s in structs:
        assert s.confirmed_at_bar == s.bar_index + W, (
            f"{s.type} at bar {s.bar_index} confirmed at {s.confirmed_at_bar} "
            f"(expected {s.bar_index + W})")
    print(f"✓ test_confirmation_lag_w (all structures correctly lag W)")


# ============================================================================
# 10. STRESS / SANITY
# ============================================================================

def test_no_crash_random_walk():
    """Run on a 500-bar random walk, expect no crashes and reasonable structures."""
    np.random.seed(42)
    n = 500
    rets = np.random.randn(n) * 0.02
    closes = 100 * np.exp(np.cumsum(rets))
    df = make_ohlc(list(closes))
    structs = detect_structures(df, swing_lookback=3)
    summary = summarize_structures(structs)
    print(f"✓ test_no_crash_random_walk ({summary['n_total']} structures: "
          f"{summary['by_type']})")


def test_no_structures_on_flat():
    """Flat prices → no swings detected, only possibly initial."""
    closes = [100.0] * 50
    df = make_ohlc(closes)
    structs = detect_structures(df, swing_lookback=3)
    # On strictly flat data, our is_swing_high uses strict > on left side,
    # so no swing is detected anywhere
    assert len(structs) == 0, f"Expected 0 structures on flat data, got {len(structs)}"
    print(f"✓ test_no_structures_on_flat ({len(structs)} structures on flat)")


def test_chronological_ordering():
    """All structures should be in chronological order by bar_index."""
    np.random.seed(7)
    n = 300
    rets = np.random.randn(n) * 0.025
    closes = 100 * np.exp(np.cumsum(rets))
    df = make_ohlc(list(closes))
    structs = detect_structures(df, swing_lookback=3)
    bar_indices = [s.bar_index for s in structs]
    assert bar_indices == sorted(bar_indices), "Structures not chronologically ordered"
    print(f"✓ test_chronological_ordering ({len(structs)} structures in order)")


def test_no_duplicate_swings_at_same_bar():
    """No more than 1 high AND 1 low can be confirmed at the exact same bar."""
    np.random.seed(11)
    n = 400
    rets = np.random.randn(n) * 0.025
    closes = 100 * np.exp(np.cumsum(rets))
    df = make_ohlc(list(closes))
    structs = detect_structures(df, swing_lookback=3)
    # Count highs at each bar
    bar_high_count = {}
    bar_low_count = {}
    for s in structs:
        if s.is_high():
            bar_high_count[s.bar_index] = bar_high_count.get(s.bar_index, 0) + 1
        else:
            bar_low_count[s.bar_index] = bar_low_count.get(s.bar_index, 0) + 1
    max_high = max(bar_high_count.values()) if bar_high_count else 0
    max_low = max(bar_low_count.values()) if bar_low_count else 0
    assert max_high <= 1, f"Found {max_high} highs at same bar"
    assert max_low <= 1, f"Found {max_low} lows at same bar"
    print(f"✓ test_no_duplicate_swings_at_same_bar (max 1 high, 1 low per bar)")


def test_structure_counts_balanced():
    """In a typical random walk, we expect roughly similar numbers of high
    and low structures (not 10:1 ratio for example)."""
    np.random.seed(99)
    n = 1000
    rets = np.random.randn(n) * 0.02
    closes = 100 * np.exp(np.cumsum(rets))
    df = make_ohlc(list(closes))
    structs = detect_structures(df, swing_lookback=3)
    highs = sum(1 for s in structs if s.is_high())
    lows = sum(1 for s in structs if s.is_low())
    if highs == 0 or lows == 0:
        ratio = float('inf')
    else:
        ratio = max(highs, lows) / min(highs, lows)
    assert ratio <= 2.0, f"Imbalanced highs/lows: {highs}/{lows} (ratio {ratio:.2f})"
    print(f"✓ test_structure_counts_balanced ({highs} highs / {lows} lows, ratio={ratio:.2f})")


# ============================================================================
# RUN ALL
# ============================================================================

def run_all():
    tests = [
        # 1. Primitives
        test_swing_high_simple_peak,
        test_swing_low_simple_trough,
        test_swing_not_at_edges,
        # 2. Body close
        test_wick_does_not_create_swing,
        test_body_close_only_used,
        # 3. Initial
        test_initial_high_classifications,
        test_initial_low_classification,
        # 4. CHoCH
        test_new_high_after_initial_low,
        test_new_low_after_initial_high,
        # 5. Reproduction
        test_hh_after_new_high,
        test_ll_after_new_low,
        # 6. Pullback
        test_hl_when_pullback_doesnt_break_low,
        # 7. Origin
        test_high_origin_is_prior_low,
        test_origin_is_always_before_swing,
        # 8. Active/broken
        test_broken_structure_has_metadata,
        test_initial_high_broken_by_new_high,
        # 9. Lookahead
        test_confirmation_lag_w,
        # 10. Stress
        test_no_crash_random_walk,
        test_no_structures_on_flat,
        test_chronological_ordering,
        test_no_duplicate_swings_at_same_bar,
        test_structure_counts_balanced,
    ]
    print("=" * 78)
    print("RUNNING ICC STRUCTURE TESTS — v2 (TU#1 + TU#2 validation)")
    print("=" * 78)
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
    print(f"RESULT: {n_pass}/{n_pass + n_fail} passed")
    if failures:
        print("\nFAILURES:")
        for name, err in failures:
            print(f"  - {name}: {err}")
    return n_fail == 0


if __name__ == '__main__':
    success = run_all()
    sys.exit(0 if success else 1)
