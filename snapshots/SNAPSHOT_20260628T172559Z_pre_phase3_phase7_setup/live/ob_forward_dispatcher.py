#!/usr/bin/env python3
"""
ob_forward_dispatcher.py — daily OB Forward Detection → Telegram (visual)
==========================================================================
Runs alongside the paper_funding_capture daemon. Every day at 12:00 UTC,
fetches the latest 60 H4 candles for Gold/ETH/BTC, runs the **V2-DYNAMIC**
OB detector, and sends to Telegram :

  - 1 annotated PNG per asset that has ≥1 OB detected
  - OR 1 short text message saying "RAS" if no OB on any asset

Caption format (per asset image) :

  🔎 OB Forward Detection — 24 May 2026 (BTC H4)
  2 OBs détectés : OB- @ 81026 (14:00 UTC), OB+ @ 77205 (20:00 UTC)

Design notes
-----------
- Standalone daemon. Launched separately from paper_funding_capture and
  watchdog. If it dies, the funding daemon is unaffected.
- Single-process loop : sleep until next 12:00 UTC, dispatch, sleep again.
- Uses Hyperliquid public `/info` + ccxt (no API keys) for BTC/ETH OHLCV.
  Uses yfinance for Gold GC=F.
- Uses the V2-DYNAMIC detector (`strategies.ob_detector_v2_dynamic`) —
  the V2-strict detector remains in production for funding capture and
  walk-forwards.
- Persists per-day output PNGs under `live/state/forward_charts/` so we
  can audit at the 3 June consolidation.

Launch :
    cd ~/Desktop/trading-bot-v2
    nohup python3 live/ob_forward_dispatcher.py > /tmp/v2_ob_forward.out 2>&1 &
    echo "Forward dispatcher PID: $!"
"""
from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
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

from strategies.ob_detector_v2_dynamic import (
    detect_obs_dynamic, summarize_obs_dynamic, DynamicOB,
)
from paper_trading.monitoring import TelegramAlerter

# Reuse the same yfinance fetcher logic as build_ob_alignment.py
try:
    import yfinance as yf
except ImportError:
    yf = None

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

N_CANDLES = 60                # rolling H4 window each day
SWING_LOOKBACK = 2            # V2-dyn default (Badoun's eye)
DISPATCH_HOUR_UTC = 12        # 12:00 UTC
DISPATCH_MINUTE_UTC = 0
POLL_INTERVAL_SEC = 60        # wake every minute to check time

ASSETS = [
    # slug, label, fetch_kind, ccxt_symbol_if_any
    ('gold', 'Gold (XAUUSD GC=F)', 'yfinance', None),
    ('eth',  'ETH/USDC perp',      'ccxt_hl',  'ETH/USDC:USDC'),
    ('btc',  'BTC/USDC perp',      'ccxt_hl',  'BTC/USDC:USDC'),
]

STATE_DIR = ROOT / "live" / "state" / "forward_charts"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = ROOT / "live" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"ob_forward_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------
# DATA FETCHERS (same as build_ob_alignment but live — anchor = "now")
# ----------------------------------------------------------------------

def fetch_hl_h4(symbol: str, dispatch_dt: datetime) -> pd.DataFrame:
    """Fetch 60 H4 OHLC ending at the candle that closed most recently
    before dispatch_dt."""
    ex = ccxt.hyperliquid({'enableRateLimit': True})
    # H4 candle that closed at or just before dispatch_dt
    # We fetch a bit more to be safe
    since_ms = int((dispatch_dt - timedelta(hours=4 * (N_CANDLES + 5))).timestamp() * 1000)
    bars = ex.fetch_ohlcv(symbol, timeframe='4h', since=since_ms, limit=N_CANDLES + 10)
    if not bars:
        raise RuntimeError(f"No bars returned for {symbol}")
    df = pd.DataFrame(bars, columns=['ts_ms', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts_ms'], unit='ms', utc=True)
    df.set_index('datetime', inplace=True)
    df.drop(columns=['ts_ms'], inplace=True)
    # Keep only candles whose OPEN is strictly before dispatch_dt
    df = df[df.index < dispatch_dt].copy()
    df = df.tail(N_CANDLES).copy()
    return df


def fetch_gold_h4(dispatch_dt: datetime) -> pd.DataFrame:
    """Fetch Gold H4 via yfinance, resampled from 1h."""
    if yf is None:
        raise RuntimeError("yfinance not installed — `pip install yfinance --break-system-packages`")
    start = (dispatch_dt - timedelta(days=20)).strftime('%Y-%m-%d')
    end   = (dispatch_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    t = yf.Ticker("GC=F")
    raw = t.history(start=start, end=end, interval="1h", auto_adjust=False)
    if raw.empty:
        raise RuntimeError("yfinance empty for GC=F")
    raw.index = raw.index.tz_convert('UTC')
    raw = raw[['Open', 'High', 'Low', 'Close', 'Volume']].rename(
        columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'vol'}
    )
    h4 = raw.resample('4h', label='left', closed='left', origin='start_day').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'
    }).dropna()
    h4 = h4[h4.index < dispatch_dt].copy()
    h4 = h4.tail(N_CANDLES).copy()
    return h4


