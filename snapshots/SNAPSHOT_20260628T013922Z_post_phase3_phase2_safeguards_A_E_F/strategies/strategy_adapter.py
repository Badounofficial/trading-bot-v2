"""
strategy_adapter.py — Wrapper around run_icc_cycle for live paper trading.

WHY THIS MODULE EXISTS
======================
ICC (in strategies/icc_cycle.py) was designed for BATCH backtesting:
- run_icc_cycle(asset, daily, h4, h1) iterates over ALL H1 bars
- Returns list[TradeSetup] containing every setup that ever happened in the data

For LIVE paper trading, we need to know "what NEW thing happened between cycle T-1 and T?"
This adapter:
1. Calls run_icc_cycle on the FULL historical window at each cycle (exactly like Session 5)
2. Compares the returned setups with the previous cycle's setups
3. Emits StrategyAction objects (OPEN/CLOSE/TRAIL/PARTIAL) for the diff

GUARANTEE OF FIDELITY
=====================
We never modify icc_cycle.py. We call run_icc_cycle with the same arguments and
the same data preparation pattern as Session 5 (walkforward_icc.py, run_session_5_verdict.py).
The adapter is OBSERVATIONAL — it watches what ICC does and translates it to actions.

ACTION TYPES
============
- OpenAction: a new IN_TRADE setup appeared → simulate BUY (or SELL for shorts later)
- CloseAction: a setup transitioned IN_TRADE → COOLDOWN (with entry filled) → simulate exit
- TrailAction: setup's sl_current changed → update SL in DB
- PartialAction: setup's partial_closed flipped False → True → record 85% close

SETUP IDENTITY
==============
We identify a setup uniquely by (asset, h4_indication.bar_index, direction).
This identifier is stable: it depends on objective H4 market structure, not on
when ICC was called.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Any

import pandas as pd

# Import ICC (frozen since Session 5 — we never modify it)
from strategies.icc_cycle import (
    run_icc_cycle,
    TradeSetup,
    TradeState,
    Direction,
    TradeMode,
    ExitReason,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    SETUP IDENTITY
# ════════════════════════════════════════════════════════════════

# We use a tuple as setup identity:
# (asset, h4_indication.confirmed_at_ts (ISO string), direction_value)
#
# WHY NOT bar_index ANYMORE (Bug #3 fix from Session 6b dry run E2E):
# - bar_index is an "absolute index in input DataFrame" (commented in
#   strategies/icc_structure.py line 63)
# - When the H1 window slides 1 bar between cycles, the position of the
#   same real structure shifts (e.g. from 152 to 151)
# - This made setup_id INSTABLE across cycles, causing the adapter to
#   emit duplicate Opens (and Closes targeting non-existent positions)
# - confirmed_at_ts is a pd.Timestamp anchored to a real moment in time,
#   independent of DataFrame indexing → stable across cycles by design
SetupId = tuple[str, str, str]


def setup_id(setup: TradeSetup) -> SetupId:
    """Compute a stable identity for a TradeSetup.

    The (asset, h4_indication.confirmed_at_ts ISO, direction) tuple is:
    - Unique : ICC only creates one setup per (h4 break, direction) by design
    - Stable : confirmed_at_ts is a pd.Timestamp = absolute moment in time
               that does NOT change when the H1 window slides between cycles
    - Reproducible : run_icc_cycle twice on same data → same setup_ids

    The timestamp is serialized to ISO format (e.g. "2026-05-12T14:00:00")
    so the identifier is plain string-compatible and easy to log/persist.
    """
    ts = setup.h4_indication.confirmed_at_ts
    # Normalize to UTC then strip tz for canonical form
    pts = pd.Timestamp(ts)
    if pts.tz is not None:
        pts = pts.tz_convert("UTC").tz_localize(None)
    ts_iso = pts.isoformat()  # e.g. "2026-05-12T14:00:00"
    return (
        setup.asset,
        ts_iso,
        setup.direction.value,
    )


# ════════════════════════════════════════════════════════════════
#                    ACTION DATACLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class OpenAction:
    """A new setup just entered IN_TRADE state. Open a paper position."""
    setup_id: SetupId
    asset: str
    direction: str               # "BUY" (long) for Session 6
    entry_timestamp: str         # ISO UTC, from setup.entry_timestamp
    entry_price: float           # the price ICC saw at entry (strategy's view)
    sl_price: float
    tp_price: Optional[float]
    sl_source: Optional[str]
    tp_source: Optional[str]


@dataclass
class CloseAction:
    """A setup just transitioned to COOLDOWN with entry_price filled.
    This means the in-flight trade has been closed. Mirror this exit
    in the paper portfolio (simulate SELL at exit_price)."""
    setup_id: SetupId
    asset: str
    exit_timestamp: str
    exit_price: float
    exit_reason: str             # ExitReason.value


@dataclass
class TrailAction:
    """A setup's sl_current changed. Update SL in DB (no order execution)."""
    setup_id: SetupId
    asset: str
    new_sl: float
    timestamp: str               # when the change was detected
    sl_source: Optional[str]


