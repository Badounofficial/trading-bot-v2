"""
compare_sl_v1_v2.py — V1 vs V2 SL Backtest (full-period, in-sample)
=====================================================================

What this does
--------------
Runs the ICC swing strategy on all 8 viable assets twice:

    Variant A  (V1, current code) : SL = previous H1 HL/LH close + 0.1% buffer
    Variant B  (V2, this fix)     : SL = active H4 HL/LH wick   + 0.1% buffer

Same data, same TFs (Daily / H4 / H1), same OB logic, same entry triggers.
The ONLY thing that differs is where the initial SL sits and how trailing
SL ratchets up (V2 trails on H4 swings too, for consistency).

Why this matters
----------------
In SWING mode the H4 is the structural REFERENCE and H1 is just the
CONFIRMATION TF. Anchoring the SL on H1 is too tight — normal H1 noise
on volatile assets (BTC, etc.) reaches the H1 swing and stops out trades
that were structurally still valid. V2 anchors on the REAL structural
invalidation level (H4 swing wick).

Period
------
2024-01-01 → 2025-12-31 — the window where Daily / 4h / 1h data overlap
for all 8 assets (~2 years).

Output
------
- results/sl_v1_vs_v2_<ts>.json   raw metrics per asset, per variant
- results/sl_v1_vs_v2_<ts>.md     human-readable comparison table
- stdout                          progress + summary table

Run:
    python scripts/compare_sl_v1_v2.py
"""
from __future__ import annotations
import sys
import json
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from strategies.icc_cycle import (
    run_icc_cycle, TradeMode, TradeState, ExitReason,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ASSETS = ['BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'LINK', 'LTC']

# Period where all 8 assets have aligned Daily + 4h + 1h coverage
PERIOD_START = '2024-01-01'
PERIOD_END = '2025-12-31'

CACHE = ROOT / 'cache'


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_asset(asset: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = pd.read_parquet(CACHE / f'kraken_1d_{asset}_USD.parquet')
    h4 = pd.read_parquet(CACHE / f'kraken_4h_{asset}_USD.parquet')
    h1 = pd.read_parquet(CACHE / f'kraken_1h_{asset}_USD.parquet')

    daily = daily.loc[PERIOD_START:PERIOD_END]
    h4 = h4.loc[PERIOD_START:PERIOD_END]
    h1 = h1.loc[PERIOD_START:PERIOD_END]
    return daily, h4, h1


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(setups: list) -> dict:
    """Per-asset metrics computed from closed setups."""
    closed = [s for s in setups if s.pnl_pct is not None]
    pnls = [s.pnl_pct for s in closed]
    durations_h = [
        (s.exit_timestamp - s.entry_timestamp).total_seconds() / 3600
        for s in closed
        if s.entry_timestamp is not None and s.exit_timestamp is not None
    ]
    rrs = []
    for s in closed:
        if s.entry_price is None or s.sl_initial is None or s.tp_target is None:
            continue
        risk = abs(s.entry_price - s.sl_initial)
        reward = abs(s.tp_target - s.entry_price)
        if risk > 1e-9:
            rrs.append(reward / risk)

    if not pnls:
        return {
            'n_total_setups': len(setups),
            'n_closed': 0, 'n_trades': 0,
            'n_wins': 0, 'n_losses': 0,
            'win_rate_pct': 0.0, 'profit_factor': 0.0,
            'total_pnl_pct': 0.0, 'avg_pnl_pct': 0.0,
            'avg_win_pct': 0.0, 'avg_loss_pct': 0.0,
            'max_dd_pct': 0.0, 'avg_rr_planned': 0.0,
            'avg_duration_h': 0.0,
            'exit_reasons': {},
            'sl_sources': {},
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0

    # Equity curve (each trade chained at risk-of-equity = pnl_pct of unit)
    equity = [1.0]
    for p in pnls:
        equity.append(equity[-1] * (1 + p))
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    max_dd = abs(dd.min())

    exit_reasons = {}
    sl_sources = {}
    for s in closed:
        if s.exit_reason:
            exit_reasons[s.exit_reason.value] = exit_reasons.get(s.exit_reason.value, 0) + 1
        if s.sl_source:
            sl_sources[s.sl_source] = sl_sources.get(s.sl_source, 0) + 1

    return {
        'n_total_setups': len(setups),
        'n_closed': len(closed),
        'n_trades': len(pnls),
        'n_wins': len(wins),
        'n_losses': len(losses),
        'win_rate_pct': 100.0 * len(wins) / len(pnls),
        'profit_factor': sum_wins / max(sum_losses, 1e-9),
        'total_pnl_pct': 100.0 * sum(pnls),
        'avg_pnl_pct': 100.0 * np.mean(pnls),
        'avg_win_pct': 100.0 * np.mean(wins) if wins else 0.0,
        'avg_loss_pct': 100.0 * np.mean(losses) if losses else 0.0,
        'max_dd_pct': 100.0 * max_dd,
        'avg_rr_planned': float(np.mean(rrs)) if rrs else 0.0,
        'avg_duration_h': float(np.mean(durations_h)) if durations_h else 0.0,
        'exit_reasons': exit_reasons,
        'sl_sources': sl_sources,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_one(asset: str, daily, h4, h1, sl_mode: str) -> dict:
    t0 = time.time()
    setups = run_icc_cycle(
        asset=asset,
        daily_prices=daily, h4_prices=h4, h1_prices=h1,
        mode=TradeMode.SWING,
        verbose=False,
        sl_mode=sl_mode,
    )
    metrics = compute_metrics(setups)
    metrics['elapsed_s'] = round(time.time() - t0, 2)
    return metrics


def fmt_row(asset, m_v1, m_v2):
    def delta(a, b, suffix=''):
        return f"{b - a:+.2f}{suffix}"
    return [
        asset,
        m_v1['n_trades'], m_v2['n_trades'],
        f"{m_v1['win_rate_pct']:.1f}%", f"{m_v2['win_rate_pct']:.1f}%",
        delta(m_v1['win_rate_pct'], m_v2['win_rate_pct'], 'pp'),
        f"{m_v1['profit_factor']:.2f}", f"{m_v2['profit_factor']:.2f}",
        delta(m_v1['profit_factor'], m_v2['profit_factor']),
        f"{m_v1['total_pnl_pct']:+.2f}%", f"{m_v2['total_pnl_pct']:+.2f}%",
        delta(m_v1['total_pnl_pct'], m_v2['total_pnl_pct'], 'pp'),
        f"{m_v1['max_dd_pct']:.1f}%", f"{m_v2['max_dd_pct']:.1f}%",
        f"{m_v1['avg_rr_planned']:.2f}", f"{m_v2['avg_rr_planned']:.2f}",
        f"{m_v1['avg_duration_h']:.0f}h", f"{m_v2['avg_duration_h']:.0f}h",
    ]


def main():
    print(f"\n=== V1 vs V2 SL — ICC Swing Backtest ===")
    print(f"Period: {PERIOD_START} → {PERIOD_END}")
    print(f"Assets: {ASSETS}\n")

    per_asset = {}

    for asset in ASSETS:
        print(f"[{asset}] loading data …", end=' ', flush=True)
        try:
            daily, h4, h1 = load_asset(asset)
        except FileNotFoundError as e:
            print(f"SKIP ({e.filename})")
            continue
        print(f"daily={len(daily)} h4={len(h4)} h1={len(h1)}")

        print(f"  V1  …", end=' ', flush=True)
        m_v1 = run_one(asset, daily, h4, h1, sl_mode='v1_h1_close')
        print(f"trades={m_v1['n_trades']} WR={m_v1['win_rate_pct']:.1f}% "
              f"PF={m_v1['profit_factor']:.2f} PnL={m_v1['total_pnl_pct']:+.2f}% "
              f"({m_v1['elapsed_s']}s)")

        print(f"  V2b …", end=' ', flush=True)
        m_v2b = run_one(asset, daily, h4, h1, sl_mode='v2b_h4_close')
        print(f"trades={m_v2b['n_trades']} WR={m_v2b['win_rate_pct']:.1f}% "
              f"PF={m_v2b['profit_factor']:.2f} PnL={m_v2b['total_pnl_pct']:+.2f}% "
              f"({m_v2b['elapsed_s']}s)")

        print(f"  V2  …", end=' ', flush=True)
        m_v2 = run_one(asset, daily, h4, h1, sl_mode='v2_h4_wick')
        print(f"trades={m_v2['n_trades']} WR={m_v2['win_rate_pct']:.1f}% "
              f"PF={m_v2['profit_factor']:.2f} PnL={m_v2['total_pnl_pct']:+.2f}% "
              f"({m_v2['elapsed_s']}s)")

        per_asset[asset] = {'v1': m_v1, 'v2b': m_v2b, 'v2': m_v2}

    # ---------------------------------------------------------------- summary
    print(f"\n{'=' * 110}")
    print(f"PER-ASSET COMPARISON  (V1 baseline · V2b H4-close · V2 H4-wick)")
    print(f"{'=' * 110}")
    hdr = f"{'Asset':<6}  {'V1 WR':>7} {'V2b WR':>8} {'V2 WR':>7}   {'V1 PF':>6} {'V2b PF':>7} {'V2 PF':>6}   {'V1 PnL':>9} {'V2b PnL':>10} {'V2 PnL':>9}   {'V1 DD':>6} {'V2b DD':>7} {'V2 DD':>6}"
    print(hdr)
    print('-' * 110)
    for asset, mm in per_asset.items():
        v1, v2b, v2 = mm['v1'], mm['v2b'], mm['v2']
        print(
            f"{asset:<6}  "
            f"{v1['win_rate_pct']:>6.1f}% {v2b['win_rate_pct']:>7.1f}% {v2['win_rate_pct']:>6.1f}%   "
            f"{v1['profit_factor']:>6.2f} {v2b['profit_factor']:>7.2f} {v2['profit_factor']:>6.2f}   "
            f"{v1['total_pnl_pct']:>+8.2f}% {v2b['total_pnl_pct']:>+9.2f}% {v2['total_pnl_pct']:>+8.2f}%   "
            f"{v1['max_dd_pct']:>5.1f}% {v2b['max_dd_pct']:>6.1f}% {v2['max_dd_pct']:>5.1f}%"
        )

    # Aggregates
    def agg(side):
        total_trades = sum(per_asset[a][side]['n_trades'] for a in per_asset)
        total_wins = sum(per_asset[a][side]['n_wins'] for a in per_asset)
        total_pnl = sum(per_asset[a][side]['total_pnl_pct'] for a in per_asset)
        avg_wr = (100.0 * total_wins / total_trades) if total_trades else 0.0
        all_pnls = []
        for a in per_asset:
            # rebuild per-trade list from closed counts: we only have aggregates,
            # so use sum/wins/losses ratio for PF approximation across assets
            pass
        # Recompute PF from per-asset wins×avg_win vs losses×avg_loss
        sum_wins_usd = sum(
            per_asset[a][side]['n_wins'] * (per_asset[a][side]['avg_win_pct'] / 100.0)
            for a in per_asset
        )
        sum_losses_usd = sum(
            per_asset[a][side]['n_losses'] * abs(per_asset[a][side]['avg_loss_pct'] / 100.0)
            for a in per_asset
        )
        pf = sum_wins_usd / max(sum_losses_usd, 1e-9)
        return total_trades, avg_wr, pf, total_pnl

    print('-' * 110)
    t1, wr1, pf1, p1 = agg('v1')
    tb, wrb, pfb, pb = agg('v2b')
    t2, wr2, pf2, p2 = agg('v2')
    print(f"  TOTAL V1 : trades={t1}  WR={wr1:.1f}%  PF={pf1:.2f}  ΣPnL={p1:+.2f}pp")
    print(f"  TOTAL V2b: trades={tb}  WR={wrb:.1f}%  PF={pfb:.2f}  ΣPnL={pb:+.2f}pp   (ΔPnL vs V1: {pb-p1:+.2f}pp)")
    print(f"  TOTAL V2 : trades={t2}  WR={wr2:.1f}%  PF={pf2:.2f}  ΣPnL={p2:+.2f}pp   (ΔPnL vs V1: {p2-p1:+.2f}pp)")

    # Save
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_json = ROOT / 'results' / f'sl_v1_vs_v2_{ts}.json'
    out_json.parent.mkdir(exist_ok=True)
    out_json.write_text(json.dumps({
        'period': {'start': PERIOD_START, 'end': PERIOD_END},
        'assets': ASSETS,
        'per_asset': per_asset,
        'aggregate': {
            'v1':  {'trades': t1, 'win_rate_pct': wr1, 'profit_factor': pf1, 'sum_pnl_pp': p1},
            'v2b': {'trades': tb, 'win_rate_pct': wrb, 'profit_factor': pfb, 'sum_pnl_pp': pb},
            'v2':  {'trades': t2, 'win_rate_pct': wr2, 'profit_factor': pf2, 'sum_pnl_pp': p2},
        },
        'timestamp_utc': ts,
    }, indent=2, default=str))
    print(f"\n✓ JSON  → {out_json.relative_to(ROOT)}")

    # Markdown
    md_lines = [
        f"# SL Anchor Comparison — ICC Swing Backtest",
        "",
        f"**Period** : {PERIOD_START} → {PERIOD_END}  ",
        f"**Assets** : {', '.join(ASSETS)}  ",
        f"**Generated** : {ts} UTC",
        "",
        "## Variants",
        "- **V1** (baseline): SL on H1 last HL/LH, anchored on the **close** price + 0.1% buffer.",
        "- **V2b**: SL on the active H4 HL/LH, anchored on the **close** + 0.1% buffer.",
        "- **V2**: SL on the active H4 HL/LH, anchored on the **wick** (low/high) + 0.1% buffer.",
        "",
        "## Per-asset comparison",
        "",
        "| Asset | Trd | WR V1 | WR V2b | WR V2 | PF V1 | PF V2b | PF V2 | PnL V1 | PnL V2b | PnL V2 | DD V1 | DD V2b | DD V2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for asset, mm in per_asset.items():
        v1, v2b, v2 = mm['v1'], mm['v2b'], mm['v2']
        md_lines.append(
            f"| {asset} | {v1['n_trades']} | "
            f"{v1['win_rate_pct']:.1f}% | {v2b['win_rate_pct']:.1f}% | {v2['win_rate_pct']:.1f}% | "
            f"{v1['profit_factor']:.2f} | {v2b['profit_factor']:.2f} | {v2['profit_factor']:.2f} | "
            f"{v1['total_pnl_pct']:+.2f}% | {v2b['total_pnl_pct']:+.2f}% | {v2['total_pnl_pct']:+.2f}% | "
            f"{v1['max_dd_pct']:.1f}% | {v2b['max_dd_pct']:.1f}% | {v2['max_dd_pct']:.1f}% |"
        )
    md_lines += [
        "",
        f"## Aggregate",
        "",
        f"- **V1**  : trades={t1}, WR={wr1:.1f}%, PF={pf1:.2f}, ΣPnL={p1:+.2f}pp",
        f"- **V2b** : trades={tb}, WR={wrb:.1f}%, PF={pfb:.2f}, ΣPnL={pb:+.2f}pp  (Δ vs V1 : {pb-p1:+.2f}pp)",
        f"- **V2**  : trades={t2}, WR={wr2:.1f}%, PF={pf2:.2f}, ΣPnL={p2:+.2f}pp  (Δ vs V1 : {p2-p1:+.2f}pp)",
    ]
    out_md = ROOT / 'results' / f'sl_v1_vs_v2_{ts}.md'
    out_md.write_text('\n'.join(md_lines))
    print(f"✓ MD    → {out_md.relative_to(ROOT)}")


if __name__ == '__main__':
    main()
