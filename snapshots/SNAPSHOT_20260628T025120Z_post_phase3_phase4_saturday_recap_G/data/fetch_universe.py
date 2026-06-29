"""
Multi-Asset Kraken Daily Data
==============================
Downloads multi-year daily prices for a universe of cryptos from Kraken.

Universe selection: top 10 cryptos by market cap that have liquid Kraken pairs.
3 years of daily data → ~1100 bars per asset, enough for proper walk-forward.

Used by mean_reversion.py and momentum_xsec.py strategies.

Usage:
    from data.fetch_universe import fetch_universe_daily
    universe = fetch_universe_daily()  # dict {symbol: DataFrame}
"""
from __future__ import annotations
import time
from pathlib import Path
from datetime import datetime, timedelta

import ccxt
import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / 'cache'

# Kraken symbols — using BTC/USD format (most reliable)
# These are 10 major cryptos with deep liquidity and 3+ years of history
UNIVERSE_SYMBOLS = [
    'BTC/USD',   # Bitcoin
    'ETH/USD',   # Ethereum
    'SOL/USD',   # Solana
    'ADA/USD',   # Cardano
    'LINK/USD',  # Chainlink
    'DOT/USD',   # Polkadot
    'AVAX/USD',  # Avalanche
    'MATIC/USD', # Polygon
    'DOGE/USD',  # Dogecoin
    'LTC/USD',   # Litecoin
]


def fetch_symbol_daily(
    symbol: str,
    years_back: int = 3,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download N years of daily OHLCV for one symbol from Kraken."""
    CACHE_DIR.mkdir(exist_ok=True)
    safe = symbol.replace('/', '_')
    cache_path = CACHE_DIR / f'kraken_daily_{safe}.parquet'

    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        return df

    print(f"  [fetch] {symbol}...", end=' ', flush=True)
    try:
        exchange = ccxt.kraken({'enableRateLimit': True})
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        since_ms = int((datetime.utcnow() - timedelta(days=365 * years_back)).timestamp() * 1000)

        all_candles = []
        current = since_ms
        consecutive_errors = 0

        while current < now_ms:
            try:
                candles = exchange.fetch_ohlcv(symbol, '1d', since=current, limit=720)
                if not candles:
                    break
                all_candles.extend(candles)
                last_ts = candles[-1][0]
                if last_ts <= current:
                    break
                current = last_ts + 1
                consecutive_errors = 0
                time.sleep(0.5)
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    print(f"⚠ {str(e)[:50]}")
                    break
                time.sleep(2 ** consecutive_errors)
    except Exception as e:
        print(f"⚠ Failed: {str(e)[:60]}")
        return pd.DataFrame()

    if not all_candles:
        print("⚠ No data")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('datetime').sort_index()
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df = df[~df.index.duplicated(keep='first')]
    df.to_parquet(cache_path)
    print(f"✓ {len(df)} bars ({df.index.min().date()} → {df.index.max().date()})")
    return df


def fetch_universe_daily(
    symbols: list = None,
    years_back: int = 3,
    force_refresh: bool = False,
) -> dict:
    """
    Download daily prices for a universe of cryptos.

    Returns dict {symbol: DataFrame}.
    Symbols that fail to download are simply omitted.
    """
    if symbols is None:
        symbols = UNIVERSE_SYMBOLS

    print(f"Loading universe of {len(symbols)} cryptos from Kraken...")
    universe = {}
    for sym in symbols:
        df = fetch_symbol_daily(sym, years_back, force_refresh)
        if not df.empty:
            universe[sym] = df

    print(f"\nLoaded {len(universe)}/{len(symbols)} symbols.")

    # Report coverage
    if universe:
        min_starts = [df.index.min() for df in universe.values()]
        max_ends = [df.index.max() for df in universe.values()]
        common_start = max(min_starts)
        common_end = min(max_ends)
        print(f"Common period: {common_start.date()} → {common_end.date()} "
              f"({(common_end - common_start).days} days)")

    return universe


def align_universe(universe: dict) -> pd.DataFrame:
    """
    Align all symbols on a common date index, return wide DataFrame of close prices.

    Returns:
        DataFrame indexed by date, columns are symbols, values are close prices.
        Missing values are forward-filled (max 5 days).
    """
    closes = pd.DataFrame({sym: df['close'] for sym, df in universe.items()})
    closes = closes.sort_index()
    closes = closes.ffill(limit=5)  # tolerate up to 5 missing days
    closes = closes.dropna()  # drop dates where any symbol is still missing
    return closes


if __name__ == '__main__':
    universe = fetch_universe_daily(years_back=3)
    print(f"\n=== UNIVERSE SUMMARY ===")
    for sym, df in universe.items():
        print(f"  {sym:<12} {len(df)} bars  "
              f"({df.index.min().date()} → {df.index.max().date()})  "
              f"last close: ${df['close'].iloc[-1]:,.2f}")

    print(f"\n=== ALIGNED CLOSES ===")
    closes = align_universe(universe)
    print(f"Shape: {closes.shape}")
    print(f"Period: {closes.index.min().date()} → {closes.index.max().date()}")
    print(f"\nLast 3 rows:")
    print(closes.tail(3).round(2))
