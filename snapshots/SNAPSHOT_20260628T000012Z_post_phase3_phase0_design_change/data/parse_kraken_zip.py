"""
Kraken Historical ZIP Parser
==============================
Parses the Kraken historical OHLCVT data dump (downloaded from Google Drive)
into parquet files compatible with our existing pipeline.

Kraken's historical ZIP structure:
    Kraken_OHLCVT.zip
    ├── XBTUSD_1.csv        (BTC/USD 1-minute)
    ├── XBTUSD_5.csv        (BTC/USD 5-minute)
    ├── XBTUSD_15.csv
    ├── XBTUSD_60.csv       (BTC/USD 1-hour)
    ├── XBTUSD_240.csv      (BTC/USD 4-hour)
    ├── XBTUSD_1440.csv     (BTC/USD daily)
    ├── ETHUSD_60.csv
    └── ... (hundreds of files)

CSV format (no header):
    unix_timestamp, open, high, low, close, volume, trades_count

Kraken's symbol naming quirks:
    - BTC is called XBT internally → XBTUSD = BTC/USD
    - Other major coins use normal tickers: ETHUSD, SOLUSD, ADAUSD, etc.

Usage:
    # After downloading and placing ZIP at ~/Downloads/Kraken_OHLCVT.zip:
    python data/parse_kraken_zip.py ~/Downloads/Kraken_OHLCVT.zip

    # Or process an already-extracted folder:
    python data/parse_kraken_zip.py /path/to/extracted/folder --extracted
"""
from __future__ import annotations
import sys
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / 'cache'

# Symbols we want to extract (with Kraken's internal naming)
# Kraken's quirks:
#   - BTC = XBT internally (XBTUSD = BTC/USD)
#   - DOGE only paired with EUR on Kraken (no DOGEUSD), so excluded
SYMBOLS_TO_EXTRACT = {
    'XBTUSD': 'BTC_USD',
    'ETHUSD': 'ETH_USD',
    'SOLUSD': 'SOL_USD',
    'ADAUSD': 'ADA_USD',
    'LINKUSD': 'LINK_USD',
    'DOTUSD': 'DOT_USD',
    'AVAXUSD': 'AVAX_USD',
    'LTCUSD': 'LTC_USD',
}

# Timeframes we want (in minutes, as Kraken names them)
TIMEFRAMES_TO_EXTRACT = {
    '60': '1h',
    '240': '4h',
    '1440': '1d',
}


def parse_kraken_csv(csv_path: Path) -> pd.DataFrame:
    """Parse a single Kraken OHLCVT CSV file."""
    df = pd.read_csv(
        csv_path,
        header=None,
        names=['ts', 'open', 'high', 'low', 'close', 'vol', 'trades'],
    )
    if df.empty:
        return pd.DataFrame()
    df['datetime'] = pd.to_datetime(df['ts'], unit='s')
    df = df.set_index('datetime').sort_index()
    df = df[['open', 'high', 'low', 'close', 'vol']]
    df = df[~df.index.duplicated(keep='first')]
    return df


