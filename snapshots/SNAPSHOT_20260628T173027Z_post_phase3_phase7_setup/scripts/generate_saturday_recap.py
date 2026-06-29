#!/usr/bin/env python3
"""
generate_saturday_recap.py — Weekly Saturday Recap generator for V2
====================================================================
Scans the past 7 days of project activity (git commits, daemon state,
paper trading ledger, file changes) and produces a structured recap in
WEEKLY_RECAPS/YYYY-MM-DD_recap.md following the format prescribed in
OPERATOR_METHODOLOGY.md Section III.

Sends a TL;DR via Telegram on completion.

Schedule (Mac launchd) :
  Saturday 12:00 UTC = either 04:00 PST (winter) or 05:00 PDT (summer)
  Recommended: launchd plist running at 12:05 UTC (small buffer)

Manual run :
  cd ~/Desktop/trading-bot-v2
  python3 scripts/generate_saturday_recap.py
  # add --no-telegram to skip notification (dry-run)
  # add --week-ending YYYY-MM-DD to backfill a past Saturday
"""
from __future__ import annotations

import json
import subprocess
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Telegram only loaded on demand (lazy import)
RECAP_DIR = ROOT / "WEEKLY_RECAPS"
RECAP_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# DATA COLLECTION
# ============================================================================

