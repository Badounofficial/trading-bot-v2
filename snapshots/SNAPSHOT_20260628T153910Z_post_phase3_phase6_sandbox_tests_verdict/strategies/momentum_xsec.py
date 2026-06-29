"""
Cross-Sectional Momentum Strategy
==================================
At each rebalance date, rank all cryptos by their N-day return:
  - LONG the top K performers (the "winners")
  - SHORT the bottom K performers (the "losers")
  - Hold the basket until the next rebalance

This is what AQR, Two Sigma, and most institutional CTAs do in crypto.

Why this works (when it works):
    Cryptos that have momentum tend to continue (short-term).
    The DISPERSION between winners and losers is wide → exploitable.
    Even if BTC drops 10% overall, the worst-performing alt may drop 40%,
    so long-top/short-bottom captures relative dispersion.

Why this might fail in crypto:
    All cryptos are highly correlated (especially in crashes).
    When BTC dumps, everything dumps — winners and losers alike.
    Edge depends on enough cross-sectional variance, which is rare in panics.

Returns a dict {symbol: position_series}.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def generate_xsec_positions(
    closes_wide: pd.DataFrame,
    lookback_days: int = 30,
    rebalance_days: int = 7,
    n_long: int = 2,
    n_short: int = 2,
) -> pd.DataFrame:
    """
    Generate position matrix for cross-sectional momentum.

    Args:
        closes_wide: DataFrame indexed by date, columns are symbols, close prices.
        lookback_days: window for computing returns to rank.
        rebalance_days: how often to rebalance (e.g. 7 = weekly).
        n_long: how many top-ranked symbols to long.
        n_short: how many bottom-ranked symbols to short.

    Returns:
        DataFrame same shape as closes_wide, with values in {-1, 0, +1}.
        +1 if we're long this symbol at this date
        -1 if we're short this symbol at this date
        0 if flat
    """
    n_dates, n_symbols = closes_wide.shape
    positions = pd.DataFrame(0, index=closes_wide.index, columns=closes_wide.columns, dtype=int)

    # Compute lookback returns (shifted so we use yesterday's info)
    returns = closes_wide.pct_change(lookback_days).shift(1)

    # Determine rebalance dates: every rebalance_days bars starting from lookback_days
    rebalance_indices = list(range(lookback_days, n_dates, rebalance_days))

    last_pos = pd.Series(0, index=closes_wide.columns, dtype=int)
    for idx in range(n_dates):
        if idx in rebalance_indices:
            # Rebalance: compute new positions
            ret_today = returns.iloc[idx]
            ret_valid = ret_today.dropna()
            if len(ret_valid) < (n_long + n_short):
                # Not enough symbols — keep last position
                positions.iloc[idx] = last_pos.values
                continue
            ranked = ret_valid.sort_values(ascending=False)
            new_pos = pd.Series(0, index=closes_wide.columns, dtype=int)
            new_pos[ranked.head(n_long).index] = 1
            new_pos[ranked.tail(n_short).index] = -1
            last_pos = new_pos
            positions.iloc[idx] = new_pos.values
        else:
            # Hold last position
            positions.iloc[idx] = last_pos.values

    return positions


def backtest_xsec(
    closes_wide: pd.DataFrame,
    positions: pd.DataFrame,
    capital_per_position: float = 10_000,
    entry_cost_bps: float = 10.0,
    exit_cost_bps: float = 10.0,
) -> dict:
    """
    Vectorized cross-sectional momentum backtest.

    The total capital deployed at any moment = capital_per_position × n_active_positions
    (depending on how many longs and shorts are active).
    """
    assert closes_wide.index.equals(positions.index)
    assert (positions.columns == closes_wide.columns).all()

    # Daily returns per symbol
    returns = closes_wide.pct_change().fillna(0)

    # Position held going INTO bar t = position at t-1
    pos_held = positions.shift(1).fillna(0)
    # P&L per symbol per day = position × return × capital
    pnl_per_sym = pos_held * returns * capital_per_position

    # Detect transitions to charge costs
    pos_diff = positions.diff().fillna(positions.iloc[0])
    n_transitions = (pos_diff != 0).sum(axis=1)  # how many position changes per day
    cost_per_day = n_transitions * (entry_cost_bps / 10_000) * capital_per_position
    # Note: when going long→short directly, that's 2 transitions counted

    daily_pnl = pnl_per_sym.sum(axis=1) - cost_per_day

    # Forced close at end: charge exit cost on all open positions
    final_positions = positions.iloc[-1]
    n_open_at_end = (final_positions != 0).sum()
    if n_open_at_end > 0:
        final_close_cost = n_open_at_end * (exit_cost_bps / 10_000) * capital_per_position
        daily_pnl.iloc[-1] -= final_close_cost

    # Total capital base (average number of active positions × capital each)
    avg_active = (positions != 0).sum(axis=1).mean()
    total_capital = max(avg_active, 1) * capital_per_position

    equity = total_capital + daily_pnl.cumsum()

    total_pnl = float(daily_pnl.sum())
    total_return_pct = total_pnl / total_capital * 100

    # CAGR
    span_days = (closes_wide.index[-1] - closes_wide.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    # Drawdown
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd_pct = float(drawdown.min() * 100)

    # Sharpe (daily → annualized)
    daily_returns = daily_pnl / total_capital
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(365)
              if daily_returns.std() > 0 else 0)

    # Long vs short P&L decomposition
    long_pnl = float((pos_held.where(pos_held > 0, 0) * returns * capital_per_position).sum().sum())
    short_pnl = float((pos_held.where(pos_held < 0, 0) * returns * capital_per_position).sum().sum())

    # Trade counts (each rebalance counts each non-zero position as a trade)
    n_long_entries = int(((pos_diff > 0) & (positions > 0)).sum().sum())
    n_short_entries = int(((pos_diff < 0) & (positions < 0)).sum().sum())

    return {
        'equity': equity,
        'daily_pnl': daily_pnl,
        'positions': positions,
        'metrics': {
            'total_capital_usd': total_capital,
            'avg_active_positions': float(avg_active),
            'total_pnl_usd': total_pnl,
            'total_return_pct': total_return_pct,
            'cagr_pct': float(cagr),
            'sharpe': float(sharpe),
            'max_dd_pct': max_dd_pct,
            'n_long_entries': n_long_entries,
            'n_short_entries': n_short_entries,
            'long_pnl_usd': long_pnl,
            'short_pnl_usd': short_pnl,
            'span_days': span_days,
        }
    }
