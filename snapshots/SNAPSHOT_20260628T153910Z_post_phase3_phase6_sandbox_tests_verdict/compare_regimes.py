"""
Regime Filter Comparison
=========================
Test the trend following strategy with different MA windows for the regime filter.

For each MA window, run the full backtest and compare:
  - CAGR, Sharpe, Max DD, Win rate, # trades, % bull/bear regime

Honest evaluation:
  - If all MAs give similar results → robust, pick any
  - If one MA explodes others → suspect (overfit risk)
  - If clear pattern (e.g. shorter MA always wins) → genuine insight

Usage:
    python compare_regimes.py
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
from data.fetch_extended import fetch_btc_extended_daily
from strategies.trend_following import (
    generate_trend_position, diagnostic_summary, compute_regime_filter
)
from backtest.directional_engine import run_directional_backtest


# MA windows to test
MA_WINDOWS = [None, 50, 100, 147, 180, 200, 250]
# None = no regime filter (baseline)


DEFAULT_PARAMS = {
    'lookback_days': 20,
    'exit_lookback_days': 10,
    'atr_period_days': 20,
    'atr_stop_multiplier': 2.0,
    'mode': 'long_short',
}


def to_daily(prices_hourly: pd.DataFrame) -> pd.DataFrame:
    return prices_hourly.resample('1D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    }).dropna()


def get_costs():
    f_cfg = cfg()['friction']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    return fee + f_cfg['slippage_median_bps']


def run_for_ma(prices_daily_by_symbol: dict, ma_days, btc_extended_daily=None,
               capital_per_symbol=10_000):
    """
    Run full backtest for one MA setting. Returns aggregate metrics.

    btc_extended_daily: optional DataFrame with multi-year BTC daily for regime.
                        If provided, used to compute regime filter (gives proper
                        MA200 testability). Otherwise falls back to Hyperliquid BTC.
    """
    btc_for_regime = btc_extended_daily if btc_extended_daily is not None and not btc_extended_daily.empty \
                      else prices_daily_by_symbol.get('BTC/USDC:USDC')
    if btc_for_regime is None or btc_for_regime.empty:
        return None

    # Compute regime filter (or None if ma_days is None)
    regime_filter = None
    if ma_days is not None:
        if len(btc_for_regime) < ma_days + 5:
            return {'ma_days': ma_days, 'error': f'Need {ma_days}+ bars, have {len(btc_for_regime)}'}
        regime_filter = compute_regime_filter(btc_for_regime, ma_days=ma_days)

    cost = get_costs()
    per_symbol = []

    for sym, prices_daily in prices_daily_by_symbol.items():
        if len(prices_daily) < DEFAULT_PARAMS['lookback_days'] + 30:
            continue

        position = generate_trend_position(
            prices_daily,
            lookback_days=DEFAULT_PARAMS['lookback_days'],
            exit_lookback_days=DEFAULT_PARAMS['exit_lookback_days'],
            atr_period_days=DEFAULT_PARAMS['atr_period_days'],
            atr_stop_multiplier=DEFAULT_PARAMS['atr_stop_multiplier'],
            mode=DEFAULT_PARAMS['mode'],
            regime_filter=regime_filter,
        )
        result = run_directional_backtest(
            prices_daily['close'], position,
            capital=capital_per_symbol,
            entry_cost_bps=cost, exit_cost_bps=cost,
        )
        per_symbol.append(result['metrics'])

    if not per_symbol:
        return None

    total_capital = capital_per_symbol * len(per_symbol)
    total_pnl = sum(m['total_pnl_usd'] for m in per_symbol)
    total_long_pnl = sum(m['long_pnl_usd'] for m in per_symbol)
    total_short_pnl = sum(m['short_pnl_usd'] for m in per_symbol)
    n_trades = sum(m['n_trades'] for m in per_symbol)
    n_long = sum(m['n_long'] for m in per_symbol)
    n_short = sum(m['n_short'] for m in per_symbol)
    avg_sharpe = float(np.mean([m['sharpe'] for m in per_symbol]))
    worst_dd = float(min(m['max_dd_pct'] for m in per_symbol))
    total_return_pct = total_pnl / total_capital * 100

    # Use Hyperliquid BTC trading period for CAGR (that's our actual backtest window)
    hl_btc = prices_daily_by_symbol.get('BTC/USDC:USDC')
    if hl_btc is not None and not hl_btc.empty:
        span_days = (hl_btc.index[-1] - hl_btc.index[0]).days
    else:
        span_days = (btc_for_regime.index[-1] - btc_for_regime.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

    bull_pct = bear_pct = neutral_pct = None
    if regime_filter is not None:
        # Restrict to the trading period (when Hyperliquid data exists)
        hl_btc = prices_daily_by_symbol.get('BTC/USDC:USDC')
        if hl_btc is not None and not hl_btc.empty:
            trade_start = hl_btc.index[0]
            trade_end = hl_btc.index[-1]
            regime_window = regime_filter[(regime_filter.index >= trade_start) &
                                          (regime_filter.index <= trade_end)]
        else:
            regime_window = regime_filter
        if len(regime_window) > 0:
            bull_pct = float((regime_window == 1).mean() * 100)
            bear_pct = float((regime_window == -1).mean() * 100)
            neutral_pct = float((regime_window == 0).mean() * 100)

    return {
        'ma_days': ma_days,
        'cagr_pct': cagr,
        'sharpe': avg_sharpe,
        'max_dd_pct': worst_dd,
        'n_trades': n_trades,
        'n_long': n_long,
        'n_short': n_short,
        'long_pnl_usd': total_long_pnl,
        'short_pnl_usd': total_short_pnl,
        'total_pnl_usd': total_pnl,
        'total_return_pct': total_return_pct,
        'bull_pct': bull_pct,
        'bear_pct': bear_pct,
        'neutral_pct': neutral_pct,
    }


def main():
    print("\n=== REGIME FILTER COMPARISON ===\n")
    print("Loading daily prices for all symbols...")

    prices_daily_by_symbol = {}
    for sym in cfg()['exchange']['symbols']:
        prices_hourly = fetch_prices(sym)
        if not prices_hourly.empty:
            prices_daily_by_symbol[sym] = to_daily(prices_hourly)
            print(f"  {sym}: {len(prices_daily_by_symbol[sym])} daily bars")

    if 'BTC/USDC:USDC' not in prices_daily_by_symbol:
        print("⚠ No BTC data — needed for regime detection")
        return

    # Download extended BTC daily for regime detection (3 years from Binance Spot)
    print("\nLoading extended BTC daily for regime filter...")
    btc_extended = fetch_btc_extended_daily(years_back=3)
    if btc_extended.empty:
        print("⚠ Could not fetch extended BTC — falling back to Hyperliquid BTC for regime")
        btc_extended = None

    btc_bars = len(prices_daily_by_symbol['BTC/USDC:USDC'])
    if btc_extended is not None and not btc_extended.empty:
        regime_bars = len(btc_extended)
        print(f"\nTrading data: {btc_bars} BTC daily bars (Hyperliquid).")
        print(f"Regime data:  {regime_bars} BTC daily bars (Binance, extended).")
        print(f"MA windows up to {regime_bars-5} are now testable.\n")
    else:
        print(f"\nBTC has {btc_bars} daily bars. MA windows > {btc_bars-5} will be skipped.\n")

    print(f"{'='*110}")
    print(f"{'MA Window':<12} {'Bull%':>7} {'Bear%':>7} {'Warmup%':>9} "
          f"{'CAGR':>9} {'Sharpe':>8} {'MaxDD':>8} {'#Trades':>9} "
          f"{'Long P&L':>12} {'Short P&L':>12} {'Total':>10}")
    print(f"(Bull/Bear/Warmup percentages are computed over the TRADING period only)")
    print(f"{'='*110}")

    results = []
    for ma in MA_WINDOWS:
        r = run_for_ma(prices_daily_by_symbol, ma, btc_extended_daily=btc_extended)
        if r is None:
            continue
        if 'error' in r:
            label = 'No filter' if ma is None else f"MA{ma}"
            print(f"{label:<12} ⚠ {r['error']}")
            continue

        label = 'No filter' if ma is None else f"MA{ma}"
        bull = f"{r['bull_pct']:.0f}%" if r['bull_pct'] is not None else 'n/a'
        bear = f"{r['bear_pct']:.0f}%" if r['bear_pct'] is not None else 'n/a'
        neut = f"{r['neutral_pct']:.0f}%" if r['neutral_pct'] is not None else 'n/a'
        print(f"{label:<12} {bull:>7} {bear:>7} {neut:>9} "
              f"{r['cagr_pct']:>8.2f}% {r['sharpe']:>8.2f} "
              f"{r['max_dd_pct']:>7.2f}% {r['n_trades']:>9} "
              f"${r['long_pnl_usd']:>10,.0f} ${r['short_pnl_usd']:>10,.0f} "
              f"${r['total_pnl_usd']:>8,.0f}")
        results.append(r)

    if not results:
        return

    # Analysis
    print(f"\n{'='*110}")
    print("HONEST INTERPRETATION")
    print(f"{'='*110}\n")

    cagrs = [r['cagr_pct'] for r in results if r.get('ma_days') is not None]
    if not cagrs:
        return
    cagr_min, cagr_max = min(cagrs), max(cagrs)
    cagr_spread = cagr_max - cagr_min
    cagr_std = float(np.std(cagrs))

    no_filter = next((r for r in results if r['ma_days'] is None), None)
    best_with_filter = max((r for r in results if r['ma_days'] is not None),
                            key=lambda x: x['cagr_pct'])

    print(f"  CAGR range across MAs: {cagr_min:.2f}% → {cagr_max:.2f}% "
          f"(spread {cagr_spread:.2f}%, std {cagr_std:.2f}%)")
    print(f"  Best MA: MA{best_with_filter['ma_days']} → CAGR {best_with_filter['cagr_pct']:.2f}%")
    if no_filter:
        gain_vs_baseline = best_with_filter['cagr_pct'] - no_filter['cagr_pct']
        print(f"  vs No filter (baseline): {no_filter['cagr_pct']:.2f}% → "
              f"{gain_vs_baseline:+.2f} points")
        dd_improvement = no_filter['max_dd_pct'] - best_with_filter['max_dd_pct']
        print(f"  Max DD improvement: {no_filter['max_dd_pct']:.2f}% → "
              f"{best_with_filter['max_dd_pct']:.2f}% ({dd_improvement:+.2f} points)")

    print()
    if cagr_spread < 5:
        print("  ✅ ROBUST: all MAs give similar CAGR (< 5pp spread).")
        print("     Use any reasonable MA. Standard choice: MA200.")
    elif cagr_spread < 15:
        print("  ⚠ MODERATE SENSITIVITY: results depend somewhat on MA choice.")
        print(f"     Best is MA{best_with_filter['ma_days']} but only marginally — pick by intuition.")
    else:
        print("  🚨 HIGH SENSITIVITY: large spread between MAs suggests OVERFITTING risk.")
        print("     Don't trust the 'best' MA — it may not work out-of-sample.")
        print("     Pick a STANDARD MA (100 or 200) by convention, not the empirical best.")

    if no_filter and best_with_filter['cagr_pct'] < no_filter['cagr_pct']:
        print()
        print("  ⚠ Note: no-filter baseline beats ALL filtered versions.")
        print("    The regime filter may not be helping for this dataset.")
        print("    Either: (a) need more data (only 7 months is too short), or")
        print("            (b) the strategy already handles regimes via stops.")


if __name__ == '__main__':
    main()
