"""
build_ob_alignment.py — V2's side of the OB alignment exercise
================================================================
Generates the three fixed windows agreed with Badoun for the OB
alignment exercise, runs V2's detector on each, exports CSV + PNG.

Anchor : 2026-05-22 23:59 UTC (Friday weekly close)
Windows: 60 H4 candles per asset, ending at the candle that closes at
         2026-05-23 00:00 UTC (the first H4 close that is > the anchor,
         which we accept because crypto trades continuous and FX/CFD's
         last fully-formed H4 close before 23:59 UTC was 20:00 UTC).
Assets : Gold (yfinance GC=F resampled 1h→4h), BTC (HL perp via ccxt),
         ETH (HL perp via ccxt).

Output : alignment_ob_2026_05_22/
           ├── README.md (protocol — written by a separate file)
           ├── INSTRUCTIONS_BADOUN.md (mobile briefing — written separately)
           ├── gold/
           │   ├── data.csv           (60 H4 OHLC)
           │   ├── ob_detection.csv   (V2's OBs with confidence, levels, notes)
           │   └── chart_annotated.png
           ├── eth/  ...
           └── btc/  ...
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from strategies.icc_structure import detect_structures
from strategies.icc_orderblocks import detect_order_blocks

# ----------------------------------------------------------------------
# CONFIG — frozen for the alignment exercise
# ----------------------------------------------------------------------
ANCHOR = datetime(2026, 5, 22, 23, 59, tzinfo=timezone.utc)
# Last H4 candle whose CLOSE is at or before anchor+1min = 22 May 24:00 UTC
LAST_CANDLE_CLOSE = datetime(2026, 5, 23, 0, 0, tzinfo=timezone.utc)
N_CANDLES = 60
TF_HOURS = 4

OUT_DIR = ROOT / "alignment_ob_2026_05_22"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ======================================================================
# DATA LOADERS
# ======================================================================

def fetch_hl_h4(symbol: str) -> pd.DataFrame:
    """Fetch 60 H4 OHLC ending at the candle closing 2026-05-23 00:00 UTC."""
    ex = ccxt.hyperliquid({'enableRateLimit': True})
    since_ms = int((LAST_CANDLE_CLOSE - timedelta(hours=TF_HOURS * (N_CANDLES + 1))).timestamp() * 1000)
    bars = ex.fetch_ohlcv(symbol, timeframe='4h', since=since_ms, limit=N_CANDLES + 5)
    if not bars:
        raise RuntimeError(f"No bars returned for {symbol}")
    df = pd.DataFrame(bars, columns=['ts_ms', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts_ms'], unit='ms', utc=True)
    df.set_index('datetime', inplace=True)
    df.drop(columns=['ts_ms'], inplace=True)
    # Filter: candle OPEN must be < LAST_CANDLE_CLOSE
    # (i.e. the candle that opens at LAST_CANDLE_CLOSE is the next one — drop it)
    df = df[df.index < LAST_CANDLE_CLOSE].copy()
    # Keep last N_CANDLES
    df = df.tail(N_CANDLES).copy()
    if len(df) != N_CANDLES:
        raise RuntimeError(f"Got {len(df)} bars, expected {N_CANDLES} for {symbol}")
    return df


def fetch_gold_h4() -> pd.DataFrame:
    """
    Fetch Gold (GC=F) hourly from yfinance, resample to H4 aligned to
    00/04/08/12/16/20 UTC, return last 60 H4 candles before anchor.
    """
    import yfinance as yf
    # Fetch a slightly larger window to ensure 60 H4 after resample
    start = (LAST_CANDLE_CLOSE - timedelta(days=15)).strftime('%Y-%m-%d')
    end = (LAST_CANDLE_CLOSE + timedelta(days=1)).strftime('%Y-%m-%d')
    t = yf.Ticker("GC=F")
    raw = t.history(start=start, end=end, interval="1h", auto_adjust=False)
    if raw.empty:
        raise RuntimeError("yfinance returned empty for GC=F")
    # Normalize to UTC, drop tz then re-attach UTC
    raw.index = raw.index.tz_convert('UTC')
    raw = raw[['Open', 'High', 'Low', 'Close', 'Volume']].rename(
        columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'vol'}
    )
    # Resample to 4h aligned to 00 UTC
    h4 = raw.resample('4h', label='left', closed='left', origin='start_day').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'
    }).dropna()
    h4 = h4[h4.index < LAST_CANDLE_CLOSE].copy()
    h4 = h4.tail(N_CANDLES).copy()
    return h4


# ======================================================================
# OB DETECTION WRAPPER + EXPORT
# ======================================================================

def run_detection(df: pd.DataFrame) -> tuple[list, pd.DataFrame, pd.DataFrame]:
    """Run V2's OB detector and return (OB list, ob_summary, structure_summary)."""
    # W=3 is standard for H4 per the ICC spec
    structures = detect_structures(df, swing_lookback=3)
    obs = detect_order_blocks(df, structures=structures)

    # Structure summary — useful to diagnose breaks that did NOT yield an OB
    struct_rows = []
    ob_bar_set = {ob.structure_broken.bar_index for ob in obs}
    for s in structures:
        struct_rows.append({
            'bar_index': s.bar_index,
            'timestamp_utc': s.timestamp.isoformat(),
            'type': s.type,
            'price': round(s.price, 4),
            'confirmed_at_bar': s.confirmed_at_bar,
            'is_break': s.type in ('NEW_HIGH', 'NEW_LOW', 'HH', 'LL'),
            'produced_ob': s.bar_index in ob_bar_set,
        })
    struct_summary = pd.DataFrame(struct_rows)

    # Build rows for CSV
    rows = []
    for ob in obs:
        rows.append({
            'bar_index': ob.bar_index,
            'timestamp_utc': ob.timestamp.isoformat(),
            'ob_type': ob.type,
            'strength': ob.strength,
            'zone_low': round(ob.zone_low, 4),
            'zone_high': round(ob.zone_high, 4),
            'pivot_level': round((ob.zone_low + ob.zone_high) / 2, 4),
            'detected_at_bar': ob.detected_at_bar,
            'detected_at_ts': ob.detected_at_ts.isoformat(),
            'n_candles_in_move': ob.n_candles_in_move,
            'has_fvg': ob.has_fvg,
            'structure_broken_type': ob.structure_broken.type,
            'consumed': ob.consumed,
            'consumed_at_bar': ob.consumed_at_bar if ob.consumed_at_bar is not None else '',
            'notes_algo': (
                f"strength={ob.strength}, "
                f"move_candles={ob.n_candles_in_move}, "
                f"fvg={'yes' if ob.has_fvg else 'no'}, "
                f"broke_{ob.structure_broken.type}, "
                f"detected_{ob.detected_at_bar - ob.bar_index}_bars_later"
            ),
        })
    # Always include columns even if no OB rows
    OB_COLS = [
        'bar_index', 'timestamp_utc', 'ob_type', 'strength',
        'zone_low', 'zone_high', 'pivot_level',
        'detected_at_bar', 'detected_at_ts',
        'n_candles_in_move', 'has_fvg', 'structure_broken_type',
        'consumed', 'consumed_at_bar', 'notes_algo',
    ]
    summary = pd.DataFrame(rows, columns=OB_COLS) if rows else pd.DataFrame(columns=OB_COLS)
    return obs, summary, struct_summary


