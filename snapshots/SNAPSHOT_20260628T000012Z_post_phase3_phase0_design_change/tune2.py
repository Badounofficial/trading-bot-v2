"""
Grid Search Tuner
==================
Test multiple parameter combinations to find the optimal configuration.

Tests combinations of:
  - smooth_hours (signal smoothing window)
  - min_hold_hours (minimum trade duration)
  - entry_threshold_apr (how strict the entry signal is)

For each combination, runs full backtest on all symbols and reports:
  CAGR, Sharpe, Max DD, Cost drag, Number of trades, Time in position

Usage:
    python tune.py                  # run full grid search
    python tune.py top              # show top configs by different metrics
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import json
import itertools

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_funding
from strategies.funding_capture import generate_position
from backtest.engine import run_backtest


# ============================================================================
# PARAMETER GRID
# ============================================================================

PARAM_GRID = {
    'smooth_hours':         [12, 24, 48, 72],
    'min_hold_hours':       [24, 48, 72, 168],
    'entry_threshold_apr':  [0.005, 0.02, 0.05, 0.10],   # 0.5% / 2% / 5% / 10% APR
}


def run_one_config(funding_data: dict, smooth_hours, min_hold_hours, entry_threshold_apr) -> dict:
    smooth = smooth_hours
    min_hold = min_hold_hours
    entry_thr = entry_threshold_apr
    """Run backtest with one config across all symbols. Returns aggregate metrics."""
    s_cfg = cfg()['strategy']
    f_cfg = cfg()['friction']
    capital = s_cfg['capital_per_symbol_usd']
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    cost_per_leg_bps = fee + f_cfg['slippage_median_bps']
    cost_bps = 2 * cost_per_leg_bps  # both legs

    per_symbol = []
    for sym, funding_df in funding_data.items():
        if funding_df.empty:
            continue
        position = generate_position(
            funding_df['fundingRate'],
            smooth_hours=smooth,
            entry_threshold_apr=entry_thr,
            exit_threshold_apr=-0.005,  # keep exit fixed for clarity
            min_hold_hours=min_hold,
            min_flat_hours=24,
        )
        result = run_backtest(
            funding_df['fundingRate'], position,
            capital=capital,
            entry_cost_bps=cost_bps, exit_cost_bps=cost_bps,
        )
        per_symbol.append(result['metrics'])

    if not per_symbol:
        return {}

    # Aggregate
    total_capital = capital * len(per_symbol)
    total_pnl = sum(m['total_pnl_usd'] for m in per_symbol)
    total_costs = sum(m['total_costs_usd'] for m in per_symbol)
    total_trades = sum(m['n_trades'] for m in per_symbol)
    total_return_pct = total_pnl / total_capital * 100
    avg_sharpe = np.mean([m['sharpe'] for m in per_symbol])
    worst_dd = min(m['max_dd_pct'] for m in per_symbol)
    avg_time_in_pos = np.mean([m['time_in_position_pct'] for m in per_symbol])
    avg_win_rate = np.mean([m['win_rate_pct'] for m in per_symbol])

    # CAGR (use first/last from any symbol)
    sample = next(iter(funding_data.values()))
    span_days = (sample.index[-1] - sample.index[0]).days
    years = max(span_days / 365.25, 0.01)
    cagr = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100 if total_return_pct > -100 else -100

    return {
        'smooth_h': smooth,
        'min_hold_h': min_hold,
        'entry_thr_pct': entry_thr * 100,
        'n_trades': int(total_trades),
        'cagr_pct': float(cagr),
        'sharpe': float(avg_sharpe),
        'max_dd_pct': float(worst_dd),
        'cost_drag_pct': float(total_costs / total_capital * 100),
        'time_in_pos_pct': float(avg_time_in_pos),
        'win_rate_pct': float(avg_win_rate),
        'total_pnl_usd': float(total_pnl),
        'total_costs_usd': float(total_costs),
    }


def cmd_grid_search():
    """Run all combinations and save results."""
    # Load all data once (reused across all combinations)
    print("Loading data for all symbols...")
    funding_data = {}
    for sym in cfg()['exchange']['symbols']:
        funding_data[sym] = fetch_funding(sym)

    # Generate all combinations
    keys = list(PARAM_GRID.keys())
    values = [PARAM_GRID[k] for k in keys]
    combos = list(itertools.product(*values))
    n_total = len(combos)
    print(f"\nRunning grid search: {n_total} combinations")
    print(f"  smooth_hours:        {PARAM_GRID['smooth_hours']}")
    print(f"  min_hold_hours:      {PARAM_GRID['min_hold_hours']}")
    print(f"  entry_threshold:     {[f'{x*100:.1f}%' for x in PARAM_GRID['entry_threshold_apr']]}")
    print()

    results = []
    for i, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))
        if i % 8 == 0 or i == 1:
            print(f"  [{i}/{n_total}] testing smooth={params['smooth_hours']}h, "
                  f"hold={params['min_hold_hours']}h, "
                  f"thr={params['entry_threshold_apr']*100:.1f}%")
        m = run_one_config(funding_data, **params)
        if m:
            results.append(m)

    if not results:
        print("\nNo results.")
        return

    df = pd.DataFrame(results)
    df = df.sort_values('cagr_pct', ascending=False).reset_index(drop=True)

    # Save raw results
    out_path = ROOT / 'results' / f'tuning_{datetime.utcnow():%Y%m%d_%H%M%S}.csv'
    df.to_csv(out_path, index=False)

    print(f"\n✓ All {len(df)} configs tested. Results saved to {out_path.name}")

    # Print top 10 by CAGR
    print_top_table(df, 'cagr_pct', 'TOP 10 BY CAGR', 10)

    # Best by Sharpe
    print_top_table(df.sort_values('sharpe', ascending=False).head(10),
                    'sharpe', 'TOP 10 BY SHARPE', 10)

    # Best by lowest cost drag (with positive CAGR)
    profitable = df[df['cagr_pct'] > 0].copy()
    if not profitable.empty:
        print_top_table(profitable.sort_values('cost_drag_pct').head(10),
                        'cost_drag_pct', 'TOP 10 BY LOWEST COST DRAG (profitable only)', 10)

    # Recommendation
    print("\n" + "=" * 90)
    print("RECOMMENDATION")
    print("=" * 90)
    # Composite score: CAGR / max_dd_abs (Calmar-like) — favors high return + low DD
    df['composite_score'] = df['cagr_pct'] / df['max_dd_pct'].abs().clip(lower=0.5)
    best = df.sort_values('composite_score', ascending=False).iloc[0]
    print(f"\nBest risk-adjusted config (CAGR / |MaxDD|):")
    print(f"  smooth_hours:        {int(best['smooth_h'])}")
    print(f"  min_hold_hours:      {int(best['min_hold_h'])}")
    print(f"  entry_threshold:     {best['entry_thr_pct']:.2f}% APR")
    print(f"  → CAGR:              {best['cagr_pct']:.2f}%")
    print(f"  → Sharpe:            {best['sharpe']:.2f}")
    print(f"  → Max DD:            {best['max_dd_pct']:.2f}%")
    print(f"  → Cost drag:         {best['cost_drag_pct']:.2f}%")
    print(f"  → Time in position:  {best['time_in_pos_pct']:.1f}%")
    print(f"  → Trades:            {int(best['n_trades'])}")
    print()
    print("To use this config, edit config.yaml:")
    print(f"  strategy:")
    print(f"    smooth_hours: {int(best['smooth_h'])}")
    print(f"    min_hold_hours: {int(best['min_hold_h'])}")
    print(f"    entry_threshold_apr: {best['entry_thr_pct']/100:.4f}")
    print()
    print("Then run:  python run.py backtest")


def print_top_table(df: pd.DataFrame, sort_col: str, title: str, n: int):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)
    print(f"{'Rank':<5} {'Smooth':>7} {'Hold':>7} {'Entry':>8} "
          f"{'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Cost':>7} {'TimeIn':>8} {'Trades':>7}")
    print("-" * 90)
    for i, (_, row) in enumerate(df.head(n).iterrows(), 1):
        print(f"{i:<5} {int(row['smooth_h']):>5}h "
              f"{int(row['min_hold_h']):>5}h "
              f"{row['entry_thr_pct']:>6.2f}% "
              f"{row['cagr_pct']:>7.2f}% "
              f"{row['sharpe']:>7.2f} "
              f"{row['max_dd_pct']:>7.2f}% "
              f"{row['cost_drag_pct']:>6.2f}% "
              f"{row['time_in_pos_pct']:>7.1f}% "
              f"{int(row['n_trades']):>7}")


def cmd_show_top():
    """Show top configs from most recent grid search."""
    res_dir = ROOT / 'results'
    files = sorted(res_dir.glob('tuning_*.csv'), reverse=True)
    if not files:
        print("No tuning results yet. Run: python tune.py")
        return
    latest = files[0]
    print(f"Loading {latest.name}\n")
    df = pd.read_csv(latest)
    print_top_table(df.sort_values('cagr_pct', ascending=False), 'cagr_pct',
                    'TOP 10 BY CAGR', 10)
    print_top_table(df.sort_values('sharpe', ascending=False), 'sharpe',
                    'TOP 10 BY SHARPE', 10)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'grid'
    if cmd == 'top':
        cmd_show_top()
    else:
        cmd_grid_search()


if __name__ == '__main__':
    main()
