"""
walkforward_v1_friction.py
==========================

Runs the V1 ICC swing strategy under METHODOLOGICAL DIRECTIVE #2:

  Methodo   : Walk-forward OOS (12m train / 6m test / 3m step) — no in-sample leak
  Friction  : Hyperliquid fees (4.5 bps/leg) + asset-tiered slippage (probabilistic) + funding
  Windows   : 2024-01-01 → 2025-12-31 (bull tape) AND 2022-01-01 → 2023-12-31 (bear→recovery)
  Regime    : explicitly tagged in the report

Outputs:
  results/walkforward_v1_oos_friction_<ts>.json   raw aggregates
  results/walkforward_v1_oos_friction_<ts>.md     qualified summary with 4-tag header

Run:
  python scripts/walkforward_v1_friction.py
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from strategies.walkforward_icc import (
    run_walkforward_asset, compute_verdict, print_asset_table,
)

ASSETS = ['BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'LINK', 'LTC']
CACHE = ROOT / 'cache'

WINDOWS = [
    {
        'tag': 'bull_2024_2025',
        'start': '2024-01-01',
        'end':   '2025-12-31',
        'regime_label': 'Bull regime (BTC +120% in 2025)',
        # WF schedule
        'train_months': 12, 'test_months': 6, 'step_months': 3,
    },
    {
        'tag': 'bear_recovery_2022_2023',
        'start': '2022-01-01',
        'end':   '2023-12-31',
        'regime_label': 'Bear → recovery (Terra/Luna May 2022, FTX Nov 2022, recovery 2023)',
        'train_months': 12, 'test_months': 6, 'step_months': 3,
    },
]


# ---------------------------------------------------------------------------
def resample_1h_to_4h(h1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Kraken-style 1h OHLCV bars into 4h bars aligned to UTC midnight."""
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
    h4 = h1.resample('4h', label='left', closed='left').agg(agg).dropna()
    return h4


