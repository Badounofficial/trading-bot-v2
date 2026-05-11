"""
Directional Backtest Engine
============================
For strategies that take long/short positions to capture PRICE moves
(trend following, mean reversion, etc.).

Different from engine.py which is for funding capture (delta-neutral).

Core logic (vectorized):
    1. Position vector: -1 (short) / 0 (flat) / +1 (long) per timestamp
    2. P&L per period = position[t-1] × price_return[t] × notional
       (position is what we HELD coming into period t, return is what happened in t)
    3. Costs charged on transitions in |position|
    4. Equity curve = capital + cumulative P&L
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def run_directional_backtest(
    prices: pd.Series,            # close prices, time-indexed
    position: pd.Series,          # -1/0/+1 with same index
    capital: float = 10_000,      # notional per trade (when in position)
    entry_cost_bps: float = 10.0, # one-sided cost in bps (fee + slippage)
    exit_cost_bps: float = 10.0,
    reverse_extra_cost_bps: float = 0.0,  # extra cost if flipping long↔short directly
) -> dict:
    """
    Vectorized backtest for directional strategies.

    prices: close prices
    position: -1/0/+1, intent for each bar
    capital: USD notional when in position (full $capital exposure, not 2x)

    Returns dict with equity, trades, metrics.
    """
    assert prices.index.equals(position.index), "prices and position must share index"
    assert position.isin([-1, 0, 1]).all(), "position must be -1, 0, or 1"

    # Per-period price return
    price_ret = prices.pct_change().fillna(0)

    # P&L: position held coming INTO bar × return that bar realized
    # If we entered at bar 5 (position becomes 1 at bar 5), we earn the return from bar 5 to bar 6
    # So position should be shifted by 1 when multiplying by return
    position_held = position.shift(1).fillna(0)
    pnl_pct = position_held * price_ret  # fraction return per bar
    pnl_usd = pnl_pct * capital

    # Detect transitions: any change in position (entries, exits, reversals)
    pos_diff = position.diff().fillna(position.iloc[0])

    # Cost per transition: depends on what happened
    #   0 → 1   : entry long  (cost = entry_cost)
    #   0 → -1  : entry short (cost = entry_cost)
    #   1 → 0   : exit long   (cost = exit_cost)
    #   -1 → 0  : exit short  (cost = exit_cost)
    #   1 → -1  : reverse     (cost = exit + entry + extra)
    #   -1 → 1  : reverse     (cost = exit + entry + extra)

    entries_long = (pos_diff > 0) & (position.shift(1).fillna(0) == 0) & (position == 1)
    entries_short = (pos_diff < 0) & (position.shift(1).fillna(0) == 0) & (position == -1)
    exits_long = (pos_diff < 0) & (position.shift(1).fillna(0) == 1) & (position == 0)
    exits_short = (pos_diff > 0) & (position.shift(1).fillna(0) == -1) & (position == 0)
    reversals = (position.shift(1).fillna(0) * position) == -1  # both nonzero, opposite signs

    cost_bps_per_bar = (
        (entries_long.astype(int) + entries_short.astype(int)) * entry_cost_bps
        + (exits_long.astype(int) + exits_short.astype(int)) * exit_cost_bps
        + reversals.astype(int) * (entry_cost_bps + exit_cost_bps + reverse_extra_cost_bps)
    )
    cost_usd = (cost_bps_per_bar / 10_000) * capital

    # Net P&L
    net_pnl = pnl_usd - cost_usd

    # Force a final close if still in position
    if position.iloc[-1] != 0:
        final_cost = (exit_cost_bps / 10_000) * capital
        net_pnl.iloc[-1] -= final_cost

    equity = capital + net_pnl.cumsum()

    # Build trades dataframe
    trades = _build_trades(prices, position, capital, entry_cost_bps, exit_cost_bps)

    # Metrics
    metrics = _compute_metrics(equity, trades, net_pnl, position, capital, prices)

    return {
        'equity': equity,
        'pnl_per_period': net_pnl,
        'gross_pnl': pnl_usd,
        'costs': cost_usd,
        'position': position,
        'trades': trades,
        'metrics': metrics,
    }


def _build_trades(prices, position, capital, entry_cost_bps, exit_cost_bps):
    """Build a trade-by-trade DataFrame."""
    trades = []
    current_pos = 0
    entry_time = None
    entry_price = None
    entry_direction = None

    for ts, pos in position.items():
        # Position changed
        if pos != current_pos:
            # If we were in position, close it
            if current_pos != 0 and entry_time is not None:
                exit_price = prices.loc[ts]
                if entry_direction == 'long':
                    raw_ret_pct = (exit_price - entry_price) / entry_price
                else:  # short
                    raw_ret_pct = (entry_price - exit_price) / entry_price
                gross_pnl = raw_ret_pct * capital
                cost = ((entry_cost_bps + exit_cost_bps) / 10_000) * capital
                net_pnl = gross_pnl - cost
                duration_h = (ts - entry_time).total_seconds() / 3600
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': ts,
                    'direction': entry_direction,
                    'duration_h': duration_h,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'raw_ret_pct': raw_ret_pct * 100,
                    'gross_pnl': gross_pnl,
                    'cost': cost,
                    'net_pnl': net_pnl,
                    'roi_pct': net_pnl / capital * 100,
                })

            # Open new position if pos != 0
            if pos != 0:
                entry_time = ts
                entry_price = prices.loc[ts]
                entry_direction = 'long' if pos == 1 else 'short'
            else:
                entry_time = None
                entry_price = None
                entry_direction = None

            current_pos = pos

    # Close any final open position at last price
    if current_pos != 0 and entry_time is not None:
        exit_price = prices.iloc[-1]
        if entry_direction == 'long':
            raw_ret_pct = (exit_price - entry_price) / entry_price
        else:
            raw_ret_pct = (entry_price - exit_price) / entry_price
        gross_pnl = raw_ret_pct * capital
        cost = ((entry_cost_bps + exit_cost_bps) / 10_000) * capital
        net_pnl = gross_pnl - cost
        duration_h = (prices.index[-1] - entry_time).total_seconds() / 3600
        trades.append({
            'entry_time': entry_time,
            'exit_time': prices.index[-1],
            'direction': entry_direction,
            'duration_h': duration_h,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'raw_ret_pct': raw_ret_pct * 100,
            'gross_pnl': gross_pnl,
            'cost': cost,
            'net_pnl': net_pnl,
            'roi_pct': net_pnl / capital * 100,
            'forced_close': True,
        })

    return pd.DataFrame(trades)


def _compute_metrics(equity, trades, net_pnl, position, capital, prices):
    total_pnl = float(net_pnl.sum())
    total_return_pct = total_pnl / capital * 100
    span_days = (prices.index[-1] - prices.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd_pct = float(drawdown.min() * 100)

    # Sharpe annualized
    if len(prices) >= 3:
        period_seconds = (prices.index[1] - prices.index[0]).total_seconds()
        periods_per_year = (365 * 86400) / period_seconds
    else:
        periods_per_year = 365 * 24
    period_returns = net_pnl / capital
    sharpe = (period_returns.mean() / period_returns.std() * np.sqrt(periods_per_year)
              if period_returns.std() > 0 else 0)

    # Long/short breakdown
    n_long = int((trades['direction'] == 'long').sum()) if len(trades) > 0 else 0
    n_short = int((trades['direction'] == 'short').sum()) if len(trades) > 0 else 0
    long_pnl = float(trades[trades['direction'] == 'long']['net_pnl'].sum()) if n_long > 0 else 0
    short_pnl = float(trades[trades['direction'] == 'short']['net_pnl'].sum()) if n_short > 0 else 0

    long_wr = (float((trades[trades['direction'] == 'long']['net_pnl'] > 0).mean() * 100)
               if n_long > 0 else 0)
    short_wr = (float((trades[trades['direction'] == 'short']['net_pnl'] > 0).mean() * 100)
                if n_short > 0 else 0)

    return {
        'n_trades': len(trades),
        'n_long': n_long,
        'n_short': n_short,
        'total_pnl_usd': total_pnl,
        'total_return_pct': total_return_pct,
        'cagr_pct': float(cagr),
        'sharpe': float(sharpe),
        'max_dd_pct': max_dd_pct,
        'long_pnl_usd': long_pnl,
        'short_pnl_usd': short_pnl,
        'long_win_rate_pct': long_wr,
        'short_win_rate_pct': short_wr,
        'win_rate_pct': float((trades['net_pnl'] > 0).mean() * 100) if len(trades) > 0 else 0,
        'avg_trade_pnl_usd': float(trades['net_pnl'].mean()) if len(trades) > 0 else 0,
        'avg_duration_h': float(trades['duration_h'].mean()) if len(trades) > 0 else 0,
        'time_in_position_pct': float((position != 0).mean() * 100),
        'best_trade_pct': float(trades['roi_pct'].max()) if len(trades) > 0 else 0,
        'worst_trade_pct': float(trades['roi_pct'].min()) if len(trades) > 0 else 0,
    }
