"""
paper_trader.py — Main orchestrator for the paper trading bot.

This is THE BOT. It coordinates:
  - data_source     (fetch H1 from Kraken)
  - data_prep       (resample to H4 + Daily for ICC)
  - strategy_adapter (call ICC, detect actions)
  - order_simulator (simulate fills with slippage + fees)
  - state_manager   (persist everything in SQLite, transactional)
  - stop_manager    (DD + Daily loss global watchdog)
  - monitoring      (JSON Lines logs + Telegram alerts)

DESIGN PRINCIPLES
=================
1. **run_one_cycle() is pure logic** — given (timestamp, fetched_data, sm, ...),
   it produces a deterministic CycleResult. No real-time waiting inside.
   This makes it testable without mocking time or network.

2. **Two boot modes**:
   - run_dev_fast(): iterates over historical H1 bars (no sleep)
     for E2E tests and fast iteration.
   - run_forever(): sleeps until next XX:00 UTC + POST_BAR_DELAY_SECONDS,
     then fetches fresh data and calls run_one_cycle.

3. **Resilience**:
   - If Kraken is down for an asset → skip that asset, log warning, continue.
   - If a single action fails (e.g. insufficient capital) → skip that action,
     log warning, continue with other actions in the cycle.
   - If the cycle itself crashes → state_manager.cycle() context manager
     rolls back atomically. We log + alert via monitor.alert_crash().

4. **HALT priority**:
   Stops are checked BEFORE processing strategy actions. If HALT triggers,
   we close all positions and skip strategy processing for the rest of the cycle.
"""
from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

import pandas as pd

