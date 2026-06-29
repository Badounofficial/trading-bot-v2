"""
Data Fetcher — Robust download with retry and cache.
=====================================================
Single source of truth for getting funding rate and price data.
Caches to parquet files for fast reload.

Usage:
    from data.fetch import fetch_funding, fetch_prices, load_cached
    funding = fetch_funding('BTC/USDC:USDC')   # downloads or returns cache
    prices = fetch_prices('BTC/USDC:USDC')
"""
from __future__ import annotations
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import ccxt
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import cfg


# ============================================================================
# CACHE PATHS
# ============================================================================

def _cache_path(kind: str, symbol: str) -> Path:
    """Build cache filename: cache/funding_hyperliquid_BTC_USDC_USDC.parquet"""
    safe_symbol = symbol.replace('/', '_').replace(':', '_')
    exchange = cfg()['exchange']['name']
    cache_dir = Path(__file__).parent.parent / cfg()['data']['cache_dir']
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / f'{kind}_{exchange}_{safe_symbol}.parquet'


# ============================================================================
# EXCHANGE FACTORY
# ============================================================================

def get_exchange() -> ccxt.Exchange:
    """Return a ccxt exchange instance."""
    name = cfg()['exchange']['name']
    if name == 'hyperliquid':
        return ccxt.hyperliquid({'enableRateLimit': True})
    elif name == 'bybit':
        return ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
    elif name == 'binance':
        return ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    raise ValueError(f"Unknown exchange: {name}")


# ============================================================================
# FETCH FUNDING (with retry)
# ============================================================================

def _fetch_funding_paginated(
    exchange: ccxt.Exchange,
    symbol: str,
    since_ms: int,
    until_ms: int,
    max_retries: int = 5,
) -> list:
    """Paginated fetch with exponential backoff."""
    all_data = []
    current = since_ms
    consecutive_errors = 0

    while current < until_ms:
        try:
            data = exchange.fetch_funding_rate_history(symbol, since=current, limit=500)
            if not data:
                break
            all_data.extend(data)
            current = data[-1]['timestamp'] + 1
            consecutive_errors = 0
            time.sleep(0.25)
        except Exception as e:
            consecutive_errors += 1
            err = str(e)[:120]
            print(f"  [retry {consecutive_errors}/{max_retries}] {err}")
            if consecutive_errors >= max_retries:
                print(f"  ⚠ Giving up on {symbol} after {max_retries} errors")
                break
            backoff = min(60, 2 ** consecutive_errors)
            time.sleep(backoff)
    return all_data


def fetch_funding(symbol: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch funding rate history for a symbol. Cached after first call.

    Returns a DataFrame indexed by datetime with columns:
        - fundingRate: per-period funding rate (e.g. 0.0001 = 0.01% per hour)
        - annualized: annualized rate (e.g. 0.10 = 10% APR), auto-detects period
    """
    cache_path = _cache_path('funding', symbol)
    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        print(f"  [cache] Loaded {symbol} funding ({len(df)} rows)")
        return df

    print(f"  [fetch] Downloading {symbol} funding from {cfg()['exchange']['name']}...")
    exchange = get_exchange()
    since_ms = int(datetime.fromisoformat(cfg()['data']['start_date']).timestamp() * 1000)
    until_ms = int(datetime.fromisoformat(cfg()['data']['end_date']).timestamp() * 1000)

    raw = _fetch_funding_paginated(exchange, symbol, since_ms, until_ms)
    if not raw:
        return pd.DataFrame()

    df = pd.DataFrame(raw)
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['fundingRate'] = df['fundingRate'].astype(float)
    df = df.set_index('datetime').sort_index()

    # Auto-detect funding period and annualize
    if len(df) >= 3:
        diffs = df.index.to_series().diff().dropna().dt.total_seconds()
        period_seconds = diffs.median()
        fundings_per_year = (365 * 86400) / period_seconds
    else:
        fundings_per_year = 365 * 3  # safe default (8h funding)
    df['annualized'] = df['fundingRate'] * fundings_per_year

    df = df[['fundingRate', 'annualized']]
    df.to_parquet(cache_path)
    print(f"  [fetch] Cached {len(df)} rows to {cache_path.name}")
    return df


# ============================================================================
# FETCH PRICES (OHLCV)
# ============================================================================

def fetch_prices(symbol: str, timeframe: str = '1h', force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch hourly OHLCV. Cached.

    Returns DataFrame indexed by datetime with columns:
        open, high, low, close, vol
    """
    cache_path = _cache_path(f'prices_{timeframe}', symbol)
    if cache_path.exists() and not force_refresh:
        df = pd.read_parquet(cache_path)
        print(f"  [cache] Loaded {symbol} prices ({len(df)} rows)")
        return df

    print(f"  [fetch] Downloading {symbol} prices from {cfg()['exchange']['name']}...")
    exchange = get_exchange()
    since_ms = int(datetime.fromisoformat(cfg()['data']['start_date']).timestamp() * 1000)
    until_ms = int(datetime.fromisoformat(cfg()['data']['end_date']).timestamp() * 1000)

    all_candles = []
    current = since_ms
    consecutive_errors = 0
    while current < until_ms:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=current, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            current = candles[-1][0] + 1
            consecutive_errors = 0
            time.sleep(0.25)
        except Exception as e:
            consecutive_errors += 1
            print(f"  [retry {consecutive_errors}/5] {str(e)[:100]}")
            if consecutive_errors >= 5:
                break
            time.sleep(min(60, 2 ** consecutive_errors))

    if not all_candles:
        return pd.DataFrame()
    df = pd.DataFrame(all_candles, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
    df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
    df = df.set_index('datetime').sort_index()[['open', 'high', 'low', 'close', 'vol']]
    df.to_parquet(cache_path)
    print(f"  [fetch] Cached {len(df)} rows")
    return df


# ============================================================================
# CONVENIENCE: LOAD ALL SYMBOLS
# ============================================================================

def load_all_funding() -> dict:
    """Returns dict {symbol: funding_df} for all configured symbols."""
    return {sym: fetch_funding(sym) for sym in cfg()['exchange']['symbols']}


def load_all_prices() -> dict:
    """Returns dict {symbol: price_df} for all configured symbols."""
    return {sym: fetch_prices(sym) for sym in cfg()['exchange']['symbols']}


if __name__ == '__main__':
    # Quick test: download/load all data and report
    print("=== DATA FETCH TEST ===")
    for sym in cfg()['exchange']['symbols']:
        f = fetch_funding(sym)
        p = fetch_prices(sym)
        print(f"\n{sym}:")
        print(f"  Funding: {len(f)} rows, "
              f"median APR {f['annualized'].median()*100:.2f}%, "
              f"max APR {f['annualized'].max()*100:.1f}%")
        print(f"  Prices:  {len(p)} rows, "
              f"date range {p.index.min().date()} → {p.index.max().date()}")
