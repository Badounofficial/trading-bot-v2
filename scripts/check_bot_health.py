"""
check_bot_health.py — Quick health check for the running production bot.

WHAT THIS DOES
==============
Read-only snapshot of the bot's state, designed for fast operational
verification (e.g. from your phone via SSH during travel).

Does NOT touch the running bot process. Just reads state.db and inspects
backup files. Safe to run anytime.

USAGE
=====
    python -m scripts.check_bot_health

EXIT CODES
==========
    0 = healthy (all checks pass)
    1 = warnings present (review needed)
    2 = critical (bot likely down or HALTED)

WHAT IT CHECKS
==============
1. Bot process status (RUNNING / HALTED / unknown)
2. State.db freshness (last cycle within expected window)
3. Open positions (count + value)
4. Current equity + drawdown
5. Local snapshots (count + most recent)
6. Telegram backup tracker (last scheduled send)
7. JSONL logs activity (last event recent enough)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from paper_trading import config


# Thresholds for the verdict (in minutes)
MAX_CYCLE_AGE_MIN = 75  # Cycles are hourly + ~10s offset; flag if > 75 min
MAX_TELEGRAM_AGE_MIN = 7 * 60  # Backup every 6h; flag if > 7h


def _fmt_age(dt: datetime | None, now: datetime) -> str:
    """Format a datetime as 'X min ago' / 'X h ago'."""
    if dt is None:
        return "never"
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "in the future (?)"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60} min ago"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d} ago"


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp safely."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _read_telegram_tracker() -> str | None:
    """Read last_backup_ts from the tracker file."""
    try:
        with open(config.LAST_TELEGRAM_BACKUP_FILE) as f:
            data = json.load(f)
            return data.get("last_backup_ts")
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _query_db(db_path: Path) -> dict:
    """Read state from the DB (read-only)."""
    if not db_path.exists():
        return {"error": "DB not found"}

    # Open read-only to avoid any chance of contention
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    except sqlite3.OperationalError as e:
        return {"error": f"Cannot open DB: {e}"}

    out: dict = {}
    try:
        cur = conn.cursor()

        # Bot state
        cur.execute("SELECT status, halt_reason FROM bot_state LIMIT 1")
        row = cur.fetchone()
        if row:
            out["bot_status"] = row[0]
            out["halt_reason"] = row[1]
        else:
            out["bot_status"] = "UNKNOWN (no row in bot_state)"
            out["halt_reason"] = None

        # Open positions (table contains only currently open ones)
        cur.execute("SELECT COUNT(*) FROM open_positions")
        out["open_positions"] = cur.fetchone()[0]

        # Closed trades
        cur.execute("SELECT COUNT(*) FROM closed_trades")
        out["closed_trades"] = cur.fetchone()[0]

        # Latest equity snapshot
        cur.execute(
            "SELECT timestamp, equity, cash, open_positions_value, "
            "peak_equity, drawdown_pct "
            "FROM equity_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            out["last_snapshot_ts"] = row[0]
            out["equity"] = row[1]
            out["cash"] = row[2]
            out["open_value"] = row[3]
            out["peak_equity"] = row[4]
            out["drawdown_pct"] = row[5]
        else:
            out["last_snapshot_ts"] = None
    finally:
        conn.close()

    return out


def main() -> int:
    now = datetime.now(timezone.utc)

    print("=" * 72)
    print(f"  TRADING BOT HEALTH CHECK — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 72)

    warnings: list[str] = []
    critical: list[str] = []

    # ── 1. DB state ──
    db_state = _query_db(config.STATE_DB_PATH)

    if "error" in db_state:
        critical.append(f"DB read failed: {db_state['error']}")
        print(f"\n  ❌ {db_state['error']}")
        print(f"     DB path: {config.STATE_DB_PATH}")
        _print_verdict(warnings, critical)
        return 2

    bot_status = db_state["bot_status"]
    if bot_status == "HALTED":
        critical.append(f"Bot is HALTED (reason: {db_state.get('halt_reason')})")
    elif bot_status not in ("RUNNING", "UNKNOWN (no row in bot_state)"):
        warnings.append(f"Unexpected bot status: {bot_status}")

    print(f"\n── Bot state ──")
    print(f"  Status              : {bot_status}")
    if db_state.get("halt_reason"):
        print(f"  ⚠ HALT reason       : {db_state['halt_reason']}")
    print(f"  Open positions      : {db_state['open_positions']}")
    print(f"  Closed trades       : {db_state['closed_trades']}")

    last_snap_dt = _parse_iso(db_state.get("last_snapshot_ts"))
    if last_snap_dt:
        age_min = (now - last_snap_dt).total_seconds() / 60
        print(f"  Last equity snap    : {db_state['last_snapshot_ts']} ({_fmt_age(last_snap_dt, now)})")
        if age_min > MAX_CYCLE_AGE_MIN:
            critical.append(
                f"Last cycle is {age_min:.0f} min old (expected < {MAX_CYCLE_AGE_MIN}). "
                "Bot may be stuck or stopped."
            )
    else:
        warnings.append("No equity snapshot in DB (bot may not have run any cycle yet)")
        print(f"  Last equity snap    : (none)")

    # ── 2. Financial state ──
    if "equity" in db_state:
        print(f"\n── Financial state ──")
        print(f"  Equity              : ${db_state['equity']:,.2f}")
        print(f"  Cash                : ${db_state['cash']:,.2f}")
        print(f"  Open positions val  : ${db_state['open_value']:,.2f}")
        print(f"  Peak equity         : ${db_state['peak_equity']:,.2f}")
        print(f"  Drawdown            : {db_state['drawdown_pct']:.2%}")

        # Invariant check
        invariant_diff = db_state["equity"] - (db_state["cash"] + db_state["open_value"])
        if abs(invariant_diff) > 0.01:
            critical.append(
                f"Invariant violation: equity - (cash + open_value) = ${invariant_diff:.6f} "
                "(should be < $0.01)"
            )
        else:
            print(f"  Invariant (eq=c+ov) : OK (diff ${invariant_diff:.6f})")

    # ── 3. Local backups ──
    backup_dir = config.BACKUPS_DIR
    print(f"\n── Local backups ──")
    if backup_dir.exists():
        snapshots = sorted(backup_dir.glob("state_*.db.gz"), key=lambda p: p.stat().st_mtime)
        print(f"  Backup dir          : {backup_dir}")
        print(f"  Snapshots count     : {len(snapshots)} (rotation keeps last {config.BACKUP_MAX_KEEP})")
        if snapshots:
            latest = snapshots[-1]
            latest_mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
            size_kb = latest.stat().st_size / 1024
            print(f"  Latest snapshot     : {latest.name} ({size_kb:.1f} KB, {_fmt_age(latest_mtime, now)})")
        else:
            warnings.append("No local snapshots found")
            print(f"  ⚠ No snapshots yet")
    else:
        warnings.append(f"Backup dir does not exist: {backup_dir}")
        print(f"  ⚠ Backup dir missing")

    # ── 4. Telegram backup tracker ──
    print(f"\n── Telegram backup ──")
    tracker_ts = _read_telegram_tracker()
    if tracker_ts:
        tracker_dt = _parse_iso(tracker_ts)
        print(f"  Last sent timestamp : {tracker_ts}")
        if tracker_dt:
            age_min = (now - tracker_dt).total_seconds() / 60
            print(f"  Time since last     : {_fmt_age(tracker_dt, now)}")
            if age_min > MAX_TELEGRAM_AGE_MIN:
                warnings.append(
                    f"Last Telegram backup was {age_min/60:.1f}h ago "
                    f"(expected every 6h at {config.TELEGRAM_BACKUP_HOURS_UTC} UTC)"
                )
    else:
        warnings.append("No Telegram backup ever sent (or tracker missing)")
        print(f"  ⚠ Tracker not found or empty")

    # ── 5. JSONL log activity ──
    logs_dir = config.LOGS_DIR if hasattr(config, "LOGS_DIR") else Path("paper_trading/logs")
    print(f"\n── JSONL log activity ──")
    today_str = now.strftime("%Y-%m-%d")
    today_log = logs_dir / f"{today_str}.jsonl"
    if today_log.exists():
        size_kb = today_log.stat().st_size / 1024
        mtime = datetime.fromtimestamp(today_log.stat().st_mtime, tz=timezone.utc)
        print(f"  Today's log         : {today_log.name} ({size_kb:.1f} KB)")
        print(f"  Last write          : {_fmt_age(mtime, now)}")
        if (now - mtime) > timedelta(minutes=MAX_CYCLE_AGE_MIN):
            warnings.append(
                f"Today's JSONL log not written in {_fmt_age(mtime, now)} — bot may be stuck"
            )
    else:
        # Could be early in the day (no cycles yet)
        if now.hour > 0:
            warnings.append(f"Today's JSONL log missing: {today_log}")
        print(f"  ⚠ Today's log not found")

    # ── Verdict ──
    return _print_verdict(warnings, critical)


def _print_verdict(warnings: list[str], critical: list[str]) -> int:
    print(f"\n{'=' * 72}")
    if critical:
        print(f"  ❌ CRITICAL ISSUES ({len(critical)})")
        for c in critical:
            print(f"     - {c}")
        if warnings:
            print(f"\n  ⚠ Also {len(warnings)} warning(s):")
            for w in warnings:
                print(f"     - {w}")
        print(f"{'=' * 72}\n")
        return 2
    elif warnings:
        print(f"  ⚠ WARNINGS ({len(warnings)})")
        for w in warnings:
            print(f"     - {w}")
        print(f"{'=' * 72}\n")
        return 1
    else:
        print(f"  ✅ HEALTHY — all checks pass")
        print(f"{'=' * 72}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
