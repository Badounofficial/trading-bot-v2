"""
build_ob_alignment_dynamic.py — V2-DYNAMIC detector on the 3 alignment windows
==============================================================================
Runs `strategies.ob_detector_v2_dynamic.detect_obs_dynamic` (Badoun's
dynamic definition) on the same 3 frozen windows used for V2-strict
(see build_ob_alignment.py).

Output additions (alongside the V2-strict files already in place):
  alignment_ob_2026_05_22/<asset>/
    ├── ob_detection_dynamic.csv   (V2-dyn OBs)
    └── chart_annotated_dynamic.png (V2-dyn chart)

The V2-strict files (ob_detection.csv, chart_annotated.png) are untouched.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategies.ob_detector_v2_dynamic import (
    detect_obs_dynamic, summarize_obs_dynamic, obs_to_dataframe,
)

ALIGN_DIR = ROOT / "alignment_ob_2026_05_22"
ASSETS = ['gold', 'eth', 'btc']
SWING_LOOKBACK = 2   # Badoun-default — more permissive than V2-strict (3)


def render_chart_dynamic(df: pd.DataFrame, obs: list, asset: str, out_png: Path) -> None:
    """Render dark-theme chart with Badoun-dynamic OBs.

    OB- → red rectangle from body close down to wick low (wick anchor)
    OB+ → green rectangle from body close up to wick high (wick anchor)
    Each OB labelled with 'OB-' or 'OB+' in bold next to its origin bar.
    """
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#0a0e17')
    ax.set_facecolor('#0a0e17')

    width = 0.6
    n = len(df)

    for i, (ts, row) in enumerate(df.iterrows()):
        is_up = row['close'] >= row['open']
        color = '#10D783' if is_up else '#F23A4E'
        ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=0.8, zorder=1)
        body_low = min(row['open'], row['close'])
        body_high = max(row['open'], row['close'])
        rect = mpatches.Rectangle(
            (i - width / 2, body_low), width, body_high - body_low,
            facecolor=color, edgecolor=color, alpha=0.85, zorder=2,
        )
        ax.add_patch(rect)

    for ob in obs:
        is_bull = ob.type == 'OB+'
        # Color per Badoun spec : red box for OB-, green box for OB+
        face = '#10D783' if is_bull else '#F23A4E'
        # Box extends from OB bar to end of window (or consumption bar)
        x_start = ob.bar_index
        x_end = ob.consumed_at_bar if ob.consumed_at_bar is not None else (n - 1)
        x_end = max(x_end, ob.break_bar)
        if is_bull:
            # OB+ zone : from body_close UP to wick_high (the wick anchor)
            y_low = min(ob.body_open, ob.body_close)
            y_high = ob.wick_high
        else:
            # OB- zone : from wick_low (wick anchor) UP to body_close
            y_low = ob.wick_low
            y_high = max(ob.body_open, ob.body_close)
        rect = mpatches.Rectangle(
            (x_start - 0.5, y_low),
            (x_end - x_start) + 1,
            y_high - y_low,
            facecolor=face,
            edgecolor=face,
            alpha=0.28,
            linewidth=1.5,
            zorder=0,
        )
        ax.add_patch(rect)
        # Label
        label_y = ob.body_close
        ax.annotate(
            f"{ob.type}",
            (ob.bar_index, label_y),
            color='#FFFFFF',
            fontsize=9, fontweight='bold',
            ha='left', va='center',
            xytext=(4, 0), textcoords='offset points',
            zorder=5,
            bbox=dict(facecolor=face, edgecolor='none', pad=2, alpha=0.85),
        )

    ax.set_xlim(-1, n)
    step = max(1, n // 10)
    ticks = list(range(0, n, step))
    labels = [df.index[i].strftime('%m-%d %H:%M') for i in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=30, color='#cccccc', fontsize=8)
    ax.tick_params(colors='#cccccc')
    for spine in ax.spines.values():
        spine.set_color('#404858')
    ax.grid(True, alpha=0.15, color='#404858')
    title = (
        f"{asset.upper()} H4 — 60 candles ending 2026-05-23 00:00 UTC "
        f"— V2-DYNAMIC OB detection (W=2)"
    )
    ax.set_title(title, color='#E5B53E', fontsize=12.5, fontweight='bold', pad=12)
    ax.set_ylabel('Price', color='#cccccc')

    s = summarize_obs_dynamic(obs)
    footer = (
        f"V2-dynamic detected: {s['n_total']} OBs  ·  "
        f"{s['n_OB_plus']} OB+ / {s['n_OB_minus']} OB-  ·  "
        f"{s['n_active_at_end']} active at anchor  ·  "
        f"{s['n_consumed']} consumed"
    )
    fig.text(0.5, 0.02, footer, ha='center', color='#aaaaaa', fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_png, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    print(f"Dynamic OB alignment build — W={SWING_LOOKBACK}\n")
    total = 0
    for slug in ASSETS:
        df = pd.read_csv(ALIGN_DIR / slug / "data.csv", index_col=0, parse_dates=True)
        obs = detect_obs_dynamic(df, swing_lookback=SWING_LOOKBACK)
        s = summarize_obs_dynamic(obs)
        out_csv = ALIGN_DIR / slug / "ob_detection_dynamic.csv"
        obs_to_dataframe(obs).to_csv(out_csv, index=False)
        out_png = ALIGN_DIR / slug / "chart_annotated_dynamic.png"
        render_chart_dynamic(df, obs, slug, out_png)
        print(f"  {slug.upper()} → {s['n_total']} OBs "
              f"({s['n_OB_plus']} OB+ / {s['n_OB_minus']} OB-)  "
              f"→ {out_csv.relative_to(ROOT)}  +  {out_png.relative_to(ROOT)}")
        total += s['n_total']

    print(f"\nTotal V2-dynamic : {total} OBs across 3 assets.")
    print(f"(Badoun target  : 12 OBs — Gold 3 / ETH 4 / BTC 5)")


if __name__ == "__main__":
    main()
