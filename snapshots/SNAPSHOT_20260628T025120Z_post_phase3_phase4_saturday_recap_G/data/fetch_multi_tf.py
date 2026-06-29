"""
Multi-Timeframe Data Pipeline for ICC
======================================
Phase 1 of ICC implementation: download Daily + H4 + H1 for the universe of
assets we'll test on.

Kraken specifics:
    - Free public API, US-friendly
    - Timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
    - Per-request limit: 720 bars
    - Rate limit: 1 second between calls (be patient!)
    - Historical depth: 4h and 1h go back ~3-5 years; daily goes back to 2014

yfinance specifics (Gold, NASDAQ):
    - Daily: 20+ years available
    - Intraday (H1, H4): only last ~60 days for free
    - For H4/H1 on Gold/NASDAQ we'd need Polygon, Alpha Vantage, or paid feeds
    - This pipeline downloads what's available — multi-TF for Gold/NASDAQ is
      limited and will need a different data source in a future session

Usage:
    python data/fetch_multi_tf.py status       # show what we have
    python data/fetch_multi_tf.py crypto       # download crypto multi-TF
    python data/fetch_multi_tf.py gold         # download Gold/NASDAQ daily + 60d H4/H1
    python data/fetch_multi_tf.py all          # everything
"""
from __future__ import annotations
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

import ccxt
import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / 'cache'

# Crypto universe (same as fetch_universe.py — Kraken)
CRYPTO_SYMBOLS = [
    'BTC/USD', 'ETH/USD', 'SOL/USD', 'ADA/USD', 'LINK/USD',
    'DOT/USD', 'AVAX/USD', 'DOGE/USD', 'LTC/USD',
]

# Yahoo Finance (Gold + NASDAQ)
YF_SYMBOLS = ['GC=F', '^NDX']

# Timeframe configurations: how many years back we want
TF_TARGETS = {
    '1d': 5,    # 5 years of daily — easy, plenty available
    '4h': 4,    # 4 years of H4 — important for ICC
    '1h': 2,    # 2 years of H1 — sufficient for many ICC cycles
}

# Kraken API limit
KRAKEN_LIMIT = 720
KRAKEN_DELAY_S = 1.5  # Be conservative with rate limit


# ============================================================================
# KRAKEN DOWNLOADER (CRYPTO)
# ============================================================================

def fetch_kraken_multi_tf(
    symbol: str,
    timeframe: str,
    years_back: int,
    force_refresh: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """Download multi-page OHLCV from Kraken for a specific timeframe."""
    CACHE_DIR.mkdir(exist_ok=True)
    safe = symbol.replace('/', '_')
    cache_path = CACHE_DIR / f'kraken_{timeframe}_{safe}.parquet'

    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        if verbose:
            span = (df.index.max() - df.index.min()).days
            print(f"    [cache] {symbol} {timeframe}: {len(df)} bars "
                  f"({df.index.min().date()} → {df.index.max().date()}, {span}d)")
        return df

    if verbose:
        print(f"    [fetch] {symbol} {timeframe} ({years_back}y)...", end=' ', flush=True)

    exchange = ccxt.kraken({'enableRateLimit': True})
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    since_ms = int((datetime.utcnow() - timedelta(days=365 * years_back)).timestamp() * 1000)

    all_candles = []
    current = since_ms
    consecutive_errors = 0
    request_count = 0
    max_requests = 100  # safety cap

    while current < now_ms and request_count < max_requests:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=current, limit=KRAKEN_LIMIT)
            request_count += 1
            if not candles:
                break
            all_candles.extend(candles)
            last_ts = candles[-1][0]
            if last_ts <= current:
                break  # no progress
            current = last_ts + 1
            consecutive_errors = 0
            time.sleep(KRAKEN_DELAY_S)
        except Exception as e:
            consecutive_errors += 1
            err = str(e)[:60]
            if consecutive_errors >= 4:
                if verbose:
                    print(f"⚠ {err}", flush=True)
                break
            time.sleep(min(30, 3 ** consecutive_errors))

    if not all_candles:
        if verbose:
            print("⚠ No data", flush=True)
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('datetime').sort_index()
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df = df[~df.index.duplicated(keep='first')]
    df.to_parquet(cache_path)
    if verbose:
        span_days = (df.index.max() - df.index.min()).days
        print(f"✓ {len(df)} bars ({df.index.min().date()} → {df.index.max().date()}, "
              f"{span_days}d, {request_count} calls)", flush=True)
    return df


# ============================================================================
# YFINANCE DOWNLOADER (GOLD, NASDAQ)
# ============================================================================