def get_week_window(week_ending: Optional[str] = None) -> tuple[datetime, datetime]:
    """Return (week_start, week_end) UTC datetimes. week_ending = Saturday 23:59 UTC."""
    if week_ending:
        end = datetime.strptime(week_ending, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    else:
        now = datetime.now(timezone.utc)
        # Find this week's Saturday
        days_until_sat = (5 - now.weekday()) % 7
        sat = now + timedelta(days=days_until_sat)
        end = sat.replace(hour=23, minute=59, second=59)
    start = end - timedelta(days=7)
    start = start.replace(hour=0, minute=0, second=0)
    return start, end


def collect_git_activity(start: datetime, end: datetime) -> dict:
    """Git log + diff stats over the window."""
    try:
        log = subprocess.check_output(
            ["git", "log",
             "--since", start.isoformat(),
             "--until", end.isoformat(),
             "--pretty=format:%h|%ai|%s|%an"],
            cwd=ROOT, text=True, timeout=10,
        ).strip()
    except Exception as e:
        return {"error": str(e), "commits": [], "files_changed": 0}

    commits = []
    for line in log.split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append({"sha": parts[0], "ts": parts[1],
                            "subject": parts[2], "author": parts[3]})

    try:
        stat = subprocess.check_output(
            ["git", "log",
             "--since", start.isoformat(),
             "--until", end.isoformat(),
             "--shortstat", "--pretty=tformat:"],
            cwd=ROOT, text=True, timeout=10,
        ).strip()
        files_changed = sum(
            int(l.split(" file")[0].strip()) for l in stat.split("\n")
            if " file" in l
        )
    except Exception:
        files_changed = 0

    return {"commits": commits, "files_changed": files_changed}


def collect_daemon_state() -> dict:
    """Current daemon state (heartbeat, positions, PnL, errors)."""
    state_dir = ROOT / "live" / "state"
    out = {}

    hb = state_dir / "heartbeat.txt"
    if hb.exists():
        out["last_heartbeat"] = hb.read_text().strip()
        try:
            hb_dt = datetime.fromisoformat(out["last_heartbeat"])
            out["heartbeat_age_sec"] = (datetime.now(timezone.utc) - hb_dt).total_seconds()
        except Exception:
            out["heartbeat_age_sec"] = None

    ds = state_dir / "daemon_state.json"
    if ds.exists():
        try:
            data = json.loads(ds.read_text())
            out["daemon"] = {
                "cycle_count": data.get("cycle_count"),
                "started_at": data.get("started_at"),
                "n_positions": len(data.get("positions", {})),
                "realized_pnl_usd": data.get("realized_pnl_usd", 0),
                "unrealized_pnl_usd": data.get("unrealized_pnl_usd", 0),
                "api_errors_hourly": data.get("api_error_count_hourly", 0),
            }
        except Exception as e:
            out["daemon"] = {"error": str(e)}

    trades_jsonl = state_dir / "trades.jsonl"
    if trades_jsonl.exists():
        try:
            lines = trades_jsonl.read_text().strip().split("\n")
            out["total_trade_events"] = len(lines) if lines and lines[0] else 0
        except Exception:
            out["total_trade_events"] = None

    return out


def collect_paper_trading_window(start: datetime, end: datetime) -> dict:
    """Paper trading activity within the week window."""
    trades_jsonl = ROOT / "live" / "state" / "trades.jsonl"
    if not trades_jsonl.exists():
        return {"trades_in_window": 0, "funding_accrued_week": 0.0}

    n = 0
    funding_week = 0.0
    try:
        for line in trades_jsonl.read_text().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ev_ts = datetime.fromisoformat(ev.get("ts", "").replace("Z", "+00:00"))
                if start <= ev_ts <= end:
                    n += 1
                    if ev.get("kind") == "funding":
                        funding_week += float(ev.get("amount_usd", 0))
            except Exception:
                continue
    except Exception as e:
        return {"trades_in_window": 0, "funding_accrued_week": 0.0, "error": str(e)}

    return {"trades_in_window": n, "funding_accrued_week": round(funding_week, 4)}


def collect_doc_changes(start: datetime, end: datetime) -> list:
    """Files modified this week (markdown + strategy + scripts)."""
    try:
        out = subprocess.check_output(
            ["git", "log",
             "--since", start.isoformat(),
             "--until", end.isoformat(),
             "--name-only", "--pretty=format:"],
            cwd=ROOT, text=True, timeout=10,
        )
        files = set(f.strip() for f in out.split("\n") if f.strip())
        return sorted(files)
    except Exception:
        return []


def check_ob_forward_health(end: datetime) -> dict:
    """Phase 3 Safeguard G — verify OB forward dispatcher emitted daily charts.

    Scans live/state/forward_charts/ for subdirectories matching pattern
    `YYYYMMDD_*` over the past 7 calendar days. Each healthy day should have
    at least one such directory (the dispatcher creates one timestamped folder
    per emission, e.g. `20260622_1200UTC`).

    Tolerance: 1 missed day per week is acceptable (occasional API blip /
    daemon restart). If actual < expected - 1 → warning flag raised.

    Returns dict consumed by format_recap() and send_tldr_telegram().
    """
    forward_dir = ROOT / "live" / "state" / "forward_charts"
    expected = 7
    if not forward_dir.exists():
        return {
            "expected": expected,
            "actual": 0,
            "missing_days": ["(directory absent)"],
            "warning": True,
            "warning_msg": (
                f"⚠️ OB forward dispatcher folder missing at "
                f"{forward_dir.relative_to(ROOT)} — dispatcher may have never run"
            ),
        }
    actual = 0
    missing = []
    for day_offset in range(expected):
        check_date = end.date() - timedelta(days=day_offset)
        day_str = check_date.strftime("%Y%m%d")
        matches = list(forward_dir.glob(f"{day_str}_*"))
        if matches:
            actual += 1
        else:
            missing.append(check_date.isoformat())
    warning = actual < (expected - 1)   # tolerate 1 miss
    warning_msg = ""
    if warning:
        warning_msg = (
            f"⚠️ OB forward dispatcher emitted only {actual}/{expected} daily "
            f"folders past 7 days (missing {', '.join(missing)}). "
            f"Investigate {forward_dir.relative_to(ROOT)} + dispatcher logs."
        )
    return {
        "expected": expected,
        "actual": actual,
        "missing_days": missing,
        "warning": warning,
        "warning_msg": warning_msg,
    }


# ============================================================================
# RECAP FORMATTER
# ============================================================================

def format_recap(week_start: datetime, week_end: datetime,
                 git: dict, daemon: dict, paper: dict, files: list,
                 ob_forward_health: Optional[dict] = None) -> str:
    """Produce the structured Saturday Recap markdown."""
    week_label = week_end.strftime("%Y-%m-%d")
    week_human = f"{week_start.strftime('%b %d')} → {week_end.strftime('%b %d, %Y')}"

    # ----- Header
    out = []
    out.append(f"# Saturday Recap — Trading Bot V2 — Week ending {week_label}")
    out.append("")
    out.append(f"> Window: **{week_human}** (7 days UTC)  ·  "
               f"Generated by `scripts/generate_saturday_recap.py`")
    out.append("")

    # ----- TL;DR (top, ~50 words)
    out.append("## TL;DR")
    out.append("")
    tldr_parts = []
    if git.get("commits"):
        tldr_parts.append(f"{len(git['commits'])} commit(s)")
    if paper.get("trades_in_window") is not None:
        tldr_parts.append(f"{paper['trades_in_window']} paper trade event(s)")
    if daemon.get("daemon", {}).get("cycle_count"):
        tldr_parts.append(f"daemon cycle {daemon['daemon']['cycle_count']}")
    if daemon.get("heartbeat_age_sec") is not None:
        age = daemon["heartbeat_age_sec"]
        if age < 1800:
            tldr_parts.append("daemon healthy")
        elif age < 7200:
            tldr_parts.append(f"heartbeat stale {int(age/60)} min")
        else:
            tldr_parts.append(f"heartbeat OFFLINE {int(age/3600)} h")

    out.append(" · ".join(tldr_parts) if tldr_parts else "_(no activity this week)_")
    out.append("")
    out.append("**Memorable phrase of the week** : _[to fill manually]_")
    out.append("")

    # ----- Belief State (5 dimensions)
    out.append("## Belief State Snapshot")
    out.append("")
    out.append("| Dimension | Last week | This week | Δ | Note |")
    out.append("|---|:-:|:-:|:-:|---|")
    out.append("| Methodological discipline | _to fill_ | _to fill_ | _to fill_ | no-lookahead, friction realism, version freezing |")
    out.append("| Empirical validation | _to fill_ | _to fill_ | _to fill_ | paper hours, trades resolved, Sharpe accumulated |")
    out.append("| Technical maturity | _to fill_ | _to fill_ | _to fill_ | test coverage, monitoring, deploy readiness |")
    out.append("| Commercial viability | _to fill_ | _to fill_ | _to fill_ | capital allocation potential, scalability |")
    out.append("| Cross-asset robustness | _to fill_ | _to fill_ | _to fill_ | ETH/LTC/AVAX/SOL consistency |")
    out.append("")

    # ----- Engineering activity
    out.append("## Engineering Activity")
    out.append("")
    if git.get("commits"):
        out.append(f"- **{len(git['commits'])} commits** · **{git.get('files_changed', 0)} file diffs**")
        out.append("")
        for c in git["commits"][:10]:
            out.append(f"  - `{c['sha']}` {c['subject']}  ({c['ts'][:10]})")
        if len(git["commits"]) > 10:
            out.append(f"  - _…and {len(git['commits']) - 10} more_")
    else:
        out.append("_(no commits this week)_")
    out.append("")

    if files:
        out.append("**Files touched (deduped) :**")
        out.append("")
        for f in files[:15]:
            out.append(f"- `{f}`")
        if len(files) > 15:
            out.append(f"- _…and {len(files) - 15} more_")
        out.append("")

    # ----- Daemon health
    out.append("## Daemon Health")
    out.append("")
    if daemon.get("daemon"):
        d = daemon["daemon"]
        out.append(f"- **Last heartbeat** : {daemon.get('last_heartbeat', '?')} "
                   f"(age {int(daemon.get('heartbeat_age_sec') or 0)} s)")
        out.append(f"- **Cycle count** : {d.get('cycle_count', '?')}")
        out.append(f"- **Started** : {d.get('started_at', '?')}")
        out.append(f"- **Open positions** : {d.get('n_positions', 0)}")
        out.append(f"- **Realized PnL (cumulative)** : ${d.get('realized_pnl_usd', 0):.2f}")
        out.append(f"- **Unrealized PnL** : ${d.get('unrealized_pnl_usd', 0):.2f}")
        out.append(f"- **API errors (last hour)** : {d.get('api_errors_hourly', 0)}")
    else:
        out.append("_(daemon state not available)_")
    out.append("")

    # ----- Paper trading window
    out.append("## Paper Trading — Week Window")
    out.append("")
    out.append(f"- **Trade events this week** : {paper.get('trades_in_window', 0)}")
    out.append(f"- **Funding accrued this week** : ${paper.get('funding_accrued_week', 0):.4f}")
    out.append(f"- **Total trade events (cumulative since start)** : {daemon.get('total_trade_events', '?')}")
    out.append("")

    # ----- OB Forward Dispatcher Health (Phase 3 Safeguard G)
    out.append("## OB Forward Dispatcher Health (Safeguard G)")
    out.append("")
    if ob_forward_health is not None:
        ofh = ob_forward_health
        status_emoji = "🔴" if ofh.get("warning") else "🟢"
        out.append(f"- **Daily emissions past 7 days** : "
                   f"{status_emoji} {ofh.get('actual', 0)}/{ofh.get('expected', 7)}")
        if ofh.get("missing_days"):
            missing = ofh["missing_days"]
            out.append(f"- **Missing days** : {', '.join(missing) if missing else 'none'}")
        if ofh.get("warning"):
            out.append("")
            out.append(f"> {ofh.get('warning_msg', '')}")
    else:
        out.append("_(OB forward health check skipped — module not invoked)_")
    out.append("")

    # ----- Layered Inquiry Surprise + Compression Check (manual)
    out.append("## Layered Inquiry — Surprise of the Week")
    out.append("")
    out.append("_[to fill manually — what question, when raised between layers, revealed an assumption we hadn't surfaced?]_")
    out.append("")

    out.append("## Compression Check")
    out.append("")
    out.append("_[to fill manually — did any new artifact created this week justify itself, or could it have been a section update?]_")
    out.append("")

    # ----- Open questions still pending
    out.append("## Open Questions Pending")
    out.append("")
    out.append("_See `STRATEGIC_LOGIC_DOC.md` consolidated questions Q1–Q25._")
    out.append("")

    # ----- Next week
    out.append("## Next Week — Intent")
    out.append("")
    out.append("_[to fill manually — single sentence summarizing what success looks like next Saturday]_")
    out.append("")

    out.append("---")
    out.append("")
    out.append(f"*Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
               f"by `generate_saturday_recap.py`. Format per OPERATOR_METHODOLOGY.md "
               f"Section III. Principles enforced: P1-P12 (see PRINCIPLES.md).*")

    return "\n".join(out) + "\n"


# ============================================================================
# TELEGRAM TL;DR
# ============================================================================

def send_tldr_telegram(week_label: str, git: dict, daemon: dict, paper: dict,
                       ob_forward_health: Optional[dict] = None) -> bool:
    """Send a compact TL;DR via Telegram. Returns success boolean."""
    try:
        from paper_trading.monitoring import TelegramAlerter
    except Exception:
        print("[recap] telegram alerter not importable — skip notification")
        return False

    alerter = TelegramAlerter()
    if not alerter.enabled:
        print("[recap] telegram not configured — skip notification")
        return False

    n_commits = len(git.get("commits", []))
    n_trades = paper.get("trades_in_window", 0)
    funding_week = paper.get("funding_accrued_week", 0)
    n_positions = daemon.get("daemon", {}).get("n_positions", 0)
    realized = daemon.get("daemon", {}).get("realized_pnl_usd", 0)
    unrealized = daemon.get("daemon", {}).get("unrealized_pnl_usd", 0)
    cycle = daemon.get("daemon", {}).get("cycle_count", "?")
    hb_age = daemon.get("heartbeat_age_sec")
    hb_status = "💚 healthy" if (hb_age is not None and hb_age < 1800) else \
                ("🟡 stale" if (hb_age is not None and hb_age < 7200) else "🔴 offline")

    # Safeguard G — OB forward health line (only shown if degraded)
    ob_health_line = ""
    if ob_forward_health and ob_forward_health.get("warning"):
        ob_health_line = (
            f"• 🔴 OB forward dispatcher: only "
            f"{ob_forward_health.get('actual', 0)}/{ob_forward_health.get('expected', 7)} "
            f"daily emissions (safeguard G warning)\n"
        )
    elif ob_forward_health:
        ob_health_line = (
            f"• 🟢 OB forward dispatcher: "
            f"{ob_forward_health.get('actual', 7)}/{ob_forward_health.get('expected', 7)} "
            f"daily emissions OK\n"
        )

    text = (
        f"📋 *V2 Saturday Recap — week ending {week_label}*\n"
        f"\n"
        f"• Engineering: *{n_commits} commits*\n"
        f"• Paper trading: *{n_trades} events* this week\n"
        f"• Funding accrued: *${funding_week:.4f}*\n"
        f"• Daemon: {hb_status} · cycle {cycle} · {n_positions} positions\n"
        f"• PnL: realized ${realized:.2f} · unrealized ${unrealized:.2f}\n"
        f"{ob_health_line}"
        f"\n"
        f"Full recap → `WEEKLY_RECAPS/{week_label}_recap.md`"
    )
    res = alerter.send(text)
    if res.ok:
        print("[recap] telegram sent OK")
        return True
    print(f"[recap] telegram SEND ERROR: {res.error}")
    return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = ArgumentParser()
    parser.add_argument("--week-ending", default=None,
                        help="Saturday YYYY-MM-DD (default: this week's Sat)")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram notification (dry-run)")
    args = parser.parse_args()

    start, end = get_week_window(args.week_ending)
    week_label = end.strftime("%Y-%m-%d")
    print(f"[recap] window {start.isoformat()} → {end.isoformat()}")

    git = collect_git_activity(start, end)
    daemon = collect_daemon_state()
    paper = collect_paper_trading_window(start, end)
    files = collect_doc_changes(start, end)
    ob_forward_health = check_ob_forward_health(end)   # Phase 3 Safeguard G
    if ob_forward_health.get("warning"):
        print(f"[recap] safeguard G warning: {ob_forward_health.get('warning_msg', '')}")
    else:
        print(f"[recap] safeguard G OK: {ob_forward_health.get('actual', 0)}/"
              f"{ob_forward_health.get('expected', 7)} daily emissions")

    md = format_recap(start, end, git, daemon, paper, files,
                      ob_forward_health=ob_forward_health)
    out_path = RECAP_DIR / f"{week_label}_recap.md"
    out_path.write_text(md)
    print(f"[recap] wrote {out_path.relative_to(ROOT)} ({len(md)} chars)")

    if not args.no_telegram:
        send_tldr_telegram(week_label, git, daemon, paper,
                           ob_forward_health=ob_forward_health)


if __name__ == "__main__":
    main()
