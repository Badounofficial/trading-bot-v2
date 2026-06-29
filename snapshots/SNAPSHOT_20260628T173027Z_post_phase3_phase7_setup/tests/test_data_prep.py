"""
Tests for paper_trading/data_prep.py.

Verifies that:
- The H1 → H4 + Daily resampling is correct
- Timezone is stripped to match Session 5 convention
- Aggregations are correct (first/max/min/last/sum)
- Edge cases (missing cols, empty, NaN) are caught
"""
from __future__ import annotations

import pandas as pd
import pytest

from paper_trading.data_prep import (
    prepare_multi_tf_for_icc,
    resample_h1_to_daily,
    DataPrepError,
)


# ════════════════════════════════════════════════════════════════
#  Fixtures — build H1 OHLCV data
# ════════════════════════════════════════════════════════════════

def _make_h1_df(
    n_bars: int = 48,
    start: str = "2026-05-14T00:00:00Z",
    tz_aware: bool = True,
    base_price: float = 80000.0,
) -> pd.DataFrame:
    """Build a synthetic H1 OHLCV DataFrame.

    Each bar: o=base+i, h=base+i+50, l=base+i-50, c=base+i+25, vol=100+i
    """
    if tz_aware:
        ts = pd.date_range(start, periods=n_bars, freq="1h", tz="UTC")
    else:
        ts = pd.date_range(start.replace("Z", ""), periods=n_bars, freq="1h")
    return pd.DataFrame({
        "open":  [base_price + i for i in range(n_bars)],
        "high":  [base_price + i + 50 for i in range(n_bars)],
        "low":   [base_price + i - 50 for i in range(n_bars)],
        "close": [base_price + i + 25 for i in range(n_bars)],
        "volume": [100.0 + i for i in range(n_bars)],
    }, index=ts)


# ════════════════════════════════════════════════════════════════
#  resample_h1_to_daily — direct tests
# ════════════════════════════════════════════════════════════════

def test_daily_resampling_24h_produces_1_bar():
    """Exactly 24 H1 bars on one calendar day → 1 daily bar."""
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert len(daily) == 1