def load_asset(asset: str, start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load Daily / H4 / H1 for asset, sliced to [start, end].

    H4: native Kraken 4h if covers the window, else resampled from 1h.
    """
    daily = pd.read_parquet(CACHE / f'kraken_1d_{asset}_USD.parquet').loc[start:end]
    h1 = pd.read_parquet(CACHE / f'kraken_1h_{asset}_USD.parquet').loc[start:end]

    h4_native_path = CACHE / f'kraken_4h_{asset}_USD.parquet'
    h4 = None
    if h4_native_path.exists():
        h4_native = pd.read_parquet(h4_native_path)
        if h4_native.index.min() <= pd.Timestamp(start) and h4_native.index.max() >= pd.Timestamp(end):
            h4 = h4_native.loc[start:end]
    if h4 is None or len(h4) < 50:
        # Resample 1h → 4h
        h4 = resample_1h_to_4h(h1)
    return daily, h4, h1


# ---------------------------------------------------------------------------
def run_window(win: dict, apply_friction: bool) -> dict:
    print(f"\n=== Window: {win['tag']}  ({win['start']} → {win['end']})  "
          f"friction={apply_friction} ===")
    asset_results = []
    for asset in ASSETS:
        try:
            daily, h4, h1 = load_asset(asset, win['start'], win['end'])
        except FileNotFoundError as e:
            print(f"  {asset}: SKIP (data missing: {e.filename})")
            continue
        if len(daily) < 30 or len(h4) < 100 or len(h1) < 500:
            print(f"  {asset}: SKIP (insufficient — d={len(daily)} h4={len(h4)} h1={len(h1)})")
            continue

        t0 = time.time()
        ar = run_walkforward_asset(
            asset=asset,
            daily_prices=daily, h4_prices=h4, h1_prices=h1,
            train_months=win['train_months'],
            test_months=win['test_months'],
            step_months=win['step_months'],
            verbose=False,
            sl_mode='v1_h1_close',
            apply_friction=apply_friction,
        )
        asset_results.append(ar)
        print(f"  {asset:<5} windows={ar.n_windows:<2} trades={ar.total_trades:<3} "
              f"WR={ar.mean_win_rate*100:5.1f}%  PF={ar.overall_profit_factor:5.2f}  "
              f"ΣPnL={ar.cumulative_pnl*100:+7.2f}pp  DD={ar.worst_max_dd*100:5.1f}%  "
              f"({time.time()-t0:.1f}s)")

    verdict = compute_verdict(asset_results)

    # Aggregate metrics
    all_pnls = [p for ar in asset_results for w in ar.windows for p in w.trade_pnls]
    wins = [p for p in all_pnls if p > 0]
    losses = [p for p in all_pnls if p <= 0]
    sum_wins = sum(wins); sum_losses = abs(sum(losses)) if losses else 0.0
    pf = sum_wins / max(sum_losses, 1e-9)
    wr = (len(wins) / len(all_pnls)) if all_pnls else 0.0
    sigma_pnl_pp = sum(all_pnls) * 100  # percentage points
    worst_dd = max((ar.worst_max_dd for ar in asset_results), default=0.0) * 100

    # Sharpe (annualized from per-trade returns) — approximation
    if len(all_pnls) >= 2:
        std = np.std(all_pnls, ddof=1)
        mean = np.mean(all_pnls)
        # Estimate trades/year from sum across assets
        total_yrs = sum(len(ar.windows) * win['test_months'] for ar in asset_results) / 12.0
        trades_per_year = (len(all_pnls) / max(total_yrs, 0.01)) if total_yrs else 0
        sharpe_ann = (mean / std) * np.sqrt(max(trades_per_year, 1)) if std > 0 else 0.0
    else:
        sharpe_ann = 0.0
        trades_per_year = 0.0

    return {
        'window': win,
        'apply_friction': apply_friction,
        'n_assets_with_results': len(asset_results),
        'aggregate': {
            'total_trades': len(all_pnls),
            'win_rate_pct': 100 * wr,
            'profit_factor': pf,
            'sum_pnl_pp': sigma_pnl_pp,
            'worst_max_dd_pct': worst_dd,
            'sharpe_ann': sharpe_ann,
            'trades_per_year': trades_per_year,
            'n_assets_profitable': verdict.n_assets_profitable,
        },
        'per_asset': [{
            'asset': ar.asset,
            'n_windows': ar.n_windows,
            'total_trades': ar.total_trades,
            'mean_win_rate_pct': ar.mean_win_rate * 100,
            'profit_factor': ar.overall_profit_factor,
            'cumulative_pnl_pp': ar.cumulative_pnl * 100,
            'worst_max_dd_pct': ar.worst_max_dd * 100,
            'pct_windows_profitable': ar.pct_windows_profitable * 100,
            'trades_per_year': ar.trades_per_year,
        } for ar in asset_results],
    }


# ---------------------------------------------------------------------------
def main():
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    print(f"\n{'=' * 80}\n  V1 WALK-FORWARD OOS + FRICTION — RUN {ts}\n{'=' * 80}")
    print(f"  Assets   : {ASSETS}")
    print(f"  Methodo  : Walk-forward (12m train / 6m test / 3m step)")
    print(f"  Friction : fees 4.5 bps × 2 legs + tiered slippage + funding")
    print(f"  Windows  : {[w['tag'] for w in WINDOWS]}")

    results = []
    for win in WINDOWS:
        # Friction-on (the real number)
        r_with = run_window(win, apply_friction=True)
        # Friction-off (for haircut measurement)
        r_without = run_window(win, apply_friction=False)
        results.append({
            'tag': win['tag'],
            'with_friction': r_with,
            'no_friction': r_without,
        })

    # ---------------------------------------------------------------- print
    print(f"\n\n{'=' * 80}\n  FINAL SUMMARY — V1 OOS WALK-FORWARD\n{'=' * 80}")
    hdr = f"  {'Window':<28} {'Frict':<6} {'Trd':>4} {'WR%':>6} {'PF':>6} {'ΣPnL pp':>9} {'DD%':>6} {'Sharpe':>7}"
    print(hdr); print('  ' + '-' * 76)
    for r in results:
        for tag, sub in [('  +friction', r['with_friction']), ('  −friction', r['no_friction'])]:
            agg = sub['aggregate']
            print(f"  {r['tag']:<28}{tag} "
                  f"{agg['total_trades']:>4} {agg['win_rate_pct']:>6.1f} {agg['profit_factor']:>6.2f} "
                  f"{agg['sum_pnl_pp']:>+9.2f} {agg['worst_max_dd_pct']:>6.1f} {agg['sharpe_ann']:>7.2f}")

    # Save
    out_json = ROOT / 'results' / f'walkforward_v1_oos_friction_{ts}.json'
    out_json.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n✓ JSON → {out_json.relative_to(ROOT)}")

    # Markdown qualified summary
    md = []
    md += [
        f"# V1 Walk-Forward OOS + Friction — Methodologically Qualified",
        "",
        f"**Run** : {ts} UTC",
        "",
        "## Mandatory 4-qualifier header",
        "",
        "| Qualifier | Value |",
        "|---|---|",
        "| **Methodo**  | Walk-forward (12 m train / 6 m test / 3 m step, sliding, strict OOS) |",
        "| **Friction** | Hyperliquid taker 4.5 bps × 2 legs + asset-tiered slippage (probabilistic, lognormal) + funding 0.001 %/h |",
        "| **Window**   | A: 2024-01-01 → 2025-12-31 (bull) · B: 2022-01-01 → 2023-12-31 (bear→recovery) |",
        "| **Regime**   | A: BTC +120 % in 2025 (bull) · B: Terra/Luna + FTX crashes + 2023 recovery (bear) |",
        "",
        "## Aggregate results (V1 = SL on H1 close + 0.1 % buffer)",
        "",
        "| Window | Friction | Trades | WR | PF | ΣPnL pp | Max DD | Sharpe (ann.) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        for label, sub in [('OFF', r['no_friction']), ('**ON**', r['with_friction'])]:
            a = sub['aggregate']
            md.append(
                f"| {r['tag']} | {label} | {a['total_trades']} | {a['win_rate_pct']:.1f}% | "
                f"{a['profit_factor']:.2f} | {a['sum_pnl_pp']:+.2f}pp | {a['worst_max_dd_pct']:.1f}% | "
                f"{a['sharpe_ann']:.2f} |"
            )
    md += ["", "## Per-asset (with friction, OOS)", ""]
    for r in results:
        md += [f"### {r['tag']}",
               "",
               "| Asset | Windows | Trades | WR | PF | ΣPnL pp | DD | %WindowsProfitable | Trades/yr |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for ar in r['with_friction']['per_asset']:
            md.append(
                f"| {ar['asset']} | {ar['n_windows']} | {ar['total_trades']} | "
                f"{ar['mean_win_rate_pct']:.1f}% | {ar['profit_factor']:.2f} | "
                f"{ar['cumulative_pnl_pp']:+.2f}pp | {ar['worst_max_dd_pct']:.1f}% | "
                f"{ar['pct_windows_profitable']:.0f}% | {ar['trades_per_year']:.1f} |"
            )
        md.append("")
    out_md = ROOT / 'results' / f'walkforward_v1_oos_friction_{ts}.md'
    out_md.write_text("\n".join(md))
    print(f"✓ MD   → {out_md.relative_to(ROOT)}")
    return results


if __name__ == '__main__':
    main()
