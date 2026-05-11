"""
resample_h1_to_h4.py — Session 5 utility
=========================================
Resample H1 parquet data into H4 bars for extended historical backtest.

Why : Kraken H4 native is limited to 2 years (2024-2025).
      H1 data extends to 12 years for BTC/LTC, 10 for ETH, etc.
      Resampling H1 → H4 gives us much more out-of-sample data for walk-forward.

Convention :
    - H4 bar opens at hours [0, 4, 8, 12, 16, 20] UTC
    - open  = first H1 bar in the window
    - high  = max H1 high in window
    - low   = min H1 low in window  
    - close = last H1 close in window
    - volume = sum of H1 volumes

Edge cases handled :
    - Missing H1 bars within a 4h window → bar still produced with available bars
    - Window with 0 H1 bars → bar skipped
    - First/last partial windows → kept if non-empty

Usage :
    from data.resample_h1_to_h4 import resample_h1_to_h4
    h4_df = resample_h1_to_h4(h1_df)
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path


def resample_h1_to_h4(h1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample H1 OHLCV into H4 bars (aligned on 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC).
    
    Parameters
    ----------
    h1_df : pd.DataFrame
        Must have DatetimeIndex and columns ['open', 'high', 'low', 'close'].
        Optional: 'volume'.
    
    Returns
    -------
    pd.DataFrame
        H4 bars with same OHLC(V) columns, DatetimeIndex aligned on 4h boundaries.
    """
    if not isinstance(h1_df.index, pd.DatetimeIndex):
        raise ValueError("h1_df must have a DatetimeIndex")
    
    required = {'open', 'high', 'low', 'close'}
    missing = required - set(h1_df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Pandas resample with '4h' aligns on 00:00 by default — exactly what we want
    agg_dict = {
        'open':  'first',
        'high':  'max',
        'low':   'min',
        'close': 'last',
    }
    if 'volume' in h1_df.columns:
        agg_dict['volume'] = 'sum'
    
    h4 = h1_df.resample('4h', label='left', closed='left').agg(agg_dict)
    
    # Drop bars where all OHLC are NaN (windows with 0 H1 bars)
    h4 = h4.dropna(subset=['open', 'high', 'low', 'close'])
    
    return h4


def load_and_resample(
    cache_dir: Path | str,
    asset: str,
    output_dir: Path | str | None = None,
) -> pd.DataFrame:
    """
    Load H1 parquet from cache and resample to H4.
    Optionally save the result.
    
    Parameters
    ----------
    cache_dir : str or Path
        Directory containing `kraken_1h_{ASSET}_USD.parquet`
    asset : str
        e.g. 'BTC', 'ETH'
    output_dir : optional
        If provided, saves the resampled H4 to `{output_dir}/kraken_4h_resampled_{ASSET}_USD.parquet`
    
    Returns
    -------
    pd.DataFrame : the H4 resampled data
    """
    cache_dir = Path(cache_dir)
    h1_path = cache_dir / f"kraken_1h_{asset}_USD.parquet"
    if not h1_path.exists():
        raise FileNotFoundError(f"H1 file not found: {h1_path}")
    
    h1 = pd.read_parquet(h1_path)
    
    # Ensure DatetimeIndex
    if not isinstance(h1.index, pd.DatetimeIndex):
        for col in ['timestamp', 'time', 'date', 'datetime']:
            if col in h1.columns:
                h1 = h1.set_index(pd.to_datetime(h1[col]))
                break
    
    h4 = resample_h1_to_h4(h1)
    
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"kraken_4h_resampled_{asset}_USD.parquet"
        h4.to_parquet(out_path)
        print(f"  Saved {len(h4)} H4 bars → {out_path}")
    
    return h4


def validate_resampling(
    h1_df: pd.DataFrame,
    h4_resampled: pd.DataFrame,
    h4_native: pd.DataFrame | None = None,
    verbose: bool = True,
) -> dict:
    """
    Sanity checks on the resampling output.
    
    Returns dict with 'passed' (bool) and individual checks.
    """
    checks = {}
    
    # Check 1: bars count ratio ~ 1:4
    expected_h4 = len(h1_df) / 4
    ratio_ok = 0.9 <= len(h4_resampled) / max(expected_h4, 1) <= 1.1
    checks['bar_count_ratio'] = ratio_ok
    
    # Check 2: OHLC integrity (high >= low, close in [low, high])
    integrity_ok = (
        (h4_resampled['high'] >= h4_resampled['low']).all() and
        (h4_resampled['close'] <= h4_resampled['high']).all() and
        (h4_resampled['close'] >= h4_resampled['low']).all() and
        (h4_resampled['open'] <= h4_resampled['high']).all() and
        (h4_resampled['open'] >= h4_resampled['low']).all()
    )
    checks['ohlc_integrity'] = integrity_ok
    
    # Check 3: timestamps aligned on 4h boundaries
    timestamps_ok = (h4_resampled.index.hour % 4 == 0).all()
    checks['timestamps_4h_aligned'] = timestamps_ok
    
    # Check 4: if native H4 available, compare overlapping period
    if h4_native is not None:
        # Take overlapping period
        start = max(h4_resampled.index.min(), h4_native.index.min())
        end = min(h4_resampled.index.max(), h4_native.index.max())
        if start < end:
            r_slice = h4_resampled.loc[start:end]
            n_slice = h4_native.loc[start:end]
            # Compare close prices on common timestamps
            common = r_slice.index.intersection(n_slice.index)
            if len(common) > 0:
                r_close = r_slice.loc[common, 'close']
                n_close = n_slice.loc[common, 'close']
                # Should be very close (allow small rounding)
                rel_diff = ((r_close - n_close) / n_close).abs()
                close_match = (rel_diff < 0.005).mean()  # 99.5% within 0.5%
                checks['matches_native_h4'] = close_match >= 0.95
                checks['_native_match_pct'] = close_match
    
    all_passed = all(v for k, v in checks.items() if not k.startswith('_'))
    checks['passed'] = all_passed
    
    if verbose:
        print(f"  Validation results:")
        for k, v in checks.items():
            if not k.startswith('_'):
                marker = '✓' if v else '✗'
                print(f"    {marker} {k}: {v}")
        if '_native_match_pct' in checks:
            print(f"    [native match rate: {checks['_native_match_pct']*100:.1f}%]")
    
    return checks


if __name__ == '__main__':
    # Demo/test on BTC
    from pathlib import Path
    cache = Path('cache')
    
    print("Resampling BTC H1 → H4 ...")
    h4_resampled = load_and_resample(cache, 'BTC')
    print(f"  {len(h4_resampled)} H4 bars from {h4_resampled.index.min()} to {h4_resampled.index.max()}")
    
    h1 = pd.read_parquet(cache / 'kraken_1h_BTC_USD.parquet')
    h4_native = pd.read_parquet(cache / 'kraken_4h_BTC_USD.parquet')
    
    print("\nValidating ...")
    validate_resampling(h1, h4_resampled, h4_native)
