"""
paper_funding_capture.py — Autonomous live paper-trading daemon
================================================================

Phase 3 design (2026-06-27 operator-validated): BTC+ETH always-in
delta-neutre, $1k × 2 = $2k total notional hardcoded, marathon 365 jours
observation. Empirical Phase 2 closure verdict P33: filter family
dominated by always-in baseline (cf. PHASE2_SESSION_DIGEST_2026-06-26.md).

Strategy mechanics: short perp + long spot at equal notional cancels
mark drift, funding rate captured as pure PnL. No entry/exit signal
filtering — daemon always holds both legs delta-neutre.

Original deployment context preserved below for archival continuity:
> Drives the funding_capture strategy on Hyperliquid PUBLIC funding/price
> data, without touching real capital. Originally launched continuously
> on Badoun's Mac for the 22 May → 2 June 2026 absence window. Migrated
> to VPS Hetzner systemd post-Phase 2 closure for marathon Phase 3.

Architecture (Phase 3)
----------------------
  fetch_loop (every 5 min):
      1. Pull latest fundingHistory + mark prices from api.hyperliquid.xyz/info
      2. Append to state/funding_history.parquet
      3. For each asset (BTC, ETH):
          a. desired_signal_for_asset() → always 1 (Phase 3 always-in)
          b. If not held → open delta-neutral position
          c. If holding → accrue funding payments
      4. Phase 3 safeguards (planned, implementation Phase 2 of plan):
          A. Kill switch DD < -1% / 24h → auto-flat + PENDING_USER_VALIDATION
          E. Position size cap hardcoded $1k/asset, $2k total
          F. PENDING_USER_VALIDATION boot-state machine + /v2_resume YES
      5. Persist state, write heartbeat
      6. Check anomaly thresholds; fire Telegram alert if any
      7. If 12:00 UTC daily → send heartbeat message
      8. If 2026-05-28 and not yet sent → send intermediate report (legacy)

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

# --- Phase 3 design (v2 operator-validated 2026-06-27) ----------------------
# Empirical evidence Phase 2 closure (cf. analysis/PHASE2_SESSION_DIGEST_2026-06-26.md):
# - 8 hypotheses tested under P33 No-Skip discipline
# - Filter family dominated by trivial always-in baseline across all configs
# - SOL killer asset: H4 friction-realistic = $90 fees > $24 gross PnL
# - Winner: BTC+ETH always-in delta-neutre = $1 686 OOS 13.5 mois, max DD -0.33%
# - Sizing: $1 000 × 2 assets = $2 000 total notional, equal weight, hardcoded
ASSETS = ["BTC", "ETH"]            # Phase 3: SOL dropped (H4 P33-validated)
CAPITAL_PER_ASSET_USD = 1_000.0    # Phase 3: $1k BTC + $1k ETH = $2k total notional (hardcoded)
LOOP_INTERVAL_SEC = 300            # 5 min

# --- DEPRECATED Phase 3 — Filter design constants (kept for rollback compat) -
# Phase 2 verdict P33: filter design empirically dominated by always-in baseline.
# These constants are NO LONGER USED in the active code path. Preserved here
# strictly to allow emergency rollback to Phase 2 filter design without
# rewriting imports. See production/phase3_rollback_protocol.md.
# DO NOT REFERENCE in new code — strategy is now always-in delta-neutre.
SMOOTH_HOURS = 24                  # DEPRECATED Phase 3
ENTRY_THRESHOLD_APR = 0.005        # DEPRECATED Phase 3
EXIT_THRESHOLD_APR = -0.005        # DEPRECATED Phase 3
MIN_HOLD_HOURS = 24                # DEPRECATED Phase 3
MIN_FLAT_HOURS = 24                # DEPRECATED Phase 3

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

# --- Phase 3 Safeguards HARDCODED (2026-06-28) -------------------------------
# These thresholds are HARDCODED in source — NOT externalized to config — to
# prevent silent tampering during the 365-day marathon. Modification requires
# explicit code change + snapshot + Sebastien validation. Cf. §10 of
# production/phase3_deployment_spec.md for the design rationale (NATIVE
# implementation, no cice.RiskGate wrap).

# Safeguard A — Kill switch on 24h rolling drawdown
KILL_SWITCH_DD_THRESHOLD_PCT = -1.0     # if DD < -1.0% of TOTAL_CAPITAL_BASE → flatten + halt
KILL_SWITCH_LOOKBACK_HOURS = 24         # rolling peak window

# Safeguard E — Position notional hard caps
MAX_POSITION_NOTIONAL_USD = 1_000.0     # per-asset cap (matches CAPITAL_PER_ASSET_USD)
MAX_TOTAL_NOTIONAL_USD = 2_000.0        # portfolio total cap ($1k BTC + $1k ETH)

# Safeguard F — IPC emergency command consumer
EMERGENCY_COMMAND_FILE = STATE_DIR / "emergency_command.json"
EMERGENCY_COMMAND_MAX_AGE_SEC = 600     # 10 min — older commands marked consumed-no-action

# Derived: capital base used as DD denominator (constant, immune to flat-state)
TOTAL_CAPITAL_BASE = CAPITAL_PER_ASSET_USD * len(ASSETS)   # $2_000.0 for BTC+ETH @ $1k each


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
    # --- Phase 3 safeguards A + F schema migration (2026-06-28) -------------
    # NORMAL = run cycle fully; PENDING_USER_VALIDATION = skip position actions,
    # heartbeat + IPC consumer only, await /v2_resume YES.
    mode: str = "NORMAL"
    # 24h rolling equity peak for Safeguard A kill switch
    equity_peak_24h: float = 0.0
    equity_peak_24h_window_start: str = ""   # ISO timestamp; "" means uninitialized
    kill_switch_triggered_at: Optional[str] = None
    # Safeguard F IPC idempotency — last command file timestamp we already consumed
    last_command_consumed_ts: Optional[str] = None


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
    """Phase 3 always-in design: always returns 1 (delta-neutral position held).

    Empirical evidence Phase 2 closure (analysis/PHASE2_SESSION_DIGEST_2026-06-26.md):
    8 hypotheses tested under P33 No-Skip discipline. Filter family
    empirically dominated by trivial always-in baseline across all
    configurations tested (H1 min_hold extension, H2 entry threshold sweep,
    H3 asset filter exclusion, H4 friction-realistic, H6 circuit breaker).

    Verdict P33-validated:
        Best filter design (BTC+ETH min_hold=60h, entry 0.015 APR):
            $1 095 OOS — 35% under benchmark FAIL beat-trivial
        Pure always-in BTC+ETH delta-neutre:
            $1 686 OOS, max DD -0.33% — WINNER, robust, no parameter

    The delta-neutral mechanics (short perp + long spot at equal notional)
    cancel mark drift by design, leaving funding rate as pure PnL source.
    Cf. open_virtual_short() L230, close_virtual_short() L246 mechanics.

    The `history` argument is preserved for signature compatibility (the
    daemon calls this function per-asset per-cycle with the funding series)
    but is no longer used to make the entry/exit decision.

    DEPRECATED filter path preserved in commented constants above for
    rollback compatibility per production/phase3_rollback_protocol.md.
    """
    return 1


# ----------------------------------------------------------------------------
# VIRTUAL EXECUTION
# ----------------------------------------------------------------------------
def open_virtual_short(
    asset: str,
    mark_price: float,
    state: DaemonState,
    log: JsonLineLogger,
    alerter: Optional[TelegramAlerter] = None,
) -> bool:
    """Open a delta-neutral short-perp + long-spot (modelled as +1 funding-collector).

    Returns True on success, False if Safeguard E (position cap) blocked the open.
    """
    notional = CAPITAL_PER_ASSET_USD
    # Safeguard E — enforce hard caps BEFORE allocating
    allowed, reason = enforce_position_cap(asset, notional, state, log, alerter)
    if not allowed:
        # alerter + log handled inside enforce_position_cap
        return False
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
    return True


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
# PHASE 3 SAFEGUARDS — A (kill switch), E (position cap), F (PENDING_USER_VALIDATION)
# ----------------------------------------------------------------------------
# Native implementation per phase3_deployment_spec.md §10 (RiskGate analysis).
# All thresholds HARDCODED above. State machine F coupled to A (kill switch
# triggers transition NORMAL → PENDING_USER_VALIDATION). IPC bridge with the
# Telegram listener (live/telegram_command_listener.py Phase 1 safeguard D)
# happens via live/state/emergency_command.json.

def compute_portfolio_equity(state: DaemonState) -> float:
    """Phase 3 portfolio equity = realized funding + currently-accrued funding.

    Since all V2 positions are delta-neutral (short perp + long spot at equal
    notional, see open_virtual_short L230), the mark drift cancels by design.
    The ONLY contribution to PnL is funding rate. Therefore portfolio equity
    relative to baseline = sum of funding accrued (realized + open).

    Returns USD value, positive = profit since daemon start, negative = loss.
    """
    open_funding = sum(p.get("funding_accrued_usd", 0.0) for p in state.positions.values())
    return state.realized_pnl_usd + open_funding


def update_equity_peak_24h(state: DaemonState, equity_now: float) -> None:
    """Maintain a 24h rolling peak of portfolio equity for Safeguard A.

    Window semantics:
      - If window uninitialized OR > 24h old → reset window, peak = equity_now.
      - Otherwise → peak = max(stored peak, equity_now).

    Sliding via reset (not strict per-second sliding) keeps state simple and
    avoids storing a history series. Worst-case the kill switch threshold is
    measured against a slightly older peak — acceptable for emergency design.
    """
    now = datetime.now(timezone.utc)
    if not state.equity_peak_24h_window_start:
        state.equity_peak_24h_window_start = now.isoformat()
        state.equity_peak_24h = equity_now
        return
    try:
        window_start = datetime.fromisoformat(state.equity_peak_24h_window_start)
    except ValueError:
        # Corrupted timestamp — reset window defensively.
        state.equity_peak_24h_window_start = now.isoformat()
        state.equity_peak_24h = equity_now
        return
    age = now - window_start
    if age > timedelta(hours=KILL_SWITCH_LOOKBACK_HOURS):
        state.equity_peak_24h_window_start = now.isoformat()
        state.equity_peak_24h = equity_now
    else:
        state.equity_peak_24h = max(state.equity_peak_24h, equity_now)


def check_kill_switch(state: DaemonState) -> tuple[bool, float]:
    """Safeguard A: returns (triggered, dd_pct) using 24h rolling peak.

    DD% denominator = TOTAL_CAPITAL_BASE (constant $2_000.0 for BTC+ETH @ $1k).
    Using the capital base instead of sum-of-open-notional avoids the
    edge case where flat positions ⇒ denominator = 0 ⇒ kill switch
    silently disabled. Triggered when dd_pct < KILL_SWITCH_DD_THRESHOLD_PCT.
    """
    equity_now = compute_portfolio_equity(state)
    update_equity_peak_24h(state, equity_now)
    peak = state.equity_peak_24h
    dd_pct = (equity_now - peak) / TOTAL_CAPITAL_BASE * 100.0
    triggered = dd_pct < KILL_SWITCH_DD_THRESHOLD_PCT
    return triggered, dd_pct


def flat_all_positions(
    state: DaemonState,
    log: JsonLineLogger,
    alerter: Optional[TelegramAlerter],
    reason: str,
    mark_prices: Optional[dict] = None,
) -> int:
    """Close every open position immediately. Used by Safeguards A + F.

    Returns the number of positions closed. Idempotent — calling with no
    open positions is a no-op (returns 0). All closes use the supplied
    mark_prices map (key=asset) when available; falls back to last-known
    entry price if not — acceptable since funding is already accrued and
    price cancels in delta-neutral PnL anyway.
    """
    if not state.positions:
        log.log("flat_all_noop", reason=reason)
        return 0
    n = 0
    for asset in list(state.positions.keys()):
        # Use mark from this cycle, or entry price as fallback (delta-neutral
        # makes the actual exit price immaterial for PnL — only funding matters).
        mark = (mark_prices or {}).get(asset) or float(state.positions[asset].get("entry_price", 0.0))
        close_virtual_short(asset, mark, state, log)
        n += 1
    log.log("flat_all_executed", reason=reason, n_closed=n)
    if alerter is not None:
        try:
            alerter.send(
                f"🚨 V2 FLAT-ALL executed — reason: {reason}. "
                f"Closed {n} positions. "
                f"State now: {state.mode}."
            )
        except Exception as e:  # noqa: BLE001
            logging.warning("flat_all Telegram alert failed: %s", e)
    return n


def enforce_position_cap(
    asset: str,
    notional_usd: float,
    state: DaemonState,
    log: JsonLineLogger,
    alerter: Optional[TelegramAlerter],
) -> tuple[bool, str]:
    """Safeguard E: returns (allowed, reason). Blocks position open if any cap violated.

    Two hard caps checked:
      1. Per-asset: notional_usd > MAX_POSITION_NOTIONAL_USD
      2. Portfolio total after open: sum(open) + notional_usd > MAX_TOTAL_NOTIONAL_USD
    """
    if notional_usd > MAX_POSITION_NOTIONAL_USD + 1e-9:
        reason = (
            f"per-asset cap violation: tried {asset} ${notional_usd:.2f} > "
            f"max ${MAX_POSITION_NOTIONAL_USD:.2f}"
        )
        log.log("safeguard_E_per_asset_block", asset=asset, attempted=notional_usd, cap=MAX_POSITION_NOTIONAL_USD)
        if alerter is not None:
            try:
                alerter.send(f"🚨 V2 SAFEGUARD E — {reason}. Open REFUSED.")
            except Exception as e:  # noqa: BLE001
                logging.warning("safeguard E alert failed: %s", e)
        return False, reason
    open_total = sum(p.get("notional_usd", 0.0) for p in state.positions.values())
    projected_total = open_total + notional_usd
    if projected_total > MAX_TOTAL_NOTIONAL_USD + 1e-9:
        reason = (
            f"total cap violation: projected ${projected_total:.2f} > "
            f"max ${MAX_TOTAL_NOTIONAL_USD:.2f} (open ${open_total:.2f} + new ${notional_usd:.2f})"
        )
        log.log("safeguard_E_total_block", projected=projected_total, cap=MAX_TOTAL_NOTIONAL_USD)
        if alerter is not None:
            try:
                alerter.send(f"🚨 V2 SAFEGUARD E — {reason}. Open REFUSED.")
            except Exception as e:  # noqa: BLE001
                logging.warning("safeguard E alert failed: %s", e)
        return False, reason
    return True, "ok"


def consume_emergency_command(
    state: DaemonState,
    log: JsonLineLogger,
    alerter: Optional[TelegramAlerter],
    mark_prices: Optional[dict] = None,
) -> Optional[str]:
    """Safeguard F: read live/state/emergency_command.json and act if fresh.

    IPC pattern with the Telegram listener (Phase 1 safeguard D). The listener
    writes the file atomically when `/v2_flat YES` or `/v2_resume YES` is
    received from the whitelisted chat_id.

    This consumer:
      1. If file absent → return None (no-op).
      2. Parse the JSON; if malformed → log error, return None.
      3. Check `consumed` flag → if True, no-op (already processed).
      4. Check timestamp age → if > 10 min, mark consumed-stale and skip.
      5. Check idempotency (state.last_command_consumed_ts) → if already
         processed THIS exact timestamp, no-op.
      6. Execute action ("flat" → flat_all + transition to
         PENDING_USER_VALIDATION; "resume" → transition to NORMAL).
      7. Write consumed=true back to file (atomic) and update state.

    Returns the action string executed, or None if no fresh command.
    """
    if not EMERGENCY_COMMAND_FILE.exists():
        return None
    try:
        payload = json.loads(EMERGENCY_COMMAND_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logging.warning("emergency_command.json read/parse failed: %s", e)
        return None
    if payload.get("consumed"):
        return None
    cmd_ts_raw = payload.get("timestamp", "")
    if state.last_command_consumed_ts == cmd_ts_raw:
        # Already consumed this exact command (race with persistence flush).
        return None
    # Staleness guard
    try:
        cmd_ts = datetime.fromisoformat(cmd_ts_raw)
    except ValueError:
        logging.warning("emergency_command.json bad timestamp: %r — marking consumed-no-action", cmd_ts_raw)
        _mark_consumed(EMERGENCY_COMMAND_FILE, payload)
        state.last_command_consumed_ts = cmd_ts_raw
        return None
    age = (datetime.now(timezone.utc) - cmd_ts).total_seconds()
    if age > EMERGENCY_COMMAND_MAX_AGE_SEC:
        log.log("safeguard_F_stale_command_skipped", age_sec=age, cmd_ts=cmd_ts_raw)
        _mark_consumed(EMERGENCY_COMMAND_FILE, payload)
        state.last_command_consumed_ts = cmd_ts_raw
        if alerter is not None:
            try:
                alerter.send(
                    f"⚠️ V2 Safeguard F — stale command ignored "
                    f"(age {int(age)}s > {EMERGENCY_COMMAND_MAX_AGE_SEC}s): {payload.get('command')}"
                )
            except Exception:  # noqa: BLE001
                pass
        return None
    # Fresh command — execute
    cmd = payload.get("command")
    issued_by = payload.get("issued_by_chat_id", "unknown")
    log.log("safeguard_F_command_received", command=cmd, age_sec=age, issued_by=issued_by)
    if cmd == "flat":
        if state.mode == "PENDING_USER_VALIDATION":
            # No-op: already in pending state
            log.log("safeguard_F_flat_noop_already_pending")
            if alerter is not None:
                try:
                    alerter.send("ℹ️ V2 — /v2_flat YES received but daemon already in PENDING_USER_VALIDATION. No-op.")
                except Exception:  # noqa: BLE001
                    pass
        else:
            flat_all_positions(state, log, alerter, reason="manual_v2_flat_command", mark_prices=mark_prices)
            state.mode = "PENDING_USER_VALIDATION"
            state.kill_switch_triggered_at = None  # this was manual, not auto
            if alerter is not None:
                try:
                    alerter.send(
                        f"🚨 V2 MANUAL FLAT executed by Telegram command (chat_id {issued_by}). "
                        f"State: PENDING_USER_VALIDATION. Resume requires /v2_resume YES."
                    )
                except Exception:  # noqa: BLE001
                    pass
    elif cmd == "resume":
        if state.mode == "NORMAL":
            log.log("safeguard_F_resume_noop_already_normal")
            if alerter is not None:
                try:
                    alerter.send("ℹ️ V2 — /v2_resume YES received but daemon already NORMAL. No-op.")
                except Exception:  # noqa: BLE001
                    pass
        else:
            state.mode = "NORMAL"
            log.log("safeguard_F_resume_executed")
            if alerter is not None:
                try:
                    alerter.send(
                        f"✅ V2 RESUMED to NORMAL by Telegram command (chat_id {issued_by}). "
                        f"Daemon will re-open positions on next cycle."
                    )
                except Exception:  # noqa: BLE001
                    pass
    else:
        logging.warning("safeguard F unknown command: %r — marking consumed-no-action", cmd)
    _mark_consumed(EMERGENCY_COMMAND_FILE, payload)
    state.last_command_consumed_ts = cmd_ts_raw
    return cmd


def _mark_consumed(path: Path, payload: dict) -> None:
    """Atomically rewrite the command file with consumed=true to prevent replay."""
    payload = dict(payload)
    payload["consumed"] = True
    payload["consumed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        tmp.replace(path)
    except OSError as e:
        logging.warning("failed to mark emergency command consumed: %s", e)


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
    """Phase 3 run_one_cycle with native Safeguards A + E + F integration.

    Order of operations (P32 — each step's failure mode contained):
      1. Bookkeeping (cycle counter, timestamp)
      2. Fetch market data (mark prices + funding histories cached)
      3. Safeguard F — consume any pending IPC emergency_command.json
         (may transition state.mode to/from PENDING_USER_VALIDATION)
      4. If state.mode == PENDING_USER_VALIDATION → heartbeat-only, return
      5. Pass 1: accrue funding on currently-held positions (updates equity)
      6. Safeguard A — check kill switch with updated equity
         (if triggered → flat_all + transition to PENDING_USER_VALIDATION)
      7. Pass 2: signal-driven open/close (Phase 3 always-in → always open
         non-held assets; close branch preserved for rollback compat)
      8. Persist state + alerting
    """
    state.cycle_count += 1
    now = datetime.now(timezone.utc)
    state.last_loop_ts = now.isoformat()

    # 1. Fetch mark prices
    mark_prices = fetch_mark_prices() or {}
    if not mark_prices:
        state.api_error_count_hourly += 1

    # 2. Cache funding histories once per cycle (avoid double-fetch)
    funding_cache: dict = {}
    for asset in ASSETS:
        h = fetch_recent_funding(asset, hours_back=96)
        if h is None or h.empty:
            state.api_error_count_hourly += 1
            continue
        funding_cache[asset] = h["fundingRate"]

    # 3. Safeguard F — consume any pending IPC command (may flip state.mode)
    consume_emergency_command(state, log, alerter, mark_prices=mark_prices)

    # 4. PENDING_USER_VALIDATION → skip position actions entirely
    if state.mode == "PENDING_USER_VALIDATION":
        log.log("cycle_skipped_pending_user_validation", cycle=state.cycle_count)
        save_state(state)
        check_anomalies(state, alerter)
        maybe_send_heartbeat(state, alerter)
        return

    # 5. Pass 1 — accrue funding on currently-held positions (updates equity)
    if not dry:
        for asset, history_ser in funding_cache.items():
            if asset in state.positions:
                booked = accrue_funding(asset, history_ser, state)
                if booked:
                    log.log("funding_booked", asset=asset, n_events=booked)

    # 6. Safeguard A — check kill switch using updated equity
    triggered, dd_pct = check_kill_switch(state)
    if triggered:
        log.log("safeguard_A_kill_switch_fired", dd_pct=dd_pct,
                peak=state.equity_peak_24h, threshold=KILL_SWITCH_DD_THRESHOLD_PCT)
        flat_all_positions(state, log, alerter,
                           reason=f"kill_switch_dd_{dd_pct:.2f}pct", mark_prices=mark_prices)
        state.mode = "PENDING_USER_VALIDATION"
        state.kill_switch_triggered_at = now.isoformat()
        if alerter is not None:
            try:
                alerter.send(
                    f"🚨 V2 KILL SWITCH FIRED — DD {dd_pct:+.2f}% < threshold "
                    f"{KILL_SWITCH_DD_THRESHOLD_PCT}% (24h rolling peak ${state.equity_peak_24h:.2f}, "
                    f"base ${TOTAL_CAPITAL_BASE:.0f}). All positions FLAT. "
                    f"State: PENDING_USER_VALIDATION. To resume after investigation: /v2_resume YES."
                )
            except Exception as e:  # noqa: BLE001
                logging.warning("kill switch Telegram alert failed: %s", e)
        save_state(state)
        return

    # 7. Pass 2 — signal-driven open/close (Phase 3: always-in for non-held)
    if not dry:
        for asset in ASSETS:
            if asset not in funding_cache:
                continue
            mark = mark_prices.get(asset)
            if mark is None:
                continue
            signal = desired_signal_for_asset(funding_cache[asset])
            current_holding = asset in state.positions
            if signal == 1 and not current_holding:
                # Safeguard E enforced inside open_virtual_short (returns False if blocked)
                open_virtual_short(asset, mark, state, log, alerter)
            elif signal == 0 and current_holding:
                # Rollback-compat path: filter design could return 0; close gracefully.
                close_virtual_short(asset, mark, state, log)

    # 8. Persist + alerting
    save_state(state)
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

    logging.info("Daemon boot — cycle %d, %d open positions, realized=%s, mode=%s",
                 state.cycle_count, len(state.positions), state.realized_pnl_usd, state.mode)

    # Safeguard F — boot-time sanity check.
    # If the previous run left the daemon in PENDING_USER_VALIDATION (e.g. after
    # a kill switch fire or a manual /v2_flat YES), DO NOT silently resume on
    # restart. Surface the condition via Telegram and wait for /v2_resume YES.
    if state.mode == "PENDING_USER_VALIDATION":
        msg = (
            f"⚠️ V2 BOOT — daemon resumed in PENDING_USER_VALIDATION state. "
            f"Previous incident: kill_switch_triggered_at={state.kill_switch_triggered_at or 'unknown'}. "
            f"No position actions will be taken until /v2_resume YES is received via Telegram. "
            f"Investigate logs in {LOG_DIR}/ before resuming."
        )
        logging.warning(msg)
        log.log("boot_pending_user_validation_detected",
                kill_switch_triggered_at=state.kill_switch_triggered_at,
                cycle_count=state.cycle_count)
        if alerter is not None:
            try:
                alerter.send(msg)
            except Exception as e:  # noqa: BLE001
                logging.warning("boot pending-user-validation Telegram alert failed: %s", e)

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
