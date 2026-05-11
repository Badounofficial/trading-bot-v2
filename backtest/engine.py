"""
Vectorized Backtest Engine
===========================
Computes funding capture P&L using pandas operations only — no for loops.
This eliminates an entire class of bugs (off-by-one, state leakage, etc.).

Core idea:
    1. Define position vector: array of 0 (flat) and 1 (in position) per timestamp
    2. P&L per period = position[t] × funding[t] × capital
    3. Costs = transitions in position × cost_per_transition
    4. Equity curve = cumulative sum of (P&L - costs)

The strategy decides the position vector. The engine just computes the math.
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd


def run_backtest(
    funding: pd.Series,           # funding rate per period (raw, not annualized)
    position: pd.Series,          # 0 or 1, same index as funding
    capital: float = 10_000,
    entry_cost_bps: float = 10.0, # round-trip entry cost (sum of legs + slippage)
    exit_cost_bps: float = 10.0,
) -> dict:
    """
    Vectorized backtest. Returns dict with equity curve and trades summary.

    funding: pd.Series
        Per-period funding rate (e.g. 0.0001 means 0.01% paid that period).
        Positive = shorts receive (we are short perp + long spot, so we receive).
    position: pd.Series
        0 (flat) or 1 (in position). Must have same index as funding.
    capital: float
        Notional in USD per leg (we hold $capital long spot AND $capital short perp,
        so total deployed = 2 × capital but funding is computed on $capital).
    entry_cost_bps / exit_cost_bps: float
        Cost in basis points charged on the FULL notional ($capital) at each
        transition. Includes fees + slippage for both legs.

    Returns:
        {
          'equity': pd.Series      cumulative equity over time
          'pnl_per_period': pd.Series
          'trades': pd.DataFrame   one row per closed trade
          'metrics': dict
        }
    """
    assert funding.index.equals(position.index), "funding and position must share index"
    assert position.isin([0, 1]).all(), "position must be 0 or 1"

    # Funding P&L: only paid when in position
    funding_pnl = position * funding * capital

    # Detect transitions (entries and exits)
    pos_diff = position.diff().fillna(position.iloc[0])  # +1 = entry, -1 = exit
    entries = (pos_diff == 1)
    exits = (pos_diff == -1)
    n_entries = int(entries.sum())
    n_exits = int(exits.sum())

    # Force a final exit if still in position at end (mark-to-market)
    forced_exit = position.iloc[-1] == 1
    if forced_exit:
        n_exits += 1

    # Costs: charged on the bar where the transition happens
    entry_cost_per_bar = entries * (entry_cost_bps / 10_000) * capital
    exit_cost_per_bar = exits * (exit_cost_bps / 10_000) * capital
    total_costs_series = entry_cost_per_bar + exit_cost_per_bar

    # Final exit cost if forced
    forced_exit_cost = (exit_cost_bps / 10_000) * capital if forced_exit else 0
    final_costs = total_costs_series.sum() + forced_exit_cost

    # Net P&L per period
    pnl_per_period = funding_pnl - total_costs_series
    if forced_exit:
        # subtract forced exit cost from last bar
        pnl_per_period.iloc[-1] -= forced_exit_cost

    equity = capital + pnl_per_period.cumsum()

    # Build trades DataFrame
    trades = _build_trades(funding, position, capital, entry_cost_bps, exit_cost_bps)

    # Metrics
    total_pnl = float(pnl_per_period.sum())
    total_return_pct = total_pnl / capital * 100
    span_days = (funding.index[-1] - funding.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr_pct = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100 if total_return_pct > -100 else -100

    # Drawdown
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd_pct = float(drawdown.min() * 100)

    # Sharpe based on per-period returns (annualized)
    if len(funding) >= 3:
        period_seconds = (funding.index[1] - funding.index[0]).total_seconds()
        periods_per_year = (365 * 86400) / period_seconds
    else:
        periods_per_year = 365 * 24
    period_returns = pnl_per_period / capital
    if period_returns.std() > 0:
        sharpe = period_returns.mean() / period_returns.std() * np.sqrt(periods_per_year)
    else:
        sharpe = 0.0

    metrics = {
        'n_entries': n_entries,
        'n_exits': n_exits,
        'n_trades': len(trades),
        'total_pnl_usd': total_pnl,
        'total_return_pct': total_return_pct,
        'cagr_pct': cagr_pct,
        'sharpe': float(sharpe),
        'max_dd_pct': max_dd_pct,
        'total_costs_usd': final_costs,
        'cost_drag_pct': final_costs / capital * 100,
        'gross_funding_usd': float(funding_pnl.sum()),
        'time_in_position_pct': float(position.mean() * 100),
        'win_rate_pct': float((trades['net_pnl'] > 0).mean() * 100) if len(trades) > 0 else 0,
        'avg_trade_pnl_usd': float(trades['net_pnl'].mean()) if len(trades) > 0 else 0,
        'avg_duration_h': float(trades['duration_h'].mean()) if len(trades) > 0 else 0,
    }

    return {
        'equity': equity,
        'pnl_per_period': pnl_per_period,
        'funding_pnl': funding_pnl,
        'position': position,
        'trades': trades,
        'metrics': metrics,
    }


def _build_trades(
    funding: pd.Series,
    position: pd.Series,
    capital: float,
    entry_cost_bps: float,
    exit_cost_bps: float,
) -> pd.DataFrame:
    """Build a trade-by-trade DataFrame from position vector."""
    pos_diff = position.diff().fillna(position.iloc[0])
    entries_idx = funding.index[pos_diff == 1].tolist()
    exits_idx = funding.index[pos_diff == -1].tolist()

    # If still in position at end, append final timestamp as forced exit
    if position.iloc[-1] == 1:
        exits_idx.append(funding.index[-1])

    if len(entries_idx) != len(exits_idx):
        # Mismatched (shouldn't happen with diff logic but defensive)
        n = min(len(entries_idx), len(exits_idx))
        entries_idx = entries_idx[:n]
        exits_idx = exits_idx[:n]

    trades = []
    for entry_t, exit_t in zip(entries_idx, exits_idx):
        # Funding earned during [entry, exit) — exclude exit bar itself
        mask = (funding.index >= entry_t) & (funding.index < exit_t)
        gross_funding = float((funding[mask] * capital).sum())
        n_periods = int(mask.sum())
        entry_cost = (entry_cost_bps / 10_000) * capital
        exit_cost = (exit_cost_bps / 10_000) * capital
        total_cost = entry_cost + exit_cost
        net_pnl = gross_funding - total_cost
        duration_h = (exit_t - entry_t).total_seconds() / 3600
        trades.append({
            'entry_time': entry_t,
            'exit_time': exit_t,
            'duration_h': duration_h,
            'n_fundings': n_periods,
            'gross_funding': gross_funding,
            'entry_cost': entry_cost,
            'exit_cost': exit_cost,
            'total_cost': total_cost,
            'net_pnl': net_pnl,
            'roi_pct': net_pnl / capital * 100,
        })
    return pd.DataFrame(trades)
