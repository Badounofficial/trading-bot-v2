"""
ICC Cycle — Session 4 — TU#4 Implementation
============================================
Faithful implementation of the ICC Indication-Correction-Continuation cycle
per Test Unitaire #4 and the full ICC specification doc.

CORE CONCEPTS:

    Multi-TF cascade (3 timeframes synchronized):
        DAILY  : bias (BULL/BEAR/NEUTRAL) - master direction
        H4     : indication (CHoCH = NEW_HIGH/NEW_LOW with valid OB)
        H1     : entry (body close past micro structure during correction)

    State machine (per setup, per asset, per TF):
        SCANNING    → no active setup, watching for indication
        INDICATION  → H4 indication confirmed + Daily aligned
        CORRECTION  → price retracing against indication
        READY       → correction validated, entry trigger about to fire
        IN_TRADE    → position open, SL/TP active
        COOLDOWN    → position closed, reset

    Correction validation (TWO valid paths):
        PATH A (classic deep correction):
            1. Price drops below H4 OB zone (for BUY) / above (for SELL)
            2. Price returns above (BUY) / below (SELL)
            3. H1 body close past a micro LH (BUY) / HL (SELL) formed during correction
            4. Price re-enters above OB H4 zone

        PATH B (shallow correction in discount/premium):
            1. Price corrects but stays ABOVE OB H4 zone (BUY) / BELOW (SELL)
            2. Price reaches discount zone (< 50% Fibo of impulse) for BUY
               or premium zone (> 50% Fibo) for SELL
            3. H1 body close past a micro LH (BUY) / HL (SELL)

    Setup invalidation:
        - Body close beyond OB H4 zone (in opposite direction)
        - Daily bias changes
        - H4 produces opposite NEW_HIGH/NEW_LOW
        - Correction exceeds 100% of impulse (price goes past origin)

    Money management:
        SL initial: below PREVIOUS H1 HL (BUY) / above PREVIOUS LH (SELL)
        SL trailing: structural (follows new HL/LH on H1)
        TP: opposite OB on H4/Daily (closest in favorable direction)
        Fallback TP: measured move (2x risk)
        Partial: 85% closed at TP, 15% trailing
        No break-even ever (TradesSAI rule)

    Multiple simultaneous trades:
        Allowed if SAME direction across different TF modes
        (e.g. BTC bull → 1 swing + 1 intraday + 1 scalp BUY all valid)
        Forbidden: opposite directions on same asset
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
from enum import Enum
import pandas as pd
import numpy as np

from strategies.icc_structure import (
    StructurePoint, detect_structures,
)
from strategies.icc_orderblocks import (
    OrderBlock, detect_order_blocks, classify_discount_premium,
)


# ============================================================================
# ENUMS & TYPES
# ============================================================================

class TradeState(Enum):
    SCANNING = "SCANNING"
    INDICATION = "INDICATION"
    CORRECTION = "CORRECTION"
    READY = "READY"
    IN_TRADE = "IN_TRADE"
    COOLDOWN = "COOLDOWN"


class Direction(Enum):
    BUY = "BUY"
    SELL = "SELL"


class BiasState(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


class TradeMode(Enum):
    SWING = "SWING"      # Daily=bias, H4=indication, H1=entry
    INTRADAY = "INTRADAY"  # H4=bias, H1=indication, M15=entry (future)
    SCALPING = "SCALPING"  # H4=bias, M15=indication, M1=entry (future)


class ExitReason(Enum):
    SL_HIT = "SL_HIT"               # Initial SL hit (true loss)
    TRAILING_HIT = "TRAILING_HIT"   # Trailing SL hit AFTER it moved past initial (profit/breakeven exit)
    TP_HIT = "TP_HIT"               # Full TP reached (or partial closed and final exit)
    PARTIAL_TP_HIT = "PARTIAL_TP_HIT"  # 85% closed at TP, 15% still running with trailing
    DAILY_REVERSAL = "DAILY_REVERSAL"
    H4_REVERSAL = "H4_REVERSAL"
    OB_BROKEN = "OB_BROKEN"
    CORRECTION_TOO_DEEP = "CORRECTION_TOO_DEEP"
    MANUAL = "MANUAL"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class TradeSetup:
    """A single ICC setup tracked through its full lifecycle."""
    asset: str
    mode: TradeMode
    direction: Direction
    state: TradeState
    created_at_bar: int  # H1 bar index when SCANNING → INDICATION
    
    # Multi-TF context (frozen at setup creation)
    daily_bias: BiasState
    h4_indication: StructurePoint  # the NEW_HIGH/NEW_LOW/HH/LL that triggered
    h4_ob: OrderBlock  # the valid OB that defined the indication
    
    # Impulse geometry (for Fibo)
    impulse_low: float   # for BUY: low at origin / for SELL: low at NEW_LOW
    impulse_high: float  # for BUY: high at NEW_HIGH / for SELL: high at origin
    fibo_50: float       # midpoint
    
    # Correction tracking
    correction_started_at_bar: Optional[int] = None
    deep_correction_reached: bool = False  # touched OB H4 zone (Path A)
    shallow_via_fibo: bool = False         # reached discount/premium without touching OB (Path B)
    h1_micro_swings: list[StructurePoint] = field(default_factory=list)  # LH/HL micro during correction
    
    # Entry
    entry_bar: Optional[int] = None
    entry_price: Optional[float] = None
    entry_timestamp: Optional[pd.Timestamp] = None
    
    # SL/TP
    sl_initial: Optional[float] = None
    sl_current: Optional[float] = None
    sl_history: list[tuple[int, float]] = field(default_factory=list)  # (bar_index, sl_price)
    tp_target: Optional[float] = None
    tp_source: Optional[str] = None  # "OB_H4" | "OB_DAILY" | "MEASURED_MOVE"
    
    # Lifecycle
    partial_closed: bool = False
    partial_closed_at_bar: Optional[int] = None
    partial_close_price: Optional[float] = None   # price at which 85% was closed
    partial_pnl_pct: Optional[float] = None       # PnL of the 85% portion
    remaining_size: float = 1.0                   # 1.0 → 0.15 after partial
    exit_bar: Optional[int] = None
    exit_price: Optional[float] = None
    exit_timestamp: Optional[pd.Timestamp] = None
    exit_reason: Optional[ExitReason] = None
    
    # PnL (computed at exit)
    pnl_pct: Optional[float] = None
    
    def __repr__(self):
        return (f"<Setup {self.asset} {self.mode.value} {self.direction.value} "
                f"state={self.state.value} entry={self.entry_price}>")


# ============================================================================
# BIAS DETECTION (DAILY)
# ============================================================================

def compute_daily_bias(daily_structs: list[StructurePoint], at_bar: int) -> BiasState:
    """
    Determine Daily bias from the last active structure before `at_bar`.
    
    Per user decision Q1:
    Last active structure direction = bias.
    - HH or HL active → BULL
    - LH or LL active → BEAR
    - NEW_HIGH (just confirmed CHoCH bullish) → BULL
    - NEW_LOW (just confirmed CHoCH bearish) → BEAR
    - Nothing meaningful → NEUTRAL
    """
    # Find the most recent structure whose confirmed_at_bar <= at_bar AND not broken
    # (or broken after at_bar)
    last_meaningful: Optional[StructurePoint] = None
    
    for s in daily_structs:
        if s.confirmed_at_bar > at_bar:
            break  # this and following are in the future
        # Skip initial bootstrap markers
        if s.type in ('INITIAL_HIGH', 'INITIAL_LOW'):
            continue
        # Was it still active at `at_bar`?
        if s.broken and s.broken_at_bar is not None and s.broken_at_bar <= at_bar:
            continue  # already broken at this point in time
        last_meaningful = s
    
    if last_meaningful is None:
        return BiasState.NEUTRAL
    
    if last_meaningful.type in ('NEW_HIGH', 'HH', 'HL'):
        return BiasState.BULL
    if last_meaningful.type in ('NEW_LOW', 'LL', 'LH'):
        return BiasState.BEAR
    return BiasState.NEUTRAL


# ============================================================================
# UTILITIES
# ============================================================================

def find_h1_bar_for_h4_timestamp(
    h1_index: pd.DatetimeIndex,
    h4_ts: pd.Timestamp,
) -> int:
    """Find H1 bar index >= h4_ts. Used to sync H4 events to H1 timeline."""
    pos = h1_index.searchsorted(h4_ts, side='left')
    return int(pos) if pos < len(h1_index) else len(h1_index) - 1


def find_daily_bar_for_h1_timestamp(
    daily_index: pd.DatetimeIndex,
    h1_ts: pd.Timestamp,
) -> int:
    """Find Daily bar index whose date contains the H1 timestamp."""
    target_date = h1_ts.normalize()
    pos = daily_index.searchsorted(target_date, side='right') - 1
    return max(0, min(int(pos), len(daily_index) - 1))


# ============================================================================
# STATE TRANSITIONS
# ============================================================================

def try_create_setup(
    asset: str,
    mode: TradeMode,
    h4_indication: StructurePoint,
    h4_ob: OrderBlock,
    daily_bias: BiasState,
    h1_bar: int,
    h1_prices: pd.DataFrame,
) -> Optional[TradeSetup]:
    """
    Try to create a new TradeSetup from an H4 indication.
    
    Returns None if:
      - Indication direction doesn't match Daily bias
      - OB already consumed at this point in time
    """
    # Determine direction from indication type
    if h4_indication.type in ('NEW_HIGH', 'HH'):
        direction = Direction.BUY
        if daily_bias != BiasState.BULL:
            return None
    elif h4_indication.type in ('NEW_LOW', 'LL'):
        direction = Direction.SELL
        if daily_bias != BiasState.BEAR:
            return None
    else:
        return None  # not a break-type structure
    
    # OB must not be consumed at this point in H1 time
    # (we check via the OB's detected_at_bar in H4 frame — translated to H1 already by caller)
    if h4_ob.consumed and h4_ob.consumed_at_bar is not None:
        # OB was consumed at some H4 bar. We need a check in caller's frame.
        # For now, accept all not-yet-consumed at indication time.
        pass
    
    # Compute impulse geometry for Fibo
    if h4_ob.structure_broken.origin_bar_index is None:
        return None  # no origin, can't compute Fibo
    
    if direction == Direction.BUY:
        # Impulse: from origin (low) to NEW_HIGH price
        impulse_low = h4_ob.structure_broken.origin_price
        impulse_high = h4_ob.structure_broken.price
    else:
        # Impulse: from origin (high) to NEW_LOW price
        impulse_high = h4_ob.structure_broken.origin_price
        impulse_low = h4_ob.structure_broken.price
    
    fibo_50 = (impulse_low + impulse_high) / 2
    
    return TradeSetup(
        asset=asset,
        mode=mode,
        direction=direction,
        state=TradeState.INDICATION,
        created_at_bar=h1_bar,
        daily_bias=daily_bias,
        h4_indication=h4_indication,
        h4_ob=h4_ob,
        impulse_low=impulse_low,
        impulse_high=impulse_high,
        fibo_50=fibo_50,
        correction_started_at_bar=h1_bar,
    )


def update_setup_state(
    setup: TradeSetup,
    h1_bar: int,
    h1_prices: pd.DataFrame,
    h1_structs: list[StructurePoint],
    daily_bias_now: BiasState,
    h4_obs: Optional[list[OrderBlock]] = None,
    daily_obs: Optional[list[OrderBlock]] = None,
) -> None:
    """
    Advance the setup's state machine by one H1 bar.
    Mutates `setup` in place.
    """
    if setup.state == TradeState.COOLDOWN:
        return  # terminal state for this setup
    
    closes = h1_prices['close'].values
    opens = h1_prices['open'].values
    highs = h1_prices['high'].values
    lows = h1_prices['low'].values
    timestamps = h1_prices.index
    
    current_close = closes[h1_bar]
    current_high = highs[h1_bar]
    current_low = lows[h1_bar]
    
    # ── INVALIDATION CHECKS (apply to INDICATION, CORRECTION, READY) ──
    if setup.state in (TradeState.INDICATION, TradeState.CORRECTION, TradeState.READY):
        # 1. Daily bias changed
        expected_bias = BiasState.BULL if setup.direction == Direction.BUY else BiasState.BEAR
        if daily_bias_now != expected_bias:
            _close_setup(setup, h1_bar, current_close, timestamps[h1_bar],
                         ExitReason.DAILY_REVERSAL)
            return
        
        # 2. Setup INVALIDATION = body close past impulse origin (not OB zone)
        # Per ICC: as long as price hasn't body-closed past the impulse_low (BUY)
        # or impulse_high (SELL), the setup is still alive even if price traverses the OB.
        # The OB can be touched, even penetrated, during correction without invalidation.
        # Only the impulse origin matters.
        if setup.direction == Direction.BUY:
            if current_close < setup.impulse_low:
                _close_setup(setup, h1_bar, current_close, timestamps[h1_bar],
                             ExitReason.CORRECTION_TOO_DEEP)
                return
        else:
            if current_close > setup.impulse_high:
                _close_setup(setup, h1_bar, current_close, timestamps[h1_bar],
                             ExitReason.CORRECTION_TOO_DEEP)
                return
    
    # ── INDICATION → CORRECTION ──
    if setup.state == TradeState.INDICATION:
        # We move to CORRECTION as soon as price starts retracing
        # (a bar in the opposite direction of the indication)
        is_retracing = False
        if setup.direction == Direction.BUY and current_close < opens[h1_bar]:
            is_retracing = True
        elif setup.direction == Direction.SELL and current_close > opens[h1_bar]:
            is_retracing = True
        
        if is_retracing:
            setup.state = TradeState.CORRECTION
            setup.correction_started_at_bar = h1_bar
        return  # one transition per bar
    
    # ── CORRECTION → READY → IN_TRADE ──
    if setup.state == TradeState.CORRECTION:
        # Track if we entered the OB H4 zone (Path A trigger)
        if not setup.deep_correction_reached:
            if setup.direction == Direction.BUY:
                # Touched OB zone if low <= OB.zone_high (entered from above)
                if current_low <= setup.h4_ob.zone_high:
                    setup.deep_correction_reached = True
            else:
                # Touched OB zone if high >= OB.zone_low (entered from below)
                if current_high >= setup.h4_ob.zone_low:
                    setup.deep_correction_reached = True
        
        # Track if price reached discount/premium zone (Path B trigger)
        if not setup.shallow_via_fibo:
            if setup.direction == Direction.BUY:
                # Discount: price went below 50% Fibo
                if current_low <= setup.fibo_50:
                    setup.shallow_via_fibo = True
            else:
                # Premium: price went above 50% Fibo
                if current_high >= setup.fibo_50:
                    setup.shallow_via_fibo = True
        
        # Now: check entry trigger
        # We need a recent H1 micro structure (LH for BUY, HL for SELL) formed during correction
        # And current bar body closes past it
        if not (setup.deep_correction_reached or setup.shallow_via_fibo):
            return  # neither path validated yet
        
        # Find the last opposite-type micro structure formed during correction
        target_type = 'LH' if setup.direction == Direction.BUY else 'HL'
        micro = _find_last_micro_during_correction(
            h1_structs, target_type,
            from_bar=setup.correction_started_at_bar,
            to_bar=h1_bar,
        )
        if micro is None:
            return  # no micro structure yet
        
        setup.h1_micro_swings.append(micro)
        
        # Check body close past it
        is_break = False
        if setup.direction == Direction.BUY and current_close > micro.price:
            is_break = True
        elif setup.direction == Direction.SELL and current_close < micro.price:
            is_break = True
        
        # Additional condition for Path A (deep correction):
        # Price must also re-enter past the OB zone in setup's direction
        if is_break and setup.deep_correction_reached and not setup.shallow_via_fibo:
            if setup.direction == Direction.BUY:
                if current_close <= setup.h4_ob.zone_high:
                    return  # break of LH but not yet back above OB
            else:
                if current_close >= setup.h4_ob.zone_low:
                    return
        
        if is_break:
            # TRIGGER ENTRY
            _trigger_entry(setup, h1_bar, current_close, timestamps[h1_bar],
                           h1_prices, h1_structs, h4_obs=h4_obs, daily_obs=daily_obs)
        return
    
    # ── IN_TRADE: monitor SL / TP / trailing ──
    if setup.state == TradeState.IN_TRADE:
        _monitor_in_trade(setup, h1_bar, h1_prices, h1_structs, current_close,
                           current_high, current_low, timestamps[h1_bar])
        return


def _find_last_micro_during_correction(
    h1_structs: list[StructurePoint],
    target_type: str,
    from_bar: int,
    to_bar: int,
) -> Optional[StructurePoint]:
    """Find the last structure of `target_type` (e.g. 'LH') confirmed between from_bar and to_bar."""
    for s in reversed(h1_structs):
        if s.confirmed_at_bar > to_bar:
            continue
        if s.confirmed_at_bar < from_bar:
            break
        if s.type == target_type:
            return s
    return None


# ============================================================================
# ENTRY & MONEY MANAGEMENT
# ============================================================================

def _trigger_entry(
    setup: TradeSetup,
    h1_bar: int,
    entry_price: float,
    entry_ts: pd.Timestamp,
    h1_prices: pd.DataFrame,
    h1_structs: list[StructurePoint],
    h4_obs: Optional[list[OrderBlock]] = None,
    daily_obs: Optional[list[OrderBlock]] = None,
):
    """Move setup to IN_TRADE, compute SL and TP."""
    setup.state = TradeState.IN_TRADE
    setup.entry_bar = h1_bar
    setup.entry_price = entry_price
    setup.entry_timestamp = entry_ts
    
    # SL = previous (avant-dernier) HL for BUY / LH for SELL on H1
    sl = _compute_initial_sl(setup, h1_bar, h1_structs)
    setup.sl_initial = sl
    setup.sl_current = sl
    setup.sl_history.append((h1_bar, sl))
    
    # TP = opposite OB on Daily/H4 (per spec) or fallback measured move 1:3
    tp, tp_source = _compute_initial_tp(setup, h1_bar, h4_obs=h4_obs, daily_obs=daily_obs)
    setup.tp_target = tp
    setup.tp_source = tp_source


def _compute_initial_sl(
    setup: TradeSetup,
    h1_bar: int,
    h1_structs: list[StructurePoint],
) -> float:
    """
    SL = below PREVIOUS HL (= avant-dernier HL) for BUY.
    SL = above PREVIOUS LH (= avant-dernier LH) for SELL.
    
    "Previous" means: the second-to-last HL/LH on H1 before the entry.
    """
    target_type = 'HL' if setup.direction == Direction.BUY else 'LH'
    found = []
    for s in reversed(h1_structs):
        if s.confirmed_at_bar > h1_bar:
            continue
        if s.type == target_type:
            found.append(s)
            if len(found) >= 2:
                break
    
    if len(found) >= 2:
        # Avant-dernier (second-to-last)
        prev = found[1]
        # SL slightly below/above
        if setup.direction == Direction.BUY:
            return prev.price * 0.999  # 0.1% buffer below
        else:
            return prev.price * 1.001  # 0.1% buffer above
    elif len(found) == 1:
        # Only one HL/LH found — use the impulse_low as fallback
        if setup.direction == Direction.BUY:
            return setup.impulse_low * 0.999
        else:
            return setup.impulse_high * 1.001
    else:
        # No HL/LH found — emergency fallback to OB H4 zone edge
        if setup.direction == Direction.BUY:
            return setup.h4_ob.zone_low * 0.999
        else:
            return setup.h4_ob.zone_high * 1.001


def _compute_initial_tp(
    setup: TradeSetup,
    h1_bar: int,
    h4_obs: Optional[list[OrderBlock]] = None,
    daily_obs: Optional[list[OrderBlock]] = None,
    min_rr_for_ob: float = 2.5,
    measured_move_rr: float = 3.0,
) -> tuple[float, str]:
    """
    Take Profit (per ICC spec + user preferences):
        Primary: closest opposite-direction OB on H4 or Daily,
                 if RR offered >= min_rr_for_ob (default 2.5)
        Fallback: measured move = entry + measured_move_rr * |entry - SL|
                  (default 3.0 per user preference for wider TP)
    """
    risk = abs(setup.entry_price - setup.sl_current)
    
    target_type = 'OB-' if setup.direction == Direction.BUY else 'OB+'
    candidate_obs: list[OrderBlock] = []
    
    for ob_list in (h4_obs or [], daily_obs or []):
        for ob in ob_list:
            if ob.type != target_type:
                continue
            if setup.direction == Direction.BUY:
                if ob.zone_low <= setup.entry_price:
                    continue
            else:
                if ob.zone_high >= setup.entry_price:
                    continue
            if ob.consumed:
                continue
            candidate_obs.append(ob)
    
    if candidate_obs:
        if setup.direction == Direction.BUY:
            best = min(candidate_obs, key=lambda ob: ob.zone_low)
            tp = best.zone_low
        else:
            best = max(candidate_obs, key=lambda ob: ob.zone_high)
            tp = best.zone_high
        
        tp_distance = abs(tp - setup.entry_price)
        rr = tp_distance / max(risk, 0.0001)
        
        # Only accept OB target if RR is good enough
        if rr >= min_rr_for_ob:
            return tp, f"OB_OPPOSITE_RR{rr:.2f}"
    
    # Fallback: measured move with user's preferred RR (default 3.0)
    if setup.direction == Direction.BUY:
        tp = setup.entry_price + measured_move_rr * risk
    else:
        tp = setup.entry_price - measured_move_rr * risk
    return tp, f"MEASURED_MOVE_1to{measured_move_rr:.1f}"


def _monitor_in_trade(
    setup: TradeSetup,
    h1_bar: int,
    h1_prices: pd.DataFrame,
    h1_structs: list[StructurePoint],
    current_close: float,
    current_high: float,
    current_low: float,
    current_ts: pd.Timestamp,
):
    """
    Monitor an open trade: check SL hit, TP hit, update trailing SL.

    SL exit semantics:
        - If sl_current == sl_initial   → SL_HIT (true loss, initial SL never moved)
        - If sl_current != sl_initial   → TRAILING_HIT (trailing SL moved, exit may be profit/BE/small loss)

    Partial close logic (per ICC spec):
        - First time price touches tp_target → close 85%, mark partial_closed
        - Remaining 15% continues with trailing SL
        - Final exit (trailing hit, daily reversal etc.) closes the 15%
        - Total PnL = 0.85 * partial_pnl + 0.15 * final_pnl
    """

    def _sl_exit_reason() -> ExitReason:
        """Determine if this is a true SL_HIT or a TRAILING_HIT."""
        # Trailing has moved if sl_current differs from sl_initial
        if setup.sl_initial is None:
            return ExitReason.SL_HIT
        # Use small tolerance for floating point equality
        if abs(setup.sl_current - setup.sl_initial) > 1e-9:
            return ExitReason.TRAILING_HIT
        return ExitReason.SL_HIT

    # ── SL hit ? ──
    if setup.direction == Direction.BUY:
        if current_low <= setup.sl_current:
            _close_setup(setup, h1_bar, setup.sl_current, current_ts, _sl_exit_reason())
            return
    else:  # SELL
        if current_high >= setup.sl_current:
            _close_setup(setup, h1_bar, setup.sl_current, current_ts, _sl_exit_reason())
            return

    # ── TP hit ? ──
    tp_hit_now = False
    if setup.direction == Direction.BUY and current_high >= setup.tp_target:
        tp_hit_now = True
    elif setup.direction == Direction.SELL and current_low <= setup.tp_target:
        tp_hit_now = True

    if tp_hit_now and not setup.partial_closed:
        # PARTIAL CLOSE: 85% locked in at TP, 15% continues with trailing
        setup.partial_closed = True
        setup.partial_closed_at_bar = h1_bar
        setup.partial_close_price = setup.tp_target

        if setup.direction == Direction.BUY:
            setup.partial_pnl_pct = (setup.tp_target - setup.entry_price) / setup.entry_price
        else:
            setup.partial_pnl_pct = (setup.entry_price - setup.tp_target) / setup.entry_price

        setup.remaining_size = 0.15

        # Move SL to entry+small buffer in the favorable direction is NOT done
        # (TradesSAI rule: no break-even). The remaining 15% keeps the structural trailing SL.
        # The trailing SL will naturally protect profits as new HL/LH form.

        # Note: we do NOT close the setup here. State stays IN_TRADE.
        # The remaining 15% will exit later via trailing/reversal/etc.
        # We just track the partial event.

    # ── Trailing SL: structural — follow new HL (BUY) / LH (SELL) ──
    target_type = 'HL' if setup.direction == Direction.BUY else 'LH'
    for s in reversed(h1_structs):
        if s.confirmed_at_bar > h1_bar:
            continue
        if s.confirmed_at_bar <= setup.entry_bar:
            break
        if s.type == target_type:
            new_sl_candidate = s.price * (0.999 if setup.direction == Direction.BUY else 1.001)
            if setup.direction == Direction.BUY and new_sl_candidate > setup.sl_current:
                setup.sl_current = new_sl_candidate
                setup.sl_history.append((h1_bar, new_sl_candidate))
            elif setup.direction == Direction.SELL and new_sl_candidate < setup.sl_current:
                setup.sl_current = new_sl_candidate
                setup.sl_history.append((h1_bar, new_sl_candidate))
            break


def _close_setup(
    setup: TradeSetup,
    h1_bar: int,
    exit_price: float,
    exit_ts: pd.Timestamp,
    reason: ExitReason,
):
    """
    Close a setup (whether in trade or pre-entry).

    PnL computation:
        - No partial: pnl_pct = simple entry→exit return
        - Partial done: pnl_pct = 0.85 * partial_pnl + 0.15 * remaining_pnl
                        (weighted by sizes per ICC partial close logic)
    """
    setup.state = TradeState.COOLDOWN
    setup.exit_bar = h1_bar
    setup.exit_price = exit_price
    setup.exit_timestamp = exit_ts
    setup.exit_reason = reason

    if setup.entry_price is None:
        # Closed before entry → no PnL
        return

    # Compute PnL of the remaining (or full) portion at this final exit
    if setup.direction == Direction.BUY:
        final_leg_pnl = (exit_price - setup.entry_price) / setup.entry_price
    else:
        final_leg_pnl = (setup.entry_price - exit_price) / setup.entry_price

    if setup.partial_closed and setup.partial_pnl_pct is not None:
        # 85% locked at partial_pnl + 15% at final_leg_pnl
        setup.pnl_pct = 0.85 * setup.partial_pnl_pct + 0.15 * final_leg_pnl
    else:
        # Full position exited at this point
        setup.pnl_pct = final_leg_pnl


# ============================================================================
# MAIN PIPELINE — multi-TF coordination
# ============================================================================

def run_icc_cycle(
    asset: str,
    daily_prices: pd.DataFrame,
    h4_prices: pd.DataFrame,
    h1_prices: pd.DataFrame,
    mode: TradeMode = TradeMode.SWING,
    daily_lookback: int = 5,
    h4_lookback: int = 3,
    h1_lookback: int = 3,
    verbose: bool = False,
    skip_daily_filter: bool = False,
    min_rr_for_ob_tp: float = 2.5,
    measured_move_rr: float = 3.0,
) -> list[TradeSetup]:
    """
    Run the full ICC cycle on synchronized multi-TF data.
    
    Args:
        asset: name of the asset
        daily_prices, h4_prices, h1_prices: OHLCV per TF
        mode: SWING (default) | INTRADAY | SCALPING
        *_lookback: swing_lookback for each TF
        skip_daily_filter: if True, ignore Daily bias (H4 alone determines direction)
                          Use this for INTRADAY mode where reactivity > strict alignment.
        min_rr_for_ob_tp: minimum RR for accepting an OB-opposite as TP (default 2.5)
        measured_move_rr: fallback TP = entry + RR * risk (default 3.0)
    
    Returns:
        List of all TradeSetup objects through their lifecycle.
    """
    # Step 1: detect structures on all 3 TFs
    daily_structs = detect_structures(daily_prices, swing_lookback=daily_lookback)
    h4_structs = detect_structures(h4_prices, swing_lookback=h4_lookback)
    h1_structs = detect_structures(h1_prices, swing_lookback=h1_lookback)
    
    # Step 2: detect Order Blocks on H4 AND Daily
    h4_obs = detect_order_blocks(h4_prices, structures=h4_structs)
    classify_discount_premium(h4_obs, h4_structs)
    
    daily_obs = detect_order_blocks(daily_prices, structures=daily_structs)
    classify_discount_premium(daily_obs, daily_structs)
    
    if verbose:
        print(f"  Daily: {len(daily_structs)} structures, {len(daily_obs)} OBs")
        print(f"  H4: {len(h4_structs)} structures, {len(h4_obs)} OBs")
        print(f"  H1: {len(h1_structs)} structures")
    
    # Step 3: identify all H4 break-type structures with valid OBs (indications)
    # These are the candidates for new setups
    indications_h4: list[tuple[StructurePoint, OrderBlock]] = []
    obs_by_struct_bar = {ob.structure_broken.bar_index: ob for ob in h4_obs}
    
    for s in h4_structs:
        if s.type not in ('NEW_HIGH', 'NEW_LOW', 'HH', 'LL'):
            continue
        ob = obs_by_struct_bar.get(s.bar_index)
        if ob is None:
            continue
        indications_h4.append((s, ob))
    
    if verbose:
        print(f"  → {len(indications_h4)} H4 indications with valid OBs")
    
    # Step 4: iterate through H1 bars and run state machine
    # For each new H4 indication encountered (in H1 time), try to create a setup.
    # All existing setups get updated each H1 bar.
    
    setups: list[TradeSetup] = []
    indication_h1_bars: dict[int, list[tuple[StructurePoint, OrderBlock]]] = {}
    
    # Pre-compute: for each H4 indication, find its H1 bar
    for h4_indic, h4_ob in indications_h4:
        h4_confirmed_ts = h4_indic.confirmed_at_ts
        h1_bar = find_h1_bar_for_h4_timestamp(h1_prices.index, h4_confirmed_ts)
        indication_h1_bars.setdefault(h1_bar, []).append((h4_indic, h4_ob))
    
    # Main loop over H1 bars
    for h1_bar in range(len(h1_prices)):
        h1_ts = h1_prices.index[h1_bar]
        
        # Compute bias at this point in time
        if skip_daily_filter:
            # INTRADAY mode: use H4 as the bias driver instead of Daily
            # Find the latest H4 bar at this H1 timestamp
            h4_pos = h4_prices.index.searchsorted(h1_ts, side='right') - 1
            h4_pos = max(0, h4_pos)
            daily_bias = compute_daily_bias(h4_structs, h4_pos)
        else:
            # SWING mode: standard Daily bias
            daily_bar = find_daily_bar_for_h1_timestamp(daily_prices.index, h1_ts)
            daily_bias = compute_daily_bias(daily_structs, daily_bar)
        
        # Update existing setups
        for setup in setups:
            if setup.state == TradeState.COOLDOWN:
                continue
            update_setup_state(setup, h1_bar, h1_prices, h1_structs, daily_bias,
                                h4_obs=h4_obs, daily_obs=daily_obs)
        
        # Try to create new setups from H4 indications confirmed at this H1 bar
        if h1_bar in indication_h1_bars:
            for h4_indic, h4_ob in indication_h1_bars[h1_bar]:
                # Only create if Daily aligned + no existing setup of same direction/asset
                # (per user decision Q5: multiple trades OK if same direction in different modes)
                new_setup = try_create_setup(
                    asset=asset, mode=mode,
                    h4_indication=h4_indic, h4_ob=h4_ob,
                    daily_bias=daily_bias,
                    h1_bar=h1_bar, h1_prices=h1_prices,
                )
                if new_setup is not None:
                    setups.append(new_setup)
    
    return setups


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def summarize_setups(setups: list[TradeSetup]) -> dict:
    if not setups:
        return {'n_total': 0}
    
    by_state = {}
    by_direction = {}
    by_exit_reason = {}
    n_in_trade = 0
    n_closed = 0
    pnls = []
    
    for s in setups:
        by_state[s.state.value] = by_state.get(s.state.value, 0) + 1
        by_direction[s.direction.value] = by_direction.get(s.direction.value, 0) + 1
        if s.exit_reason:
            by_exit_reason[s.exit_reason.value] = by_exit_reason.get(s.exit_reason.value, 0) + 1
        if s.state == TradeState.IN_TRADE:
            n_in_trade += 1
        if s.pnl_pct is not None:
            n_closed += 1
            pnls.append(s.pnl_pct)
    
    summary = {
        'n_total': len(setups),
        'n_in_trade': n_in_trade,
        'n_closed': n_closed,
        'by_state': by_state,
        'by_direction': by_direction,
        'by_exit_reason': by_exit_reason,
    }
    
    if pnls:
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        summary['n_wins'] = len(wins)
        summary['n_losses'] = len(losses)
        summary['win_rate'] = len(wins) / len(pnls) if pnls else 0
        summary['avg_pnl_pct'] = np.mean(pnls)
        summary['total_pnl_pct'] = sum(pnls)
        summary['avg_win_pct'] = np.mean(wins) if wins else 0
        summary['avg_loss_pct'] = np.mean(losses) if losses else 0
    
    return summary
