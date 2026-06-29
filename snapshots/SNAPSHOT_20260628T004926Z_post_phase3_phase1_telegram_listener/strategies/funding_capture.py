"""
Funding Capture Strategy (Always-On with smart filters)
=========================================================
Generates a position vector (0/1 per timestamp) based on smoothed funding signal.

The strategy is INTENTIONALLY simple:
  - Smooth funding over N hours (default 24h)
  - In position when smoothed funding > entry threshold
  - Out of position when smoothed funding < exit threshold
  - Min hold: don't exit before N hours after entry
  - Min flat: don't re-enter before N hours after exit

The ENGINE handles all P&L math (vectorized, no bugs).
This module just decides WHEN to be in position.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def generate_position(
    funding: pd.Series,           # raw per-period funding rate
    smooth_hours: int = 24,
    entry_threshold_apr: float = 0.005,
    exit_threshold_apr: float = -0.005,
    min_hold_hours: int = 24,
    min_flat_hours: int = 24,
) -> pd.Series:
    """
    Generate a 0/1 position vector based on funding signal.

    Args:
        funding: per-period funding rate (e.g. 0.0001 per hour for Hyperliquid)
        smooth_hours: rolling mean window
        entry/exit thresholds: in APR (annualized fraction, e.g. 0.005 = 0.5% APR)
        min_hold/flat_hours: timing filters to avoid whipsaw

    Returns:
        pd.Series of 0/1 with same index as funding
    """
    # Detect funding period
    if len(funding) >= 3:
        period_seconds = (funding.index[1] - funding.index[0]).total_seconds()
        period_hours = max(1, round(period_seconds / 3600))
    else:
        period_hours = 1

    # Annualize: convert per-period rate to APR
    fundings_per_year = (365 * 86400) / (period_hours * 3600)
    annualized = funding * fundings_per_year

    # Smooth
    n_smooth = max(1, smooth_hours // period_hours)
    smoothed_apr = annualized.rolling(n_smooth, min_periods=n_smooth).mean()

    # Generate raw signal: 1 when funding favorable, 0 when not, NaN during warmup
    raw_signal = pd.Series(np.nan, index=funding.index)
    raw_signal[smoothed_apr > entry_threshold_apr] = 1
    raw_signal[smoothed_apr < exit_threshold_apr] = 0
    # Forward-fill: stay in last state when signal is between thresholds
    raw_signal = raw_signal.ffill().fillna(0).astype(int)

    # Apply min-hold and min-flat: requires sequential processing
    # (this loop is over transitions, not over every bar — fast)
    position = raw_signal.copy()
    n_min_hold = max(1, min_hold_hours // period_hours)
    n_min_flat = max(1, min_flat_hours // period_hours)

    # Find all transition points
    transitions = position.diff().fillna(0)
    entry_indices = np.where(transitions == 1)[0]
    exit_indices = np.where(transitions == -1)[0]

    # For each entry, ensure we don't exit before n_min_hold periods
    for entry_idx in entry_indices:
        end_hold = min(entry_idx + n_min_hold, len(position))
        # Force position = 1 during this window
        position.iloc[entry_idx:end_hold] = 1

    # Recompute exits after min-hold extension
    transitions = position.diff().fillna(0)
    exit_indices = np.where(transitions == -1)[0]

    # For each exit, ensure we don't re-enter before n_min_flat periods
    for exit_idx in exit_indices:
        end_flat = min(exit_idx + n_min_flat, len(position))
        # Force position = 0 during this window
        position.iloc[exit_idx:end_flat] = 0

    return position.astype(int)


def diagnostic_summary(funding: pd.Series, position: pd.Series) -> dict:
    """Quick stats about the strategy's behavior."""
    return {
        'n_bars': len(funding),
        'time_in_position_pct': float(position.mean() * 100),
        'n_entries': int((position.diff() == 1).sum()),
        'n_exits': int((position.diff() == -1).sum()),
        'avg_position_duration_bars': (
            float(position.sum() / max(1, (position.diff() == 1).sum()))
        ),
        'funding_when_in_position_mean': float(
            (funding * position).sum() / max(1, position.sum())
        ),
        'funding_when_flat_mean': float(
            (funding * (1 - position)).sum() / max(1, (1 - position).sum())
        ),
    }
