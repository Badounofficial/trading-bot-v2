"""
run_session_5_verdict.py — Session 5 Walk-Forward orchestrator
==============================================================
Runs the full Session 5 walk-forward backtest and produces the final verdict.

USAGE:
    python scripts/run_session_5_verdict.py [--quick] [--asset BTC]
    
    --quick  : run with reduced step (faster, less stat power)
    --asset  : run a single asset (debugging)

PROTOCOL:
    1. Load all 8 cryptos data (Daily, H1, and resampled H4 from H1)
    2. For each asset, run walk-forward with 12mo train / 6mo test / 3mo step
    3. Aggregate metrics across windows
    4. Apply Hard/Soft rule to compute final verdict
    5. Save full results to docs/RECAPS/SESSION_5_RESULTS.md

The script DOES NOT modify the ICC strategy. All parameters frozen at CONFIG A
baseline (from Session 4).
"""
from __future__ import annotations
import sys
import time
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

# Make project importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.resample_h1_to_h4 import resample_h1_to_h4
from strategies.walkforward_icc import (
    run_walkforward_asset, compute_verdict, print_asset_table, AssetResult,
)


# ============================================================================
# CONFIG (frozen)
# ============================================================================
CACHE_DIR = Path('cache')
DOCS_RECAPS = Path('docs/RECAPS')
ASSETS = ['BTC', 'ETH', 'SOL', 'ADA', 'LINK', 'DOT', 'AVAX', 'LTC']
TRAIN_MONTHS = 12
TEST_MONTHS = 6
STEP_MONTHS = 3
QUICK_STEP_MONTHS = 6  # quick mode


# ============================================================================
# DATA LOADING
# ============================================================================

