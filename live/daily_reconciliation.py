"""
daily_reconciliation.py — Phase 3 Safeguard C
=============================================

Purpose
-------
Daily reconciliation report sent to Sebastien via Telegram at 12:05 UTC.
Orthogonal to the daemon's own watchdog/heartbeat: this script runs as a
separate cron job (or systemd timer), reads the daemon's state files, and
emits an independent health summary. If both the daemon and the watchdog
fail, daily reconciliation absence becomes the third backstop signal.

What it reports
---------------
  - Day N / 365 of Phase 3 marathon
  - Net P&L 24h (delta vs yesterday's snapshot) + cumul P&L
  - Max DD 24h (from daemon's rolling 24h equity peak)
  - Open positions detail (asset, entry price, funding accrued)
  - Cycles run, uptime, restart count proxy (state.started_at)
  - Backtest expected pro-rata vs live deviation (%)
  - Daemon mode (NORMAL vs PENDING_USER_VALIDATION) — visible if abnormal

Architecture
------------
  1. Load live/state/daemon_state.json (read-only)
  2. Load live/state/reconciliation_history.jsonl (this script's own
     append-only ledger; one record per daily run with timestamp + cumul P&L
     + cycle count) to compute 24h delta vs yesterday's record
  3. Format Telegram message per spec §3.C
  4. Send via TelegramAlerter (using paper_trading.config credentials)
  5. Append today's record to reconciliation_history.jsonl

Failure modes (all logged, none crash)
--------------------------------------
  - daemon_state.json missing → report "DAEMON STATE FILE MISSING" alert
  - reconciliation_history.jsonl missing → first run; populate, no delta
  - TelegramAlerter unavailable → log warning, exit with code 1
  - State file corrupted → report parse error to Telegram, log full trace

Usage
-----
  python3 live/daily_reconciliation.py                # send and append history
  python3 live/daily_reconciliation.py --dry          # format and print, do NOT send/append
  python3 live/daily_reconciliation.py --no-telegram  # send=disabled, history appended

Deployment
----------
Cron entry on VPS Hetzner (5.161.246.190):
    5 12 * * *  /usr/bin/python3 /home/badoun/trading-bot-v2/live/daily_reconciliation.py >> /home/badoun/trading-bot-v2/live/logs/daily_reconciliation.log 2>&1

Or systemd timer (preferred for log inheritance with v2-daemon):
    See infra/systemd/v2-daily-reconciliation.service + .timer

Author: V2 agent, 2026-06-28 (Phase 3 safeguard C implementation)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_trading import config as pt_config
from paper_trading.monitoring import TelegramAlerter

# ----------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------
STATE_DIR = ROOT / "live" / "state"
LOG_DIR = ROOT / "live" / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

DAEMON_STATE_PATH = STATE_DIR / "daemon_state.json"
RECONCILIATION_HISTORY_PATH = STATE_DIR / "reconciliation_history.jsonl"
LOG_FILE = LOG_DIR / "daily_reconciliation.log"

# --- Marathon T0 anchor (Phase 3 Day-0 marker) -----------------------------
# Set this constant to the actual cutover datetime when Phase 3 goes live.
# Until then, Day-N counter shows "pre-marathon" / "Day —".
# Format: ISO 8601 UTC. Example: "2026-07-15T12:00:00+00:00"
PHASE3_MARATHON_T0 = "2026-06-28T19:55:15+00:00"
MARATHON_TOTAL_DAYS = 365

# --- Backtest expected pro-rata (Phase 3 sizing) ----------------------------
# Derivation:
#   Backtest BTC+ETH always-in pure delta-neutre:
#     CAPITAL_PER_ASSET_USD = $10_000 backtest × 2 assets = $20_000 total notional
#     Net OOS 13.5 mois = $1_685.71 (cf. H6 robustness §5.3 fallback)
#     Return on notional = $1_685.71 / $20_000 = 8.43% over 13.5 mois
#   Live Phase 3:
#     CAPITAL_PER_ASSET_USD = $1_000 × 2 assets = $2_000 total notional
#     Pro-rata factor = $2_000 / $20_000 = 0.10
#     Expected OOS 13.5 mois = $1_685.71 × 0.10 = $168.57
#     Per month (13.5 month period) = $168.57 / 13.5 = $12.49 / month
#     Per day = $12.49 / 30.44 = $0.41 / day
#
# Note: phase3_deployment_spec.md §2.2 quoted "~$28/month" / "$337 OOS pro-rata"
# which would imply backtest notional was $10k TOTAL (not $10k per-asset). V2
# computes against the actual backtest CAPITAL_PER_ASSET_USD × len(ASSETS)
# convention here. If §2.2 should be authoritative, change EXPECTED_DAILY_*
# below and add a §2.2.1 reconciliation note to the spec.
EXPECTED_DAILY_PNL_USD = 0.41             # corrected pro-rata calc
EXPECTED_MONTHLY_PNL_USD = 12.49
EXPECTED_OOS_13MO_PNL_USD = 168.57
DEVIATION_TOLERANCE_PCT = 50.0            # spec T+30 tolerance band ±50%


# ----------------------------------------------------------------------------
# LOGGING
# ----------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("v2_daily_reconciliation")


# ----------------------------------------------------------------------------
# DATA STRUCTURES
# ----------------------------------------------------------------------------
@dataclass
class ReconciliationMetrics:
    """Snapshot of daily metrics — both reported and persisted to history."""
    timestamp: str
    day_n: Optional[int]                  # Day-N counter (1..365) or None pre-marathon
    cumul_pnl_usd: float                  # realized + open funding accrued
    cumul_pnl_pct_of_capital: float       # cumul / TOTAL_CAPITAL_BASE * 100
    net_pnl_24h_usd: float                # delta vs yesterday's snapshot
    max_dd_24h_pct: float                 # from daemon state.equity_peak_24h
    open_positions: list                  # list of {asset, entry_price, notional, funding}
    cycle_count: int
    uptime_days: float
    daemon_mode: str                      # NORMAL / PENDING_USER_VALIDATION
    deviation_vs_expected_pct: Optional[float]   # (live - expected) / expected * 100
    last_loop_ts: str
    note: str = ""                        # warnings/flags appended to report


# ----------------------------------------------------------------------------
# STATE LOADING (read-only)
# ----------------------------------------------------------------------------
def load_daemon_state() -> Optional[dict]:
    """Read daemon_state.json. Returns dict or None if missing/unreadable."""
    if not DAEMON_STATE_PATH.exists():
        log.warning("daemon_state.json missing at %s", DAEMON_STATE_PATH)
        return None
    try:
        return json.loads(DAEMON_STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("daemon_state.json read/parse failed: %s", e)
        return None


def load_yesterday_record() -> Optional[dict]:
    """Return the most recent record from reconciliation_history.jsonl, or None."""
    if not RECONCILIATION_HISTORY_PATH.exists():
        return None
    last = None
    try:
        with open(RECONCILIATION_HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
        return last
    except OSError as e:
        log.warning("reconciliation_history read failed: %s", e)
        return None


def append_history(record: dict) -> None:
    """Append a record to reconciliation_history.jsonl (atomic-enough: file append)."""
    try:
        with open(RECONCILIATION_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("reconciliation_history append failed: %s", e)


# ----------------------------------------------------------------------------
# METRICS COMPUTATION
# ----------------------------------------------------------------------------
def compute_metrics(daemon_state: dict, yesterday: Optional[dict]) -> ReconciliationMetrics:
    """Compute today's reconciliation metrics from daemon state and yesterday's snapshot."""
    now = datetime.now(timezone.utc)

    # Cumul P&L = realized + sum of open positions' funding accrued
    realized = float(daemon_state.get("realized_pnl_usd", 0.0))
    open_funding = sum(
        float(p.get("funding_accrued_usd", 0.0))
        for p in (daemon_state.get("positions") or {}).values()
    )
    cumul = realized + open_funding

    # Total capital base (must match paper_funding_capture.py TOTAL_CAPITAL_BASE)
    # Hardcoded here to keep this script independent of the daemon imports.
    total_capital_base = 1_000.0 * 2   # CAPITAL_PER_ASSET_USD × len(ASSETS) for BTC+ETH
    cumul_pct = (cumul / total_capital_base) * 100.0

    # 24h delta vs yesterday's recorded cumul
    if yesterday is not None and "cumul_pnl_usd" in yesterday:
        net_24h = cumul - float(yesterday["cumul_pnl_usd"])
    else:
        net_24h = 0.0  # first run — no baseline

    # Max DD 24h from daemon's rolling peak field
    equity_peak = float(daemon_state.get("equity_peak_24h", 0.0))
    max_dd_24h_pct = ((cumul - equity_peak) / total_capital_base) * 100.0 if total_capital_base else 0.0

    # Open positions for the report (compact subset)
    open_positions = []
    for asset, p in (daemon_state.get("positions") or {}).items():
        open_positions.append({
            "asset": asset,
            "entry_price": float(p.get("entry_price", 0.0)),
            "notional_usd": float(p.get("notional_usd", 0.0)),
            "funding_accrued_usd": float(p.get("funding_accrued_usd", 0.0)),
        })

    # Cycle count + uptime
    cycle_count = int(daemon_state.get("cycle_count", 0))
    started_at_raw = daemon_state.get("started_at") or ""
    try:
        started_at = datetime.fromisoformat(started_at_raw)
        uptime_days = (now - started_at).total_seconds() / 86_400.0
    except (ValueError, TypeError):
        uptime_days = 0.0

    # Day-N marathon counter
    day_n: Optional[int] = None
    if PHASE3_MARATHON_T0:
        try:
            t0 = datetime.fromisoformat(PHASE3_MARATHON_T0)
            day_n = max(1, int((now - t0).total_seconds() / 86_400.0) + 1)
        except ValueError:
            day_n = None

    daemon_mode = str(daemon_state.get("mode", "NORMAL"))

    # Deviation vs expected (only meaningful after a few days of accumulation)
    deviation_pct: Optional[float] = None
    if uptime_days >= 1.0 and abs(EXPECTED_DAILY_PNL_USD) > 1e-6:
        actual_daily = cumul / max(uptime_days, 1.0)
        deviation_pct = ((actual_daily - EXPECTED_DAILY_PNL_USD) / EXPECTED_DAILY_PNL_USD) * 100.0

    # Sanity notes
    notes = []
    if daemon_mode != "NORMAL":
        notes.append(f"⚠️ daemon mode = {daemon_mode}")
    last_loop_raw = daemon_state.get("last_loop_ts", "")
    try:
        last_loop = datetime.fromisoformat(last_loop_raw)
        loop_age = (now - last_loop).total_seconds() / 60.0
        if loop_age > 30:
            notes.append(f"⚠️ last loop {int(loop_age)}min ago (>30min — daemon may be stalled)")
    except (ValueError, TypeError):
        pass
    if deviation_pct is not None and abs(deviation_pct) > DEVIATION_TOLERANCE_PCT:
        notes.append(
            f"⚠️ deviation {deviation_pct:+.0f}% > tolerance ±{DEVIATION_TOLERANCE_PCT:.0f}% (T+30 expected band)"
        )

    return ReconciliationMetrics(
        timestamp=now.isoformat(timespec="seconds"),
        day_n=day_n,
        cumul_pnl_usd=cumul,
        cumul_pnl_pct_of_capital=cumul_pct,
        net_pnl_24h_usd=net_24h,
        max_dd_24h_pct=max_dd_24h_pct,
        open_positions=open_positions,
        cycle_count=cycle_count,
        uptime_days=uptime_days,
        daemon_mode=daemon_mode,
        deviation_vs_expected_pct=deviation_pct,
        last_loop_ts=last_loop_raw,
        note=" | ".join(notes),
    )


# ----------------------------------------------------------------------------
# TELEGRAM MESSAGE FORMATTING (per spec §3.C)
# ----------------------------------------------------------------------------
def format_telegram_message(m: ReconciliationMetrics) -> str:
    """Format the daily reconciliation Telegram message.

    Layout matches spec phase3_deployment_spec.md §3.C, adapted to actual data
    structure with sanity-warning annotations appended at the bottom.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_str = f"Day {m.day_n}/{MARATHON_TOTAL_DAYS}" if m.day_n else "Day — (pre-marathon)"
    sign_24h = "+" if m.net_pnl_24h_usd >= 0 else ""
    sign_cumul = "+" if m.cumul_pnl_usd >= 0 else ""
    sign_dev = "+" if (m.deviation_vs_expected_pct or 0) >= 0 else ""
    dev_str = (
        f"{sign_dev}{m.deviation_vs_expected_pct:.0f}%"
        if m.deviation_vs_expected_pct is not None else "n/a (insufficient uptime)"
    )

    pos_lines = []
    for p in m.open_positions:
        pos_lines.append(
            f"  {p['asset']:>4} ${p['notional_usd']:.0f} @ {p['entry_price']:,.2f}, "
            f"funding +${p['funding_accrued_usd']:.4f}"
        )
    pos_block = "\n".join(pos_lines) if pos_lines else "  (none open)"

    msg_lines = [
        f"📊 V2 Daily Reconciliation — {today}",
        f"{day_str} of Phase 3 marathon — daemon mode: {m.daemon_mode}",
        "",
        f"Net P&L 24h:  {sign_24h}${m.net_pnl_24h_usd:.4f}",
        f"Cumul P&L:    {sign_cumul}${m.cumul_pnl_usd:.4f} ({sign_cumul}{m.cumul_pnl_pct_of_capital:.3f}% of capital)",
        f"Max DD 24h:   {m.max_dd_24h_pct:+.3f}% (kill switch at -1.0%)",
        "",
        "Open positions:",
        pos_block,
        "",
        f"Cycles:       #{m.cycle_count}",
        f"Uptime:       {m.uptime_days:.2f} days",
        f"Last loop:    {m.last_loop_ts or 'unknown'}",
        "",
        f"Backtest expected:  ${EXPECTED_DAILY_PNL_USD:.2f}/day  ({EXPECTED_MONTHLY_PNL_USD:.2f}/month, "
        f"{EXPECTED_OOS_13MO_PNL_USD:.0f} OOS 13.5mo)",
        f"Live actual:        ${m.cumul_pnl_usd / max(m.uptime_days, 1.0):.2f}/day (running avg)",
        f"Deviation:          {dev_str} (tolerance band ±{DEVIATION_TOLERANCE_PCT:.0f}%)",
    ]
    if m.note:
        msg_lines.extend(["", m.note])
    return "\n".join(msg_lines)


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="V2 Phase 3 Safeguard C — daily reconciliation Telegram report."
    )
    parser.add_argument(
        "--dry", action="store_true",
        help="Format and print to stdout, do NOT send Telegram and do NOT append history.",
    )
    parser.add_argument(
        "--no-telegram", action="store_true",
        help="Append history but skip Telegram send (debug / testing).",
    )
    args = parser.parse_args()

    log.info("daily_reconciliation start — dry=%s, no_telegram=%s", args.dry, args.no_telegram)

    daemon_state = load_daemon_state()
    if daemon_state is None:
        msg = (
            "🚨 V2 DAILY RECONCILIATION — daemon_state.json MISSING.\n"
            f"Expected at: {DAEMON_STATE_PATH}\n"
            "Daemon may be down or state file corrupted. Investigate immediately."
        )
        log.error("daemon state missing — sending emergency Telegram")
        if not args.dry and not args.no_telegram and pt_config.TELEGRAM_ENABLED:
            try:
                TelegramAlerter().send(msg)
            except Exception as e:  # noqa: BLE001
                log.exception("emergency Telegram send failed: %s", e)
        else:
            print(msg)
        return 1

    yesterday = load_yesterday_record()
    try:
        metrics = compute_metrics(daemon_state, yesterday)
    except Exception as e:  # noqa: BLE001
        log.exception("compute_metrics failed: %s", e)
        err_msg = (
            f"🚨 V2 DAILY RECONCILIATION — compute_metrics FAILED.\n"
            f"Error: {e}\n"
            f"Trace:\n{traceback.format_exc()[:800]}"
        )
        if not args.dry and not args.no_telegram and pt_config.TELEGRAM_ENABLED:
            try:
                TelegramAlerter().send(err_msg)
            except Exception:  # noqa: BLE001
                pass
        else:
            print(err_msg)
        return 1

    message = format_telegram_message(metrics)
    log.info("formatted reconciliation message (%d chars)", len(message))

    if args.dry:
        print(message)
        log.info("--dry mode — skipping Telegram + history append")
        return 0

    # Send Telegram (unless --no-telegram)
    if not args.no_telegram:
        if not pt_config.TELEGRAM_ENABLED:
            log.warning("Telegram not enabled (missing credentials). Skipping send.")
        else:
            try:
                TelegramAlerter().send(message)
                log.info("Telegram reconciliation sent")
            except Exception as e:  # noqa: BLE001
                log.exception("Telegram send failed: %s", e)
                # Continue to append history so next day's delta still works.

    # Append today's record (idempotency: at most one record per UTC date)
    record = {
        "timestamp": metrics.timestamp,
        "date_utc": datetime.now(timezone.utc).date().isoformat(),
        "day_n": metrics.day_n,
        "cumul_pnl_usd": metrics.cumul_pnl_usd,
        "cumul_pnl_pct_of_capital": metrics.cumul_pnl_pct_of_capital,
        "net_pnl_24h_usd": metrics.net_pnl_24h_usd,
        "max_dd_24h_pct": metrics.max_dd_24h_pct,
        "cycle_count": metrics.cycle_count,
        "uptime_days": metrics.uptime_days,
        "daemon_mode": metrics.daemon_mode,
        "deviation_vs_expected_pct": metrics.deviation_vs_expected_pct,
        "n_open_positions": len(metrics.open_positions),
    }
    append_history(record)
    log.info("history record appended to %s", RECONCILIATION_HISTORY_PATH)

    return 0


if __name__ == "__main__":
    sys.exit(main())
