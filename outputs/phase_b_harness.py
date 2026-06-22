"""
Phase B Backtest Harness — measure look-ahead bias impact.

Runs the funding_capture strategy through backtest/engine.py on BTC/ETH/SOL
over the last 6 months of cached Hyperliquid funding data. Outputs a JSON
with per-asset and aggregate metrics so we can diff NOFIX vs WITHFIX.

Usage:
    python3 outputs/phase_b_harness.py outputs/phase_b_<label>.json
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategies.funding_capture import generate_position, diagnostic_summary
from backtest.engine import run_backtest

# Constants — fixed across both runs so the only delta is engine.py:55
ASSETS = ['BTC', 'ETH', 'SOL']
CAPITAL = 10_000.0
# Friction matches config.yaml: 4.5 bps taker + 0.87 bps slippage per leg, 2 legs
PER_LEG_BPS = 4.5 + 0.87
ENTRY_COST_BPS = 2 * PER_LEG_BPS   # 10.74
EXIT_COST_BPS = 2 * PER_LEG_BPS    # 10.74

# Strategy params from config.yaml
SMOOTH_HOURS = 24
ENTRY_THR_APR = 0.005
EXIT_THR_APR = -0.005
MIN_HOLD_H = 24
MIN_FLAT_H = 24

# Period: last 6 months of the cached data window
PERIOD_START = pd.Timestamp('2025-11-04')
PERIOD_END = pd.Timestamp('2026-05-04')


def load_funding(asset: str) -> pd.Series:
    fn = ROOT / 'cache' / f'funding_hyperliquid_{asset}_USDC_USDC.parquet'
    df = pd.read_parquet(fn)
    # Normalise sub-second jitter onto hourly grid
    df.index = df.index.floor('h')
    df = df[~df.index.duplicated(keep='last')]
    df = df.loc[(df.index >= PERIOD_START) & (df.index <= PERIOD_END)]
    return df['fundingRate']


def run_one(asset: str) -> dict:
    funding = load_funding(asset)
    position = generate_position(
        funding,
        smooth_hours=SMOOTH_HOURS,
        entry_threshold_apr=ENTRY_THR_APR,
        exit_threshold_apr=EXIT_THR_APR,
        min_hold_hours=MIN_HOLD_H,
        min_flat_hours=MIN_FLAT_H,
    )
    diag = diagnostic_summary(funding, position)
    result = run_backtest(
        funding,
        position,
        capital=CAPITAL,
        entry_cost_bps=ENTRY_COST_BPS,
        exit_cost_bps=EXIT_COST_BPS,
    )
    m = dict(result['metrics'])
    m['symbol'] = asset
    m['n_bars'] = int(len(funding))
    m['period_start'] = str(funding.index[0])
    m['period_end'] = str(funding.index[-1])
    m['diagnostic'] = diag
    return m


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'outputs' / 'phase_b_run.json'
    per_asset = []
    for asset in ASSETS:
        try:
            m = run_one(asset)
            per_asset.append(m)
            print(f"[{asset}] PnL=${m['total_pnl_usd']:.2f}  "
                  f"Sharpe={m['sharpe']:.2f}  DD={m['max_dd_pct']:.2f}%  "
                  f"Trades={m['n_trades']}  WR={m['win_rate_pct']:.1f}%  "
                  f"TIP={m['time_in_position_pct']:.1f}%")
        except Exception as e:
            print(f"[{asset}] FAILED: {e}")
            per_asset.append({'symbol': asset, 'error': str(e)})

    valid = [m for m in per_asset if 'error' not in m]
    if valid:
        total_cap = CAPITAL * len(valid)
        agg = {
            'total_capital_usd': total_cap,
            'total_pnl_usd': sum(m['total_pnl_usd'] for m in valid),
            'total_costs_usd': sum(m['total_costs_usd'] for m in valid),
            'mean_sharpe': sum(m['sharpe'] for m in valid) / len(valid),
            'min_sharpe': min(m['sharpe'] for m in valid),
            'max_dd_pct_worst_asset': min(m['max_dd_pct'] for m in valid),
            'sum_n_trades': sum(m['n_trades'] for m in valid),
            'mean_win_rate_pct': sum(m['win_rate_pct'] for m in valid) / len(valid),
            'mean_time_in_position_pct': sum(m['time_in_position_pct'] for m in valid) / len(valid),
        }
        agg['total_return_pct'] = agg['total_pnl_usd'] / total_cap * 100
    else:
        agg = {}

    payload = {
        'assets': ASSETS,
        'period_start_target': str(PERIOD_START),
        'period_end_target': str(PERIOD_END),
        'capital_per_asset_usd': CAPITAL,
        'entry_cost_bps': ENTRY_COST_BPS,
        'exit_cost_bps': EXIT_COST_BPS,
        'strategy_params': {
            'smooth_hours': SMOOTH_HOURS,
            'entry_threshold_apr': ENTRY_THR_APR,
            'exit_threshold_apr': EXIT_THR_APR,
            'min_hold_hours': MIN_HOLD_H,
            'min_flat_hours': MIN_FLAT_H,
        },
        'per_asset': per_asset,
        'aggregate': agg,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved -> {out_path}")


if __name__ == '__main__':
    main()
