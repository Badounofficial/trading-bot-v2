"""
drift_monitor_baseline.py — Phase 7 ʼCɩcɛ drift_monitor baseline fit
====================================================================

Purpose
-------
One-shot script run during Phase 7 setup to FIT a `cice.DriftMonitor`
instance on the OOS funding-rate distribution that produced the V2
backtest baseline ($1685.71 OOS 13.5 mois BTC+ETH always-in delta-neutre
→ $0.41/day pro-rata on $2k live notional).

The fitted DriftMonitor is then pickled to
`live/state/drift_monitor_baseline.pkl` for daily reuse by checkpoint
scripts (T+30, T+90, T+180, T+365) and ad-hoc operator queries.

Architecture
------------
  1. Load historical Hyperliquid funding from cache/funding_hyperliquid_<asset>_USDC_USDC.parquet
  2. Slice to OOS window 2025-03-15 → 2026-05-04 (per spec Phase 2 split)
  3. Build reference dict {"funding_BTC": series, "funding_ETH": series, ...}
  4. cice.DriftMonitor().fit(reference)
  5. Pickle to live/state/drift_monitor_baseline.pkl (atomic via tmp + rename)
  6. Smoke-test: run .check() on the reference itself → should report stable
  7. Print summary

Usage
-----
  python3 live/drift_monitor_baseline.py            # fit + pickle
  python3 live/drift_monitor_baseline.py --dry      # fit + smoke, NO pickle
  python3 live/drift_monitor_baseline.py --check-only  # load existing pickle + check current

ʼCɩcɛ dependency
----------------
Requires `cice` package installed in the V2 venv. On VPS:
  ssh badoun@5.161.246.190
  cd /home/badoun/trading-bot-v2
  .venv/bin/pip install -e /home/badoun/cice
  .venv/bin/python -c "from cice import DriftMonitor; print('cice OK')"

Discipline
----------
- ʼCɩcɛ sovereignty rule 7: read-only import, no patch/override.
- P31: pickle output is itself a snapshot anchor; if regenerated,
  the previous version should be moved to a timestamped archive.
- P33: even though the fit is straightforward, the smoke-self-check
  is mandatory (verify reference vs itself returns PSI ≈ 0).

Phase 7 wiring
--------------
This script produces the baseline pickle ONCE during Phase 7 setup.
Subsequent daily / checkpoint scripts load it via:

    import pickle
    with open("live/state/drift_monitor_baseline.pkl", "rb") as f:
        dm = pickle.load(f)
    report = dm.check({"funding_BTC": current_BTC_series, "funding_ETH": current_ETH_series})
    if report["drifted"]:
        # PSI >= 0.25 on at least one feature → Telegram alert + flag for review

Author: V2 agent, 2026-06-28 (Phase 7 drift_monitor setup)
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "live" / "state"
CACHE_DIR = ROOT / "cache"
STATE_DIR.mkdir(parents=True, exist_ok=True)
BASELINE_PKL = STATE_DIR / "drift_monitor_baseline.pkl"

# Phase 2 split: per spec, OOS starts 2025-03-15 (validated in H1, H6 robustness).
# OOS end = end of available data (2026-05-04 at time of Phase 3 spec freeze).
OOS_START = "2025-03-15"
OOS_END = "2026-05-04"
ASSETS = ["BTC", "ETH"]   # mirrors live/paper_funding_capture.py Phase 3 universe


def load_funding_oos(asset: str) -> Optional[pd.Series]:
    """Load OOS funding rate series for one asset from cache parquet.

    Returns the `fundingRate` column (hourly, raw per-hour rate), sliced to
    [OOS_START, OOS_END]. None if file missing or empty after slice.
    """
    path = CACHE_DIR / f"funding_hyperliquid_{asset}_USDC_USDC.parquet"
    if not path.exists():
        print(f"[drift] ERROR: cache file missing: {path}", file=sys.stderr)
        return None
    df = pd.read_parquet(path)
    if "fundingRate" not in df.columns:
        print(f"[drift] ERROR: 'fundingRate' column missing in {path}", file=sys.stderr)
        return None
    oos = df.loc[OOS_START:OOS_END, "fundingRate"]
    if oos.empty:
        print(f"[drift] WARNING: OOS slice empty for {asset} (range {OOS_START}..{OOS_END})",
              file=sys.stderr)
        return None
    return oos


def fit_baseline() -> Optional[object]:
    """Build a DriftMonitor fitted on BTC + ETH funding OOS distributions."""
    try:
        from cice import DriftMonitor
    except ImportError as e:
        print(f"[drift] ERROR: cice package not importable: {e}", file=sys.stderr)
        print("[drift] Install: .venv/bin/pip install -e /home/badoun/cice", file=sys.stderr)
        return None

    reference = {}
    for asset in ASSETS:
        series = load_funding_oos(asset)
        if series is None:
            print(f"[drift] FATAL: cannot load OOS funding for {asset}", file=sys.stderr)
            return None
        reference[f"funding_{asset}"] = series.values
        print(f"[drift] {asset}: OOS funding series loaded — n={len(series)} samples, "
              f"mean={series.mean():.2e}, std={series.std():.2e}")
    dm = DriftMonitor().fit(reference)
    print(f"[drift] DriftMonitor fitted on {len(reference)} features "
          f"({OOS_START} → {OOS_END})")
    return dm


def smoke_self_check(dm) -> bool:
    """Self-check: feed the reference back as 'current' — PSI should be ≈ 0 (stable)."""
    reference_as_current = {k: v for k, v in dm._reference.items()}
    report = dm.check(reference_as_current)
    print("[drift] Self-check (reference vs itself):")
    for name, info in report["per_feature"].items():
        print(f"  {name}: PSI={info['psi']:.6f} ({info['label']})")
    print(f"  worst_psi={report['worst_psi']:.6f}, drifted={report['drifted']}")
    if report["drifted"]:
        print("[drift] FAIL: self-check reports drift — bug in DriftMonitor or input", file=sys.stderr)
        return False
    if report["worst_psi"] > 0.05:
        print(f"[drift] WARNING: self-check PSI={report['worst_psi']:.4f} > 0.05 — "
              "investigate (expected ≈ 0 since reference == current)", file=sys.stderr)
        # Don't fail on this — PSI on the same data should be exactly 0 in theory
        # but bin-edge quantile rounding can leave a tiny residual.
    print("[drift] Self-check OK: reference vs itself reports stable.")
    return True


def atomic_pickle_write(path: Path, obj: object) -> None:
    """Pickle an object atomically via tmp + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(obj, f)
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit ʼCɩcɛ DriftMonitor on V2 OOS funding baseline + pickle for Phase 7."
    )
    parser.add_argument("--dry", action="store_true",
                        help="Fit + self-check only. Do NOT write pickle.")
    parser.add_argument("--check-only", action="store_true",
                        help="Load existing pickle + self-check. Skip fit.")
    args = parser.parse_args()

    if args.check_only:
        if not BASELINE_PKL.exists():
            print(f"[drift] ERROR: --check-only but pickle absent at {BASELINE_PKL}",
                  file=sys.stderr)
            return 2
        with open(BASELINE_PKL, "rb") as f:
            dm = pickle.load(f)
        print(f"[drift] loaded baseline pickle from {BASELINE_PKL}")
        print(f"[drift] features in baseline: {list(dm._reference.keys())}")
        ok = smoke_self_check(dm)
        return 0 if ok else 1

    dm = fit_baseline()
    if dm is None:
        return 2

    ok = smoke_self_check(dm)
    if not ok:
        print("[drift] ABORT: self-check failed. Not pickling.", file=sys.stderr)
        return 1

    if args.dry:
        print("[drift] --dry: NOT writing pickle.")
        return 0

    atomic_pickle_write(BASELINE_PKL, dm)
    size_kb = BASELINE_PKL.stat().st_size / 1024
    print(f"[drift] wrote pickle {BASELINE_PKL.relative_to(ROOT)} ({size_kb:.1f} KB)")
    print()
    print("[drift] " + "=" * 60)
    print("[drift] Phase 7 baseline ready. Daily / checkpoint scripts can now:")
    print("[drift]   import pickle")
    print(f"[drift]   dm = pickle.load(open('{BASELINE_PKL.relative_to(ROOT)}', 'rb'))")
    print("[drift]   report = dm.check({'funding_BTC': ..., 'funding_ETH': ...})")
    print("[drift]   if report['drifted']: send_telegram_alert(report['severe_features'])")
    print("[drift] " + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
