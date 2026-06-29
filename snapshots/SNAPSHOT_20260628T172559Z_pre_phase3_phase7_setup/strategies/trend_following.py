"""
Trend Following Strategy
=========================
Donchian breakout with ATR-based stop loss.

Signal:
    - LONG when close > rolling max of last N days (Donchian high breakout)
    - SHORT when close < rolling min of last N days (Donchian low breakout)
    - EXIT long when close < N/2-day rolling min (chandelier-style trailing exit)
    - EXIT short when close > N/2-day rolling max
    - HARD STOP at 2× ATR(N) below/above entry price (catastrophic break protection)

This is the classic "Turtles" trend following with modern refinements.

Parameters (calibrated for BTC 2026 from btc_pattern.py analysis):
    lookback_days: 20    (5j was best but too noisy, 50d too slow → 20j sweet spot)
    exit_lookback_days: 10    (half of lookback, for faster exits)
    atr_stop_multiplier: 2.0   (classic Turtles value)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Literal


def compute_atr(prices: pd.DataFrame, period_days: int = 20) -> pd.Series:
    """
    Average True Range over `period_days`.
    Assumes prices DataFrame has 'high', 'low', 'close' columns (daily or resampled).
    """
    high = prices['high']
    low = prices['low']
    close = prices['close']
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period_days, min_periods=period_days).mean()
    return atr


def generate_trend_position(
    prices_daily: pd.DataFrame,
    lookback_days: int = 20,
    exit_lookback_days: int = 10,
    atr_period_days: int = 20,
    atr_stop_multiplier: float = 2.0,
    mode: Literal['long_only', 'long_short', 'short_only'] = 'long_short',
    regime_filter: pd.Series = None,
    regime_ma_days: int = 200,
) -> pd.Series:
    """
    Generate position vector (-1/0/+1) for trend following.

    prices_daily: DataFrame with columns ['open', 'high', 'low', 'close']
                  indexed by day.

    regime_filter: optional pd.Series of +1 (bull regime allowed long) /
                   -1 (bear regime allowed short) / 0 (no trades).
                   If provided, gates entries.
                   Typically computed from BTC vs its MA200.

    Logic:
      - Compute rolling high(N), low(N), high(N/2), low(N/2), ATR(N)
      - At each bar (using PREVIOUS bar data to avoid look-ahead):
          * If we're flat:
              - close[t] > prior_max_N AND regime allows long → enter LONG (position = 1)
              - close[t] < prior_min_N AND regime allows short → enter SHORT (position = -1)
              - else stay flat
          * If we're long:
              - close[t] < entry_price - 2*ATR → STOP, exit (position = 0)
              - close[t] < prior_min_N/2 → exit on trailing low (position = 0)
              - else stay long
          * If we're short:
              - close[t] > entry_price + 2*ATR → STOP, exit
              - close[t] > prior_max_N/2 → exit on trailing high
              - else stay short

      Note: Once in a position, regime change does NOT force exit (we let the
      trailing stop or ATR stop do its work). This avoids whipsaw at regime
      boundaries.

    Returns:
        pd.Series of -1/0/+1 indexed by day.
    """
    close = prices_daily['close']
    n = len(close)

    # Rolling bands (use shift(1) to ensure no look-ahead — band at t uses bars [t-N, t-1])
    high_N = close.rolling(lookback_days).max().shift(1)
    low_N = close.rolling(lookback_days).min().shift(1)
    high_exit = close.rolling(exit_lookback_days).max().shift(1)
    low_exit = close.rolling(exit_lookback_days).min().shift(1)
    atr = compute_atr(prices_daily, atr_period_days).shift(1)

    position = pd.Series(0, index=prices_daily.index, dtype=int)
    entry_price = 0.0
    current_pos = 0

    for i in range(n):
        ts = prices_daily.index[i]
        c = close.iloc[i]
        hN = high_N.iloc[i]
        lN = low_N.iloc[i]
        hX = high_exit.iloc[i]
        lX = low_exit.iloc[i]
        a = atr.iloc[i]

        # Skip until warmup is done
        if pd.isna(hN) or pd.isna(lN) or pd.isna(a):
            position.iloc[i] = 0
            continue

        # Determine regime allowance at this bar
        # +1 = long allowed, -1 = short allowed, 0 = no entries, None = no filter (all allowed)
        if regime_filter is not None and ts in regime_filter.index:
            regime = regime_filter.loc[ts]
            long_allowed = (regime == 1)
            short_allowed = (regime == -1)
        else:
            long_allowed = True
            short_allowed = True

        if current_pos == 0:
            # Flat: look for entry breakout (gated by regime if filter active)
            if mode in ('long_only', 'long_short') and c > hN and long_allowed:
                current_pos = 1
                entry_price = c
            elif mode in ('short_only', 'long_short') and c < lN and short_allowed:
                current_pos = -1
                entry_price = c

        elif current_pos == 1:
            # Long: stop loss at entry - 2*ATR, or trailing low
            stop_level = entry_price - atr_stop_multiplier * a
            if c < stop_level or c < lX:
                current_pos = 0
                entry_price = 0.0
                # Possible immediate reversal? Only if long_short and short signal AND regime allows
                if mode == 'long_short' and c < lN and short_allowed:
                    current_pos = -1
                    entry_price = c

        elif current_pos == -1:
            # Short: stop loss at entry + 2*ATR, or trailing high
            stop_level = entry_price + atr_stop_multiplier * a
            if c > stop_level or c > hX:
                current_pos = 0
                entry_price = 0.0
                if mode == 'long_short' and c > hN and long_allowed:
                    current_pos = 1
                    entry_price = c

        position.iloc[i] = current_pos

    return position


def compute_regime_filter(
    btc_prices_daily: pd.DataFrame,
    ma_days: int = 200,
) -> pd.Series:
    """
    Compute a regime filter based on BTC vs its moving average.

    Returns a Series indexed by day:
      +1 if BTC close > MA_N (bull regime, only longs allowed)
      -1 if BTC close < MA_N (bear regime, only shorts allowed)
       0 during warmup (no trades)

    Uses BTC as the global crypto regime indicator — even for ETH/SOL/etc.
    This is the standard approach in crypto CTAs: BTC sets the tide.

    Args:
        btc_prices_daily: BTC OHLC daily DataFrame
        ma_days: moving average length (default 200, industry standard)
    """
    close = btc_prices_daily['close']
    ma = close.rolling(ma_days, min_periods=ma_days).mean()
    # Use yesterday's MA to avoid look-ahead
    ma_lag = ma.shift(1)
    close_lag = close.shift(1)

    regime = pd.Series(0, index=close.index, dtype=int)
    regime[close_lag > ma_lag] = 1
    regime[close_lag < ma_lag] = -1
    return regime


def diagnostic_summary(prices: pd.DataFrame, position: pd.Series) -> dict:
    """Summary stats about the strategy's behavior."""
    n_bars = len(position)
    n_long_bars = int((position == 1).sum())
    n_short_bars = int((position == -1).sum())
    n_flat_bars = int((position == 0).sum())

    # Count distinct trades
    pos_diff = position.diff().fillna(position.iloc[0])
    n_entries_long = int(((pos_diff > 0) & (position == 1) &
                          (position.shift(1).fillna(0) == 0)).sum())
    n_entries_short = int(((pos_diff < 0) & (position == -1) &
                            (position.shift(1).fillna(0) == 0)).sum())
    n_reversals = int(((position.shift(1).fillna(0) * position) == -1).sum())

    return {
        'n_bars': n_bars,
        'n_long_bars': n_long_bars,
        'n_short_bars': n_short_bars,
        'n_flat_bars': n_flat_bars,
        'time_long_pct': n_long_bars / n_bars * 100 if n_bars > 0 else 0,
        'time_short_pct': n_short_bars / n_bars * 100 if n_bars > 0 else 0,
        'time_flat_pct': n_flat_bars / n_bars * 100 if n_bars > 0 else 0,
        'n_entries_long': n_entries_long,
        'n_entries_short': n_entries_short,
        'n_reversals': n_reversals,
    }
