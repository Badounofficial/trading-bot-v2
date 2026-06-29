"""
BTC Pattern Analysis
====================
Before applying a trend-following strategy, analyze the actual price behavior:

  1. VOLATILITY: How volatile is BTC across periods? Is 2026 really more volatile?
  2. TRENDINESS: How "trendy" is BTC? Does it sustain directional moves or oscillate?
  3. OPTIMAL LOOKBACK: Which Donchian / MA window matches the average trend duration?

This decides:
  - Whether trend-following is appropriate at all
  - Which lookback to use (20d, 50d, 100d, 200d)
  - Whether to add a volatility filter

Usage:
    python btc_pattern.py
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


# Periods to compare
PERIODS = [
    ('2024-H1',  '2024-01-01', '2024-07-01'),
    ('2024-H2',  '2024-07-01', '2025-01-01'),
    ('2025-H1',  '2025-01-01', '2025-07-01'),
    ('2025-H2',  '2025-07-01', '2026-01-01'),
    ('2026 YTD', '2026-01-01', '2026-04-30'),
    ('FULL',     '2024-01-01', '2026-04-30'),
]

# Lookback windows to test (in days)
LOOKBACKS_DAYS = [10, 20, 50, 100, 200]


# ============================================================================
# VOLATILITY ANALYSIS
# ============================================================================

def volatility_analysis(prices: pd.DataFrame) -> pd.DataFrame:
    """Per-period volatility stats."""
    rows = []
    for label, start, end in PERIODS:
        window = prices[(prices.index >= start) & (prices.index < end)]
        if len(window) < 10:
            continue
        rets = window['close'].pct_change().dropna()
        # Annualized (hourly data → 24×365 periods per year)
        daily_rets = window['close'].resample('1D').last().pct_change().dropna()

        rows.append({
            'period': label,
            'n_days': len(daily_rets),
            'mean_daily_ret_%': float(daily_rets.mean() * 100),
            'daily_vol_%': float(daily_rets.std() * 100),
            'annualized_vol_%': float(daily_rets.std() * np.sqrt(365) * 100),
            'max_daily_gain_%': float(daily_rets.max() * 100),
            'max_daily_loss_%': float(daily_rets.min() * 100),
            'avg_abs_move_%': float(daily_rets.abs().mean() * 100),
        })
    return pd.DataFrame(rows)


# ============================================================================
# TRENDINESS ANALYSIS
# ============================================================================

def compute_trendiness(prices: pd.Series, window_days: int) -> dict:
    """
    Compute "trendiness" of a price series over a given lookback.

    Trendiness metric: Hurst exponent + autocorrelation + signal-to-noise ratio.

    - Hurst > 0.5 → trending (moves persist)
    - Hurst ~ 0.5 → random walk
    - Hurst < 0.5 → mean-reverting (moves reverse)

    SNR (signal-to-noise): how much of the move is "real" trend vs noise.
    """
    if len(prices) < window_days * 24:
        return {}

    # Daily returns
    daily = prices.resample('1D').last().dropna()
    rets = daily.pct_change().dropna()
    if len(rets) < 30:
        return {}

    # Hurst exponent via rescaled range (simplified)
    def hurst(ts, max_lag=20):
        lags = range(2, min(max_lag, len(ts) // 2))
        if len(list(lags)) < 3:
            return 0.5
        tau = [np.std(np.subtract(ts[lag:], ts[:-lag])) for lag in lags]
        tau = [t for t in tau if t > 0]
        if len(tau) < 3:
            return 0.5
        valid_lags = list(lags)[:len(tau)]
        # Linear fit log(tau) vs log(lag) → slope = Hurst
        try:
            slope = np.polyfit(np.log(valid_lags), np.log(tau), 1)[0]
            return slope
        except Exception:
            return 0.5

    h = hurst(daily.values)

    # Autocorrelation of returns at lag 1
    autocorr = float(rets.autocorr(lag=1)) if len(rets) > 2 else 0

    # Signal-to-noise: cumulative price change / sum of absolute daily changes
    total_change = abs(daily.iloc[-1] - daily.iloc[0])
    total_movement = daily.diff().abs().sum()
    snr = total_change / total_movement if total_movement > 0 else 0

    return {
        'hurst': float(h),
        'autocorr_lag1': autocorr,
        'signal_noise_ratio': float(snr),
        'n_days': len(daily),
    }


def trendiness_analysis(prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, start, end in PERIODS:
        window = prices['close'][(prices.index >= start) & (prices.index < end)]
        if len(window) < 200:
            continue
        t = compute_trendiness(window, window_days=30)
        if t:
            t['period'] = label
            rows.append(t)
    return pd.DataFrame(rows)


# ============================================================================
# DONCHIAN BREAKOUT VIABILITY
# ============================================================================

def donchian_analysis(prices: pd.Series, lookback_days: int) -> dict:
    """
    Test how a Donchian breakout strategy would behave for a given lookback.

    For each day:
      - Check if today's close is above the highest close of last N days → BUY signal
      - Check if today's close is below the lowest close of last N days → SELL signal

    Measure:
      - How many breakouts happened
      - How long they "lasted" before reversing
      - What was the average return from a long breakout entry until it reversed
    """
    daily = prices.resample('1D').last().dropna()
    if len(daily) < lookback_days + 30:
        return {}

    # Rolling high/low excluding today (use shift(1))
    rolling_high = daily.shift(1).rolling(lookback_days).max()
    rolling_low = daily.shift(1).rolling(lookback_days).min()

    # Signals
    long_breakout = (daily > rolling_high).fillna(False)
    short_breakout = (daily < rolling_low).fillna(False)

    n_long = int(long_breakout.sum())
    n_short = int(short_breakout.sum())

    # For each long breakout, measure how the price evolved over next 30 days
    long_returns_30d = []
    long_indices = np.where(long_breakout.values)[0]
    for idx in long_indices:
        if idx + 30 < len(daily):
            entry_price = daily.iloc[idx]
            future_max = daily.iloc[idx:idx+30].max()
            ret_max = (future_max - entry_price) / entry_price * 100
            long_returns_30d.append(ret_max)

    short_returns_30d = []
    short_indices = np.where(short_breakout.values)[0]
    for idx in short_indices:
        if idx + 30 < len(daily):
            entry_price = daily.iloc[idx]
            future_min = daily.iloc[idx:idx+30].min()
            ret_min = (entry_price - future_min) / entry_price * 100  # profit on short
            short_returns_30d.append(ret_min)

    return {
        'lookback_days': lookback_days,
        'n_long_signals': n_long,
        'n_short_signals': n_short,
        'avg_long_30d_max_%': float(np.mean(long_returns_30d)) if long_returns_30d else 0,
        'avg_short_30d_max_%': float(np.mean(short_returns_30d)) if short_returns_30d else 0,
        'long_win_rate_%': float(np.mean([r > 5 for r in long_returns_30d]) * 100) if long_returns_30d else 0,
    }


def lookback_comparison(prices: pd.DataFrame):
    """Compare different lookback windows on the full period."""
    print(f"\n{'=' * 100}")
    print("DONCHIAN BREAKOUT VIABILITY: which lookback works best?")
    print(f"{'=' * 100}")
    print("Backtest signal quality per lookback (over full 2.4y period):\n")
    print(f"{'Lookback':<12} {'#Long sig':>10} {'#Short sig':>11} "
          f"{'Avg 30d Long gain':>20} {'Avg 30d Short gain':>20} {'Long win rate':>15}")
    print('-' * 100)

    for n_days in LOOKBACKS_DAYS:
        r = donchian_analysis(prices['close'], n_days)
        if r:
            print(f"{n_days:>5}d       {r['n_long_signals']:>10} {r['n_short_signals']:>11} "
                  f"{r['avg_long_30d_max_%']:>18.2f}%  {r['avg_short_30d_max_%']:>18.2f}%  "
                  f"{r['long_win_rate_%']:>14.1f}%")


# ============================================================================
# TREND DURATION ANALYSIS
# ============================================================================

def trend_duration_analysis(prices: pd.DataFrame):
    """
    Identify "macro trends" via 50-day MA and measure their typical duration.
    A trend = consecutive days where price > 50dMA (up trend) or below (down trend).
    """
    daily = prices['close'].resample('1D').last().dropna()
    ma50 = daily.rolling(50, min_periods=50).mean()
    above_ma = (daily > ma50).dropna()

    # Find runs of consecutive True/False
    changes = above_ma.diff().fillna(False).astype(bool)
    runs = []
    start_idx = 0
    for i, changed in enumerate(changes):
        if changed and i > 0:
            duration = i - start_idx
            direction = 'up' if above_ma.iloc[start_idx] else 'down'
            runs.append({'duration_days': duration, 'direction': direction})
            start_idx = i
    # Last run
    if start_idx < len(above_ma):
        runs.append({
            'duration_days': len(above_ma) - start_idx,
            'direction': 'up' if above_ma.iloc[start_idx] else 'down',
        })

    df = pd.DataFrame(runs)
    if df.empty:
        return

    print(f"\n{'=' * 100}")
    print("TREND DURATION (above/below 50-day MA)")
    print(f"{'=' * 100}")
    print(f"\nNumber of trend changes (50-day MA crossings): {len(df)}")
    print(f"Average trend duration: {df['duration_days'].mean():.1f} days")
    print(f"Median trend duration:  {df['duration_days'].median():.1f} days")
    print(f"\nUp trends:   {len(df[df['direction']=='up'])} "
          f"(avg {df[df['direction']=='up']['duration_days'].mean():.0f} days, "
          f"max {df[df['direction']=='up']['duration_days'].max()} days)")
    print(f"Down trends: {len(df[df['direction']=='down'])} "
          f"(avg {df[df['direction']=='down']['duration_days'].mean():.0f} days, "
          f"max {df[df['direction']=='down']['duration_days'].max()} days)")

    print(f"\nTrend duration distribution:")
    print(f"  <30 days:  {(df['duration_days'] < 30).sum()} ({(df['duration_days'] < 30).mean()*100:.0f}%)")
    print(f"  30-90d:    {((df['duration_days'] >= 30) & (df['duration_days'] < 90)).sum()}")
    print(f"  >90 days:  {(df['duration_days'] >= 90).sum()}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n=== BTC PATTERN ANALYSIS ===\n")
    print("Loading BTC price data...")

    prices = fetch_prices('BTC/USDC:USDC')
    if prices.empty:
        print("⚠ No BTC price data. Run: python run.py fetch")
        return

    print(f"  Loaded {len(prices)} hourly bars "
          f"({prices.index.min().date()} → {prices.index.max().date()})")

    # ===== Volatility per period =====
    print(f"\n{'=' * 100}")
    print("VOLATILITY ANALYSIS (per period)")
    print(f"{'=' * 100}\n")
    vol_df = volatility_analysis(prices)
    print(f"{'Period':<12} {'#Days':>7} {'MeanDailyRet':>14} {'DailyVol':>10} "
          f"{'AnnVol':>9} {'MaxGain':>10} {'MaxLoss':>10} {'AvgAbsMove':>12}")
    print('-' * 100)
    for _, r in vol_df.iterrows():
        print(f"{r['period']:<12} {r['n_days']:>7.0f} {r['mean_daily_ret_%']:>12.3f}% "
              f"{r['daily_vol_%']:>8.2f}% {r['annualized_vol_%']:>7.1f}% "
              f"{r['max_daily_gain_%']:>8.2f}% {r['max_daily_loss_%']:>8.2f}% "
              f"{r['avg_abs_move_%']:>10.2f}%")

    # ===== Trendiness =====
    print(f"\n{'=' * 100}")
    print("TRENDINESS ANALYSIS (Hurst exponent & signal-to-noise)")
    print(f"{'=' * 100}")
    print("\nHurst > 0.5 = trending market (good for trend following)")
    print("Hurst < 0.5 = mean-reverting market (bad for trend following)")
    print("SNR > 0.3   = strong directional bias\n")
    trend_df = trendiness_analysis(prices)
    print(f"{'Period':<12} {'Hurst':>8} {'AutoCorr':>10} {'SignalNoise':>12} {'Verdict':>20}")
    print('-' * 70)
    for _, r in trend_df.iterrows():
        verdict = "TRENDING ✓" if r['hurst'] > 0.55 else ("RANDOM" if r['hurst'] > 0.45 else "MEAN-REVERTING ✗")
        print(f"{r['period']:<12} {r['hurst']:>8.3f} {r['autocorr_lag1']:>10.3f} "
              f"{r['signal_noise_ratio']:>12.3f} {verdict:>20}")

    # ===== Lookback comparison =====
    lookback_comparison(prices)

    # ===== Trend duration =====
    trend_duration_analysis(prices)

    # ===== Verdict =====
    print(f"\n{'=' * 100}")
    print("VERDICT FOR TREND FOLLOWING ON BTC")
    print(f"{'=' * 100}")
    print("""
  Read the data above and answer:

  A. Is volatility HIGH enough? (annualized vol > 40% = good for trend following)
  B. Is the market TRENDING? (Hurst > 0.55 over the full period)
  C. What's the optimal LOOKBACK? (the one where:
     - Number of signals is reasonable (5-20 per year)
     - Average 30-day gain after breakout is positive and > 5%)
  D. Are trends LONG enough? (avg duration > 30 days = good for 50d Donchian)

  If A+B+C+D all positive → trend following 50d Donchian is appropriate
  If trends are short (<20d avg) → use shorter lookback (20-30d)
  If trends are short AND volatility is low → trend following is NOT a good fit
  If Hurst < 0.5 → don't bother with trend following, try mean reversion instead
""")


if __name__ == '__main__':
    main()
