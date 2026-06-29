"""
paper_funding_capture.py — Autonomous live paper-trading daemon
================================================================

Drives the funding_capture strategy on Hyperliquid PUBLIC funding/price data,
without touching real capital. Runs continuously on Badoun's Mac for the
22 May → 2 June absence window.

Architecture
------------
  fetch_loop (every 5 min):
      1. Pull latest fundingHistory + mark prices from api.hyperliquid.xyz/info
      2. Append to state/funding_history.parquet
      3. For each asset (BTC, ETH, SOL):
          a. Compute smoothed signal via strategies.funding_capture
          b. If signal transition → open/close virtual position
          c. If holding → accrue funding payments and mark-to-market
      4. Persist state, write heartbeat
      5. Check anomaly thresholds; fire Telegram alert if any
      6. If 12:00 UTC daily → send heartbeat message
      7. If 2026-05-28 and not yet sent → send intermediate report

Persistence
-----------
  state/positions.json          current virtual open positions
  state/trades.jsonl            append-only ledger of every entry/exit
  state/funding_history.parquet rolling history of funding rates per asset
  state/heartbeat.txt           last-successful-loop ISO timestamp
  state/sent_messages.json      idempotency keys for Telegram (no double-send)

Reliability
-----------
  - All Telegram calls are best-effort (failure ≠ crash)
  - Crash recovery: every loop reloads state from disk before deciding
  - Watchdog: separate process can read heartbeat.txt to detect freezes
  - Designed to be wrapped in `caffeinate -i ./run_daemon.sh` for sleep-immunity

Usage
-----
  python live/paper_funding_capture.py          # production: full loop, 5-min cycle
  python live/paper_funding_capture.py --once   # single cycle, then exit (for tests)
  python live/paper_funding_capture.py --dry    # signals only, no virtual trades

(Note: this is the skeleton. Wednesday delivers structure + API wrapper +
persistence. Thursday wires in the actual decision loop + alerter + smoke run.)
"""
from __future__ import annotations
import argparse
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_trading import config as pt_config  # for Telegram creds + LOGS_DIR
from paper_trading.monitoring import JsonLineLogger, TelegramAlerter
from strategies.funding_capture import generate_position


# ----------------------------------------------------------------------------
# CONSTANTS
# ----------------------------------------------------------------------------
LIVE_DIR = ROOT / "live"
STATE_DIR = LIVE_DIR / "state"
LOG_DIR   = LIVE_DIR / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = ["BTC", "ETH", "SOL"]
CAPITAL_PER_ASSET_USD = 10_000.0   # virtual notional per asset
LOOP_INTERVAL_SEC = 300            # 5 min

# Strategy thresholds (from config.yaml)
SMOOTH_HOURS = 24
ENTRY_THRESHOLD_APR = 0.005
EXIT_THRESHOLD_APR = -0.005
MIN_HOLD_HOURS = 24
MIN_FLAT_HOURS = 24

# Hyperliquid public API
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_REQUEST_TIMEOUT = 10

# Anomaly thresholds (trigger Telegram alert)
ANOMALY_PNL_PCT_TRIGGER = -10.0   # -10% portfolio PnL
ANOMALY_API_ERRORS_PER_HOUR = 5
ANOMALY_HEARTBEAT_MAX_GAP_MIN = 120

# Daily heartbeat / scheduled reports
DAILY_HEARTBEAT_UTC_HOUR = 12
INTERMEDIATE_REPORT_DATE = "2026-05-28"   # send extended summary on this UTC date


# ----------------------------------------------------------------------------
# DATA STRUCTURES
# ----------------------------------------------------------------------------
@dataclass
class VirtualPosition:
    asset: str
    direction: int                  # +1 = short perp (capture positive funding); 0 = flat
    entry_ts: str
    entry_price: float
    notional_usd: float
    units: float
    funding_accrued_usd: float = 0.0
    last_funding_ts: Optional[str] = None


@dataclass
class DaemonState:
    started_at: str
    last_loop_ts: str
    cycle_count: int = 0
    api_error_count_hourly: int = 0
    api_error_window_start: str = ""
    positions: dict = field(default_factory=dict)   # asset → VirtualPosition (as dict)
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    sent_messages: dict = field(default_factory=dict)   # idempotency keys