@dataclass
class PartialAction:
    """A setup's partial_closed flipped False → True. Record the 85% close."""
    setup_id: SetupId
    asset: str
    partial_price: float
    partial_timestamp: str       # use the bar's timestamp
    partial_pnl_pct: Optional[float]


StrategyAction = Any  # one of: OpenAction | CloseAction | TrailAction | PartialAction


# ════════════════════════════════════════════════════════════════
#                    THE ADAPTER
# ════════════════════════════════════════════════════════════════

class IccStrategyAdapter:
    """Observational wrapper around run_icc_cycle.

    Stateful: maintains a snapshot of last cycle's setups per asset to compute
    deltas. Stateless mode is also supported (pass prev_setups explicitly).

    The adapter calls run_icc_cycle EXACTLY as Session 5 backtest does
    (walkforward_icc.py pattern). This guarantees behavior parity.
    """

    def __init__(
        self,
        mode: TradeMode = TradeMode.SWING,
        daily_lookback: int = 5,
        h4_lookback: int = 3,
        h1_lookback: int = 3,
        skip_daily_filter: bool = False,
        min_rr_for_ob_tp: float = 2.5,
        measured_move_rr: float = 3.0,
        sl_mode: str = "v1_h1_close",
    ):
        """Initialize the adapter with ICC parameters frozen since Session 5.

        Defaults match Session 5 / walkforward_icc.py exactly. Do not change
        without re-validating the strategy.
        """
        self.mode = mode
        self.daily_lookback = daily_lookback
        self.h4_lookback = h4_lookback
        self.h1_lookback = h1_lookback
        self.skip_daily_filter = skip_daily_filter
        self.min_rr_for_ob_tp = min_rr_for_ob_tp
        self.measured_move_rr = measured_move_rr
        self.sl_mode = sl_mode

        # Per-asset cache of last cycle's setups (keyed by SetupId)
        self._last_setups_by_asset: dict[str, dict[SetupId, TradeSetup]] = {}

    # ─── ICC call (mirrors Session 5 exactly) ─────────────────────

    def _call_icc(
        self,
        asset: str,
        daily_df: pd.DataFrame,
        h4_df: pd.DataFrame,
        h1_df: pd.DataFrame,
    ) -> list[TradeSetup]:
        """Call run_icc_cycle with locked parameters. Returns all setups."""
        return run_icc_cycle(
            asset=asset,
            daily_prices=daily_df,
            h4_prices=h4_df,
            h1_prices=h1_df,
            mode=self.mode,
            daily_lookback=self.daily_lookback,
            h4_lookback=self.h4_lookback,
            h1_lookback=self.h1_lookback,
            verbose=False,
            skip_daily_filter=self.skip_daily_filter,
            min_rr_for_ob_tp=self.min_rr_for_ob_tp,
            measured_move_rr=self.measured_move_rr,
            sl_mode=self.sl_mode,
        )

    # ─── Delta detection ──────────────────────────────────────────

    @staticmethod
    def _is_open_position(setup: TradeSetup) -> bool:
        """A setup represents an OPEN position iff state == IN_TRADE."""
        return setup.state == TradeState.IN_TRADE

    @staticmethod
    def _is_closed_trade(setup: TradeSetup) -> bool:
        """A setup represents a CLOSED trade iff it's in COOLDOWN AND we
        actually entered (entry_price is not None).

        Setups that died in SCANNING/INDICATION/CORRECTION/READY without
        ever entering → state goes to COOLDOWN but entry_price stays None.
        Those are NOT trades — they're just setups that didn't pan out.
        """
        return (
            setup.state == TradeState.COOLDOWN
            and setup.entry_price is not None
        )

    @staticmethod
    def diff_setups(
        prev_setups: dict[SetupId, TradeSetup],
        curr_setups: dict[SetupId, TradeSetup],
        asset: str,
    ) -> list[StrategyAction]:
        """Compare two snapshots of setups and emit actions.

        Based on the REAL ICC state machine (verified by reading icc_cycle.py):
        - IN_TRADE = position is currently open
        - COOLDOWN + entry_price is not None = trade has been closed
        - COOLDOWN + entry_price is None = setup never entered (ignore)

        See _is_open_position and _is_closed_trade for the canonical predicates.

        Args:
            prev_setups: setup_id → TradeSetup, as of previous cycle
            curr_setups: setup_id → TradeSetup, as of current cycle
            asset: asset name (for log + action fields)

        Returns:
            Ordered list of actions. The orchestrator processes them sequentially.
        """
        diff = IccStrategyAdapter
        actions: list[StrategyAction] = []

        # 1. OPEN: a setup that's currently a position (IN_TRADE or already
        #    closed trade with entry filled), and wasn't yet in T-1.
        for sid, cs in curr_setups.items():
            currently_open = diff._is_open_position(cs)
            currently_closed_trade = diff._is_closed_trade(cs)
            if not (currently_open or currently_closed_trade):
                continue  # not a trade at all yet (still SCANNING/INDICATION/...)
            ps = prev_setups.get(sid)
            was_open_or_closed_trade_before = ps is not None and (
                diff._is_open_position(ps) or diff._is_closed_trade(ps)
            )
            if not was_open_or_closed_trade_before:
                # Emit OPEN action
                if cs.entry_price is None:
                    continue  # shouldn't happen given the checks above, defensive
                actions.append(OpenAction(
                    setup_id=sid,
                    asset=asset,
                    direction=cs.direction.value,
                    entry_timestamp=str(cs.entry_timestamp),
                    entry_price=cs.entry_price,
                    sl_price=cs.sl_initial if cs.sl_initial is not None else 0.0,
                    tp_price=cs.tp_target,
                    sl_source=cs.sl_source,
                    tp_source=cs.tp_source,
                ))

        # 2. CLOSE: setup that's now a closed trade and wasn't already in
        #    the closed-trade state before (open→closed, OR new+closed in 1 cycle).
        for sid, cs in curr_setups.items():
            if not diff._is_closed_trade(cs):
                continue
            ps = prev_setups.get(sid)
            was_already_closed_trade = (
                ps is not None and diff._is_closed_trade(ps)
            )
            if was_already_closed_trade:
                continue  # already counted in a previous cycle
            # First time we see this trade as closed: emit CLOSE
            if cs.exit_price is None:
                continue  # defensive
            actions.append(CloseAction(
                setup_id=sid,
                asset=asset,
                exit_timestamp=str(cs.exit_timestamp),
                exit_price=cs.exit_price,
                exit_reason=(
                    cs.exit_reason.value if cs.exit_reason else "UNKNOWN"
                ),
            ))

        # 3. PARTIAL: partial_closed flipped False → True
        for sid, cs in curr_setups.items():
            if not cs.partial_closed:
                continue
            ps = prev_setups.get(sid)
            was_partial_before = ps is not None and ps.partial_closed
            if not was_partial_before and cs.partial_close_price is not None:
                ts = str(cs.entry_timestamp)
                actions.append(PartialAction(
                    setup_id=sid,
                    asset=asset,
                    partial_price=cs.partial_close_price,
                    partial_timestamp=ts,
                    partial_pnl_pct=cs.partial_pnl_pct,
                ))

        # 4. TRAIL: sl_current changed AND setup still currently in open position
        for sid, cs in curr_setups.items():
            if not diff._is_open_position(cs):
                continue  # only emit trail while position is still open
            if cs.sl_current is None:
                continue
            ps = prev_setups.get(sid)
            if ps is None or ps.sl_current is None or not diff._is_open_position(ps):
                # First time seeing this in open position → SL is initial, not trailed
                continue
            if abs(cs.sl_current - ps.sl_current) > 1e-9:
                ts = str(cs.entry_timestamp)
                actions.append(TrailAction(
                    setup_id=sid,
                    asset=asset,
                    new_sl=cs.sl_current,
                    timestamp=ts,
                    sl_source=cs.sl_source,
                ))

        return actions

    # ─── Main entry point ─────────────────────────────────────────

    def get_actions_for_cycle(
        self,
        asset: str,
        daily_df: pd.DataFrame,
        h4_df: pd.DataFrame,
        h1_df: pd.DataFrame,
        prev_setups: Optional[dict[SetupId, TradeSetup]] = None,
    ) -> tuple[list[StrategyAction], dict[SetupId, TradeSetup]]:
        """Run ICC for one cycle and emit actions for what changed.

        Args:
            asset: e.g. "BTC"
            daily_df, h4_df, h1_df: OHLCV DataFrames with DatetimeIndex (UTC)
            prev_setups: optional explicit previous snapshot. If None, we use
                         the internal cache populated by the last call to this
                         method on the same asset.

        Returns:
            (actions, current_setups_dict)
            - actions: ordered list of StrategyAction objects to execute
            - current_setups_dict: snapshot of all setups after this cycle
              (caller can persist or pass back next time as prev_setups)
        """
        # Pull previous snapshot
        if prev_setups is None:
            prev_setups = self._last_setups_by_asset.get(asset, {})

        # Run ICC on the full window (same pattern as Session 5)
        all_setups = self._call_icc(asset, daily_df, h4_df, h1_df)

        # Build the current snapshot dict
        curr_setups = {setup_id(s): s for s in all_setups}

        # Diff to emit actions
        actions = self.diff_setups(prev_setups, curr_setups, asset)

        # Cache for next call
        self._last_setups_by_asset[asset] = curr_setups

        if actions:
            logger.info(
                "Adapter %s: %d actions emitted (%d total setups in cycle)",
                asset, len(actions), len(curr_setups),
            )

        return actions, curr_setups


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : self-test
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print("=" * 64)
    print("  strategy_adapter.py — démo")
    print("=" * 64)

    print(f"\nDataclasses available:")
    print(f"  OpenAction({list(OpenAction.__dataclass_fields__.keys())})")
    print(f"  CloseAction({list(CloseAction.__dataclass_fields__.keys())})")
    print(f"  TrailAction({list(TrailAction.__dataclass_fields__.keys())})")
    print(f"  PartialAction({list(PartialAction.__dataclass_fields__.keys())})")

    adapter = IccStrategyAdapter()
    print(f"\nAdapter initialized with Session 5 defaults:")
    print(f"  mode={adapter.mode}, sl_mode={adapter.sl_mode}")
    print(f"  daily_lookback={adapter.daily_lookback}, h4_lookback={adapter.h4_lookback}")
    print(f"  min_rr_for_ob_tp={adapter.min_rr_for_ob_tp}")

    # Test the static diff_setups with empty inputs
    actions = IccStrategyAdapter.diff_setups({}, {}, "BTC")
    print(f"\nEmpty → empty diff: {len(actions)} actions (expected 0)")

    print("\n" + "=" * 64)
    print("  strategy_adapter.py OK (full tests in tests/test_strategy_adapter.py)")
    print("=" * 64)
