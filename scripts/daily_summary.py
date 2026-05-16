"""
daily_summary.py — Send a daily summary of the trading bot to Telegram.

WHAT THIS DOES
==============
Builds a human-readable summary of the bot's state, covering:
- Current state (status, equity, drawdown)
- Today UTC (since 00:00 UTC of current day)
- Last 24h (rolling window)
- Snapshot counts and Telegram backup history

Sends to stdout AND Telegram (configurable via flags).
Read-only on state.db — safe to run anytime, even while bot is in cycle.

USAGE
=====
    python -m scripts.daily_summary               # both stdout + Telegram
    python -m scripts.daily_summary --no-telegram # stdout only
    python -m scripts.daily_summary --no-stdout   # Telegram only

DESIGNED FOR
============
- Manual morning check during trip (via SSH iPhone)
- Optional: integration into bot's run_one_cycle() to auto-send at HEARTBEAT_HOUR_UTC
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from paper_trading import config


# ─────────────────────────────────────────────────────────────────────
#  Data fetchers (read-only)
# ─────────────────────────────────────────────────────────────────────

def _query_db(db_path: Path, now: datetime) -> dict:
    """Read everything needed for the summary from state.db (read-only)."""
    if not db_path.exists():
        return {"error": "DB not found"}

    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    except sqlite3.OperationalError as e:
        return {"error": f"Cannot open DB: {e}"}

    out: dict = {}
    try:
        cur = conn.cursor()

        # Bot state
        cur.execute("SELECT status, halt_reason, halt_timestamp, last_cycle_timestamp FROM bot_state LIMIT 1")
        row = cur.fetchone()
        if row:
            out["bot_status"] = row[0]
            out["halt_reason"] = row[1]
            out["halt_timestamp"] = row[2]
            out["last_cycle_timestamp"] = row[3]
        else:
            out["bot_status"] = "UNKNOWN"

        # Latest equity snapshot (= current state)
        cur.execute(
            "SELECT timestamp, equity, cash, open_positions_value, peak_equity, drawdown_pct "
            "FROM equity_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            out["current_ts"] = row[0]
            out["current_equity"] = row[1]
            out["current_cash"] = row[2]
            out["current_open_value"] = row[3]
            out["peak_equity"] = row[4]
            out["current_drawdown_pct"] = row[5]

        # Equity at start of today UTC (first snapshot >= 00:00 UTC)
        today_start_iso = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat().replace("+00:00", "Z")
        cur.execute(
            "SELECT timestamp, equity FROM equity_snapshots "
            "WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
            (today_start_iso,),
        )
        row = cur.fetchone()
        if row:
            out["today_start_ts"] = row[0]
            out["today_start_equity"] = row[1]

        # Equity 24h ago (closest snapshot >= now - 24h)
        ago_24h_iso = (now - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        cur.execute(
            "SELECT timestamp, equity FROM equity_snapshots "
            "WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT 1",
            (ago_24h_iso,),
        )
        row = cur.fetchone()
        if row:
            out["ago_24h_ts"] = row[0]
            out["ago_24h_equity"] = row[1]

        # Min/max equity today UTC
        cur.execute(
            "SELECT MIN(equity), MAX(equity) FROM equity_snapshots "
            "WHERE timestamp >= ?",
            (today_start_iso,),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            out["today_min_equity"] = row[0]
            out["today_max_equity"] = row[1]

        # Cycles count today UTC
        cur.execute(
            "SELECT COUNT(*) FROM equity_snapshots WHERE timestamp >= ?",
            (today_start_iso,),
        )
        out["today_cycles"] = cur.fetchone()[0]

        # Open positions
        cur.execute("SELECT COUNT(*), COALESCE(SUM(units * entry_price), 0) FROM open_positions")
        row = cur.fetchone()
        out["open_positions_count"] = row[0]
        out["open_positions_notional"] = row[1] or 0.0

        # Closed trades total
        cur.execute("SELECT COUNT(*) FROM closed_trades")
        out["total_closed_trades"] = cur.fetchone()[0]

        # Closed trades today UTC (using exit_timestamp + pnl_dollars)
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_dollars), 0) FROM closed_trades "
            "WHERE exit_timestamp >= ?",
            (today_start_iso,),
        )
        row = cur.fetchone()
        out["today_closed_count"] = row[0]
        out["today_closed_pnl"] = row[1] or 0.0

        # Closed trades 24h
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(pnl_dollars), 0) FROM closed_trades "
            "WHERE exit_timestamp >= ?",
            (ago_24h_iso,),
        )
        row = cur.fetchone()
        out["last24h_closed_count"] = row[0]
        out["last24h_closed_pnl"] = row[1] or 0.0

    finally:
        conn.close()

    return out


def _query_backups() -> dict:
    """Read local backup info."""
    backup_dir = config.BACKUPS_DIR
    out = {}
    if backup_dir.exists():
        snapshots = sorted(backup_dir.glob("state_*.db.gz"))
        out["count"] = len(snapshots)
        if snapshots:
            latest = snapshots[-1]
            out["latest_name"] = latest.name
            out["latest_mtime"] = datetime.fromtimestamp(
                latest.stat().st_mtime, tz=timezone.utc,
            )
    else:
        out["count"] = 0
    return out


# ─────────────────────────────────────────────────────────────────────
#  Formatting
# ─────────────────────────────────────────────────────────────────────

def _fmt_money(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"${x:,.2f}"


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.2%}"


def _fmt_delta_money(a: float | None, b: float | None) -> str:
    """Format the difference (a - b) as money with sign."""
    if a is None or b is None:
        return "n/a"
    d = a - b
    return f"{'+' if d >= 0 else ''}{d:,.2f}"


def _fmt_age(dt: datetime | None, now: datetime) -> str:
    if dt is None:
        return "never"
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d} ago"
    return f"{secs // 86400}d ago"


def build_summary(db: dict, backups: dict, now: datetime) -> tuple[str, str]:
    """Build summary in two formats:
    - text_plain: nice ASCII for stdout
    - text_telegram: Markdown for Telegram sendMessage
    """
    if "error" in db:
        msg = f"❌ Cannot read DB: {db['error']}"
        return msg, msg

    bot_status = db.get("bot_status", "UNKNOWN")
    cur_eq = db.get("current_equity")
    today_start_eq = db.get("today_start_equity")
    ago_24h_eq = db.get("ago_24h_equity")
    peak_eq = db.get("peak_equity")
    cur_dd = db.get("current_drawdown_pct")
    cur_cash = db.get("current_cash")
    cur_open_val = db.get("current_open_value")

    # Today UTC PnL
    if cur_eq is not None and today_start_eq is not None:
        today_pnl = cur_eq - today_start_eq
        today_pnl_pct = today_pnl / today_start_eq if today_start_eq else 0
    else:
        today_pnl = None
        today_pnl_pct = None

    # Last 24h PnL
    if cur_eq is not None and ago_24h_eq is not None:
        h24_pnl = cur_eq - ago_24h_eq
        h24_pnl_pct = h24_pnl / ago_24h_eq if ago_24h_eq else 0
    else:
        h24_pnl = None
        h24_pnl_pct = None

    # Status icon
    if bot_status == "RUNNING":
        status_icon = "🟢"
    elif bot_status == "HALTED":
        status_icon = "🔴"
    else:
        status_icon = "⚪"

    # Today emoji
    today_emoji = "📈" if (today_pnl or 0) >= 0 else "📉"
    h24_emoji = "📈" if (h24_pnl or 0) >= 0 else "📉"

    # ── PLAIN TEXT (stdout) ──
    lines = []
    lines.append("=" * 72)
    lines.append(f"  TRADING BOT DAILY SUMMARY — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"── Current state ──")
    lines.append(f"  Status              : {status_icon} {bot_status}")
    if db.get("halt_reason"):
        lines.append(f"  ⚠ HALT reason       : {db['halt_reason']}")
    lines.append(f"  Equity              : {_fmt_money(cur_eq)}")
    lines.append(f"  Cash                : {_fmt_money(cur_cash)}")
    lines.append(f"  Open positions val  : {_fmt_money(cur_open_val)}")
    lines.append(f"  Peak equity         : {_fmt_money(peak_eq)}")
    lines.append(f"  Drawdown from peak  : {_fmt_pct(cur_dd)}")
    lines.append("")
    lines.append(f"── Today (since 00:00 UTC) ──")
    if today_start_eq is not None:
        lines.append(f"  Start equity        : {_fmt_money(today_start_eq)}")
    lines.append(f"  PnL today           : {today_emoji} {_fmt_money(today_pnl) if today_pnl is not None else 'n/a'} ({_fmt_pct(today_pnl_pct)})")
    lines.append(f"  Cycles completed    : {db.get('today_cycles', 'n/a')}")
    if db.get("today_min_equity") is not None:
        lines.append(f"  Min equity today    : {_fmt_money(db['today_min_equity'])}")
        lines.append(f"  Max equity today    : {_fmt_money(db['today_max_equity'])}")
    if db.get("today_closed_count") is not None:
        lines.append(f"  Trades closed today : {db['today_closed_count']} (PnL: {_fmt_money(db.get('today_closed_pnl'))})")
    lines.append("")
    lines.append(f"── Last 24h (rolling) ──")
    if ago_24h_eq is not None:
        lines.append(f"  Equity 24h ago      : {_fmt_money(ago_24h_eq)}")
    lines.append(f"  PnL last 24h        : {h24_emoji} {_fmt_money(h24_pnl) if h24_pnl is not None else 'n/a'} ({_fmt_pct(h24_pnl_pct)})")
    if db.get("last24h_closed_count") is not None:
        lines.append(f"  Trades closed 24h   : {db['last24h_closed_count']} (PnL: {_fmt_money(db.get('last24h_closed_pnl'))})")
    lines.append("")
    lines.append(f"── Positions & trades ──")
    lines.append(f"  Open positions      : {db.get('open_positions_count', 'n/a')}")
    if db.get("open_positions_notional"):
        lines.append(f"  Open notional       : {_fmt_money(db.get('open_positions_notional'))}")
    lines.append(f"  Total closed trades : {db.get('total_closed_trades', 'n/a')}")
    lines.append("")
    lines.append(f"── Backups ──")
    lines.append(f"  Local snapshots     : {backups.get('count', 'n/a')}")
    if backups.get("latest_mtime"):
        lines.append(f"  Latest local        : {backups['latest_name']} ({_fmt_age(backups['latest_mtime'], now)})")
    lines.append("")
    lines.append("=" * 72)

    text_plain = "\n".join(lines)

    # ── TELEGRAM (Markdown) ──
    tg = []
    tg.append(f"📊 *Daily summary* — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    tg.append("")
    tg.append(f"*Status*: {status_icon} {bot_status}")
    if db.get("halt_reason"):
        tg.append(f"⚠ HALT: `{db['halt_reason']}`")
    tg.append(f"*Equity*: {_fmt_money(cur_eq)}")
    tg.append(f"*Peak*: {_fmt_money(peak_eq)}  ·  *DD*: {_fmt_pct(cur_dd)}")
    tg.append("")
    tg.append(f"*Today UTC*")
    tg.append(f"  PnL: {today_emoji} {_fmt_money(today_pnl) if today_pnl is not None else 'n/a'} ({_fmt_pct(today_pnl_pct)})")
    tg.append(f"  Cycles: {db.get('today_cycles', 'n/a')}")
    if db.get("today_closed_count") is not None:
        tg.append(f"  Trades closed: {db['today_closed_count']}")
    tg.append("")
    tg.append(f"*Last 24h*")
    tg.append(f"  PnL: {h24_emoji} {_fmt_money(h24_pnl) if h24_pnl is not None else 'n/a'} ({_fmt_pct(h24_pnl_pct)})")
    if db.get("last24h_closed_count") is not None:
        tg.append(f"  Trades closed: {db['last24h_closed_count']}")
    tg.append("")
    tg.append(f"*Positions*: {db.get('open_positions_count', 'n/a')} open  ·  {db.get('total_closed_trades', 'n/a')} total closed")

    text_telegram = "\n".join(tg)
    return text_plain, text_telegram


# ─────────────────────────────────────────────────────────────────────
#  Telegram sender (text message, not file)
# ─────────────────────────────────────────────────────────────────────

def _send_telegram(text_md: str) -> tuple[bool, str | None]:
    """Send Markdown text message to Telegram via sendMessage."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False, "telegram_not_configured"

    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_md,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            return True, None
        return False, f"http_{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"exception: {e}"


# ─────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Send a daily summary of the trading bot.")
    parser.add_argument("--no-stdout", action="store_true", help="Do not print to stdout")
    parser.add_argument("--no-telegram", action="store_true", help="Do not send to Telegram")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    db = _query_db(config.STATE_DB_PATH, now)
    backups = _query_backups()
    text_plain, text_tg = build_summary(db, backups, now)

    # Output stdout
    if not args.no_stdout:
        print(text_plain)

    # Send Telegram
    if not args.no_telegram:
        ok, err = _send_telegram(text_tg)
        if ok:
            print(f"\n✅ Sent to Telegram successfully.")
        else:
            print(f"\n⚠ Telegram send failed: {err}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