def fetch_yf_multi_tf(
    symbol: str,
    interval: str,
    period: str = None,
    force_refresh: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    yfinance has limited intraday history (60d for hourly/4h) but unlimited daily.
    interval: '1d', '1h', '4h' (we'll resample to 4h since yfinance doesn't have it)
    """
    CACHE_DIR.mkdir(exist_ok=True)
    safe = symbol.replace('=', '_').replace('^', '').replace('/', '_')
    cache_path = CACHE_DIR / f'yf_{interval}_{safe}.parquet'

    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        if verbose:
            span_days = (df.index.max() - df.index.min()).days
            print(f"    [cache] {symbol} {interval}: {len(df)} bars "
                  f"({df.index.min().date()} → {df.index.max().date()}, {span_days}d)")
        return df

    if verbose:
        print(f"    [fetch] {symbol} {interval}...", end=' ', flush=True)
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        if interval == '1d':
            # 5 years of daily
            df = ticker.history(period='5y', interval='1d', auto_adjust=False)
        elif interval == '1h':
            # yfinance: max 730 days for hourly, but in practice often 60d
            df = ticker.history(period='730d', interval='1h', auto_adjust=False)
        elif interval == '4h':
            # No native 4h on yfinance; download 1h and resample
            df_1h = ticker.history(period='730d', interval='1h', auto_adjust=False)
            if df_1h.empty:
                if verbose:
                    print("⚠ no 1h data to resample", flush=True)
                return pd.DataFrame()
            # Resample 1h to 4h
            df = df_1h.resample('4h').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum',
            }).dropna(subset=['Close'])
        else:
            if verbose:
                print(f"⚠ unsupported interval {interval}", flush=True)
            return pd.DataFrame()

        if df.empty:
            if verbose:
                print("⚠ empty response", flush=True)
            return pd.DataFrame()

        # Normalize column names
        df = df.rename(columns={
            'Open': 'open', 'High': 'high', 'Low': 'low',
            'Close': 'close', 'Volume': 'vol',
        })
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df[['open', 'high', 'low', 'close', 'vol']]
        df = df.dropna(subset=['close'])
        df.to_parquet(cache_path)
        if verbose:
            span_days = (df.index.max() - df.index.min()).days
            print(f"✓ {len(df)} bars ({df.index.min().date()} → {df.index.max().date()}, "
                  f"{span_days}d)", flush=True)
        return df
    except Exception as e:
        if verbose:
            print(f"⚠ {str(e)[:60]}", flush=True)
        return pd.DataFrame()


# ============================================================================
# COMMANDS
# ============================================================================

def cmd_status():
    """Show what we have in cache."""
    print("\n=== CACHE STATUS ===\n")
    cache_files = sorted(CACHE_DIR.glob('*.parquet'))
    if not cache_files:
        print("  (cache empty)")
        return

    # Group by type
    groups = {}
    for f in cache_files:
        name = f.stem
        # Detect source
        if name.startswith('kraken_'):
            parts = name.split('_')
            tf = parts[1]
            sym = '_'.join(parts[2:])
            groups.setdefault(f'Kraken {tf}', []).append((sym, f))
        elif name.startswith('yf_'):
            parts = name.split('_')
            tf = parts[1]
            sym = '_'.join(parts[2:])
            groups.setdefault(f'yfinance {tf}', []).append((sym, f))
        else:
            groups.setdefault('Other', []).append((name, f))

    for group_name, files in sorted(groups.items()):
        print(f"  {group_name}:")
        for sym, f in sorted(files):
            try:
                df = pd.read_parquet(f)
                if df.empty:
                    print(f"    {sym}: (empty)")
                    continue
                span = (df.index.max() - df.index.min()).days
                print(f"    {sym:<25}  {len(df):>6} bars  "
                      f"{df.index.min().date()} → {df.index.max().date()}  ({span}d)")
            except Exception as e:
                print(f"    {sym}: ⚠ {str(e)[:40]}")
        print()


def cmd_crypto():
    """Download all crypto multi-TF."""
    print("\n=== DOWNLOADING CRYPTO MULTI-TF FROM KRAKEN ===\n")
    print(f"  Universe: {len(CRYPTO_SYMBOLS)} symbols")
    print(f"  Timeframes: {list(TF_TARGETS.keys())}")
    print(f"  Estimated time: ~{len(CRYPTO_SYMBOLS) * len(TF_TARGETS) * 30 / 60:.0f}-"
          f"{len(CRYPTO_SYMBOLS) * len(TF_TARGETS) * 90 / 60:.0f} minutes\n")

    for tf, years in TF_TARGETS.items():
        print(f"\n  ── Timeframe: {tf} ({years} years) ──")
        for sym in CRYPTO_SYMBOLS:
            fetch_kraken_multi_tf(sym, tf, years_back=years)


def cmd_gold():
    """Download Gold + NASDAQ data."""
    print("\n=== DOWNLOADING GOLD + NASDAQ MULTI-TF FROM YFINANCE ===\n")
    print("  Note: intraday limited to ~60-730 days on yfinance free")
    print(f"  Symbols: {YF_SYMBOLS}")
    print(f"  Intervals: 1d (5y), 1h (~730d), 4h (resampled from 1h)\n")

    for sym in YF_SYMBOLS:
        print(f"\n  ── {sym} ──")
        for interval in ['1d', '1h', '4h']:
            fetch_yf_multi_tf(sym, interval)


def cmd_all():
    cmd_crypto()
    cmd_gold()
    print("\n\n")
    cmd_status()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'status':
        cmd_status()
    elif cmd == 'crypto':
        cmd_crypto()
        cmd_status()
    elif cmd == 'gold':
        cmd_gold()
        cmd_status()
    elif cmd == 'all':
        cmd_all()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