def test_daily_resampling_48h_produces_2_bars():
    h1 = _make_h1_df(n_bars=48, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert len(daily) == 2


def test_daily_open_is_first_h1_open():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert daily["open"].iloc[0] == h1["open"].iloc[0]


def test_daily_close_is_last_h1_close():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert daily["close"].iloc[0] == h1["close"].iloc[-1]


def test_daily_high_is_max_h1_high():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert daily["high"].iloc[0] == h1["high"].max()


def test_daily_low_is_min_h1_low():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert daily["low"].iloc[0] == h1["low"].min()


def test_daily_volume_is_sum_h1_volume():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    assert daily["volume"].iloc[0] == h1["volume"].sum()


def test_daily_resampling_aligned_on_midnight():
    """Daily bars must be timestamped at 00:00 of each UTC day."""
    h1 = _make_h1_df(n_bars=48, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    for ts in daily.index:
        assert ts.hour == 0
        assert ts.minute == 0
        assert ts.second == 0


def test_daily_without_volume_column_ok():
    """Volume column is optional."""
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    h1 = h1.drop(columns=["volume"])
    daily = resample_h1_to_daily(h1)
    assert "volume" not in daily.columns
    assert len(daily) == 1


def test_daily_missing_required_column_raises():
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    h1 = h1.drop(columns=["close"])
    with pytest.raises(DataPrepError, match="Missing"):
        resample_h1_to_daily(h1)


def test_daily_no_datetime_index_raises():
    df = pd.DataFrame({
        "open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2],
    })
    with pytest.raises(DataPrepError, match="DatetimeIndex"):
        resample_h1_to_daily(df)


def test_daily_ohlc_consistency_preserved():
    """high >= max(open, close) and low <= min(open, close)."""
    h1 = _make_h1_df(n_bars=48, tz_aware=False)
    daily = resample_h1_to_daily(h1)
    for _, row in daily.iterrows():
        assert row["high"] >= max(row["open"], row["close"])
        assert row["low"] <= min(row["open"], row["close"])


# ════════════════════════════════════════════════════════════════
#  prepare_multi_tf_for_icc — end-to-end
# ════════════════════════════════════════════════════════════════

def test_prepare_returns_3_dataframes():
    h1 = _make_h1_df(n_bars=24)
    daily, h4, h1_out = prepare_multi_tf_for_icc(h1)
    assert isinstance(daily, pd.DataFrame)
    assert isinstance(h4, pd.DataFrame)
    assert isinstance(h1_out, pd.DataFrame)


def test_prepare_strips_timezone_to_match_session5():
    """All 3 outputs must be tz-naive (Session 5 convention)."""
    h1 = _make_h1_df(n_bars=24, tz_aware=True)
    assert h1.index.tz is not None  # input is tz-aware
    daily, h4, h1_out = prepare_multi_tf_for_icc(h1)
    assert daily.index.tz is None
    assert h4.index.tz is None
    assert h1_out.index.tz is None


def test_prepare_idempotent_with_naive_input():
    """If input is already tz-naive, no error."""
    h1 = _make_h1_df(n_bars=24, tz_aware=False)
    daily, h4, h1_out = prepare_multi_tf_for_icc(h1)
    assert daily.index.tz is None
    assert h4.index.tz is None
    assert h1_out.index.tz is None


def test_prepare_h1_unchanged_except_tz():
    """H1 output should equal the input modulo timezone stripping."""
    h1 = _make_h1_df(n_bars=24, tz_aware=True)
    _, _, h1_out = prepare_multi_tf_for_icc(h1)
    assert len(h1_out) == len(h1)
    # Same OHLC values
    assert (h1_out["open"].values == h1["open"].values).all()
    assert (h1_out["close"].values == h1["close"].values).all()


def test_prepare_24h_produces_6_h4_bars():
    """24 H1 bars → 6 H4 bars (24/4=6)."""
    h1 = _make_h1_df(n_bars=24)
    _, h4, _ = prepare_multi_tf_for_icc(h1)
    assert len(h4) == 6


def test_prepare_h4_alignment_on_session5_pattern():
    """H4 bars open at 00, 04, 08, 12, 16, 20 UTC (Session 5 alignment)."""
    h1 = _make_h1_df(n_bars=24, start="2026-05-14T00:00:00Z")
    _, h4, _ = prepare_multi_tf_for_icc(h1)
    hours = [ts.hour for ts in h4.index]
    assert hours == [0, 4, 8, 12, 16, 20]


def test_prepare_columns_preserved():
    h1 = _make_h1_df(n_bars=24)
    daily, h4, h1_out = prepare_multi_tf_for_icc(h1)
    expected_cols = {"open", "high", "low", "close", "volume"}
    assert set(daily.columns) >= expected_cols
    assert set(h4.columns) >= expected_cols
    assert set(h1_out.columns) >= expected_cols


def test_prepare_missing_h1_column_raises():
    h1 = _make_h1_df(n_bars=24)
    h1 = h1.drop(columns=["high"])
    with pytest.raises(DataPrepError, match="Missing"):
        prepare_multi_tf_for_icc(h1)


def test_prepare_empty_h1_raises():
    h1 = pd.DataFrame(columns=["open", "high", "low", "close"])
    h1.index = pd.DatetimeIndex([])
    with pytest.raises(DataPrepError, match="empty"):
        prepare_multi_tf_for_icc(h1)


def test_prepare_no_datetime_index_raises():
    h1 = pd.DataFrame({
        "open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2],
    })
    with pytest.raises(DataPrepError, match="DatetimeIndex"):
        prepare_multi_tf_for_icc(h1)


# ════════════════════════════════════════════════════════════════
#  Realistic scenario: 30 days of H1 like a real cycle would get
# ════════════════════════════════════════════════════════════════

def test_prepare_30_days_realistic():
    """30 days * 24 hours = 720 bars → 720 H1 + 180 H4 + 30 Daily."""
    h1 = _make_h1_df(n_bars=720)  # 30 days
    daily, h4, h1_out = prepare_multi_tf_for_icc(h1)
    assert len(h1_out) == 720
    assert len(h4) == 180  # 720/4
    assert len(daily) == 30


def test_prepare_does_not_mutate_input():
    """The input DataFrame should not be modified in-place."""
    h1 = _make_h1_df(n_bars=24, tz_aware=True)
    h1_copy = h1.copy()
    prepare_multi_tf_for_icc(h1)
    # Input still tz-aware after the call
    assert h1.index.tz is not None
    assert h1.equals(h1_copy)
