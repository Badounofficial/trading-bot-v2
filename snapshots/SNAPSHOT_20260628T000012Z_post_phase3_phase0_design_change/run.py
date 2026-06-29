"""
Trading Bot v2 — Main Runner
=============================
Single command-line entry point. Everything else is a module.

Usage:
    python run.py test                # run all unit tests (do this FIRST)
    python run.py fetch               # download/refresh data
    python run.py backtest            # run backtest with current config
    python run.py monte-carlo [N]     # run N simulations with friction sampling
    python run.py status              # show config and data status
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import cfg
from data.fetch import fetch_funding, fetch_prices, load_all_funding
from strategies.funding_capture import generate_position, diagnostic_summary
from backtest.engine import run_backtest


# ============================================================================
# PRETTY PRINT
# ============================================================================

def print_metrics(label: str, metrics: dict):
    print(f"\n=== {label} ===")
    key_metrics = [
        ('n_trades',            'Trades',              '{:.0f}'),
        ('cagr_pct',            'CAGR',                '{:.2f}%'),
        ('sharpe',              'Sharpe',              '{:.2f}'),
        ('max_dd_pct',          'Max Drawdown',        '{:.2f}%'),
        ('win_rate_pct',        'Win Rate',            '{:.1f}%'),
        ('time_in_position_pct','Time in Position',    '{:.1f}%'),
        ('cost_drag_pct',       'Cost Drag',           '{:.2f}%'),
        ('avg_duration_h',      'Avg Trade Duration',  '{:.0f}h'),
        ('total_pnl_usd',       'Total P&L',           '${:,.2f}'),
    ]
    for key, label, fmt in key_metrics:
        if key in metrics:
            print(f"  {label:<22} {fmt.format(metrics[key])}")


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_test():
    """Run all unit tests. MUST pass before trusting backtest results."""
    from tests.test_engine import run_all
    success = run_all()
    sys.exit(0 if success else 1)


def cmd_fetch():
    """Download or refresh all data."""
    print(f"Fetching data for {len(cfg()['exchange']['symbols'])} symbols...")
    for sym in cfg()['exchange']['symbols']:
        print(f"\n>>> {sym}")
        fetch_funding(sym)
        fetch_prices(sym)
    print("\n✓ All data ready.")


def cmd_backtest():
    """Run the backtest with current config."""
    s_cfg = cfg()['strategy']
    f_cfg = cfg()['friction']

    # Round-trip cost = fees + slippage on both legs (spot + perp)
    fee = f_cfg['maker_fee_bps'] if f_cfg.get('use_maker_orders') else f_cfg['taker_fee_bps']
    cost_per_leg_bps = fee + f_cfg['slippage_median_bps']
    entry_cost_bps = 2 * cost_per_leg_bps  # both legs at entry
    exit_cost_bps = 2 * cost_per_leg_bps   # both legs at exit
    print(f"[config] entry/exit cost: {entry_cost_bps:.2f} bps each "
          f"(fee {fee} + slip {f_cfg['slippage_median_bps']:.2f}, ×2 legs)")
    print(f"[config] strategy: smooth={s_cfg['smooth_hours']}h, "
          f"entry>{s_cfg['entry_threshold_apr']*100:.1f}% APR, "
          f"exit<{s_cfg['exit_threshold_apr']*100:.1f}% APR")
    print(f"[config] min_hold={s_cfg['min_hold_hours']}h, "
          f"min_flat={s_cfg['min_flat_hours']}h")

    all_metrics = []
    all_equities = {}
    capital = s_cfg['capital_per_symbol_usd']

    for sym in cfg()['exchange']['symbols']:
        print(f"\n>>> {sym}")
        funding_df = fetch_funding(sym)
        if funding_df.empty:
            print(f"  ⚠ No data, skipping")
            continue

        # Generate position
        position = generate_position(
            funding_df['fundingRate'],
            smooth_hours=s_cfg['smooth_hours'],
            entry_threshold_apr=s_cfg['entry_threshold_apr'],
            exit_threshold_apr=s_cfg['exit_threshold_apr'],
            min_hold_hours=s_cfg['min_hold_hours'],
            min_flat_hours=s_cfg['min_flat_hours'],
        )

        # Diagnostic
        diag = diagnostic_summary(funding_df['fundingRate'], position)
        print(f"  Time in position: {diag['time_in_position_pct']:.1f}%, "
              f"entries: {diag['n_entries']}, exits: {diag['n_exits']}")

        # Run backtest
        result = run_backtest(
            funding_df['fundingRate'],
            position,
            capital=capital,
            entry_cost_bps=entry_cost_bps,
            exit_cost_bps=exit_cost_bps,
        )
        m = result['metrics']
        m['symbol'] = sym
        all_metrics.append(m)
        all_equities[sym] = result['equity']

        print_metrics(sym, m)

    # Aggregate
    if all_metrics:
        total_capital = capital * len(all_metrics)
        total_pnl = sum(m['total_pnl_usd'] for m in all_metrics)
        total_costs = sum(m['total_costs_usd'] for m in all_metrics)
        # Combine equity curves (sum across symbols)
        equity_combined = pd.concat(all_equities.values(), axis=1).sum(axis=1)
        # Recompute aggregate metrics
        running_max = equity_combined.cummax()
        max_dd = ((equity_combined - running_max) / running_max).min()
        first_ts = min(e.index[0] for e in all_equities.values())
        last_ts = max(e.index[-1] for e in all_equities.values())
        years = max((last_ts - first_ts).days / 365.25, 0.01)
        total_return_pct = total_pnl / total_capital * 100
        cagr = ((1 + total_return_pct/100) ** (1/years) - 1) * 100 if total_return_pct > -100 else -100

        print(f"\n{'='*60}")
        print(f"AGGREGATE (${total_capital:,.0f} deployed across "
              f"{len(all_metrics)} symbols)")
        print(f"{'='*60}")
        print(f"  Total P&L:        ${total_pnl:,.2f}")
        print(f"  Total return:     {total_return_pct:.2f}%")
        print(f"  CAGR:             {cagr:.2f}%")
        print(f"  Max DD:           {max_dd*100:.2f}%")
        print(f"  Total costs:      ${total_costs:,.2f}")
        print(f"  Cost drag:        {total_costs/total_capital*100:.2f}%")
        print(f"{'='*60}")

        # Save results
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        out_path = ROOT / 'results' / f'backtest_{ts}.json'
        out_path.write_text(json.dumps({
            'config': cfg(),
            'per_symbol': all_metrics,
            'aggregate': {
                'total_capital_usd': total_capital,
                'total_pnl_usd': total_pnl,
                'total_return_pct': total_return_pct,
                'cagr_pct': cagr,
                'max_dd_pct': float(max_dd * 100),
                'total_costs_usd': total_costs,
            },
            'timestamp': ts,
        }, indent=2, default=str))
        print(f"\n✓ Results saved to {out_path.relative_to(ROOT)}")


def cmd_status():
    """Show current configuration and data status."""
    print("=== TRADING BOT v2 STATUS ===\n")
    c = cfg()
    print(f"Exchange: {c['exchange']['name']}")
    print(f"Symbols:  {c['exchange']['symbols']}")
    print(f"Period:   {c['data']['start_date']} → {c['data']['end_date']}")
    print(f"Capital:  ${c['strategy']['capital_per_symbol_usd']:,} per symbol")
    print(f"\nFriction:  slippage={c['friction']['slippage_median_bps']:.2f}bps, "
          f"taker fee={c['friction']['taker_fee_bps']}bps")
    print(f"Strategy:  {c['strategy']['name']}")
    print(f"  smooth: {c['strategy']['smooth_hours']}h")
    print(f"  entry threshold: {c['strategy']['entry_threshold_apr']*100:.2f}% APR")
    print(f"  exit threshold:  {c['strategy']['exit_threshold_apr']*100:.2f}% APR")
    print(f"  min hold: {c['strategy']['min_hold_hours']}h, "
          f"min flat: {c['strategy']['min_flat_hours']}h")

    # Cache status
    print(f"\nData cache:")
    cache_dir = ROOT / c['data']['cache_dir']
    if cache_dir.exists():
        files = sorted(cache_dir.glob('*.parquet'))
        for f in files:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.0f} KB)")
    else:
        print(f"  No cache yet (run: python run.py fetch)")

    # Recent results
    print(f"\nRecent results:")
    res_dir = ROOT / 'results'
    if res_dir.exists():
        recent = sorted(res_dir.glob('*.json'), reverse=True)[:5]
        for f in recent:
            print(f"  {f.name}")
    else:
        print("  No results yet")


# ============================================================================
# MAIN
# ============================================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'test':
        cmd_test()
    elif cmd == 'fetch':
        cmd_fetch()
    elif cmd == 'backtest':
        cmd_backtest()
    elif cmd == 'status':
        cmd_status()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
