"""
ICC Structure Detection — v2 (clean 2-step architecture)
==========================================================
Faithful implementation of ICC market structure detection per the Test Unitaires
(TU#1 La Bougie, TU#2 La Structure de Marché) and the full ICC specification.

Architecture (2-step, no shortcuts):

    STEP 1: SWING CONFIRMATION (lag = swing_lookback bars)
        A bar i is confirmed as a swing high at time (i + W) if:
            close[i] >= close[j] for all j in [i-W, i+W], j != i
        Same for swing low (minimum).
        We never use future data to confirm a swing — only past bars at lag W.

    STEP 2: CLASSIFICATION (per swing event)
        For each newly-confirmed swing, we classify it as one of:
            INITIAL_HIGH / INITIAL_LOW  — first swing of its kind
            NEW_HIGH / NEW_LOW          — CHoCH (1st break of opposite trend)
            HH / HL / LH / LL           — reproduction in established trend
        Classification depends on:
            (a) the current active high/low (last unbroken reference)
            (b) the current trend direction (BULL / BEAR / NEUTRAL)
            (c) the swing price vs reference

Key rules enforced (per TU specifications):
    1. Body close only — wicks never trigger anything (TU#1)
    2. Lag-W confirmation — no lookahead bias
    3. Origin of impulse — swing high's "origin" = the prior swing low
    4. Sequence awareness — HH only after the trend was already BULL
    5. State persistence — active vs broken structures tracked
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
import pandas as pd
import numpy as np


# ============================================================================
# DATA STRUCTURES
# ============================================================================

StructureType = Literal[
    'INITIAL_HIGH',
    'INITIAL_LOW',
    'NEW_HIGH',
    'NEW_LOW',
    'HH',
    'HL',
    'LH',
    'LL',
]

TrendState = Literal['BULL', 'BEAR', 'NEUTRAL']


@dataclass
class StructurePoint:
    """A confirmed ICC structure point with full context."""
    type: StructureType
    price: float                       # close at the swing bar
    timestamp: pd.Timestamp
    bar_index: int                     # absolute index in input DataFrame
    confirmed_at_bar: int              # the bar at which we could "see" this swing (bar_index + W)
    confirmed_at_ts: pd.Timestamp
    origin_bar_index: Optional[int] = None   # the prior opposite swing
    origin_price: Optional[float] = None
    broken: bool = False
    broken_at_bar: Optional[int] = None
    broken_at_ts: Optional[pd.Timestamp] = None

    def is_high(self) -> bool:
        return self.type in ('INITIAL_HIGH', 'NEW_HIGH', 'HH', 'LH')

    def is_low(self) -> bool:
        return self.type in ('INITIAL_LOW', 'NEW_LOW', 'HL', 'LL')

    def __repr__(self):
        status = '✗broken' if self.broken else '✓active'
        return (f"<{self.type} @ bar{self.bar_index} "
                f"price={self.price:.2f} {status}>")


# ============================================================================
# STEP 1: SWING DETECTION (with lag = W)
# ============================================================================

def is_swing_high(closes: np.ndarray, i: int, w: int) -> bool:
    """Bar i is a swing high if its close is the maximum of [i-w, i+w] (inclusive).
    Strict on the left (must be strictly greater than all left neighbors),
    inclusive on the right (allows equality on right neighbors) — but we still
    require it to be the maximum overall."""
    if i < w or i + w >= len(closes):
        return False
    window = closes[i - w: i + w + 1]
    return closes[i] == window.max() and closes[i] > closes[i - w: i].max()


def is_swing_low(closes: np.ndarray, i: int, w: int) -> bool:
    """Bar i is a swing low if its close is the minimum of [i-w, i+w]."""
    if i < w or i + w >= len(closes):
        return False
    window = closes[i - w: i + w + 1]
    return closes[i] == window.min() and closes[i] < closes[i - w: i].min()


# ============================================================================
# STEP 2: MAIN DETECTION PIPELINE
# ============================================================================

def detect_structures(
    prices: pd.DataFrame,
    swing_lookback: int = 3,
) -> list[StructurePoint]:
    """
    Detect ICC market structure points from chronologically-sorted OHLCV.

    Args:
        prices: DataFrame with columns ['open', 'high', 'low', 'close']
                and a sorted DatetimeIndex.
        swing_lookback: W parameter — number of bars on each side needed
                        to confirm a swing (default 3).

    Returns:
        List of StructurePoint objects in chronological order by bar_index.
    """
    required = {'open', 'high', 'low', 'close'}
    if not required.issubset(prices.columns):
        raise ValueError(f"prices must have columns {required}")
    if len(prices) < 2 * swing_lookback + 5:
        return []

    closes = prices['close'].values
    timestamps = prices.index
    W = swing_lookback

    structures: list[StructurePoint] = []

    # State variables
    active_high: Optional[StructurePoint] = None
    active_low: Optional[StructurePoint] = None
    trend: TrendState = 'NEUTRAL'

    # We iterate through bars and confirm swings with lag W.
    # At iteration i, we check if bar (i - W) was a swing.
    n = len(closes)
    for i in range(W, n):
        cand_bar = i - W
        # We need bar (i+W) inside data to confirm — but we're already at i, so
        # we need i + 0 = i to be valid (since right-side has W bars from cand_bar)
        # i.e. cand_bar + W = i, which is current bar. OK.

        # Cannot confirm yet if not enough right context
        if cand_bar < W:
            continue

        # Check swing high at cand_bar
        if is_swing_high(closes, cand_bar, W):
            _process_new_swing(
                kind='HIGH',
                cand_bar=cand_bar,
                confirmed_at=i,
                closes=closes,
                timestamps=timestamps,
                structures=structures,
                state=lambda: (active_high, active_low, trend),
            )
            # Update state by reading the last added structure
            active_high, active_low, trend = _refresh_state(structures)

        # Check swing low at cand_bar (can coexist with swing high in degenerate cases)
        if is_swing_low(closes, cand_bar, W):
            _process_new_swing(
                kind='LOW',
                cand_bar=cand_bar,
                confirmed_at=i,
                closes=closes,
                timestamps=timestamps,
                structures=structures,
                state=lambda: (active_high, active_low, trend),
            )
            active_high, active_low, trend = _refresh_state(structures)

    return structures


# ============================================================================
# CORE CLASSIFICATION LOGIC
# ============================================================================

def _process_new_swing(
    kind: Literal['HIGH', 'LOW'],
    cand_bar: int,
    confirmed_at: int,
    closes: np.ndarray,
    timestamps: pd.DatetimeIndex,
    structures: list[StructurePoint],
    state,
):
    """Classify a newly-confirmed swing and append it to structures."""
    active_high, active_low, trend = state()
    new_price = closes[cand_bar]

    if kind == 'HIGH':
        sp_type = _classify_high(new_price, active_high, trend)
        origin = _find_prior_opposite_swing(structures, want_high=False, before_bar=cand_bar)
    else:
        sp_type = _classify_low(new_price, active_low, trend)
        origin = _find_prior_opposite_swing(structures, want_high=True, before_bar=cand_bar)

    sp = StructurePoint(
        type=sp_type,
        price=new_price,
        timestamp=timestamps[cand_bar],
        bar_index=cand_bar,
        confirmed_at_bar=confirmed_at,
        confirmed_at_ts=timestamps[confirmed_at],
        origin_bar_index=origin.bar_index if origin else None,
        origin_price=origin.price if origin else None,
    )
    structures.append(sp)

    # If this swing broke the active opposite reference, mark it broken
    if kind == 'HIGH' and active_high is not None and new_price > active_high.price:
        active_high.broken = True
        active_high.broken_at_bar = cand_bar
        active_high.broken_at_ts = timestamps[cand_bar]
    elif kind == 'LOW' and active_low is not None and new_price < active_low.price:
        active_low.broken = True
        active_low.broken_at_bar = cand_bar
        active_low.broken_at_ts = timestamps[cand_bar]


def _classify_high(
    new_price: float,
    active_high: Optional[StructurePoint],
    trend: TrendState,
) -> StructureType:
    """Decide if a new swing high is INITIAL_HIGH, NEW_HIGH, HH, or LH."""
    if active_high is None:
        return 'INITIAL_HIGH'
    if new_price > active_high.price:
        # Breaks the active high — bullish event
        if trend == 'BULL':
            return 'HH'  # already bullish → reproduction
        else:
            return 'NEW_HIGH'  # CHoCH: first bullish break after bear/neutral
    else:
        # Doesn't break active high → it's a lower high
        return 'LH'


def _classify_low(
    new_price: float,
    active_low: Optional[StructurePoint],
    trend: TrendState,
) -> StructureType:
    """Decide if a new swing low is INITIAL_LOW, NEW_LOW, LL, or HL."""
    if active_low is None:
        return 'INITIAL_LOW'
    if new_price < active_low.price:
        if trend == 'BEAR':
            return 'LL'
        else:
            return 'NEW_LOW'
    else:
        return 'HL'


# ============================================================================
# STATE MANAGEMENT
# ============================================================================

def _refresh_state(
    structures: list[StructurePoint],
) -> tuple[Optional[StructurePoint], Optional[StructurePoint], TrendState]:
    """Recompute (active_high, active_low, trend) from the current structures list."""
    active_high: Optional[StructurePoint] = None
    active_low: Optional[StructurePoint] = None
    trend: TrendState = 'NEUTRAL'

    for s in structures:
        if s.is_high() and not s.broken:
            active_high = s
        elif s.is_low() and not s.broken:
            active_low = s

    # Determine trend from the most recent meaningful structure
    # BULL: last meaningful was HH or NEW_HIGH and not broken
    # BEAR: last meaningful was LL or NEW_LOW and not broken
    # Otherwise NEUTRAL
    for s in reversed(structures):
        if s.type in ('HH', 'NEW_HIGH'):
            trend = 'BULL'
            break
        if s.type in ('LL', 'NEW_LOW'):
            trend = 'BEAR'
            break
        # HL alone after NEW_LOW could still mean bull is starting; we keep it neutral
        # LH alone after NEW_HIGH could still mean bear is starting; we keep it neutral

    return active_high, active_low, trend


def _find_prior_opposite_swing(
    structures: list[StructurePoint],
    want_high: bool,
    before_bar: int,
) -> Optional[StructurePoint]:
    """Find the most recent swing of the opposite type before a given bar."""
    for s in reversed(structures):
        if s.bar_index >= before_bar:
            continue
        if want_high and s.is_high():
            return s
        if not want_high and s.is_low():
            return s
    return None


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def summarize_structures(structures: list[StructurePoint]) -> dict:
    """Return summary stats."""
    if not structures:
        return {'n_total': 0}
    counts = {}
    for s in structures:
        counts[s.type] = counts.get(s.type, 0) + 1
    return {
        'n_total': len(structures),
        'n_active': sum(1 for s in structures if not s.broken),
        'n_broken': sum(1 for s in structures if s.broken),
        'by_type': counts,
        'first': structures[0].timestamp,
        'last': structures[-1].timestamp,
    }


def get_active_structures(structures: list[StructurePoint]) -> list[StructurePoint]:
    return [s for s in structures if not s.broken]


def get_structures_by_type(
    structures: list[StructurePoint],
    structure_type: StructureType,
) -> list[StructurePoint]:
    return [s for s in structures if s.type == structure_type]