def render_chart(df: pd.DataFrame, obs: list, asset: str, out_png: Path) -> None:
    """Plot OHLC candles + annotated OBs."""
    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor('#0a0e17')
    ax.set_facecolor('#0a0e17')

    x = np.arange(len(df))
    width = 0.6

    for i, (ts, row) in enumerate(df.iterrows()):
        is_up = row['close'] >= row['open']
        color = '#10D783' if is_up else '#F23A4E'
        # Wick
        ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=0.8, zorder=1)
        # Body
        body_low = min(row['open'], row['close'])
        body_high = max(row['open'], row['close'])
        rect = mpatches.Rectangle(
            (i - width / 2, body_low), width, body_high - body_low,
            facecolor=color, edgecolor=color, alpha=0.85, zorder=2,
        )
        ax.add_patch(rect)

    # Plot OB zones as horizontal rectangles spanning from OB bar to end
    for ob in obs:
        is_bull = ob.type == 'OB+'
        face = '#22D3EE' if is_bull else '#FFB347'
        edge = '#22D3EE' if is_bull else '#FFB347'
        # Detection: from OB bar to consumed_at_bar (or end)
        x_start = ob.bar_index
        x_end = ob.consumed_at_bar if ob.consumed_at_bar is not None else (len(df) - 1)
        # Always extend the box at least to the detection bar (when the break confirmed)
        x_end = max(x_end, ob.detected_at_bar)
        rect = mpatches.Rectangle(
            (x_start - 0.5, ob.zone_low),
            (x_end - x_start) + 1,
            ob.zone_high - ob.zone_low,
            facecolor=face,
            edgecolor=edge,
            alpha=0.25,
            linewidth=1.5,
            zorder=0,
        )
        ax.add_patch(rect)
        # Label
        midprice = (ob.zone_low + ob.zone_high) / 2
        label = f"{ob.type} {ob.strength[:3]}"
        ax.annotate(
            label,
            (ob.bar_index, midprice),
            color='#E5B53E' if is_bull else '#F8C8DC',
            fontsize=8, fontweight='bold',
            ha='left', va='center',
            xytext=(3, 0), textcoords='offset points',
            zorder=5,
        )

    # Axes
    ax.set_xlim(-1, len(df))
    ax.set_xticks(np.arange(0, len(df), 8))
    labels = [df.index[i].strftime('%m-%d %H:%M') for i in range(0, len(df), 8)]
    ax.set_xticklabels(labels, rotation=30, color='#cccccc', fontsize=8)
    ax.tick_params(colors='#cccccc')
    for spine in ax.spines.values():
        spine.set_color('#404858')
    ax.grid(True, alpha=0.15, color='#404858')
    ax.set_title(
        f"{asset} H4 — 60 candles ending 2026-05-23 00:00 UTC — V2 OB detection",
        color='#E5B53E', fontsize=13, fontweight='bold', pad=12,
    )
    ax.set_ylabel('Price', color='#cccccc')

    # Footer with stats
    n_obs = len(obs)
    n_active = sum(1 for ob in obs if not ob.consumed)
    n_strong = sum(1 for ob in obs if ob.strength in ('STRONG', 'VERY_STRONG'))
    footer = f"V2 detected: {n_obs} OBs total · {n_strong} strong/very_strong · {n_active} active at anchor"
    fig.text(0.5, 0.02, footer, ha='center', color='#aaaaaa', fontsize=9)

    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_png, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


