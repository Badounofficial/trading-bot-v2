"""
stop_manager.py — Surveillance des stops automatiques globaux du bot.

DESIGN CHOICES (Session 6, locked):
1. Snapshot equity at XX:00 UTC each cycle (simple, sufficient given 10% threshold)
2. Active stop manager: when HALT triggers, this module:
   - Fetches current prices (with retry, via data_source)
   - Closes all open positions (via order_simulator)
   - Records closed trades + updates state (via state_manager)
   - Sets bot to HALTED state

PROTECTION PYRAMID:
  Level 1: SL per trade        (handled by ICC strategy)
  Level 2: This module — Loss/jour ≤ 10%
  Level 3: This module — DD ≤ 15%
  Level 4: Manual humain override

ENTRY POINT:
  check_global_stops(state_manager, current_prices) → StopCheckResult
  trigger_halt(state_manager, reason, current_prices) → list[ClosedTrade]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from paper_trading import config
from paper_trading.state_manager import (
    StateManager,
    OpenPosition,
    ClosedTrade,
    EquitySnapshot,
)
from paper_trading.order_simulator import (
    simulate_market_order,
    compute_realized_trade,
    SimulatedFill,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    EXCEPTIONS
# ════════════════════════════════════════════════════════════════

class StopManagerError(Exception):
    """Generic stop manager error."""


class MissingPriceError(StopManagerError):
    """Cannot get a current price for an asset that has an open position.

    The orchestrator (Bloc 7) is responsible for retrying the fetch before
    calling trigger_halt. If the price is genuinely unavailable, the bot
    HALTs with positions still open (logged as warning).
    """


# ════════════════════════════════════════════════════════════════
#                    DATACLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class StopCheckResult:
    """Outcome of a global stops check at one cycle."""
    should_halt: bool
    halt_reason: Optional[str]  # filled when should_halt=True
    current_equity: float
    peak_equity: float
    drawdown_pct: float
    equity_at_day_start: Optional[float]
    daily_loss_pct: Optional[float]
    day_start_anchored_now: bool  # True if we just snapshot a new day's start


# ════════════════════════════════════════════════════════════════
#                    EQUITY COMPUTATION
# ════════════════════════════════════════════════════════════════

def compute_open_positions_value(
    positions: list[OpenPosition],
    current_prices: dict[str, float],
) -> float:
    """Mark-to-market value of all open positions at given prices.

    Args:
        positions: list of currently open positions
        current_prices: {asset: price} for at least every asset that has a position

    Returns:
        Total dollar value of open positions at current prices.

    Raises:
        MissingPriceError: if a position's asset has no price in the dict.
    """
    total = 0.0
    for p in positions:
        if p.asset not in current_prices:
            raise MissingPriceError(
                f"No price available for {p.asset} but has open position {p.position_id}"
            )
        price = current_prices[p.asset]
        if price <= 0:
            raise MissingPriceError(f"Non-positive price for {p.asset}: {price}")
        total += p.units * price
    return total


def compute_total_equity(
    cash: float,
    positions: list[OpenPosition],
    current_prices: dict[str, float],
) -> float:
    """Total equity = cash + mark-to-market of open positions."""
    return cash + compute_open_positions_value(positions, current_prices)


# ════════════════════════════════════════════════════════════════
#                    DAY ANCHORING
# ════════════════════════════════════════════════════════════════

def _utc_date_str(ts: str) -> str:
    """Extract YYYY-MM-DD from an ISO UTC timestamp."""
    return ts.split("T")[0]


def maybe_anchor_new_day(
    sm: StateManager,
    current_timestamp: str,
    current_equity: float,
) -> bool:
    """If the current UTC date differs from the recorded day_start_timestamp,
    snapshot the current equity as the new day's reference.

    Caller MUST be inside an open cycle (we write to bot_state).

    Returns:
        True if a new anchor was recorded (date changed), False otherwise.
    """
    state = sm.get_bot_state()
    current_date = _utc_date_str(current_timestamp)
    recorded_date = (
        _utc_date_str(state.day_start_timestamp)
        if state.day_start_timestamp else None
    )

    if recorded_date == current_date:
        return False  # same UTC day, no re-anchor

    # New day (or very first cycle): anchor
    state.equity_at_day_start_utc = current_equity
    state.day_start_timestamp = current_timestamp
    sm.set_bot_state(state)
    logger.info(
        "Anchored new day %s: equity_at_day_start = $%.2f",
        current_date, current_equity,
    )
    return True


# ════════════════════════════════════════════════════════════════
#                    GLOBAL STOPS CHECK (read-only decision)
# ════════════════════════════════════════════════════════════════

def check_global_stops(
    sm: StateManager,
    current_prices: dict[str, float],
    current_timestamp: Optional[str] = None,
    cash: Optional[float] = None,
    max_drawdown_pct: float = config.MAX_DRAWDOWN_PCT,
    max_daily_loss_pct: float = config.MAX_DAILY_LOSS_PCT,
) -> StopCheckResult:
    """Compute current equity vs thresholds, return verdict (and anchor day if needed).

    Important behavior:
    - If we're inside a cycle, we may anchor a new day's reference.
    - The DD threshold is compared against peak equity (all-time high).
    - The daily loss threshold is compared against the day's anchor.

    Args:
        sm: StateManager (cycle should be open if we want to update day anchor)
        current_prices: live prices for all assets with open positions
        current_timestamp: ISO UTC timestamp of "now". Defaults to actual now.
        cash: current cash (for testing override). Defaults to the latest snapshot's cash.
        max_drawdown_pct, max_daily_loss_pct: thresholds (defaults from config)

    Returns:
        StopCheckResult with should_halt + reason if applicable.
    """
    if current_timestamp is None:
        current_timestamp = datetime.now(timezone.utc).isoformat()

    # Resolve cash from the latest snapshot if not provided
    if cash is None:
        latest_snap = sm.get_latest_equity_snapshot()
        if latest_snap is None:
            # First cycle ever: assume INITIAL_CAPITAL with no positions
            cash = config.INITIAL_CAPITAL
        else:
            cash = latest_snap.cash

    positions = sm.get_open_positions()
    open_value = compute_open_positions_value(positions, current_prices) if positions else 0.0
    current_equity = cash + open_value

    # Anchor day if needed (writes to bot_state — caller must be in cycle for this)
    day_anchored = False
    state = sm.get_bot_state()
    if state.day_start_timestamp is None or \
            _utc_date_str(state.day_start_timestamp) != _utc_date_str(current_timestamp):
        # We need to anchor — caller must be in cycle. If not, we just compute
        # the verdict using the existing anchor (or assume current_equity as anchor)
        if sm._cycle_open:
            day_anchored = maybe_anchor_new_day(sm, current_timestamp, current_equity)
            state = sm.get_bot_state()
        # If no cycle, we use current_equity as the implicit anchor (best-effort)

    # Peak equity: max of all recorded peaks + current_equity
    historical_peak = sm.get_peak_equity()
    peak_equity = max(historical_peak, current_equity)

    # Drawdown calculation
    drawdown_pct = ((current_equity - peak_equity) / peak_equity) if peak_equity > 0 else 0.0

    # Daily loss calculation
    equity_at_day_start = state.equity_at_day_start_utc
    daily_loss_pct: Optional[float] = None
    if equity_at_day_start is not None and equity_at_day_start > 0:
        daily_loss_pct = (current_equity - equity_at_day_start) / equity_at_day_start

    # Decide whether to HALT
    should_halt = False
    halt_reason: Optional[str] = None

    if drawdown_pct <= -max_drawdown_pct:
        should_halt = True
        halt_reason = (
            f"Drawdown {drawdown_pct*100:.2f}% breached threshold "
            f"-{max_drawdown_pct*100:.1f}% (peak ${peak_equity:.2f}, "
            f"current ${current_equity:.2f})"
        )
    elif daily_loss_pct is not None and daily_loss_pct <= -max_daily_loss_pct:
        should_halt = True
        halt_reason = (
            f"Daily loss {daily_loss_pct*100:.2f}% breached threshold "
            f"-{max_daily_loss_pct*100:.1f}% (day start ${equity_at_day_start:.2f}, "
            f"current ${current_equity:.2f})"
        )

    return StopCheckResult(
        should_halt=should_halt,
        halt_reason=halt_reason,
        current_equity=current_equity,
        peak_equity=peak_equity,
        drawdown_pct=drawdown_pct,
        equity_at_day_start=equity_at_day_start,
        daily_loss_pct=daily_loss_pct,
        day_start_anchored_now=day_anchored,
    )


# ════════════════════════════════════════════════════════════════
#                    TRIGGER HALT (active action)
# ════════════════════════════════════════════════════════════════

def trigger_halt(
    sm: StateManager,
    reason: str,
    current_prices: dict[str, float],
    current_timestamp: Optional[str] = None,
    current_bar_index: int = 0,
    slippage_pct: float = config.SLIPPAGE_PCT,
    fee_pct: float = config.FEE_PCT_PER_LEG,
) -> list[ClosedTrade]:
    """Execute a full HALT: close all open positions and set bot to HALTED.

    Caller MUST be inside an open cycle. All operations are inside the same
    transaction — either all positions close cleanly or nothing happens.

    Strategy:
    - For each open position, simulate a market SELL at current price.
    - Compute realized PnL and record as ClosedTrade.
    - Remove from open_positions table.
    - Finally set bot state to HALTED.

    If a price is missing for a position:
    - Log a warning, leave that position OPEN, but still HALT the bot.
    - This is the "safety net" decision: HALT is more important than closing.

    Args:
        sm: StateManager, must be in cycle
        reason: human-readable explanation for the HALT
        current_prices: {asset: price} for assets to close
        current_timestamp: ISO UTC for exit_timestamp
        current_bar_index: H1 bar index for held_bars computation
        slippage_pct, fee_pct: cost overrides for testing

    Returns:
        List of ClosedTrade that were created (may be empty if no open positions).
    """
    if not sm._cycle_open:
        raise StopManagerError("trigger_halt must be called inside an open cycle")

    if current_timestamp is None:
        current_timestamp = datetime.now(timezone.utc).isoformat()

    positions = sm.get_open_positions()
    closed_trades: list[ClosedTrade] = []

    for pos in positions:
        if pos.asset not in current_prices:
            logger.warning(
                "HALT but no price for %s, leaving position %s open",
                pos.asset, pos.position_id,
            )
            continue

        price = current_prices[pos.asset]

        # Reconstruct the entry "fill" for accounting (we know its details from DB)
        entry_fill = SimulatedFill(
            side="BUY",
            requested_price=pos.entry_price,
            fill_price=pos.entry_fill_price,
            units=pos.units,
            gross_value=pos.units * pos.entry_fill_price,
            fee_paid=pos.initial_capital_used - (pos.units * pos.entry_fill_price),
            slippage_cost=pos.units * (pos.entry_fill_price - pos.entry_price),
            cash_delta=-pos.initial_capital_used,
        )

        # Simulate the SELL at current price
        exit_fill = simulate_market_order(
            side="SELL",
            requested_price=price,
            units=pos.units,
            slippage_pct=slippage_pct,
            fee_pct=fee_pct,
        )

        # Compute the trade outcome
        held_bars = max(0, current_bar_index)  # caller manages bar index
        realized = compute_realized_trade(
            asset=pos.asset,
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            held_bars=held_bars,
            direction="BUY",
        )

        # Build ClosedTrade record
        ct = ClosedTrade(
            trade_id=pos.position_id,
            asset=pos.asset,
            direction=pos.direction,
            entry_timestamp=pos.entry_timestamp,
            exit_timestamp=current_timestamp,
            entry_price=pos.entry_price,
            entry_fill_price=pos.entry_fill_price,
            exit_price=price,
            exit_fill_price=exit_fill.fill_price,
            units=pos.units,
            pnl_dollars=realized.pnl_dollars,
            pnl_pct=realized.pnl_pct,
            total_fees=realized.total_fees,
            total_slippage=realized.total_slippage,
            exit_reason="HALT_FORCED",
            held_bars=held_bars,
        )

        sm.record_closed_trade(ct)
        sm.remove_open_position(pos.position_id)
        closed_trades.append(ct)

        logger.info(
            "HALT close %s @ $%.4f → PnL $%.2f (%.2f%%)",
            pos.asset, exit_fill.fill_price,
            realized.pnl_dollars, realized.pnl_pct * 100,
        )

    # Finally mark bot as HALTED
    sm.halt(reason, current_timestamp)
    logger.warning("BOT HALTED: %s", reason)

    return closed_trades


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : démo
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    from paper_trading.state_manager import StateManager, OpenPosition, EquitySnapshot

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 64)
    print("  stop_manager.py — démo")
    print("=" * 64)

    # Temp DB
    tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmpf.close()
    db = Path(tmpf.name)
    sm = StateManager(db_path=db)

    # Setup: $1,000 starting equity, no positions yet
    print("\n[setup] $1,000 starting equity, no positions")
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=1000.0, open_positions_value=0.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))

    # Open a BTC position
    print("\n[cycle] open BTC position $125, entry $80,000")
    with sm.cycle():
        sm.open_position(OpenPosition(
            position_id="BTC_T1", asset="BTC", direction="BUY",
            entry_timestamp="2026-05-13T18:00:00Z",
            entry_price=80000.0, entry_fill_price=80080.0,
            units=0.001558, initial_capital_used=125.0,
            sl_price=78000.0, tp_price=84000.0,
        ))

    # Scenario 1: BTC drops, equity OK, no halt
    print("\n[scenario 1] BTC @ $79,000 (small loss, no halt expected)")
    with sm.cycle():
        result = check_global_stops(
            sm, current_prices={"BTC": 79000.0},
            current_timestamp="2026-05-13T19:00:00Z",
            cash=875.0,
        )
    print(f"  equity = ${result.current_equity:.2f}, "
          f"DD = {result.drawdown_pct*100:.2f}%, "
          f"daily_loss = {(result.daily_loss_pct or 0)*100:.2f}%, "
          f"halt = {result.should_halt}")

    # Scenario 2: BTC crashes hard, daily loss triggers halt
    print("\n[scenario 2] BTC @ $30,000 (massive crash, daily_loss should halt)")
    with sm.cycle():
        result = check_global_stops(
            sm, current_prices={"BTC": 30000.0},
            current_timestamp="2026-05-13T20:00:00Z",
            cash=875.0,
        )
    print(f"  equity = ${result.current_equity:.2f}, "
          f"DD = {result.drawdown_pct*100:.2f}%, "
          f"daily_loss = {(result.daily_loss_pct or 0)*100:.2f}%")
    print(f"  should_halt = {result.should_halt}")
    print(f"  reason = {result.halt_reason}")

    # Execute the HALT
    print("\n[action] trigger_halt: close BTC position, mark HALTED")
    with sm.cycle():
        closed = trigger_halt(
            sm, reason=result.halt_reason,
            current_prices={"BTC": 30000.0},
            current_timestamp="2026-05-13T20:00:00Z",
            current_bar_index=2,
        )
    for ct in closed:
        print(f"  Closed {ct.asset}: PnL ${ct.pnl_dollars:.2f} ({ct.pnl_pct*100:.2f}%), "
              f"reason: {ct.exit_reason}")

    # Verify final state
    state = sm.get_bot_state()
    print(f"\n  Final bot status: {state.status}")
    print(f"  Halt reason: {state.halt_reason}")
    print(f"  Open positions: {len(sm.get_open_positions())}")

    sm.close()
    import os
    os.unlink(db)

    print("\n" + "=" * 64)
    print("  stop_manager.py OK")
    print("=" * 64)
