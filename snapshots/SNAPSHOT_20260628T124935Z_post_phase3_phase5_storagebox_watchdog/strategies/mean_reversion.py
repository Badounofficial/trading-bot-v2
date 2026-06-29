"""
Mean Reversion Strategy
========================
Bollinger Bands + RSI based mean reversion.

Logic:
    - BUY (long) when price drops to lower Bollinger Band AND RSI < 30 (oversold)
    - SELL (short) when price reaches upper Bollinger Band AND RSI > 70 (overbought)
    - EXIT when price returns to the moving average (mean reversion completed)
    - HARD STOP at 2× ATR beyond entry (catastrophic move protection)

Why this works (when it works):
    Markets in range mode oscillate around a fair value. When price gets stretched
    too far from the mean (>2 std dev) AND momentum is exhausted (extreme RSI),
    the probability of reversion is high.

Why this fails (when it fails):
    Trending markets don't revert — they keep going. RSI stays oversold for weeks
    in a strong downtrend. ATR stop helps but doesn't save you fully.

So this is the OPPOSITE of trend following: it makes money when trend following loses.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Literal


def compute_bollinger(prices: pd.Series, period: int = 20, n_std: float = 2.0):
    """Returns (lower_band, middle_band, upper_band) over `period` bars."""
    middle = prices.rolling(period, min_periods=period).mean()
    std = prices.rolling(period, min_periods=period).std()
    lower = middle - n_std * std
    upper = middle + n_std * std
    return lower, middle, upper


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI computation."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    # When avg_loss == 0 (pure uptrend), RSI should be 100
    # When avg_gain == 0 (pure downtrend), RSI should be 0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # Handle edge cases: avg_loss=0 → rs=inf → rsi=100
    rsi = rsi.where(avg_loss > 0, 100)
    # Handle: avg_gain=0 → rs=0 → rsi=0 (already correct from formula)
    rsi = rsi.where(~rsi.isna(), 50)  # neutral during warmup
    return rsi


def compute_atr(prices_daily: pd.DataFrame, period: int = 14) -> pd.Series:
    high = prices_daily['high']
    low = prices_daily['low']
    close = prices_daily['close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def generate_mean_reversion_position(
    prices_daily: pd.DataFrame,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    atr_period: int = 14,
    atr_stop_multiplier: float = 2.0,
    mode: Literal['long_only', 'long_short', 'short_only'] = 'long_short',
) -> pd.Series:
    """
    Generate position vector -1/0/+1 for mean reversion.

    Enters long when:  price < lower_BB AND RSI < oversold threshold
    Enters short when: price > upper_BB AND RSI > overbought threshold
    Exits when:        price crosses the middle BB (mean reverted)
    Hard stop:         entry_price ± 2× ATR
    """
    close = prices_daily['close']
    lower_bb, mid_bb, upper_bb = compute_bollinger(close, bb_period, bb_std)
    rsi = compute_rsi(close, rsi_period)
    atr = compute_atr(prices_daily, atr_period)

    # Use shifted values to avoid look-ahead
    lower_lag = lower_bb.shift(1)
    upper_lag = upper_bb.shift(1)
    mid_lag = mid_bb.shift(1)
    rsi_lag = rsi.shift(1)
    atr_lag = atr.shift(1)

    position = pd.Series(0, index=prices_daily.index, dtype=int)
    current_pos = 0
    entry_price = 0.0

    for i in range(len(prices_daily)):
        c = close.iloc[i]
        lo = lower_lag.iloc[i]
        hi = upper_lag.iloc[i]
        md = mid_lag.iloc[i]
        r = rsi_lag.iloc[i]
        a = atr_lag.iloc[i]

        # Skip warmup
        if pd.isna(lo) or pd.isna(hi) or pd.isna(r) or pd.isna(a):
            position.iloc[i] = 0
            continue

        if current_pos == 0:
            # Look for entry
            if mode in ('long_only', 'long_short') and c < lo and r < rsi_oversold:
                current_pos = 1
                entry_price = c
            elif mode in ('short_only', 'long_short') and c > hi and r > rsi_overbought:
                current_pos = -1
                entry_price = c

        elif current_pos == 1:
            # Long: exit when price reaches middle BB (mean reverted)
            # or when hit hard stop below
            stop_level = entry_price - atr_stop_multiplier * a
            if c >= md or c < stop_level:
                current_pos = 0
                entry_price = 0.0

        elif current_pos == -1:
            # Short: exit when price reaches middle BB or hits stop above
            stop_level = entry_price + atr_stop_multiplier * a
            if c <= md or c > stop_level:
                current_pos = 0
                entry_price = 0.0

        position.iloc[i] = current_pos

    return position


def diagnostic_summary(prices: pd.DataFrame, position: pd.Series) -> dict:
    n_bars = len(position)
    n_long = int((position == 1).sum())
    n_short = int((position == -1).sum())
    n_flat = int((position == 0).sum())
    return {
        'n_bars': n_bars,
        'time_long_pct': n_long / n_bars * 100,
        'time_short_pct': n_short / n_bars * 100,
        'time_flat_pct': n_flat / n_bars * 100,
        'n_entries_long': int(((position.diff() == 1) & (position == 1)).sum()),
        'n_entries_short': int(((position.diff() == -1) & (position == -1)).sum()),
    }