from paper_trading import config
from paper_trading import data_source as ds
from paper_trading import data_prep
from paper_trading import order_simulator as os_
from paper_trading import stop_manager as sm_
from paper_trading.state_manager import (
    StateManager, OpenPosition, ClosedTrade, EquitySnapshot,
)
from paper_trading.monitoring import Monitor
from paper_trading.order_simulator import SimulatedFill
from strategies.strategy_adapter import (
    IccStrategyAdapter,
    OpenAction, CloseAction, TrailAction, PartialAction,
    SetupId,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    CYCLE RESULT
# ════════════════════════════════════════════════════════════════

@dataclass
class CycleResult:
    """Outcome of running one H1 cycle."""
    timestamp: str
    success: bool                        # False if a fatal error rolled back the tx
    n_trades_opened: int = 0
    n_trades_closed: int = 0
    n_trades_skipped: int = 0
    n_trails: int = 0
    n_partials: int = 0
    halt_triggered: bool = False
    halt_reason: Optional[str] = None
    cycle_duration_seconds: float = 0.0
    assets_with_data: list[str] = field(default_factory=list)
    assets_failed: list[str] = field(default_factory=list)
    error_message: Optional[str] = None  # filled if success=False


# ════════════════════════════════════════════════════════════════
#                    POSITION ID MAPPING
# ════════════════════════════════════════════════════════════════

def _setup_id_to_position_id(sid: SetupId) -> str:
    """Convert a strategy SetupId tuple to a stable string position_id.

    Format: "{asset}__{ts_sanitized}__{direction}"
    where ts_sanitized = confirmed_at_ts ISO with ":" replaced by "-"
    (because ":" can cause issues in file paths and DB queries on some
    platforms).

    Example: ("BTC", "2026-05-12T14:00:00", "BUY") → "BTC__2026-05-12T14-00-00__BUY"

    Bug #3 fix (Session 6b dry run E2E):
    Previously used bar_index (int) → INSTABLE across cycles.
    Now uses confirmed_at_ts → stable, anchored to a real moment in time.
    """
    asset, ts_iso, direction = sid
    ts_sanitized = ts_iso.replace(":", "-")
    return f"{asset}__{ts_sanitized}__{direction}"


def _position_id_to_setup_id(pid: str) -> SetupId:
    """Inverse of _setup_id_to_position_id. For lookups.

    Splits on "__" (double underscore) to preserve timestamp formatting
    and reconstructs the original ":" in the timestamp portion.
    """
    parts = pid.split("__")
    if len(parts) != 3:
        raise ValueError(f"Invalid position_id format: {pid}")
    asset, ts_sanitized, direction = parts
    # Reconstruct ISO timestamp: T14-00-00 → T14:00:00 (only after the 'T')
    ts_iso = _unsanitize_ts(ts_sanitized)
    return (asset, ts_iso, direction)


def _unsanitize_ts(ts_sanitized: str) -> str:
    """Reverse the ':' → '-' replacement done in _setup_id_to_position_id.

    Only after the 'T' (in case the date contains '-' that we must preserve).
    Example: "2026-05-12T14-00-00" → "2026-05-12T14:00:00"
    """
    if "T" not in ts_sanitized:
        return ts_sanitized  # defensive: shouldn't happen but no crash
    date_part, time_part = ts_sanitized.split("T", 1)
    time_part = time_part.replace("-", ":")
    return f"{date_part}T{time_part}"


# ════════════════════════════════════════════════════════════════
#                    THE ORCHESTRATOR
# ════════════════════════════════════════════════════════════════

class PaperTrader:
    """Main loop. Orchestrates all paper trading modules."""

    def __init__(
        self,
        state_manager: Optional[StateManager] = None,
        monitor: Optional[Monitor] = None,
        adapter: Optional[IccStrategyAdapter] = None,
        data_fetcher: Optional[Callable[[], dict[str, pd.DataFrame]]] = None,
        assets: Optional[list[str]] = None,
    ):
        """Inject dependencies (all optional, defaults to production).

        Args:
            state_manager: pre-initialized StateManager (default: open on config.STATE_DB_PATH)
            monitor: Monitor (default: real JSON logs + Telegram if .env set)
            adapter: ICC adapter (default: Session 5 frozen parameters)
            data_fetcher: callable returning {asset: H1_DataFrame}.
                          Default = ds.fetch_all_assets_h1 (live Kraken).
                          Can be mocked for tests.
            assets: list of assets to trade (default: config.ASSETS)
        """
        self.sm = state_manager if state_manager is not None else StateManager()
        self.monitor = monitor if monitor is not None else Monitor()
        self.adapter = adapter if adapter is not None else IccStrategyAdapter()
        self.data_fetcher = data_fetcher if data_fetcher is not None else (
            lambda: ds.fetch_all_assets_h1(n_bars=config.ROLLING_BUFFER_SIZE)
        )
        self.assets = assets if assets is not None else list(config.ASSETS)

    # ═══════════════════════════════════════════════════════════
    #                CORE LOGIC : 1 cycle
    # ═══════════════════════════════════════════════════════════

    def run_one_cycle(
        self,
        timestamp_iso: Optional[str] = None,
        prefetched_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> CycleResult:
        """Run one H1 cycle of the bot.

        Args:
            timestamp_iso: ISO UTC timestamp of "now". Defaults to actual now.
            prefetched_data: if provided, skip the live fetch and use this.
                             Used by run_dev_fast for historical replay.

        Returns:
            CycleResult describing what happened.
        """
        t0 = time.time()
        if timestamp_iso is None:
            timestamp_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        result = CycleResult(timestamp=timestamp_iso, success=False)

        # ── 0. Check if bot is currently HALTED ──
        bot_state = self.sm.get_bot_state()
        if bot_state.status == "HALTED":
            logger.warning(
                "Bot is HALTED (reason: %s). Skipping cycle %s.",
                bot_state.halt_reason, timestamp_iso,
            )
            result.success = True
            result.error_message = f"Bot HALTED: {bot_state.halt_reason}"
            result.cycle_duration_seconds = time.time() - t0
            return result

        self.monitor.log_cycle_start(ts=timestamp_iso)

        # ── 1. Fetch data ──
        try:
            if prefetched_data is not None:
                fetched = prefetched_data
            else:
                fetched = self.data_fetcher()
        except Exception as e:
            logger.exception("Data fetch failed catastrophically")
            tb = traceback.format_exc()
            self.monitor.alert_crash(error=f"data_fetch: {e}", traceback_snippet=tb, ts=timestamp_iso)
            result.error_message = f"data_fetch: {e}"
            result.cycle_duration_seconds = time.time() - t0
            return result

        result.assets_with_data = [a for a in self.assets if a in fetched]
        result.assets_failed = [a for a in self.assets if a not in fetched]
        if result.assets_failed:
            logger.warning("No data for: %s — skipping these assets this cycle.",
                           result.assets_failed)

        # ── 2. Compute current prices (last close of each asset H1) ──
        current_prices: dict[str, float] = {}
        for asset in result.assets_with_data:
            df = fetched[asset]
            if df is not None and len(df) > 0:
                current_prices[asset] = float(df["close"].iloc[-1])

        # ── 3. Open transaction ──
        try:
            with self.sm.cycle():
                # ── 4. Day anchoring + global stops check ──
                stop_check = sm_.check_global_stops(
                    self.sm,
                    current_prices=current_prices,
                    current_timestamp=timestamp_iso,
                )

                if stop_check.should_halt:
                    # HALT mode: close everything, mark bot HALTED
                    closed = sm_.trigger_halt(
                        self.sm,
                        reason=stop_check.halt_reason,
                        current_prices=current_prices,
                        current_timestamp=timestamp_iso,
                    )
                    self.monitor.alert_halt(
                        reason=stop_check.halt_reason,
                        current_equity=stop_check.current_equity,
                        peak_equity=stop_check.peak_equity,
                        ts=timestamp_iso,
                    )
                    result.halt_triggered = True
                    result.halt_reason = stop_check.halt_reason
                    result.n_trades_closed = len(closed)
                    # No strategy processing once HALTED
                else:
                    # ── 5. Process each asset through strategy adapter ──
                    for asset in result.assets_with_data:
                        try:
                            self._process_asset(asset, fetched[asset], timestamp_iso, result)
                        except Exception as e:
                            # Asset-level error: log but continue with other assets
                            logger.exception("Asset %s processing failed", asset)
                            self.monitor.logger.log(
                                "asset_processing_failed", level="ERROR", ts=timestamp_iso,
                                asset=asset, error=str(e),
                            )

                # ── 6. Record equity snapshot ──
                self._record_equity_snapshot(timestamp_iso, current_prices)

                # ── 7. Update last_cycle_timestamp on bot_state ──
                bs = self.sm.get_bot_state()
                bs.last_cycle_timestamp = timestamp_iso
                self.sm.set_bot_state(bs)

            # transaction committed here
            result.success = True

        except Exception as e:
            logger.exception("Cycle crashed; transaction rolled back")
            tb = traceback.format_exc()
            self.monitor.alert_crash(error=f"cycle: {e}", traceback_snippet=tb, ts=timestamp_iso)
            result.error_message = f"cycle: {e}"

        # ── 8. Cycle-end logging ──
        n_open_after = len(self.sm.get_open_positions())
        latest_snap = self.sm.get_latest_equity_snapshot()
        equity_now = latest_snap.equity if latest_snap else None
        self.monitor.log_cycle_end(ts=timestamp_iso, n_open=n_open_after, equity=equity_now)

        # ── 9. Heartbeat / weekly recap if applicable ──
        if result.success and not result.halt_triggered:
            self._maybe_send_heartbeat(timestamp_iso)
            self._maybe_send_weekly_recap(timestamp_iso)

        result.cycle_duration_seconds = time.time() - t0
        return result

    # ─── Asset processing ─────────────────────────────────────────

    def _process_asset(
        self,
        asset: str,
        h1_df: pd.DataFrame,
        timestamp_iso: str,
        result: CycleResult,
    ) -> None:
        """Process one asset: prep data, run adapter, execute actions."""
        try:
            daily, h4, h1 = data_prep.prepare_multi_tf_for_icc(h1_df)
        except data_prep.DataPrepError as e:
            logger.warning("Data prep failed for %s: %s", asset, e)
            return

        actions, _ = self.adapter.get_actions_for_cycle(asset, daily, h4, h1)

        # Process actions in order, with special handling for setups that
        # have BOTH an Open and a Close in the same cycle (this happens when
        # ICC sees a setup's full lifecycle within the visible window).
        #
        # Standard order: TRAIL → CLOSE → PARTIAL → OPEN
        # Why: closes free up capital before opens try to use it.
        #
        # EXCEPTION (Bug fix from dry run, Session 7):
        # For setups that have BOTH Open and Close emitted in the same cycle,
        # we must process Open FIRST, then Close on that same setup.
        # Otherwise, _exec_close skips with "unknown position" warning because
        # the position hasn't been recorded in state_manager yet.
        trails = [a for a in actions if isinstance(a, TrailAction)]
        closes = [a for a in actions if isinstance(a, CloseAction)]
        partials = [a for a in actions if isinstance(a, PartialAction)]
        opens = [a for a in actions if isinstance(a, OpenAction)]

        # Step 1: All Trails (free, just update SL in DB)
        for a in trails:
            if self._exec_trail(a, timestamp_iso):
                result.n_trails += 1

        # Step 2: Identify setups with BOTH open AND close in this cycle
        sids_with_open = {a.setup_id for a in opens}
        sids_with_close = {a.setup_id for a in closes}
        sids_open_and_close = sids_with_open & sids_with_close

        # Step 2a: Pair-process those setups (Open first, then Close)
        for sid in sids_open_and_close:
            open_a = next(a for a in opens if a.setup_id == sid)
            close_a = next(a for a in closes if a.setup_id == sid)
            if self._exec_open(open_a, timestamp_iso):
                result.n_trades_opened += 1
                if self._exec_close(close_a, timestamp_iso):
                    result.n_trades_closed += 1
            else:
                result.n_trades_skipped += 1

        # Step 3: Closes for setups WITHOUT a paired Open (real closes of
        # positions already in DB) — frees up capital for subsequent opens
        for a in closes:
            if a.setup_id in sids_open_and_close:
                continue  # already handled above
            if self._exec_close(a, timestamp_iso):
                result.n_trades_closed += 1

        # Step 4: Partials (mark 90% taken on existing positions)
        for a in partials:
            if self._exec_partial(a, timestamp_iso):
                result.n_partials += 1

        # Step 5: Opens for setups WITHOUT a paired Close (real new entries)
        for a in opens:
            if a.setup_id in sids_open_and_close:
                continue  # already handled above
            if self._exec_open(a, timestamp_iso):
                result.n_trades_opened += 1
            else:
                result.n_trades_skipped += 1

    # ─── Action executors ─────────────────────────────────────────

    def _exec_open(self, a: OpenAction, ts: str) -> bool:
        """Execute an OpenAction. Returns True if a position was opened, False if skipped."""
        # Compute free capital from latest snapshot
        latest = self.sm.get_latest_equity_snapshot()
        free_cap = latest.cash if latest else config.INITIAL_CAPITAL

        fill = os_.try_open_trade(
            asset=a.asset,
            requested_price=a.entry_price,
            free_capital=free_cap,
        )
        if fill is None:
            self.monitor.log_trade_skipped(
                a.asset, reason="insufficient_capital", ts=ts,
            )
            return False

        # Persist the position
        position_id = _setup_id_to_position_id(a.setup_id)
        pos = OpenPosition(
            position_id=position_id,
            asset=a.asset,
            direction=a.direction,
            entry_timestamp=a.entry_timestamp,
            entry_price=a.entry_price,
            entry_fill_price=fill.fill_price,
            units=fill.units,
            initial_capital_used=-fill.cash_delta,
            sl_price=a.sl_price,
            tp_price=a.tp_price if a.tp_price is not None else a.sl_price * 2,
            sl_source=a.sl_source,
            tp_source=a.tp_source,
        )
        self.sm.open_position(pos)

        self.monitor.log_trade_opened(
            asset=a.asset, units=fill.units,
            entry_price=a.entry_price, entry_fill_price=fill.fill_price,
            sl_price=a.sl_price,
            tp_price=a.tp_price if a.tp_price is not None else 0.0,
            ts=ts,
        )
        return True

    def _exec_close(self, a: CloseAction, ts: str) -> bool:
        """Execute a CloseAction: simulate SELL, record, remove position.

        Returns:
            True if the close was executed, False if skipped (position unknown).
            Bug #2 fix: caller can use this to increment counters accurately.
        """
        position_id = _setup_id_to_position_id(a.setup_id)
        pos = self.sm.get_open_position(position_id)
        if pos is None:
            # Position not in DB. Either:
            # - We missed the OPEN (shouldn't happen after Bug 3 fix)
            # - Adapter emitted close for a setup we never opened
            logger.warning("Close action for unknown position %s — skipping", position_id)
            return False

        # Reconstruct the entry fill from persisted data
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

        # Simulate the SELL at the strategy's exit_price
        exit_fill = os_.simulate_market_order(
            side="SELL",
            requested_price=a.exit_price,
            units=pos.units,
        )

        realized = os_.compute_realized_trade(
            asset=a.asset,
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            held_bars=0,  # bar index not tracked in this version
            direction="BUY",
        )

        ct = ClosedTrade(
            trade_id=position_id,
            asset=a.asset,
            direction=pos.direction,
            entry_timestamp=pos.entry_timestamp,
            exit_timestamp=a.exit_timestamp,
            entry_price=pos.entry_price,
            entry_fill_price=pos.entry_fill_price,
            exit_price=a.exit_price,
            exit_fill_price=exit_fill.fill_price,
            units=pos.units,
            pnl_dollars=realized.pnl_dollars,
            pnl_pct=realized.pnl_pct,
            total_fees=realized.total_fees,
            total_slippage=realized.total_slippage,
            exit_reason=a.exit_reason,
            held_bars=0,
        )
        self.sm.record_closed_trade(ct)
        self.sm.remove_open_position(position_id)

        self.monitor.log_trade_closed(
            asset=a.asset,
            pnl_dollars=realized.pnl_dollars, pnl_pct=realized.pnl_pct,
            exit_reason=a.exit_reason, held_bars=0,
            ts=ts,
        )
        return True

    def _exec_trail(self, a: TrailAction, ts: str) -> bool:
        """Execute a TrailAction: just update SL in DB.

        Returns True if the SL was updated, False if position unknown.
        """
        position_id = _setup_id_to_position_id(a.setup_id)
        pos = self.sm.get_open_position(position_id)
        if pos is None:
            logger.warning("Trail action for unknown position %s — skipping", position_id)
            return False
        self.sm.update_position_sl(
            position_id, new_sl=a.new_sl,
            timestamp=a.timestamp, sl_source=a.sl_source,
        )
        return True

    def _exec_partial(self, a: PartialAction, ts: str) -> bool:
        """Execute a PartialAction: mark the position as partial-taken.

        Returns True if the position was marked, False if position unknown.
        """
        position_id = _setup_id_to_position_id(a.setup_id)
        pos = self.sm.get_open_position(position_id)
        if pos is None:
            logger.warning("Partial action for unknown position %s — skipping", position_id)
            return False
        self.sm.mark_partial_taken(position_id)
        return True

    # ─── Equity snapshot ──────────────────────────────────────────

    def _record_equity_snapshot(
        self, timestamp_iso: str, current_prices: dict[str, float],
    ) -> None:
        """Compute mark-to-market equity and persist snapshot."""
        # Get cash from previous snapshot, then adjust by transactions of THIS cycle
        latest = self.sm.get_latest_equity_snapshot()
        if latest is None:
            cash = config.INITIAL_CAPITAL
        else:
            # We can't easily track cash changes here without intrusive plumbing.
            # Approximation: cash = previous_cash; better tracking is a future improvement.
            # For now, recompute from positions + INITIAL_CAPITAL minus closed_trades net.
            cash = latest.cash
            # (TODO: precise cash tracking via order_simulator deltas)

        positions = self.sm.get_open_positions()
        try:
            open_val = sm_.compute_open_positions_value(positions, current_prices)
        except sm_.MissingPriceError:
            open_val = 0.0  # safely skip if a price is missing for a position
            logger.warning("Missing price during equity snapshot — recording partial value")

        equity = cash + open_val
        prev_peak = self.sm.get_peak_equity() if latest else equity
        peak = max(prev_peak, equity)
        drawdown = (equity - peak) / peak if peak > 0 else 0.0

        snap = EquitySnapshot(
            timestamp=timestamp_iso,
            cash=cash,
            open_positions_value=open_val,
            equity=equity,
            peak_equity=peak,
            drawdown_pct=min(0.0, drawdown),  # clamp at 0 (no positive DD)
        )
        self.sm.record_equity_snapshot(snap)

    # ─── Heartbeat / weekly recap ─────────────────────────────────

    def _maybe_send_heartbeat(self, timestamp_iso: str) -> None:
        """Send daily heartbeat if it's HEARTBEAT_HOUR_UTC."""
        dt = pd.Timestamp(timestamp_iso)
        if dt.hour != config.HEARTBEAT_HOUR_UTC:
            return
        # Compute today's stats
        latest = self.sm.get_latest_equity_snapshot()
        equity = latest.equity if latest else config.INITIAL_CAPITAL
        n_open = len(self.sm.get_open_positions())
        today_trades = self._trades_today(dt)
        pnl_today = sum(t.pnl_dollars for t in today_trades)
        self.monitor.send_heartbeat(
            equity=equity, n_open_positions=n_open,
            pnl_today=pnl_today, n_trades_today=len(today_trades),
            ts=timestamp_iso,
        )

    def _maybe_send_weekly_recap(self, timestamp_iso: str) -> None:
        """Send weekly recap if Sunday at WEEKLY_RECAP_HOUR."""
        dt = pd.Timestamp(timestamp_iso)
        if dt.dayofweek != config.WEEKLY_RECAP_DAY:  # Sunday=6
            return
        if dt.hour != config.WEEKLY_RECAP_HOUR:
            return
        # Compute this week's stats
        latest = self.sm.get_latest_equity_snapshot()
        if latest is None:
            return
        week_ago = dt - pd.Timedelta(days=7)
        trades_this_week = [
            t for t in self.sm.get_closed_trades()
            if pd.Timestamp(t.exit_timestamp) >= week_ago
        ]
        winners = sum(1 for t in trades_this_week if t.pnl_dollars > 0)
        losers = sum(1 for t in trades_this_week if t.pnl_dollars <= 0)
        total_pnl = sum(t.pnl_dollars for t in trades_this_week)
        if trades_this_week:
            best = max(trades_this_week, key=lambda t: t.pnl_dollars).asset
            worst = min(trades_this_week, key=lambda t: t.pnl_dollars).asset
        else:
            best = worst = None

        # Equity 7 days ago (approximate: first snapshot ≥ week_ago)
        # For simplicity, use current equity - total_pnl as an estimate.
        equity_end = latest.equity
        equity_start = equity_end - total_pnl

        self.monitor.send_weekly_recap(
            equity_start=equity_start, equity_end=equity_end,
            n_trades=len(trades_this_week),
            winners=winners, losers=losers, total_pnl=total_pnl,
            best_asset=best, worst_asset=worst,
            ts=timestamp_iso,
        )

    def _trades_today(self, now: pd.Timestamp) -> list[ClosedTrade]:
        """All closed trades whose exit_timestamp is in the same UTC day as now."""
        today_date = now.date()
        out = []
        for t in self.sm.get_closed_trades():
            try:
                exit_dt = pd.Timestamp(t.exit_timestamp)
                if exit_dt.tz is not None:
                    exit_dt = exit_dt.tz_localize(None)
                if exit_dt.date() == today_date:
                    out.append(t)
            except Exception:
                continue
        return out

    # ═══════════════════════════════════════════════════════════
    #              MODE 1 : DEV_FAST (historical replay)
    # ═══════════════════════════════════════════════════════════

    def run_dev_fast(
        self,
        cycles_data: list[tuple[str, dict[str, pd.DataFrame]]],
    ) -> list[CycleResult]:
        """Replay a sequence of cycles from prefetched historical data.

        Args:
            cycles_data: ordered list of (timestamp_iso, {asset: h1_df}).
                         Each entry simulates one cycle.

        Returns:
            List of CycleResult, one per cycle.
        """
        results = []
        for ts, fetched in cycles_data:
            r = self.run_one_cycle(timestamp_iso=ts, prefetched_data=fetched)
            results.append(r)
            if r.halt_triggered:
                logger.info("HALT during dev_fast at %s — stopping", ts)
                break
        return results

    # ═══════════════════════════════════════════════════════════
    #              MODE 2 : FOREVER (production loop)
    # ═══════════════════════════════════════════════════════════

    def run_forever(
        self,
        max_cycles: Optional[int] = None,
        sleep_function: Callable[[float], None] = time.sleep,
    ) -> None:
        """Run cycles continuously, waiting until each next H1 close + delay.

        Args:
            max_cycles: optional cap (for testing/manual stop). None = infinite.
            sleep_function: injectable for testing (default: time.sleep).
        """
        cycles_run = 0
        logger.info("Starting paper trader forever loop (max_cycles=%s)", max_cycles)
        while max_cycles is None or cycles_run < max_cycles:
            wait_s = self._seconds_until_next_cycle()
            if wait_s > 0:
                logger.info("Sleeping %.1fs until next cycle...", wait_s)
                sleep_function(wait_s)
            ts_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            result = self.run_one_cycle(timestamp_iso=ts_iso)
            cycles_run += 1
            logger.info(
                "Cycle %s done: %s (opened=%d closed=%d trails=%d skipped=%d, halt=%s)",
                ts_iso, "OK" if result.success else "FAIL",
                result.n_trades_opened, result.n_trades_closed,
                result.n_trails, result.n_trades_skipped,
                result.halt_triggered,
            )
            if result.halt_triggered:
                logger.warning("Bot HALTED. Exiting forever loop.")
                return

    @staticmethod
    def _seconds_until_next_cycle() -> float:
        """Compute seconds until next XX:00 UTC + POST_BAR_DELAY_SECONDS."""
        now = datetime.now(timezone.utc)
        next_hour = (now.replace(minute=0, second=0, microsecond=0)
                     + timedelta(hours=1))
        target = next_hour + timedelta(seconds=config.POST_BAR_DELAY_SECONDS)
        return max(0.0, (target - now).total_seconds())