def fetch_asset(slug: str, dispatch_dt: datetime) -> pd.DataFrame:
    for s, _label, kind, symbol in ASSETS:
        if s != slug:
            continue
        if kind == 'yfinance':
            return fetch_gold_h4(dispatch_dt)
        if kind == 'ccxt_hl':
            return fetch_hl_h4(symbol, dispatch_dt)
    raise RuntimeError(f"unknown asset slug {slug}")


# ----------------------------------------------------------------------
# CHART RENDERING (dark theme — same style as alignment)
# ----------------------------------------------------------------------

def render_forward_chart(
    df: pd.DataFrame,
    obs: list[DynamicOB],
    asset_label: str,
    dispatch_date: datetime,
    out_png: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 8))
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

    # OB zones
    for ob in obs:
        is_bull = ob.type == 'OB+'
        face = '#10D783' if is_bull else '#F23A4E'
        x_start = ob.bar_index
        x_end = ob.consumed_at_bar if ob.consumed_at_bar is not None else (n - 1)
        x_end = max(x_end, ob.break_bar)
        if is_bull:
            y_low = min(ob.body_open, ob.body_close)
            y_high = ob.wick_high
        else:
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
        ax.annotate(
            ob.type,
            (ob.bar_index, ob.body_close),
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

    s = summarize_obs_dynamic(obs)
    title = (
        f"{asset_label} H4 — {dispatch_date.strftime('%d %b %Y')} dispatch — "
        f"{s['n_total']} OB ({s['n_OB_plus']}+/{s['n_OB_minus']}-) — V2-dyn W=2"
    )
    ax.set_title(title, color='#E5B53E', fontsize=12, fontweight='bold', pad=12)
    ax.set_ylabel('Price', color='#cccccc')

    foot = (f"Window: {df.index[0].strftime('%m-%d %H:%M')} → "
            f"{df.index[-1].strftime('%m-%d %H:%M')} UTC  ·  "
            f"{s['n_active_at_end']} active at dispatch  ·  {s['n_consumed']} consumed")
    fig.text(0.5, 0.02, foot, ha='center', color='#aaaaaa', fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_png, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)


# ----------------------------------------------------------------------
# CAPTION BUILDER
# ----------------------------------------------------------------------

def build_caption(asset_label: str, dispatch_date: datetime, obs: list[DynamicOB]) -> str:
    n_plus = sum(1 for o in obs if o.type == 'OB+')
    n_minus = sum(1 for o in obs if o.type == 'OB-')
    header = (
        f"🔎 *OB Forward Detection* — {dispatch_date.strftime('%d %b %Y')} "
        f"({asset_label})\n"
        f"{len(obs)} OBs détectés ({n_plus}+ / {n_minus}-)\n"
    )
    # List up to first 6 OBs with anchor + timestamp; truncate if more
    lines = []
    for ob in obs[:6]:
        anchor_kind = 'wick_low' if ob.type == 'OB-' else 'wick_high'
        ts = ob.timestamp.strftime('%m-%d %H:%M')
        lines.append(
            f"• {ob.type} @ {ob.wick_anchor_price:.2f} ({ts} UTC, "
            f"body {ob.body_close:.2f}, {anchor_kind})"
        )
    if len(obs) > 6:
        lines.append(f"…+{len(obs) - 6} more (see image)")
    caption = header + "\n".join(lines)
    if len(caption) > 1020:
        caption = caption[:1020] + "..."
    return caption


# ----------------------------------------------------------------------
# DISPATCH (one tick)
# ----------------------------------------------------------------------

def dispatch_once(dispatch_dt: datetime, dry_run: bool = False) -> None:
    """Run one full dispatch cycle : fetch each asset, detect, send.

    Args:
        dispatch_dt: the "anchor" datetime — last candle close considered
        dry_run: if True, generate charts but do NOT send to Telegram
    """
    alerter = TelegramAlerter() if not dry_run else None
    if dry_run:
        _log("DRY RUN — charts generated locally, no Telegram send")
    elif not alerter.enabled:
        _log("WARN — TelegramAlerter not configured. Skipping send.")
    date_slug = dispatch_dt.strftime('%Y%m%d_%H%MUTC')
    chart_dir = STATE_DIR / date_slug
    chart_dir.mkdir(parents=True, exist_ok=True)

    any_obs = False
    per_asset_summary = []
    for slug, label, _kind, _sym in ASSETS:
        try:
            df = fetch_asset(slug, dispatch_dt)
            obs = detect_obs_dynamic(df, swing_lookback=SWING_LOOKBACK)
        except Exception as e:
            _log(f"{slug.upper()} FETCH/DETECT ERROR : {e}")
            per_asset_summary.append(f"{slug.upper()}: ERROR ({type(e).__name__})")
            continue

        s = summarize_obs_dynamic(obs)
        per_asset_summary.append(f"{slug.upper()}: {s['n_total']} OBs")
        if s['n_total'] == 0:
            continue

        any_obs = True
        out_png = chart_dir / f"{slug}_forward.png"
        try:
            render_forward_chart(df, obs, label, dispatch_dt, out_png)
        except Exception as e:
            _log(f"{slug.upper()} RENDER ERROR : {e}")
            continue

        caption = build_caption(label, dispatch_dt, obs)
        if dry_run:
            _log(f"{slug.upper()} would send {s['n_total']} OBs → {out_png}")
        elif alerter.enabled:
            res = alerter.send_photo(str(out_png), caption=caption)
            if res.ok:
                _log(f"{slug.upper()} sent OK ({s['n_total']} OBs)")
            else:
                _log(f"{slug.upper()} SEND ERROR : {res.error}")
        else:
            _log(f"{slug.upper()} would send {s['n_total']} OBs (telegram disabled)")

    if not any_obs and not dry_run and alerter and alerter.enabled:
        # Send RAS text message
        text = (
            f"🔎 *OB Forward Detection* — {dispatch_dt.strftime('%d %b %Y')}\n"
            f"Aucun OB détecté sur Gold/ETH/BTC H4 aujourd'hui.\n\n"
            f"_{' · '.join(per_asset_summary)}_"
        )
        res = alerter.send(text)
        if res.ok:
            _log("RAS message sent OK")
        else:
            _log(f"RAS SEND ERROR : {res.error}")


# ----------------------------------------------------------------------
# SCHEDULING
# ----------------------------------------------------------------------

def next_dispatch_dt(now: datetime) -> datetime:
    """Return the next datetime at DISPATCH_HOUR_UTC:DISPATCH_MINUTE_UTC."""
    candidate = now.replace(
        hour=DISPATCH_HOUR_UTC, minute=DISPATCH_MINUTE_UTC, second=0, microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def main() -> None:
    _log("ob_forward_dispatcher started")
    _log(f"  dispatch time UTC : {DISPATCH_HOUR_UTC:02d}:{DISPATCH_MINUTE_UTC:02d}")
    _log(f"  assets : {[a[0] for a in ASSETS]}")
    _log(f"  swing_lookback W : {SWING_LOOKBACK}")

    # Flags for smoke-testing
    if len(sys.argv) > 1 and sys.argv[1] in ("--once", "--dry-run"):
        dry_run = (sys.argv[1] == "--dry-run")
        now = datetime.now(timezone.utc)
        mode = "DRY RUN" if dry_run else "--once"
        _log(f"{mode}: dispatching now ({now.isoformat()})")
        dispatch_once(now, dry_run=dry_run)
        _log(f"{mode} done. Exiting.")
        return

    while True:
        now = datetime.now(timezone.utc)
        next_dt = next_dispatch_dt(now)
        sleep_s = (next_dt - now).total_seconds()
        _log(f"sleeping {sleep_s:.0f}s until next dispatch at {next_dt.isoformat()}")
        # Cap each sleep at the poll interval so we wake up to check state and
        # are not stuck for 24h in one syscall (resilience to clock changes)
        while sleep_s > 0:
            chunk = min(sleep_s, POLL_INTERVAL_SEC)
            time.sleep(chunk)
            sleep_s -= chunk
        now = datetime.now(timezone.utc)
        _log(f"dispatching at {now.isoformat()}")
        try:
            dispatch_once(now)
        except Exception:
            _log("DISPATCH FATAL — traceback:")
            _log(traceback.format_exc())
        # Loop continues to next day


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _log("stopped by user (SIGINT)")
        sys.exit(0)
    except Exception:
        _log("FATAL — traceback:")
        _log(traceback.format_exc())
        sys.exit(1)