def process_zip(zip_path: Path):
    """Process a Kraken historical ZIP file."""
    CACHE_DIR.mkdir(exist_ok=True)
    
    if not zip_path.exists():
        print(f"⚠ ZIP not found: {zip_path}")
        return
    
    print(f"\nOpening ZIP: {zip_path}")
    print(f"Size: {zip_path.stat().st_size / 1e9:.2f} GB\n")
    
    matches_found = 0
    matches_saved = 0
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        all_names = z.namelist()
        print(f"Total files in ZIP: {len(all_names)}")
        
        # Build a list of files we want
        wanted = []
        for kraken_sym, our_sym in SYMBOLS_TO_EXTRACT.items():
            for kraken_tf, our_tf in TIMEFRAMES_TO_EXTRACT.items():
                # Look for files like "XBTUSD_60.csv" in the ZIP
                target = f"{kraken_sym}_{kraken_tf}.csv"
                # Match exact name or with subfolder prefix
                for name in all_names:
                    if name.endswith(target) or name == target:
                        wanted.append({
                            'zip_name': name,
                            'kraken_sym': kraken_sym,
                            'our_sym': our_sym,
                            'kraken_tf': kraken_tf,
                            'our_tf': our_tf,
                        })
                        break
        
        if not wanted:
            print(f"⚠ No matching files found! Symbols expected: {list(SYMBOLS_TO_EXTRACT.keys())}")
            # Show sample of what IS in the ZIP for debugging
            sample = [n for n in all_names if n.endswith('.csv')][:20]
            print(f"\nSample of CSV files in ZIP:")
            for s in sample:
                print(f"  {s}")
            return
        
        print(f"Found {len(wanted)} matching files (out of "
              f"{len(SYMBOLS_TO_EXTRACT) * len(TIMEFRAMES_TO_EXTRACT)} expected)\n")
        
        matches_found = len(wanted)
        
        for item in wanted:
            target_path = CACHE_DIR / f"kraken_{item['our_tf']}_{item['our_sym']}.parquet"
            print(f"  Processing {item['zip_name']} → kraken_{item['our_tf']}_{item['our_sym']}.parquet")
            
            # Extract CSV to memory and parse
            try:
                with z.open(item['zip_name']) as f:
                    df = pd.read_csv(
                        f, header=None,
                        names=['ts', 'open', 'high', 'low', 'close', 'vol', 'trades'],
                    )
                if df.empty:
                    print(f"    ⚠ empty file")
                    continue
                df['datetime'] = pd.to_datetime(df['ts'], unit='s')
                df = df.set_index('datetime').sort_index()
                df = df[['open', 'high', 'low', 'close', 'vol']]
                df = df[~df.index.duplicated(keep='first')]
                df.to_parquet(target_path)
                span_days = (df.index.max() - df.index.min()).days
                print(f"    ✓ {len(df):,} bars  "
                      f"{df.index.min().date()} → {df.index.max().date()}  ({span_days}d)")
                matches_saved += 1
            except Exception as e:
                print(f"    ⚠ error: {str(e)[:80]}")
    
    print(f"\n{'='*70}")
    print(f"SUMMARY: {matches_saved}/{matches_found} files processed successfully")
    print(f"{'='*70}\n")


def process_folder(folder_path: Path):
    """Process an already-extracted folder of CSV files."""
    CACHE_DIR.mkdir(exist_ok=True)
    
    if not folder_path.exists():
        print(f"⚠ Folder not found: {folder_path}")
        return
    
    print(f"\nScanning folder: {folder_path}\n")
    
    matches_saved = 0
    for kraken_sym, our_sym in SYMBOLS_TO_EXTRACT.items():
        for kraken_tf, our_tf in TIMEFRAMES_TO_EXTRACT.items():
            target = folder_path / f"{kraken_sym}_{kraken_tf}.csv"
            if not target.exists():
                # Try recursive search
                matches = list(folder_path.rglob(f"{kraken_sym}_{kraken_tf}.csv"))
                if not matches:
                    print(f"  ⚠ Not found: {kraken_sym}_{kraken_tf}.csv")
                    continue
                target = matches[0]
            
            target_parquet = CACHE_DIR / f"kraken_{our_tf}_{our_sym}.parquet"
            print(f"  {target.name} → kraken_{our_tf}_{our_sym}.parquet")
            try:
                df = parse_kraken_csv(target)
                if df.empty:
                    print(f"    ⚠ empty file")
                    continue
                df.to_parquet(target_parquet)
                span_days = (df.index.max() - df.index.min()).days
                print(f"    ✓ {len(df):,} bars  "
                      f"{df.index.min().date()} → {df.index.max().date()}  ({span_days}d)")
                matches_saved += 1
            except Exception as e:
                print(f"    ⚠ error: {str(e)[:80]}")
    
    print(f"\nSaved {matches_saved} parquet files to {CACHE_DIR}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print(f"  python {sys.argv[0]} <path-to-zip>           # process ZIP")
        print(f"  python {sys.argv[0]} <path-to-folder> --extracted  # process extracted folder")
        sys.exit(1)
    
    path = Path(sys.argv[1]).expanduser().resolve()
    is_extracted = '--extracted' in sys.argv
    
    if is_extracted or path.is_dir():
        process_folder(path)
    else:
        process_zip(path)


if __name__ == '__main__':
    main()