def load_asset_data(
    asset: str,
    cache_dir: Path = CACHE_DIR,
    use_resampled_h4: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load Daily, H4 (resampled from H1), and H1 for one asset.
    
    Returns (daily, h4, h1).
    """
    # Daily
    daily_path = cache_dir / f"kraken_1d_{asset}_USD.parquet"
    daily = pd.read_parquet(daily_path)
    daily = _ensure_datetime_index(daily)
    
    # H1
    h1_path = cache_dir / f"kraken_1h_{asset}_USD.parquet"
    h1 = pd.read_parquet(h1_path)
    h1 = _ensure_datetime_index(h1)
    
    # H4: resample from H1 (use full historical depth)
    if use_resampled_h4:
        h4 = resample_h1_to_h4(h1)
    else:
        h4_path = cache_dir / f"kraken_4h_{asset}_USD.parquet"
        h4 = pd.read_parquet(h4_path)
        h4 = _ensure_datetime_index(h4)
    
    # Standardize columns (lowercase)
    for df in (daily, h4, h1):
        df.columns = [c.lower() for c in df.columns]
    
    return daily, h4, h1


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        for col in ['timestamp', 'time', 'date', 'datetime']:
            if col in df.columns:
                df = df.set_index(pd.to_datetime(df[col]))
                df = df.drop(columns=[col])
                break
    # Ensure tz-naive (consistent across files)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    # Drop duplicates if any
    df = df[~df.index.duplicated(keep='first')]
    return df


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true',
                         help='Faster: use 6mo step instead of 3mo')
    parser.add_argument('--asset', type=str, default=None,
                         help='Run single asset only (debug)')
    parser.add_argument('--save', action='store_true', default=True,
                         help='Save results to docs/RECAPS/SESSION_5_RESULTS.md')
    parser.add_argument('--verbose', action='store_true',
                         help='Print per-window results')
    args = parser.parse_args()
    
    step = QUICK_STEP_MONTHS if args.quick else STEP_MONTHS
    assets = [args.asset] if args.asset else ASSETS
    
    print()
    print("=" * 70)
    print(f"  SESSION 5 — WALK-FORWARD ICC")
    print(f"  Schedule: train {TRAIN_MONTHS}mo / test {TEST_MONTHS}mo / step {step}mo")
    print(f"  Assets:   {', '.join(assets)}")
    print(f"  Mode:     {'QUICK' if args.quick else 'FULL'}")
    print("=" * 70)
    
    results: list[AssetResult] = []
    t0 = time.time()
    
    for asset in assets:
        print(f"\n  → {asset} ...")
        t_a = time.time()
        try:
            daily, h4, h1 = load_asset_data(asset)
            print(f"    Loaded {len(daily)} daily, {len(h4)} h4 (resampled), {len(h1)} h1 bars")
            print(f"    Range: {h1.index.min().date()} → {h1.index.max().date()}")
            
            ar = run_walkforward_asset(
                asset=asset,
                daily_prices=daily,
                h4_prices=h4,
                h1_prices=h1,
                train_months=TRAIN_MONTHS,
                test_months=TEST_MONTHS,
                step_months=step,
                verbose=args.verbose,
            )
            results.append(ar)
            
            dt = time.time() - t_a
            print(f"    Done in {dt:.1f}s — {ar.n_windows} windows, "
                  f"{ar.total_trades} trades, "
                  f"PnL {ar.cumulative_pnl*100:+.2f}%, "
                  f"PF {ar.overall_profit_factor:.2f}, "
                  f"DD {ar.worst_max_dd*100:.1f}%")
        except Exception as e:
            print(f"    ERROR on {asset}: {e}")
            import traceback
            traceback.print_exc()
            results.append(AssetResult(asset=asset, n_windows=0, windows=[]))
    
    total_dt = time.time() - t0
    print(f"\n  ⏱ Total run time: {total_dt:.1f}s\n")
    
    # Per-asset table
    print("─" * 70)
    print("  PER-ASSET SUMMARY (cumulative across all test windows)")
    print("─" * 70)
    print_asset_table(results)
    
    # Verdict
    verdict = compute_verdict(results)
    print(verdict.summary())
    
    # Save results
    if args.save and not args.asset:  # only save when running full
        DOCS_RECAPS.mkdir(parents=True, exist_ok=True)
        out_path = DOCS_RECAPS / 'SESSION_5_RESULTS.md'
        _save_results(out_path, results, verdict, total_dt, step)
        print(f"\n  💾 Saved full report → {out_path}")
    
    return 0 if verdict.is_viable else 1


def _save_results(path: Path, results, verdict, runtime_sec: float, step: int):
    """Write a structured markdown report."""
    lines = [
        f"# SESSION 5 — Walk-Forward Results & Verdict",
        f"",
        f"**Date** : {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Runtime** : {runtime_sec:.1f}s",
        f"**Schedule** : train {TRAIN_MONTHS}mo / test {TEST_MONTHS}mo / step {step}mo",
        f"**Assets** : {', '.join(ASSETS)}",
        f"**H4 data source** : H1 resampled to H4 (extended historical depth)",
        f"",
        f"## Per-Asset Results",
        f"",
        f"| Asset | Windows | Trades | Win % | PF | PnL% | MaxDD% | Win.OK% | Profitable |",
        f"|---|---|---|---|---|---|---|---|---|",
    ]
    for ar in results:
        if ar.total_trades == 0:
            lines.append(f"| {ar.asset} | {ar.n_windows} | 0 | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {ar.asset} | {ar.n_windows} | {ar.total_trades} "
            f"| {ar.mean_win_rate*100:.1f}% "
            f"| {ar.overall_profit_factor:.2f} "
            f"| {ar.cumulative_pnl*100:+.2f}% "
            f"| {ar.worst_max_dd*100:.1f}% "
            f"| {ar.pct_windows_profitable*100:.1f}% "
            f"| {'✓' if ar.is_profitable else '✗'} |"
        )
    
    lines.extend([
        f"",
        f"## Verdict (Hard/Soft Rule)",
        f"",
        f"```",
        verdict.summary(),
        f"```",
        f"",
        f"## Aggregated Metrics",
        f"",
        f"- Overall Profit Factor: **{verdict.overall_profit_factor:.2f}**",
        f"- Worst Max Drawdown: **{verdict.worst_max_dd*100:.1f}%**",
        f"- Profitable assets: **{verdict.n_assets_profitable}/8**",
        f"- Mean Win Rate: **{verdict.mean_win_rate*100:.1f}%**",
        f"- Mean Sharpe (annualized): **{verdict.mean_sharpe:.2f}**",
        f"- Mean Trades/Year: **{verdict.mean_trades_per_year:.1f}**",
        f"- Mean % Profitable Windows: **{verdict.mean_pct_windows_profitable*100:.1f}%**",
        f"",
        f"## Verdict Detail",
        f"",
        f"- HARD criteria passed: **{verdict.n_hard_passed}/3**",
        f"- SOFT criteria passed: **{verdict.n_soft_passed}/4**",
        f"- **FINAL : {'✅ VIABLE' if verdict.is_viable else '❌ NON-VIABLE'}**",
        f"",
        f"## Next Steps",
        f"",
        f"{'- Proceed to paper trading on Kraken' if verdict.is_viable else '- Do NOT paper trade ICC as-is'}",
        f"{'- Set up live data ingestion + order routing' if verdict.is_viable else '- Analyze failed criteria to identify improvement axes'}",
        f"{'- Add monitoring + alerts' if verdict.is_viable else '- Consider Session 6 (Gold/NAS100 spot) for cross-market validation'}",
        f"",
        f"---",
        f"",
        f"*Generated by `scripts/run_session_5_verdict.py`*",
    ])
    
    path.write_text("\n".join(lines), encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
