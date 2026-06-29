"""
ICC Order Blocks Detection — Session 3
========================================
Faithful implementation of Order Blocks per Test Unitaire #3 and the full
ICC specification.

KEY CONCEPTS (per TU#3 + spec doc):

    OB+ (bullish demand) = last bearish candle before a strong bullish move
    OB- (bearish supply) = last bullish candle before a strong bearish move

    Zone of an OB = [open, close] of that candle (body only, never wicks)

VALIDATION (mandatory for OB to be valid):

    The move following the OB must:
    1. Break an opposite-direction structure (per icc_structure):
       - OB+ must be followed by a move that breaks an LH or LL
       - OB- must be followed by a move that breaks a HL or HH
    2. Have minimum N candles of the same direction:
       - 3+ candles + FVG present → VALID
       - 5+ candles without FVG → VALID
       - < 3 candles → INVALID even with FVG

STRENGTH SCORING (per spec):

    VERY_STRONG : FVG + breaks old structure + min 3 candles
    STRONG      : (FVG + 3 candles) OR (structure break + 5+ candles)
    MODERATE    : 5+ candles, no FVG, no structure break
    WEAK        : < 3 candles or 3-4 without FVG = INVALID, not kept

FAIR VALUE GAP (FVG) detection:

    Bullish FVG: low[i+2] > high[i]   (gap between candle i and candle i+2)
    Bearish FVG: high[i+2] < low[i]

DISCOUNT / PREMIUM:

    Range = active_high.price - active_low.price (from icc_structure)
    50% = midpoint = equilibrium
    Premium zone (above 50%) → look for OB- to sell
    Discount zone (below 50%) → look for OB+ to buy

USAGE UNIQUE:

    Once an OB is tested (price returns into its zone), it's marked consumed
    and never used again.

NO LOOKAHEAD:

    OBs are detected only when the structure break is confirmed (at bar X+W
    in icc_structure). The OB itself is historical, but we don't "see" it
    until the break is confirmed. This keeps backtest fidelity.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
import numpy as np
import pandas as pd

# Use the structures from Session 2
from strategies.icc_structure import (
    StructurePoint,
    detect_structures,
)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

OBType = Literal['OB+', 'OB-']
StrengthLevel = Literal['VERY_STRONG', 'STRONG', 'MODERATE']  # WEAK = rejected, not stored


@dataclass
class OrderBlock:
    """A validated Order Block per ICC spec."""
    type: OBType
    zone_high: float         # max(open, close) of the OB candle
    zone_low: float          # min(open, close) of the OB candle
    timestamp: pd.Timestamp
    bar_index: int           # index of the OB candle in the input data
    
    # Validation context
    detected_at_bar: int     # bar where break was confirmed (= when OB became "visible")
    detected_at_ts: pd.Timestamp
    structure_broken: StructurePoint  # the structure that was broken (validates OB)
    
    # Movement characteristics
    n_candles_in_move: int   # number of same-direction candles between OB and break
    has_fvg: bool            # FVG present in the move
    
    # Strength
    strength: StrengthLevel
    
    # Consumption tracking
    consumed: bool = False
    consumed_at_bar: Optional[int] = None
    consumed_at_ts: Optional[pd.Timestamp] = None
    
    # Optional: discount/premium classification (computed at detection time)
    in_discount: Optional[bool] = None  # True if OB+ in discount, OB- in premium
    
    def is_bullish(self) -> bool:
        return self.type == 'OB+'
    
    def is_bearish(self) -> bool:
        return self.type == 'OB-'
    
    def contains_price(self, price: float) -> bool:
        """Check if a price falls within the OB zone."""
        return self.zone_low <= price <= self.zone_high
    
    def __repr__(self):
        status = '✗consumed' if self.consumed else '✓active'
        dp = '' if self.in_discount is None else (' [D]' if self.in_discount else ' [P]')
        return (f"<{self.type} {self.strength}{dp} @ bar{self.bar_index} "
                f"zone=[{self.zone_low:.2f}, {self.zone_high:.2f}] {status}>")


# ============================================================================
# CORE DETECTION ALGORITHM
# ============================================================================

def detect_order_blocks(
    prices: pd.DataFrame,
    structures: Optional[list[StructurePoint]] = None,
    swing_lookback: int = 3,
) -> list[OrderBlock]:
    """
    Detect ICC Order Blocks from OHLCV data.
    
    Args:
        prices: DataFrame with ['open', 'high', 'low', 'close']
        structures: optional pre-computed structures from detect_structures().
                    If None, will be computed automatically.
        swing_lookback: W parameter for structure detection (only used if
                        structures is None).
    
    Returns:
        List of OrderBlock objects in chronological order (by detection bar).
    """
    required = {'open', 'high', 'low', 'close'}
    if not required.issubset(prices.columns):
        raise ValueError(f"prices must have columns {required}")
    
    if structures is None:
        structures = detect_structures(prices, swing_lookback=swing_lookback)
    
    if not structures:
        return []
    
    opens = prices['open'].values
    closes = prices['close'].values
    highs = prices['high'].values
    lows = prices['low'].values
    timestamps = prices.index
    
    order_blocks: list[OrderBlock] = []
    
    # For each structure that represents a BREAK (NEW_HIGH/NEW_LOW/HH/LL),
    # find the OB that initiated the impulse.
    # The OB candle is the LAST opposite-direction candle BEFORE the impulse.
    
    for struct in structures:
        # Only break-type structures trigger OB detection
        if struct.type not in ('NEW_HIGH', 'NEW_LOW', 'HH', 'LL'):
            continue
        
        # Find the OB candle by scanning back from the break bar
        ob_type: OBType = 'OB+' if struct.type in ('NEW_HIGH', 'HH') else 'OB-'
        
        ob_candle_bar = _find_ob_candle(
            opens=opens, closes=closes,
            break_bar=struct.bar_index,
            search_back_until=struct.origin_bar_index if struct.origin_bar_index else 0,
            ob_type=ob_type,
        )
        
        if ob_candle_bar is None:
            continue  # no opposite candle found, skip
        
        # Count consecutive same-direction candles in the move
        n_candles = _count_move_candles(
            opens=opens, closes=closes,
            from_bar=ob_candle_bar + 1,
            to_bar=struct.bar_index,
            bullish=(ob_type == 'OB+'),
        )
        
        # Detect FVG in the move
        has_fvg = _detect_fvg_in_move(
            highs=highs, lows=lows,
            from_bar=ob_candle_bar,
            to_bar=struct.bar_index,
            bullish=(ob_type == 'OB+'),
        )
        
        # Strength scoring per spec
        strength = _score_strength(
            n_candles=n_candles,
            has_fvg=has_fvg,
            structure_broken=True,  # always true here (struct is a break event)
        )
        
        if strength is None:
            # WEAK or INVALID — not kept
            continue
        
        # Build the OrderBlock
        ob = OrderBlock(
            type=ob_type,
            zone_high=max(opens[ob_candle_bar], closes[ob_candle_bar]),
            zone_low=min(opens[ob_candle_bar], closes[ob_candle_bar]),
            timestamp=timestamps[ob_candle_bar],
            bar_index=ob_candle_bar,
            detected_at_bar=struct.confirmed_at_bar,
            detected_at_ts=struct.confirmed_at_ts,
            structure_broken=struct,
            n_candles_in_move=n_candles,
            has_fvg=has_fvg,
            strength=strength,
        )
        order_blocks.append(ob)
    
    # Track consumption: scan forward, when price re-enters an OB zone, mark consumed
    _track_consumption(order_blocks, opens, closes, highs, lows, timestamps)
    
    return order_blocks


# ============================================================================
# OB CANDLE DETECTION (retrospective search)
# ============================================================================

def _find_ob_candle(
    opens: np.ndarray,
    closes: np.ndarray,
    break_bar: int,
    search_back_until: int,
    ob_type: OBType,
) -> Optional[int]:
    """
    Find the OB candle by scanning back from break_bar.
    
    For OB+ (bullish move ahead): find the last BEARISH candle (close < open)
                                   before the bullish move.
    For OB- (bearish move ahead): find the last BULLISH candle (close > open)
                                   before the bearish move.
    
    We scan back from break_bar - 1 toward search_back_until.
    """
    want_bearish_candle = (ob_type == 'OB+')
    
    # Search range: from just before the break, back to the origin
    start = max(search_back_until, 0)
    
    for i in range(break_bar - 1, start - 1, -1):
        is_bearish = closes[i] < opens[i]
        is_bullish = closes[i] > opens[i]
        
        if want_bearish_candle and is_bearish:
            return i
        if not want_bearish_candle and is_bullish:
            return i
    
    return None


# ============================================================================
# MOVE ANALYSIS
# ============================================================================

def _count_move_candles(
    opens: np.ndarray,
    closes: np.ndarray,
    from_bar: int,
    to_bar: int,
    bullish: bool,
) -> int:
    """Count consecutive same-direction candles in the move [from_bar, to_bar]."""
    if from_bar > to_bar:
        return 0
    
    count = 0
    for i in range(from_bar, to_bar + 1):
        if bullish and closes[i] > opens[i]:
            count += 1
        elif not bullish and closes[i] < opens[i]:
            count += 1
        # doji or opposite candle: still counted in the move (just not same-direction)
        # Per spec, we count "consecutive same-direction" — strict reading:
        # we count only bullish-for-OB+ or bearish-for-OB-
    return count


def _detect_fvg_in_move(
    highs: np.ndarray,
    lows: np.ndarray,
    from_bar: int,
    to_bar: int,
    bullish: bool,
) -> bool:
    """
    Detect if there's a Fair Value Gap in the move.
    
    Bullish FVG: low[i+2] > high[i]  (gap between candle i and candle i+2)
    Bearish FVG: high[i+2] < low[i]
    
    Scans all 3-candle windows in [from_bar, to_bar - 2].
    """
    if to_bar - from_bar < 2:
        return False
    
    for i in range(from_bar, to_bar - 1):
        if i + 2 > to_bar:
            break
        if bullish:
            # Bullish FVG: gap between bar i (high) and bar i+2 (low)
            if lows[i + 2] > highs[i]:
                return True
        else:
            # Bearish FVG: gap between bar i (low) and bar i+2 (high)
            if highs[i + 2] < lows[i]:
                return True
    return False


# ============================================================================
# STRENGTH SCORING (strict to spec)
# ============================================================================

def _score_strength(
    n_candles: int,
    has_fvg: bool,
    structure_broken: bool,
) -> Optional[StrengthLevel]:
    """
    Score the OB strength per spec rules.
    
    Per ICC_SPEC.md:
        VERY_STRONG : FVG + breaks structure + min 3 candles
        STRONG      : (FVG + 3 candles) OR (structure break + 5+ candles)
        MODERATE    : 5+ candles, no FVG, no structure break
        WEAK / INVALID : < 3 candles, or 3-4 without FVG
                         → return None (not kept)
    
    NOTE: In our pipeline, structure_broken is always True for stored OBs,
    so this function's primary discriminator is n_candles + has_fvg.
    """
    # Invalid: less than 3 candles in the move
    if n_candles < 3:
        return None
    
    # 3-4 candles: need FVG to be valid
    if n_candles < 5 and not has_fvg:
        return None  # WEAK
    
    # Now we have either (3-4 with FVG) or (5+ with/without FVG), and structure_broken=True
    
    if has_fvg and structure_broken and n_candles >= 3:
        return 'VERY_STRONG'
    
    if (has_fvg and n_candles >= 3) or (structure_broken and n_candles >= 5):
        return 'STRONG'
    
    if n_candles >= 5:
        return 'MODERATE'
    
    return None  # safety fallback


# ============================================================================
# CONSUMPTION TRACKING
# ============================================================================

def _track_consumption(
    order_blocks: list[OrderBlock],
    opens: np.ndarray,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    timestamps: pd.DatetimeIndex,
):
    """
    Mark OBs as consumed when price re-enters their zone after detection.
    
    An OB is consumed at the first bar (after detected_at_bar) where the
    candle's range [low, high] intersects the OB's zone [zone_low, zone_high].
    """
    for ob in order_blocks:
        # Scan from the bar AFTER detection forward
        start = ob.detected_at_bar + 1
        for i in range(start, len(closes)):
            bar_high = highs[i]
            bar_low = lows[i]
            # Check if bar range intersects OB zone
            if bar_low <= ob.zone_high and bar_high >= ob.zone_low:
                ob.consumed = True
                ob.consumed_at_bar = i
                ob.consumed_at_ts = timestamps[i]
                break


# ============================================================================
# DISCOUNT / PREMIUM CLASSIFICATION
# ============================================================================

def classify_discount_premium(
    order_blocks: list[OrderBlock],
    structures: list[StructurePoint],
):
    """
    For each OB, classify whether it sits in the discount or premium zone
    relative to the active range at detection time.
    
    Range = (active_high.price + active_low.price) / 2 = midpoint (50%)
    Premium zone: above midpoint
    Discount zone: below midpoint
    
    For OB+: ideally in DISCOUNT (below 50% range) — sets in_discount=True
    For OB-: ideally in PREMIUM (above 50% range) — sets in_discount=True
    
    "in_discount" actually means "in the favorable zone for this OB type."
    """
    for ob in order_blocks:
        # Find active high/low at the moment of OB detection
        active_high = None
        active_low = None
        for s in structures:
            if s.bar_index > ob.detected_at_bar:
                break
            if s.is_high() and not s.broken:
                active_high = s
            elif s.is_low() and not s.broken:
                active_low = s
            # If broken: check if broken_at_bar > ob.detected_at_bar
            elif s.broken and s.broken_at_bar is not None and s.broken_at_bar > ob.detected_at_bar:
                # was still active at OB detection time
                if s.is_high():
                    active_high = s
                else:
                    active_low = s
        
        if active_high is None or active_low is None:
            ob.in_discount = None
            continue
        
        midpoint = (active_high.price + active_low.price) / 2
        ob_midpoint = (ob.zone_high + ob.zone_low) / 2
        
        if ob.type == 'OB+':
            # OB+ should be in DISCOUNT (below 50%)
            ob.in_discount = ob_midpoint < midpoint
        else:
            # OB- should be in PREMIUM (above 50%)
            ob.in_discount = ob_midpoint > midpoint


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def summarize_order_blocks(obs: list[OrderBlock]) -> dict:
    """Summary statistics."""
    if not obs:
        return {'n_total': 0}
    
    by_type = {}
    by_strength = {}
    for ob in obs:
        by_type[ob.type] = by_type.get(ob.type, 0) + 1
        by_strength[ob.strength] = by_strength.get(ob.strength, 0) + 1
    
    n_consumed = sum(1 for ob in obs if ob.consumed)
    n_active = sum(1 for ob in obs if not ob.consumed)
    n_with_fvg = sum(1 for ob in obs if ob.has_fvg)
    
    return {
        'n_total': len(obs),
        'n_active': n_active,
        'n_consumed': n_consumed,
        'n_with_fvg': n_with_fvg,
        'by_type': by_type,
        'by_strength': by_strength,
        'first': obs[0].timestamp,
        'last': obs[-1].timestamp,
    }


def get_active_obs(obs: list[OrderBlock]) -> list[OrderBlock]:
    return [ob for ob in obs if not ob.consumed]


def get_obs_by_type(obs: list[OrderBlock], ob_type: OBType) -> list[OrderBlock]:
    return [ob for ob in obs if ob.type == ob_type]


def get_obs_by_strength(obs: list[OrderBlock], strength: StrengthLevel) -> list[OrderBlock]:
    return [ob for ob in obs if ob.strength == strength]