# ----------------------------------------------------------------------------
# PERSISTENCE
# ----------------------------------------------------------------------------
POSITIONS_PATH = STATE_DIR / "positions.json"
TRADES_PATH    = STATE_DIR / "trades.jsonl"
FUNDING_PATH   = STATE_DIR / "funding_history.parquet"
HEARTBEAT_PATH = STATE_DIR / "heartbeat.txt"
SENT_PATH      = STATE_DIR / "sent_messages.json"
STATE_PATH     = STATE_DIR / "daemon_state.json"


def load_state() -> DaemonState:
    if STATE_PATH.exists():
        try:
            d = json.loads(STATE_PATH.read_text())
            return DaemonState(**d)
        except Exception as e:
            logging.exception("Failed to load state; starting fresh: %s", e)
    now = datetime.now(timezone.utc).isoformat()
    return DaemonState(started_at=now, last_loop_ts=now)


def save_state(state: DaemonState) -> None:
    STATE_PATH.write_text(json.dumps(asdict(state), indent=2, default=str))
    HEARTBEAT_PATH.write_text(state.last_loop_ts)


def append_trade(record: dict) -> None:
    with open(TRADES_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ----------------------------------------------------------------------------
# HYPERLIQUID DATA SOURCE
# ----------------------------------------------------------------------------
def hl_post(payload: dict) -> Optional[dict]:
    """Best-effort POST to HL info endpoint. Returns None on failure."""
    try:
        r = requests.post(HL_INFO_URL, json=payload, timeout=HL_REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.warning("HL API error %s: %s", payload.get("type"), e)
    return None


def fetch_recent_funding(asset: str, hours_back: int = 96) -> Optional[pd.DataFrame]:
    """Fetch the last `hours_back` hours of hourly funding rates for `asset`."""
    start_ms = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp() * 1000)
    raw = hl_post({"type": "fundingHistory", "coin": asset, "startTime": start_ms})
    if not raw:
        return None
    df = pd.DataFrame(raw)
    if df.empty:
        return None
    df["ts"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df["fundingRate"] = df["fundingRate"].astype(float)
    df = df.set_index("ts").sort_index()
    return df[["fundingRate"]]


def fetch_mark_prices() -> Optional[dict]:
    """Returns dict {asset: mark_price_usd} from metaAndAssetCtxs."""
    raw = hl_post({"type": "metaAndAssetCtxs"})
    if not raw or len(raw) < 2:
        return None
    meta, ctxs = raw[0], raw[1]
    out = {}
    for asset_meta, ctx in zip(meta.get("universe", []), ctxs):
        name = asset_meta.get("name")
        if name in ASSETS and "markPx" in ctx:
            out[name] = float(ctx["markPx"])
    return out


# ----------------------------------------------------------------------------
# DECISION LOOP (the actual strategy, lifted from funding_capture.generate_position)
# ----------------------------------------------------------------------------
def desired_signal_for_asset(history: pd.Series) -> int:
    """Apply the V1 funding_capture rules and return the desired position (0 or 1)
    for the current timestamp, given the recent funding history."""
    if len(history) < SMOOTH_HOURS + 1:
        return 0  # warmup
    pos = generate_position(
        history,
        smooth_hours=SMOOTH_HOURS,
        entry_threshold_apr=ENTRY_THRESHOLD_APR,
        exit_threshold_apr=EXIT_THRESHOLD_APR,
        min_hold_hours=MIN_HOLD_HOURS,
        min_flat_hours=MIN_FLAT_HOURS,
    )
    return int(pos.iloc[-1])


# ----------------------------------------------------------------------------
# VIRTUAL EXECUTION
# ----------------------------------------------------------------------------
def open_virtual_short(asset: str, mark_price: float, state: DaemonState, log: JsonLineLogger) -> None:
    """Open a delta-neutral short-perp + long-spot (modelled as +1 funding-collector)."""
    notional = CAPITAL_PER_ASSET_USD
    units = notional / mark_price
    now = datetime.now(timezone.utc).isoformat()
    pos = VirtualPosition(
        asset=asset, direction=+1,
        entry_ts=now, entry_price=mark_price,
        notional_usd=notional, units=units,
        funding_accrued_usd=0.0, last_funding_ts=now,
    )
    state.positions[asset] = asdict(pos)
    rec = {"event": "open", "ts": now, **asdict(pos)}
    append_trade(rec)
    log.log("paper_open", asset=asset, price=mark_price, units=units, notional=notional)


def close_virtual_short(asset: str, mark_price: float, state: DaemonState, log: JsonLineLogger) -> None:
    """Close the position. PnL = funding_accrued (since the spot+perp legs offset on price)."""
    if asset not in state.positions:
        return
    p = state.positions.pop(asset)
    now = datetime.now(timezone.utc).isoformat()
    realized = p["funding_accrued_usd"]   # delta-neutral: price PnL cancels, funding nets out
    state.realized_pnl_usd += realized
    rec = {"event": "close", "ts": now, "asset": asset, "exit_price": mark_price,
           "realized_pnl_usd": realized, "funding_accrued_usd": p["funding_accrued_usd"]}
    append_trade(rec)
    log.log("paper_close", asset=asset, price=mark_price, realized_pnl_usd=realized)


def accrue_funding(asset: str, funding_history: pd.Series, state: DaemonState) -> int:
    """Book any HL funding events for `asset` that are newer than the position's
    last_funding_ts. HL pays funding hourly — we credit notional × rate per event,
    deduplicating against the position's last booked timestamp.

    Returns the number of events booked this cycle (typically 0 or 1).
    """
    if asset not in state.positions:
        return 0
    p = state.positions[asset]
    last_booked = pd.to_datetime(p["last_funding_ts"], utc=True) if p.get("last_funding_ts") else None
    booked = 0
    for ts, rate in funding_history.items():
        if last_booked is not None and ts <= last_booked:
            continue
        p["funding_accrued_usd"] += p["notional_usd"] * float(rate)
        p["last_funding_ts"] = ts.isoformat()
        booked += 1
    state.positions[asset] = p
    return booked


# ----------------------------------------------------------------------------
# ALERTING (Telegram via existing TelegramAlerter)
# ----------------------------------------------------------------------------
def _alerter() -> Optional[TelegramAlerter]:
    if not pt_config.TELEGRAM_ENABLED:
        return None
    return TelegramAlerter()


def maybe_send_heartbeat(state: DaemonState, alerter: Optional[TelegramAlerter]) -> None:
    """Send a daily heartbeat at 12:00 UTC if not already sent today."""
    if alerter is None:
        return
    now = datetime.now(timezone.utc)
    if now.hour != DAILY_HEARTBEAT_UTC_HOUR:
        return
    key = f"heartbeat_{now.date().isoformat()}"
    if key in state.sent_messages:
        return
    open_positions = list(state.positions.keys())
    msg = (f"💚 V2 Day {now.date()} · "
           f"{len(open_positions)} open ({', '.join(open_positions) or 'none'}) · "
           f"realized ${state.realized_pnl_usd:+.2f} · "
           f"cycle #{state.cycle_count} · last loop {state.last_loop_ts}")
    try:
        alerter.send(msg)
        state.sent_messages[key] = now.isoformat()
    except Exception as e:
        logging.warning("heartbeat send failed: %s", e)


def maybe_send_intermediate_report(state: DaemonState, alerter: Optional[TelegramAlerter]) -> None:
    """Send the extended intermediate report on 2026-05-28 at 12:00 UTC."""
    if alerter is None:
        return
    now = datetime.now(timezone.utc)
    if now.date().isoformat() != INTERMEDIATE_REPORT_DATE:
        return
    if now.hour != DAILY_HEARTBEAT_UTC_HOUR:
        return
    key = "intermediate_report"
    if key in state.sent_messages:
        return
    # Count trades from ledger
    n_trades = 0
    if TRADES_PATH.exists():
        with open(TRADES_PATH) as f:
            n_trades = sum(1 for _ in f)
    msg = (f"📊 V2 INTERMEDIATE REPORT (J+8)\n"
           f"Cycles: {state.cycle_count}\n"
           f"Trades logged: {n_trades}\n"
           f"Realized PnL: ${state.realized_pnl_usd:+.2f}\n"
           f"Open positions: {list(state.positions.keys()) or 'none'}\n"
           f"API errors (rolling hour): {state.api_error_count_hourly}\n"
           f"Last successful loop: {state.last_loop_ts}\n"
           f"\nIf this looks healthy, no action needed. Détails complets au retour 3 juin.")
    try:
        alerter.send(msg)
        state.sent_messages[key] = now.isoformat()
    except Exception as e:
        logging.warning("intermediate report send failed: %s", e)


def check_anomalies(state: DaemonState, alerter: Optional[TelegramAlerter]) -> None:
    """Trigger Telegram alerts on serious anomalies."""
    if alerter is None:
        return
    # 1. Big drawdown
    total_capital = CAPITAL_PER_ASSET_USD * len(ASSETS)
    pnl_pct = (state.realized_pnl_usd / total_capital) * 100
    if pnl_pct < ANOMALY_PNL_PCT_TRIGGER and "alert_dd" not in state.sent_messages:
        try:
            alerter.send(f"🚨 V2 ALERTE — PnL {pnl_pct:+.2f}% < {ANOMALY_PNL_PCT_TRIGGER}% threshold. "
                         f"Check daemon. realized=${state.realized_pnl_usd:.2f}")
            state.sent_messages["alert_dd"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            pass
    # 2. API error rate
    if state.api_error_count_hourly >= ANOMALY_API_ERRORS_PER_HOUR and "alert_api" not in state.sent_messages:
        try:
            alerter.send(f"🚨 V2 ALERTE — {state.api_error_count_hourly} API errors in the past hour.")
            state.sent_messages["alert_api"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# MAIN LOOP
# ----------------------------------------------------------------------------
RUNNING = True
def _sigterm(signum, frame):
    global RUNNING
    RUNNING = False
    logging.info("Received signal %s, draining loop and exiting cleanly.", signum)
signal.signal(signal.SIGTERM, _sigterm)
signal.signal(signal.SIGINT,  _sigterm)


def run_one_cycle(state: DaemonState, log: JsonLineLogger, alerter: Optional[TelegramAlerter],
                  dry: bool = False) -> None:
    state.cycle_count += 1
    now = datetime.now(timezone.utc)
    state.last_loop_ts = now.isoformat()

    # 1. Fetch mark prices
    mark_prices = fetch_mark_prices() or {}
    if not mark_prices:
        state.api_error_count_hourly += 1

    # 2. For each asset: fetch funding history, decide, execute
    for asset in ASSETS:
        history = fetch_recent_funding(asset, hours_back=96)
        if history is None or history.empty:
            state.api_error_count_hourly += 1
            continue
        history_ser = history["fundingRate"]
        signal = desired_signal_for_asset(history_ser)
        mark = mark_prices.get(asset)
        if mark is None:
            continue

        current_holding = asset in state.positions

        if not dry:
            # Decision: if signal=1 and not holding → OPEN; if signal=0 and holding → CLOSE
            if signal == 1 and not current_holding:
                open_virtual_short(asset, mark, state, log)
            elif signal == 0 and current_holding:
                close_virtual_short(asset, mark, state, log)
            elif current_holding:
                # Holding: book any HL funding events newer than last seen
                # (HL pays hourly — accrue exactly the new events, not "every cycle")
                booked = accrue_funding(asset, history_ser, state)
                if booked:
                    log.log("funding_booked", asset=asset, n_events=booked)

    # 3. Persist
    save_state(state)

    # 4. Alerting
    check_anomalies(state, alerter)
    maybe_send_heartbeat(state, alerter)
    maybe_send_intermediate_report(state, alerter)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run one cycle and exit")
    p.add_argument("--dry",  action="store_true", help="Decide signals but do not execute virtual trades")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / f"daemon_{datetime.utcnow().date().isoformat()}.log"),
            logging.StreamHandler(),
        ],
    )

    state = load_state()
    log = JsonLineLogger(LOG_DIR)
    alerter = _alerter()

    logging.info("Daemon boot — cycle %d, %d open positions, realized=%s",
                 state.cycle_count, len(state.positions), state.realized_pnl_usd)

    if args.once:
        run_one_cycle(state, log, alerter, dry=args.dry)
        return

    while RUNNING:
        try:
            run_one_cycle(state, log, alerter, dry=args.dry)
        except Exception as e:
            logging.exception("Cycle failed: %s", e)
            state.api_error_count_hourly += 1
            save_state(state)
        # Sleep, but interruptible
        for _ in range(LOOP_INTERVAL_SEC):
            if not RUNNING:
                break
            time.sleep(1)

    logging.info("Daemon exiting cleanly.")


if __name__ == "__main__":
    main()
