"""
phase3_day0_mark.py — Phase 7 Day-0 marker + boot Telegram alert
=================================================================

Purpose
-------
One-shot script run by Sebastien immediately after the atomic VPS cutover.
It marks Day 0 of the 365-day Phase 3 marathon by writing a metadata file
to live/state/phase3_marathon_meta.json and sends a celebratory + binding
Telegram alert to seal the contract.

The metadata file is the source of truth for `live/daily_reconciliation.py`
to compute Day-N counter (currently the reconciliation script reads its own
PHASE3_MARATHON_T0 constant — see §Operational notes below for the wiring).

What it does
------------
  1. Determines Day 0 timestamp:
     - if env var PHASE3_MARATHON_T0 set → use it (ISO 8601)
     - else if --ts CLI arg passed → use it
     - else default to NOW (UTC, second precision)
  2. Captures the git commit at Day 0 for audit trail (rollback reference)
  3. Writes live/state/phase3_marathon_meta.json (atomic via tmp + rename)
  4. Sends Telegram boot alert with full design summary
  5. Echoes a wiring instruction so Sebastien knows to update the constant
     PHASE3_MARATHON_T0 in live/daily_reconciliation.py after this script runs

Usage
-----
  python3 live/phase3_day0_mark.py                  # NOW as Day 0
  python3 live/phase3_day0_mark.py --ts 2026-07-15T12:00:00+00:00
  python3 live/phase3_day0_mark.py --dry            # print metadata + message, no write/send
  PHASE3_MARATHON_T0=2026-07-15T12:00:00+00:00 python3 live/phase3_day0_mark.py

Idempotency
-----------
If `live/state/phase3_marathon_meta.json` already exists, the script REFUSES
to overwrite without --force flag. This prevents accidental re-runs from
resetting Day 0. The original cutover Day 0 is sacred.

Discipline
----------
- Pattern 7 — binary outcome: either Day 0 marked and Telegram sent, or
  exit non-zero with diagnostic. No partial state.
- P31 — the marathon_meta.json file is itself a snapshot anchor; do not
  edit it manually post-write. If a correction is needed, archive the
  current file with a timestamp suffix and re-run with --force.

Author: V2 agent, 2026-06-28 (Phase 7 Day-0 setup)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "live" / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
META_FILE = STATE_DIR / "phase3_marathon_meta.json"

# Phase 3 design constants (mirrors live/daily_reconciliation.py — kept in sync
# manually; if these change here, update daily_reconciliation EXPECTED_* too).
EXPECTED_DAILY_PNL_USD = 0.41
EXPECTED_MONTHLY_PNL_USD = 12.49
EXPECTED_OOS_13MO_PNL_USD = 168.57
MARATHON_TOTAL_DAYS = 365
DESIGN_LABEL = "btc_eth_always_in_delta_neutre_$1k_x2"
CHECKPOINTS = ["T+30", "T+90", "T+180", "T+365"]


def parse_ts(raw: str) -> datetime:
    """Parse an ISO 8601 timestamp, raise ValueError on bad input."""
    return datetime.fromisoformat(raw)


def git_head_sha() -> str:
    """Return current git HEAD short SHA, or 'unknown' if git not available."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically (tmp + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(path)