# ======================================================================
# MAIN
# ======================================================================

ASSETS = [
    ('gold', 'GOLD (XAUUSD, yfinance GC=F)', fetch_gold_h4),
    ('eth',  'ETH/USDC perp (Hyperliquid)',  lambda: fetch_hl_h4('ETH/USDC:USDC')),
    ('btc',  'BTC/USDC perp (Hyperliquid)',  lambda: fetch_hl_h4('BTC/USDC:USDC')),
]


def main() -> None:
    print(f"OB alignment build — anchor={ANCHOR.isoformat()}, last_candle_close={LAST_CANDLE_CLOSE.isoformat()}")
    print(f"Output dir: {OUT_DIR}\n")

    for slug, label, loader in ASSETS:
        print(f"── {slug.upper()} ──── {label}")
        try:
            df = loader()
        except Exception as e:
            print(f"  DATA ERROR — {e}\n")
            continue

        print(f"  loaded {len(df)} bars : {df.index[0]} → {df.index[-1]}")
        print(f"  price range : low={df['low'].min():.2f}  high={df['high'].max():.2f}")

        # Save data
        asset_dir = OUT_DIR / slug
        asset_dir.mkdir(parents=True, exist_ok=True)
        data_csv = asset_dir / "data.csv"
        df.to_csv(data_csv)
        print(f"  → {data_csv.relative_to(ROOT)}")

        # Run OB detection
        obs, summary, struct_summary = run_detection(df)
        print(f"  detected {len(obs)} OBs : "
              f"{sum(1 for o in obs if o.type=='OB+')} OB+, "
              f"{sum(1 for o in obs if o.type=='OB-')} OB-")
        ob_csv = asset_dir / "ob_detection.csv"
        summary.to_csv(ob_csv, index=False)
        print(f"  → {ob_csv.relative_to(ROOT)}")
        struct_csv = asset_dir / "structure_summary.csv"
        struct_summary.to_csv(struct_csv, index=False)
        n_breaks = int(struct_summary['is_break'].sum()) if not struct_summary.empty else 0
        n_breaks_no_ob = int((struct_summary['is_break'] & ~struct_summary['produced_ob']).sum()) if not struct_summary.empty else 0
        print(f"  → {struct_csv.relative_to(ROOT)} ({n_breaks} breaks, {n_breaks_no_ob} without OB)")

        # Render chart
        chart_png = asset_dir / "chart_annotated.png"
        render_chart(df, obs, label, chart_png)
        print(f"  → {chart_png.relative_to(ROOT)}\n")

    print("Done.")


if __name__ == "__main__":
    main()
