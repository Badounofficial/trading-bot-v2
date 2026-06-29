"""
Trend Following Runner
======================
Backtest Donchian breakout (long+short) on BTC/ETH/SOL.

Usage:
    python run_trend.py test          # validate engine + strategy
    python run_trend.py backtest      # full backtest
    python run_trend.py tune          # grid search for best params
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import itertools
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_prices
from strategies.trend_following import (
    generate_trend_position, diagnostic_summary, compute_regime_filter
)
from backtest.directional_engine import run_directional_backtest


# ============================================================================
# DEFAULT STRATEGY CONFIG (data-driven from btc_pattern.py)
# ============================================================================

DEFAULT_CONFIG = {
    'lookback_days': 20,           # Donchian entry window
    'exit_lookback_days': 10,      # trailing exit (half of lookback)
    'atr_period_days': 20,
    'atr_stop_multiplier': 2.0,
    'mode': 'long_short',
    'capital_per_symbol_usd': 10_000,
    'use_regime_filter': True,     # NEW: gate entries by BTC vs MA200
    'regime_ma_days': 200,         # NEW: BTC MA window for regime detection
}


# ============================================================================
# COSTS (different from funding arb — single-leg directional)
# ============================================================================

def get_directional_costs() -> tuple:
    """Returns (entry_cost_bps, exit_cost_bps) for a single-leg directional trade."""
    f_cfg = cfg()['friction']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    cost_per_side = fee + f_cfg['slippage_median_bps']
    return cost_per_side, cost_per_side


# ============================================================================
# DAILY RESAMPLE
# ============================================================================

def to_daily(prices_hourly: pd.DataFrame) -> pd.DataFrame:
    """Resample hourly prices to daily OHLC."""
    daily = prices_hourly.resample('1D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna()
    return daily


# ============================================================================
# BACKTEST
# ============================================================================

def run_one_symbol(symbol: str, params: dict, verbose: bool = True,
                   regime_filter: pd.Series = None) -> dict:
    """Run trend following backtest on one symbol."""
    prices_hourly = fetch_prices(symbol)
    if prices_hourly.empty:
        if verbose:
            print(f"  ⚠ No price data for {symbol}")
        return {}

    prices_daily = to_daily(prices_hourly)
    if len(prices_daily) < params['lookback_days'] + 30:
        if verbose:
            print(f"  ⚠ Not enough daily bars for {symbol} "
                  f"({len(prices_daily)} vs required {params['lookback_days'] + 30})")
        return {}

    # Generate position
    position = generate_trend_position(
        prices_daily,
        lookback_days=params['lookback_days'],
        exit_lookback_days=params['exit_lookback_days'],
        atr_period_days=params['atr_period_days'],
        atr_stop_multiplier=params['atr_stop_multiplier'],
        mode=params['mode'],
        regime_filter=regime_filter,
        regime_ma_days=params.get('regime_ma_days', 200),
    )

    # Run backtest
    entry_cost, exit_cost = get_directional_costs()
    capital = params['capital_per_symbol_usd']
    result = run_directional_backtest(
        prices_daily['close'], position,
        capital=capital,
        entry_cost_bps=entry_cost, exit_cost_bps=exit_cost,
    )

    diag = diagnostic_summary(prices_daily, position)
    metrics = result['metrics']
    metrics['symbol'] = symbol
    metrics.update({
        'time_long_pct': diag['time_long_pct'],
        'time_short_pct': diag['time_short_pct'],
        'time_flat_pct': diag['time_flat_pct'],
    })

    if verbose:
        print(f"\n=== {symbol} ===")
        print(f"  Time long/short/flat: {diag['time_long_pct']:.0f}% / "
              f"{diag['time_short_pct']:.0f}% / {diag['time_flat_pct']:.0f}%")
        print(f"  Trades:          {metrics['n_trades']} "
              f"({metrics['n_long']} long, {metrics['n_short']} short)")
        print(f"  CAGR:            {metrics['cagr_pct']:.2f}%")
        print(f"  Sharpe:          {metrics['sharpe']:.2f}")
        print(f"  Max DD:          {metrics['max_dd_pct']:.2f}%")
        print(f"  Win rate:        {metrics['win_rate_pct']:.1f}% "
              f"(long {metrics['long_win_rate_pct']:.1f}%, "
              f"short {metrics['short_win_rate_pct']:.1f}%)")
        print(f"  Best/worst trade: +{metrics['best_trade_pct']:.1f}% / "
              f"{metrics['worst_trade_pct']:.1f}%")
        print(f"  Long P&L:        ${metrics['long_pnl_usd']:,.2f}")
        print(f"  Short P&L:       ${metrics['short_pnl_usd']:,.2f}")
        print(f"  Total P&L:       ${metrics['total_pnl_usd']:,.2f}")

    return metrics


def cmd_test():
    """Run unit tests."""
    from tests.test_trend import run_all
    sys.exit(0 if run_all() else 1)


def cmd_backtest(params=None, verbose=True):
    if params is None:
        params = DEFAULT_CONFIG.copy()
    if verbose:
        print(f"[strategy] Trend Following — Donchian {params['lookback_days']}d breakout")
        print(f"[strategy] Mode: {params['mode']}, "
              f"exit: {params['exit_lookback_days']}d, "
              f"stop: {params['atr_stop_multiplier']}× ATR{params['atr_period_days']}")
        if params.get('use_regime_filter'):
            print(f"[strategy] Regime filter: BTC vs MA{params.get('regime_ma_days', 200)} "
                  f"(longs in bull, shorts in bear)")
        cost_in, cost_out = get_directional_costs()
        print(f"[strategy] Round-trip cost: {cost_in + cost_out:.2f} bps")

    # Compute regime filter ONCE from BTC, applied to all symbols
    regime_filter = None
    if params.get('use_regime_filter'):
        btc_prices = fetch_prices('BTC/USDC:USDC')
        if not btc_prices.empty:
            btc_daily = to_daily(btc_prices)
            ma_days = params.get('regime_ma_days', 200)
            # Adapt: if we have less data than ma_days, fall back to shorter MA
            if len(btc_daily) < ma_days:
                fallback_ma = min(len(btc_daily) // 2, 100)
                if verbose:
                    print(f"[warn] Only {len(btc_daily)} BTC daily bars, falling back to "
                          f"MA{fallback_ma} for regime detection (vs requested MA{ma_days})")
                ma_days = fallback_ma
            regime_filter = compute_regime_filter(btc_daily, ma_days=ma_days)
            if verbose:
                bull_pct = (regime_filter == 1).mean() * 100
                bear_pct = (regime_filter == -1).mean() * 100
                neutral_pct = (regime_filter == 0).mean() * 100
                print(f"[regime] BTC vs MA{ma_days}: "
                      f"bull {bull_pct:.0f}% / bear {bear_pct:.0f}% / "
                      f"warmup {neutral_pct:.0f}%")

    all_metrics = []
    for sym in cfg()['exchange']['symbols']:
        m = run_one_symbol(sym, params, verbose=verbose, regime_filter=regime_filter)
        if m:
            all_metrics.append(m)

    if not all_metrics:
        return [], {}

    # Aggregate
    total_capital = params['capital_per_symbol_usd'] * len(all_metrics)
    total_pnl = sum(m['total_pnl_usd'] for m in all_metrics)
    total_return_pct = total_pnl / total_capital * 100
    avg_sharpe = float(np.mean([m['sharpe'] for m in all_metrics]))
    worst_dd = float(min(m['max_dd_pct'] for m in all_metrics))
    n_trades = sum(m['n_trades'] for m in all_metrics)

    # CAGR: use first symbol's date range
    prices_sample = to_daily(fetch_prices(all_metrics[0]['symbol']))
    span_days = (prices_sample.index[-1] - prices_sample.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    if verbose:
        print(f"\n{'='*60}")
        print(f"AGGREGATE (${total_capital:,.0f} deployed)")
        print(f"{'='*60}")
        print(f"  Total trades:    {n_trades}")
        print(f"  Total P&L:       ${total_pnl:,.2f}")
        print(f"  Total return:    {total_return_pct:.2f}%")
        print(f"  CAGR:            {cagr:.2f}%")
        print(f"  Avg Sharpe:      {avg_sharpe:.2f}")
        print(f"  Worst Max DD:    {worst_dd:.2f}%")
        print(f"  Period:          {span_days} days ({years:.2f} years)")
        print(f"{'='*60}")

        # Save
        out_path = ROOT / 'results' / f'trend_{datetime.utcnow():%Y%m%d_%H%M%S}.json'
        out_path.write_text(json.dumps({
            'params': params,
            'per_symbol': all_metrics,
            'aggregate': {
                'total_capital_usd': total_capital,
                'total_pnl_usd': total_pnl,
                'cagr_pct': cagr,
                'avg_sharpe': avg_sharpe,
                'worst_max_dd_pct': worst_dd,
                'n_trades': n_trades,
            },
        }, indent=2, default=str))
        print(f"\n✓ Saved to {out_path.relative_to(ROOT)}")

    return all_metrics, {
        'cagr_pct': cagr,
        'sharpe': avg_sharpe,
        'max_dd_pct': worst_dd,
        'n_trades': n_trades,
        'total_pnl_usd': total_pnl,
    }


def cmd_tune():
    """Grid search across parameter combinations."""
    print("\n=== TREND FOLLOWING GRID SEARCH ===\n")

    PARAM_GRID = {
        'lookback_days':       [10, 20, 30, 50],
        'exit_lookback_days':  [5, 10, 20],
        'atr_stop_multiplier': [1.5, 2.0, 3.0],
    }

    keys = list(PARAM_GRID.keys())
    values = [PARAM_GRID[k] for k in keys]
    combos = list(itertools.product(*values))
    print(f"Testing {len(combos)} parameter combinations...\n")

    results = []
    for i, combo in enumerate(combos, 1):
        params = DEFAULT_CONFIG.copy()
        for k, v in zip(keys, combo):
            params[k] = v
        if i % 5 == 0 or i == 1:
            print(f"  [{i}/{len(combos)}] testing lookback={params['lookback_days']}, "
                  f"exit={params['exit_lookback_days']}, "
                  f"stop={params['atr_stop_multiplier']}× ATR")
        _, agg = cmd_backtest(params, verbose=False)
        if agg:
            agg.update({
                'lookback': params['lookback_days'],
                'exit_lookback': params['exit_lookback_days'],
                'atr_stop': params['atr_stop_multiplier'],
            })
            results.append(agg)

    if not results:
        print("No results.")
        return

    df = pd.DataFrame(results)
    df = df.sort_values('cagr_pct', ascending=False).reset_index(drop=True)

    print(f"\n{'='*90}")
    print("TOP 10 CONFIGS BY CAGR")
    print(f"{'='*90}")
    print(f"{'Rank':<5} {'Lookback':>9} {'Exit':>6} {'ATRStop':>8} "
          f"{'CAGR':>9} {'Sharpe':>8} {'MaxDD':>9} {'Trades':>8}")
    print('-' * 90)
    for i, (_, row) in enumerate(df.head(10).iterrows(), 1):
        print(f"{i:<5} {int(row['lookback']):>7}d "
              f"{int(row['exit_lookback']):>5}d "
              f"{row['atr_stop']:>7.1f}x "
              f"{row['cagr_pct']:>8.2f}% "
              f"{row['sharpe']:>8.2f} "
              f"{row['max_dd_pct']:>8.2f}% "
              f"{int(row['n_trades']):>8}")

    df.to_csv(ROOT / 'results' / f'trend_tuning_{datetime.utcnow():%Y%m%d_%H%M%S}.csv',
              index=False)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'backtest'
    if cmd == 'test':
        cmd_test()
    elif cmd == 'backtest':
        cmd_backtest()
    elif cmd == 'tune':
        cmd_tune()
    else:
        print(f"Unknown: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
