"""
data_prep.py — Multi-TF data preparation for ICC.

PURPOSE
=======
Our data_source.py produces H1 OHLCV DataFrames with tz-aware UTC index.
ICC (Session 5, frozen) was developed and tested with tz-NAIVE DataFrames
and expects 3 timeframes: Daily, H4, H1.

This module bridges the two: takes our tz-aware H1, produces a (daily, h4, h1)
tuple in the EXACT format Session 5 used (verified by reading
scripts/run_session_5_verdict.py and data/resample_h1_to_h4.py).

WHY THIS MATTERS
================
If we feed ICC data in a slightly different format (e.g. tz-aware vs naive,
or with different column casing), some functions may behave subtly differently.
Sticking 100% to the Session 5 convention guarantees that backtested behavior
== live paper behavior.

The conversion happens ONLY at the boundary between our paper modules and ICC.
The rest of the paper trading code continues to use tz-aware UTC throughout
(state_manager, monitoring, etc.).
"""
from __future__ import annotations

import logging

import pandas as pd

from data.resample_h1_to_h4 import resample_h1_to_h4

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    EXCEPTIONS
# ════════════════════════════════════════════════════════════════

class DataPrepError(Exception):
    """Generic data preparation error."""


# ════════════════════════════════════════════════════════════════
#                    H1 → DAILY RESAMPLING
# ════════════════════════════════════════════════════════════════

# Same aggregation as resample_h1_to_h4 (consistency)
_OHLCV_AGG = {
    "open":   "first",
    "high":   "max",
    "low":    "min",
    "close":  "last",
}


def resample_h1_to_daily(h1_df: pd.DataFrame) -> pd.DataFrame:
    """Resample H1 OHLCV to daily bars (aligned on 00:00 UTC).

    Mirror of data/resample_h1_to_h4.py but for '1D' frequency.

    Args:
        h1_df: DataFrame with DatetimeIndex and columns [open, high, low, close].
               Optional: 'volume'.

    Returns:
        DataFrame with daily bars (same OHLCV columns).
    """
    if not isinstance(h1_df.index, pd.DatetimeIndex):
        raise DataPrepError("h1_df must have a DatetimeIndex")

    required = {"open", "high", "low", "close"}
    missing = required - set(h1_df.columns)
    if missing:
        raise DataPrepError(f"Missing required columns: {missing}")

    agg_dict = dict(_OHLCV_AGG)
    if "volume" in h1_df.columns:
        agg_dict["volume"] = "sum"

    daily = h1_df.resample("1D", label="left", closed="left").agg(agg_dict)

    # Drop bars where all OHLC are NaN (days with no H1 data)
    daily = daily.dropna(subset=["open", "high", "low", "close"])

    return daily


# ════════════════════════════════════════════════════════════════
#                    MULTI-TF PREPARATION FOR ICC
# ════════════════════════════════════════════════════════════════

def _strip_timezone(df: pd.DataFrame) -> pd.DataFrame:
    """Convert tz-aware DatetimeIndex to tz-naive (Session 5 convention).

    Session 5 backtest used tz-naive indices (verified in
    scripts/run_session_5_verdict.py _ensure_datetime_index).
    We must match exactly for fidelity.

    Idempotent: if already tz-naive, returns the input unchanged.
    """
    if df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


def prepare_multi_tf_for_icc(
    h1_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Prepare (daily, h4, h1) DataFrames in the exact Session 5 format.

    Steps (mirroring scripts/run_session_5_verdict.py):
    1. Validate H1 input (DatetimeIndex + required columns)
    2. Strip timezone if present (Session 5 used tz-naive)
    3. Resample to H4 using the same function as Session 5
    4. Resample to Daily
    5. Return (daily, h4, h1)

    Args:
        h1_df: Our tz-aware H1 OHLCV DataFrame (from data_source.py).
               Must have DatetimeIndex + columns [open, high, low, close]
               (and optionally 'volume').

    Returns:
        (daily_df, h4_df, h1_df) — all tz-naive, all with the same OHLCV
        schema, sorted by index.

    Raises:
        DataPrepError if input is malformed.
    """
    if not isinstance(h1_df.index, pd.DatetimeIndex):
        raise DataPrepError("h1_df must have a DatetimeIndex")

    required = {"open", "high", "low", "close"}
    missing = required - set(h1_df.columns)
    if missing:
        raise DataPrepError(f"Missing required columns: {missing}")

    if len(h1_df) < 1:
        raise DataPrepError("h1_df is empty — cannot prepare multi-TF")

    # 1. Strip timezone (Session 5 convention)
    h1_naive = _strip_timezone(h1_df).sort_index()

    # 2. Resample to H4 (use the SAME function Session 5 uses → guaranteed parity)
    h4_naive = resample_h1_to_h4(h1_naive)

    # 3. Resample to Daily
    daily_naive = resample_h1_to_daily(h1_naive)

    # Sanity: all dataframes should have rows
    if len(h4_naive) == 0:
        raise DataPrepError("H4 resampling produced 0 bars (H1 too short?)")
    if len(daily_naive) == 0:
        raise DataPrepError("Daily resampling produced 0 bars (H1 too short?)")

    logger.info(
        "Multi-TF prepared: %d H1 bars → %d H4 bars + %d Daily bars",
        len(h1_naive), len(h4_naive), len(daily_naive),
    )

    return daily_naive, h4_naive, h1_naive


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : quick demo
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print("=" * 64)
    print("  data_prep.py — démo")
    print("=" * 64)

    # Build a fake H1 DataFrame (24 hours of BTC data, tz-aware UTC)
    n_bars = 24
    timestamps = pd.date_range("2026-05-14T00:00:00Z", periods=n_bars, freq="1h", tz="UTC")
    fake_h1 = pd.DataFrame({
        "open":  [80000.0 + i * 10 for i in range(n_bars)],
        "high":  [80100.0 + i * 10 for i in range(n_bars)],
        "low":   [79950.0 + i * 10 for i in range(n_bars)],
        "close": [80050.0 + i * 10 for i in range(n_bars)],
        "volume": [100.0 + i for i in range(n_bars)],
    }, index=timestamps)

    print(f"\nInput H1: {len(fake_h1)} bars, index tz={fake_h1.index.tz}")
    print(f"  First: {fake_h1.index[0]}, Last: {fake_h1.index[-1]}")

    daily, h4, h1 = prepare_multi_tf_for_icc(fake_h1)

    print(f"\nOutput H1: {len(h1)} bars, index tz={h1.index.tz}")
    print(f"Output H4: {len(h4)} bars, index tz={h4.index.tz}")
    print(f"  Times: {[str(t) for t in h4.index[:6]]}")
    print(f"Output Daily: {len(daily)} bars, index tz={daily.index.tz}")
    print(f"  Times: {[str(t) for t in daily.index]}")

    print(f"\nH4 first bar: O={h4['open'].iloc[0]:.2f}, H={h4['high'].iloc[0]:.2f}, "
          f"L={h4['low'].iloc[0]:.2f}, C={h4['close'].iloc[0]:.2f}, V={h4['volume'].iloc[0]:.0f}")

    print("\n" + "=" * 64)
    print("  data_prep.py OK")
    print("=" * 64)
