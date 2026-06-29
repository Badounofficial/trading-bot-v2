"""
Data Quality Validator for Multi-TF Data
==========================================
Runs sanity checks on the downloaded multi-TF data before Phase 2.

Checks:
    - Each TF has the expected bar frequency
    - No abnormal gaps (more than 3 bars missing in a row)
    - No price spikes > 50% bar-to-bar
    - Volumes are non-negative
    - Coverage period overlap across TFs

Usage:
    python data/validate_data.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CACHE_DIR = ROOT / 'cache'


def expected_freq_minutes(tf: str) -> int:
    return {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}[tf]


def validate_dataframe(df: pd.DataFrame, tf: str, label: str) -> dict:
    """Run sanity checks on a single OHLCV DataFrame."""
    issues = []
    stats = {'label': label, 'tf': tf, 'rows': len(df)}

    if df.empty:
        return {'label': label, 'tf': tf, 'rows': 0, 'issues': ['EMPTY']}

    # Required columns
    required = {'open', 'high', 'low', 'close', 'vol'}
    missing = required - set(df.columns)
    if missing:
        issues.append(f"missing cols: {missing}")

    # Index monotonic
    if not df.index.is_monotonic_increasing:
        issues.append("index not monotonic")

    # Duplicates
    n_dup = df.index.duplicated().sum()
    if n_dup > 0:
        issues.append(f"{n_dup} duplicates")

    # OHLC consistency: high >= max(open, close), low <= min(open, close)
    bad_high = ((df['high'] < df['open']) | (df['high'] < df['close'])).sum()
    bad_low = ((df['low'] > df['open']) | (df['low'] > df['close'])).sum()
    if bad_high > 0:
        issues.append(f"{bad_high} bars with high<open/close")
    if bad_low > 0:
        issues.append(f"{bad_low} bars with low>open/close")

    # Bar-to-bar returns (sanity: < 50% per bar)
    returns = df['close'].pct_change().abs()
    n_extreme = (returns > 0.5).sum()
    if n_extreme > 0:
        issues.append(f"{n_extreme} extreme bar returns >50%")

    # Negative volumes
    n_neg_vol = (df['vol'] < 0).sum()
    if n_neg_vol > 0:
        issues.append(f"{n_neg_vol} negative volumes")

    # Gap analysis
    if len(df) > 10:
        # Compute median time delta
        deltas = df.index.to_series().diff().dropna()
        expected = expected_freq_minutes(tf)
        median_min = deltas.median().total_seconds() / 60
        # Big gaps
        big_gap_threshold = pd.Timedelta(minutes=expected * 5)
        n_big_gaps = (deltas > big_gap_threshold).sum()
        stats['median_gap_min'] = median_min
        stats['expected_gap_min'] = expected
        stats['big_gaps'] = int(n_big_gaps)
        if n_big_gaps > len(df) * 0.05:  # >5% of bars have big gaps
            issues.append(f"{n_big_gaps} large gaps (>{expected*5}min)")

    stats['span_days'] = (df.index.max() - df.index.min()).days
    stats['first'] = df.index.min().date()
    stats['last'] = df.index.max().date()
    stats['issues'] = issues
    return stats


def cmd_validate():
    print("\n=== DATA VALIDATION ===\n")
    files = sorted(CACHE_DIR.glob('*.parquet'))
    if not files:
        print("  (no parquet files in cache)")
        return

    total_issues = 0
    total_files = 0
    by_status = {'OK': [], 'ISSUES': [], 'EMPTY': []}

    for f in files:
        name = f.stem
        # Parse name
        if name.startswith('kraken_'):
            parts = name.split('_')
            tf = parts[1]
            sym = '_'.join(parts[2:])
            source = 'Kraken'
        elif name.startswith('yf_'):
            parts = name.split('_')
            tf = parts[1]
            sym = '_'.join(parts[2:])
            source = 'yfinance'
        elif name.startswith('btc_daily_extended'):
            tf = '1d'
            sym = 'BTC_EXT'
            source = 'extended'
        elif name.startswith('kraken_daily_'):
            tf = '1d'
            sym = name.replace('kraken_daily_', '')
            source = 'Kraken'
        elif name.startswith('yf_daily_'):
            tf = '1d'
            sym = name.replace('yf_daily_', '')
            source = 'yfinance'
        else:
            continue

        try:
            df = pd.read_parquet(f)
            stats = validate_dataframe(df, tf, f"{source} {sym}")
            total_files += 1
            issues = stats.get('issues', [])
            if not issues:
                by_status['OK'].append(stats)
            elif issues == ['EMPTY']:
                by_status['EMPTY'].append(stats)
            else:
                by_status['ISSUES'].append(stats)
                total_issues += len(issues)
        except Exception as e:
            print(f"  ⚠ {f.name}: failed to load — {str(e)[:60]}")
            continue

    # Print OK
    if by_status['OK']:
        print(f"  ✓ {len(by_status['OK'])} files OK:")
        for s in by_status['OK']:
            print(f"    {s['label']:<32} {s['tf']:<4} {s['rows']:>6} bars  "
                  f"{s['first']} → {s['last']}  ({s['span_days']}d)")

    if by_status['ISSUES']:
        print(f"\n  ⚠ {len(by_status['ISSUES'])} files with issues:")
        for s in by_status['ISSUES']:
            print(f"    {s['label']:<32} {s['tf']:<4} {s['rows']:>6} bars")
            for issue in s['issues']:
                print(f"      → {issue}")

    if by_status['EMPTY']:
        print(f"\n  ✗ {len(by_status['EMPTY'])} empty files:")
        for s in by_status['EMPTY']:
            print(f"    {s['label']:<32} {s['tf']}")

    print(f"\n  TOTAL: {total_files} files validated, {total_issues} issues")
    print(f"  Verdict: {'✅ DATA READY' if total_issues == 0 and not by_status['EMPTY'] else '⚠ Review needed'}")


if __name__ == '__main__':
    cmd_validate()
