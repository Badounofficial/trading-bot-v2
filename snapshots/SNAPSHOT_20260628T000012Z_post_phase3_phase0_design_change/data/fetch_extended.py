"""
Extended BTC daily data fetcher.
================================
Downloads multi-year BTC daily prices from Kraken (US-accessible, free, reliable).

Used by compare_regimes.py to compute regime filter on enough data to make
MA100/MA147/MA200 actually testable.

The trading data for backtest stays on Hyperliquid (where we'll actually trade).
This is just the BTC reference series for the regime filter.

Why Kraken:
  - US-friendly (no geographic blocking like Binance)
  - Multi-year BTC/USD daily data available
  - Free public API, supported by ccxt

Usage:
    from data.fetch_extended import fetch_btc_extended_daily
    btc = fetch_btc_extended_daily()  # downloads or uses cache
"""
from __future__ import annotations
import time
from pathlib import Path
from datetime import datetime, timedelta

import ccxt
import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / 'cache'


def fetch_btc_extended_daily(
    years_back: int = 3,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Download BTC/USD daily prices from Kraken.

    Returns DataFrame indexed by datetime with columns: open, high, low, close, vol.
    Cached as cache/btc_daily_extended.parquet.

    Args:
        years_back: how many years of history to fetch (default 3 = ~1100 days)
        force_refresh: if True, ignore cache and re-download
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / 'btc_daily_extended.parquet'

    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        span_days = (df.index.max() - df.index.min()).days
        print(f"  [cache] Loaded extended BTC daily ({len(df)} bars, "
              f"{span_days} days, {df.index.min().date()} → {df.index.max().date()})")
        return df

    print(f"  [fetch] Downloading {years_back} years of BTC/USD daily from Kraken...")
    exchange = ccxt.kraken({'enableRateLimit': True})

    now_ms = int(datetime.utcnow().timestamp() * 1000)
    since_ms = int((datetime.utcnow() - timedelta(days=365 * years_back)).timestamp() * 1000)

    # Kraken uses BTC/USD pair
    all_candles = []
    current = since_ms
    consecutive_errors = 0

    while current < now_ms:
        try:
            candles = exchange.fetch_ohlcv('BTC/USD', '1d', since=current, limit=720)
            if not candles:
                break
            all_candles.extend(candles)
            last_ts = candles[-1][0]
            if last_ts <= current:
                # No progress, we're done
                break
            current = last_ts + 1
            consecutive_errors = 0
            time.sleep(0.5)  # Kraken is rate-limit sensitive
        except Exception as e:
            consecutive_errors += 1
            err = str(e)[:100]
            print(f"    [retry {consecutive_errors}/5] {err}")
            if consecutive_errors >= 5:
                print(f"    ⚠ Giving up after 5 errors")
                break
            time.sleep(min(60, 2 ** consecutive_errors))

    if not all_candles:
        print("  ⚠ No data received")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('datetime').sort_index()
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df = df[~df.index.duplicated(keep='first')]
    df.to_parquet(cache_path)

    span_days = (df.index.max() - df.index.min()).days
    print(f"  [fetch] Downloaded {len(df)} daily bars "
          f"({span_days} days, {df.index.min().date()} → {df.index.max().date()})")
    print(f"  [fetch] Cached to {cache_path.relative_to(cache_path.parent.parent)}")
    return df


if __name__ == '__main__':
    df = fetch_btc_extended_daily(years_back=3)
    if not df.empty:
        print(f"\nFirst 3 rows:")
        print(df.head(3))
        print(f"\nLast 3 rows:")
        print(df.tail(3))
        print(f"\nStats:")
        print(f"  Daily return mean: {df['close'].pct_change().mean()*100:.3f}%")
        print(f"  Daily return std:  {df['close'].pct_change().std()*100:.3f}%")
        print(f"  Annualized vol:    {df['close'].pct_change().std()*(365**0.5)*100:.1f}%")