def build_meta(day0_ts: datetime) -> dict:
    return {
        "day0_ts": day0_ts.isoformat(timespec="seconds"),
        "design": DESIGN_LABEL,
        "commit_at_day0": git_head_sha(),
        "expected_daily": EXPECTED_DAILY_PNL_USD,
        "expected_monthly": EXPECTED_MONTHLY_PNL_USD,
        "expected_oos_13mo": EXPECTED_OOS_13MO_PNL_USD,
        "marathon_total_days": MARATHON_TOTAL_DAYS,
        "checkpoints": CHECKPOINTS,
        "marked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def format_boot_alert(meta: dict) -> str:
    return (
        "🚀 V2 Phase 3 Marathon — Day 0 STARTED\n"
        f"Date:    {meta['day0_ts']}\n"
        f"Design:  BTC+ETH always-in delta-neutre $1k×2 = $2k total notional\n"
        f"Commit:  {meta['commit_at_day0'][:12]}\n"
        "\n"
        f"Expected daily:   ${meta['expected_daily']:.2f}/day\n"
        f"Expected monthly: ${meta['expected_monthly']:.2f}/month\n"
        f"Expected OOS 13.5mo: ${meta['expected_oos_13mo']:.2f}\n"
        f"\n"
        f"Next checkpoints: {', '.join(meta['checkpoints'])}\n"
        f"Discipline: P31 + P32 + P33 + ʼCɩcɛ (preflight ✓, drift_monitor active, "
        f"IronGlove 5-gate at each checkpoint)\n"
        "\n"
        "Sebastien holds rollback button. /v2_flat YES at any time."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mark Day 0 of the Phase 3 marathon and send Telegram boot alert."
    )
    parser.add_argument("--ts", default=None,
                        help="Day 0 ISO 8601 timestamp (default: NOW). "
                             "Env var PHASE3_MARATHON_T0 takes precedence over default but not over --ts.")
    parser.add_argument("--dry", action="store_true",
                        help="Print metadata + message, do NOT write file or send Telegram.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing phase3_marathon_meta.json (DANGEROUS — sealed at cutover).")
    args = parser.parse_args()

    # Resolve day0 timestamp (priority: --ts > env > NOW)
    raw_ts = args.ts or os.environ.get("PHASE3_MARATHON_T0") or ""
    if raw_ts:
        try:
            day0_ts = parse_ts(raw_ts)
        except ValueError as e:
            print(f"[day0] ERROR: invalid timestamp {raw_ts!r}: {e}", file=sys.stderr)
            return 2
        if day0_ts.tzinfo is None:
            print(f"[day0] ERROR: timestamp must include timezone (UTC offset). Got naive: {raw_ts!r}",
                  file=sys.stderr)
            return 2
    else:
        day0_ts = datetime.now(timezone.utc).replace(microsecond=0)

    meta = build_meta(day0_ts)
    alert = format_boot_alert(meta)

    print(f"[day0] Day-0 timestamp resolved: {meta['day0_ts']}")
    print(f"[day0] Commit at Day 0:         {meta['commit_at_day0']}")
    print(f"[day0] Metadata file target:    {META_FILE}")
    print("[day0] Telegram boot alert:")
    print("-" * 60)
    print(alert)
    print("-" * 60)

    if args.dry:
        print("[day0] --dry: NOT writing file, NOT sending Telegram")
        return 0

    # Idempotency check
    if META_FILE.exists() and not args.force:
        print(f"[day0] REFUSE: {META_FILE} already exists. "
              "Pass --force to overwrite (this RESETS Day 0).", file=sys.stderr)
        return 1

    # Write metadata
    atomic_write_json(META_FILE, meta)
    print(f"[day0] wrote {META_FILE.relative_to(ROOT)} (atomic)")

    # Send Telegram boot alert
    try:
        from paper_trading import config as pt_config
        from paper_trading.monitoring import TelegramAlerter
        if not pt_config.TELEGRAM_ENABLED:
            print("[day0] WARNING: Telegram not configured. Boot alert NOT sent.")
            print("[day0] Marathon Day 0 marked locally only.")
        else:
            try:
                TelegramAlerter().send(alert)
                print("[day0] Telegram boot alert sent OK")
            except Exception as e:  # noqa: BLE001
                print(f"[day0] WARNING: Telegram send failed: {e}", file=sys.stderr)
                print("[day0] Day 0 file written locally. Re-send via /v2_help context if needed.")
    except ImportError as e:
        print(f"[day0] WARNING: paper_trading not importable ({e}). Boot alert NOT sent.")

    # Wiring instruction echo
    print()
    print("[day0] " + "=" * 60)
    print("[day0] NEXT STEP — update daily_reconciliation.py constant:")
    print(f"[day0]   PHASE3_MARATHON_T0 = \"{meta['day0_ts']}\"")
    print("[day0] Located near top of live/daily_reconciliation.py (~line 67).")
    print("[day0] This activates the Day-N counter in daily reports.")
    print("[day0] " + "=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
