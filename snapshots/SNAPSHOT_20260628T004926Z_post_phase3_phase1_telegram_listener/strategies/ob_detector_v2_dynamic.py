"""
ob_detector_v2_dynamic.py — Badoun's dynamic OB definition
============================================================

Refactored OB detector built on Badoun's explicit clarification (22 May 2026).

THE CORE INSIGHT — what changed vs `icc_orderblocks.py`
------------------------------------------------------

The PREVIOUS detector (icc_orderblocks.py) treats an OB as valid only if:
  - the impulsive move has 3+ same-direction candles (consecutive)
  - AND a FVG is present
  - AND the move breaks a structure
  - Otherwise the OB is filtered out by `_score_strength` → WEAK → rejected

Badoun's DYNAMIC definition — the structural break IS the sole validator:

  > "OB- = la DERNIÈRE bougie haussière avant le mouvement baissier qui
  >  finalise le LL. Si pendant le move baissier une autre bougie haussière
  >  apparaît, elle devient la NOUVELLE référence OB- (parce qu'elle est la
  >  plus récente avant la continuation baissière qui finalise le break)."
  > —Badoun, 22 mai 2026

No requirement of N consecutive bars. No hard FVG requirement.

Algorithm
---------

For every confirmed structural break (CHoCH or BoS — i.e. NEW_HIGH/NEW_LOW/HH/LL):

1. Identify the search range : from `break_bar - 1` back to the
   `origin_bar_index` of the broken structure (= the opposite-direction
   swing pivot that preceded the broken swing).
2. Walk backwards in that range, looking for the **most recent**
   body-close candle whose color is OPPOSITE to the impulse direction :
     - OB- (bearish move that broke a swing high) → most recent **bullish** candle
     - OB+ (bullish move that broke a swing low)  → most recent **bearish** candle
3. Skip dojis (open == close exactly).
4. That candle is the OB.
5. Anchors :
     - OB- :  wick_anchor = `low` of the wick (Badoun's invalidation level)
              body_anchor = `close` of the OB candle (the validated level)
              zone        = [low, high] full range (wick included)
     - OB+ :  wick_anchor = `high` of the wick
              body_anchor = `close`
              zone        = [low, high] full range

Successive breaks → successive OBs (each break produces its own OB,
no dedup). Per Badoun's explicit confirmation: "chaîne de cassures = chaîne
de OBs distincts".

Differences vs the previous detector
-------------------------------------

| Aspect                | icc_orderblocks.py (V2 strict) | this file (V2 dynamic)        |
|-----------------------|-------------------------------|-------------------------------|
| Structure default W   | 3                             | 2  (matches Badoun's eye)     |
| Strength filter       | VERY_STRONG / STRONG / MOD    | None — break is the validator |
| FVG requirement       | Required for VERY_STRONG      | Detected and logged, optional |
| Consec candles        | Required (3+ with FVG, 5+ no) | Not required                  |
| OB candle scan        | Walk back, last opposite      | SAME — walk back, last opposite |
| Doji handling         | Treated as non-opposite       | Explicitly skipped            |
| Zone definition       | Body only [min(o,c), max(o,c)] | Full wick range [low, high]   |
| Wick anchor field     | Not stored                    | Stored explicitly             |

The OB candle search logic itself (walk back from break to origin, find
last opposite-color candle) is unchanged — V2 strict already implements
that correctly via `_find_ob_candle`. The big change is removing the
strength filter and the consec-candle requirement.

Backwards compatibility
-----------------------

This file is STANDALONE. It does NOT modify `icc_orderblocks.py`. Both
detectors live side by side. The decision of which one to canonicalize
(or whether to merge) is deferred to the gate of 12 August 2026 per
the project's no-mid-trip-parameter-change rule.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
import numpy as np
import pandas as pd

from strategies.icc_structure import (
    StructurePoint,
    detect_structures,
)


OBType = Literal['OB+', 'OB-']


# ============================================================================
# DATA STRUCTURE
# ============================================================================

@dataclass
class DynamicOB:
    """A Badoun-dynamic OB. Single validator = the structural break."""

    type: OBType
    bar_index: int                # the OB candle in the input DataFrame
    timestamp: pd.Timestamp

    # Anchors (Badoun's vocabulary)
    wick_anchor_price: float      # low for OB-, high for OB+
    body_open: float
    body_close: float
    wick_high: float
    wick_low: float

    # Full zone (wick-inclusive)
    zone_low: float               # = wick_low always
    zone_high: float              # = wick_high always

    # Break context
    structure_broken: StructurePoint
    break_bar: int                # confirmation bar
    break_ts: pd.Timestamp

    # Informational (not used as filters in this detector)
    n_bars_between_ob_and_break: int   # how far back from the break
    has_fvg_after: bool                # FVG detected in the move (info only)
    consec_same_color_count: int       # consecutive opposite-color in the move (info only)

    # Consumption tracking (downstream use)
    consumed: bool = False
    consumed_at_bar: Optional[int] = None
    consumed_at_ts: Optional[pd.Timestamp] = None

    def is_bullish(self) -> bool:
        return self.type == 'OB+'

    def is_bearish(self) -> bool:
        return self.type == 'OB-'

    def contains_price(self, price: float) -> bool:
        """Price inside the full wick-inclusive zone."""
        return self.zone_low <= price <= self.zone_high

    def __repr__(self):
        status = '✗consumed' if self.consumed else '✓active'
        anchor_kind = 'wick_low' if self.type == 'OB-' else 'wick_high'
        return (f"<{self.type}-dyn @ bar{self.bar_index} "
                f"{anchor_kind}={self.wick_anchor_price:.2f} "
                f"body_close={self.body_close:.2f} {status}>")


# ============================================================================
# HELPERS
# ============================================================================

def _is_strictly_bullish(opens: np.ndarray, closes: np.ndarray, i: int) -> bool:
    return closes[i] > opens[i]

def _is_strictly_bearish(opens: np.ndarray, closes: np.ndarray, i: int) -> bool:
    return closes[i] < opens[i]

def _find_last_opposite_candle(
    opens: np.ndarray,
    closes: np.ndarray,
    break_bar: int,
    search_back_until: int,
    want_bullish: bool,
) -> Optional[int]:
    """Walk backward from break_bar-1 to search_back_until, return MOST RECENT
    strictly-opposite-color body-close candle. Dojis are skipped."""
    start = max(search_back_until, 0)
    for i in range(break_bar - 1, start - 1, -1):
        if want_bullish and _is_strictly_bullish(opens, closes, i):
            return i
        if (not want_bullish) and _is_strictly_bearish(opens, closes, i):
            return i
        # Doji (open == close exactly) is skipped → continue
    return None


def _detect_fvg_in_move(
    highs: np.ndarray,
    lows: np.ndarray,
    from_bar: int,
    to_bar: int,
    bullish_move: bool,
) -> bool:
    """Look for an FVG (gap between candle i and i+2) inside [from_bar, to_bar].
    Information only — not used as a filter in this detector."""
    if to_bar - from_bar < 2:
        return False
    for i in range(from_bar, to_bar - 1):
        if i + 2 >= len(highs):
            break
        if bullish_move and lows[i + 2] > highs[i]:
            return True
        if (not bullish_move) and highs[i + 2] < lows[i]:
            return True
    return False


def _count_consecutive_same_color(
    opens: np.ndarray,
    closes: np.ndarray,
    from_bar: int,
    bullish_move: bool,
) -> int:
    """Info: count strictly same-color candles starting at from_bar."""
    n = 0
    for i in range(from_bar, len(closes)):
        if bullish_move and _is_strictly_bullish(opens, closes, i):
            n += 1
        elif (not bullish_move) and _is_strictly_bearish(opens, closes, i):
            n += 1
        else:
            break
    return n


# ============================================================================
# CORE DETECTION
# ============================================================================

def detect_obs_dynamic(
    prices: pd.DataFrame,
    structures: Optional[list[StructurePoint]] = None,
    swing_lookback: int = 2,
) -> list[DynamicOB]:
    """Detect OBs per Badoun's dynamic definition.

    Args
    ----
    prices : DataFrame with ['open', 'high', 'low', 'close']
    structures : optional pre-computed structures. If None, computed with
                 the provided swing_lookback (default W=2 — more permissive
                 than icc_orderblocks default W=3 to match Badoun's eye).
    swing_lookback : passed to detect_structures if structures is None.

    Returns
    -------
    list of DynamicOB, chronologically ordered by detection (break) bar.
    """
    required = {'open', 'high', 'low', 'close'}
    if not required.issubset(prices.columns):
        raise ValueError(f"prices must have columns {required}")

    if structures is None:
        structures = detect_structures(prices, swing_lookback=swing_lookback)

    if not structures:
        return []

    opens   = prices['open'].values
    closes  = prices['close'].values
    highs   = prices['high'].values
    lows    = prices['low'].values
    timestamps = prices.index

    obs: list[DynamicOB] = []

    for struct in structures:
        # Only structural BREAKS produce OBs (CHoCH/BoS) — per Badoun.
        if struct.type not in ('NEW_HIGH', 'NEW_LOW', 'HH', 'LL'):
            continue

        # OB type from break direction
        is_bullish_break = struct.type in ('NEW_HIGH', 'HH')
        ob_type: OBType = 'OB+' if is_bullish_break else 'OB-'

        # For OB- (bearish move broke a high) → we want the LAST BULLISH
        # candle before the break.
        # For OB+ (bullish move broke a low) → we want the LAST BEARISH
        # candle before the break.
        want_bullish = (ob_type == 'OB-')

        search_back_until = struct.origin_bar_index if struct.origin_bar_index is not None else 0

        ob_bar = _find_last_opposite_candle(
            opens, closes,
            break_bar=struct.bar_index,
            search_back_until=search_back_until,
            want_bullish=want_bullish,
        )
        if ob_bar is None:
            # No opposite-color candle in the search range → skip
            continue

        # Info-only context : FVG and consec count
        move_start = ob_bar + 1
        move_end   = struct.bar_index
        has_fvg = _detect_fvg_in_move(highs, lows, move_start, move_end, bullish_move=is_bullish_break)
        consec  = _count_consecutive_same_color(opens, closes, move_start, bullish_move=is_bullish_break)

        # Anchors per Badoun's wording
        wick_anchor = lows[ob_bar] if ob_type == 'OB-' else highs[ob_bar]

        obs.append(DynamicOB(
            type=ob_type,
            bar_index=int(ob_bar),
            timestamp=timestamps[ob_bar],
            wick_anchor_price=float(wick_anchor),
            body_open=float(opens[ob_bar]),
            body_close=float(closes[ob_bar]),
            wick_high=float(highs[ob_bar]),
            wick_low=float(lows[ob_bar]),
            zone_low=float(lows[ob_bar]),
            zone_high=float(highs[ob_bar]),
            structure_broken=struct,
            break_bar=int(struct.bar_index),
            break_ts=timestamps[struct.bar_index],
            n_bars_between_ob_and_break=int(struct.bar_index - ob_bar),
            has_fvg_after=bool(has_fvg),
            consec_same_color_count=int(consec),
        ))

    # Track consumption (price returns into the wick-inclusive zone)
    _track_consumption_dynamic(obs, highs, lows, timestamps)

    return obs


def _track_consumption_dynamic(
    obs: list[DynamicOB],
    highs: np.ndarray,
    lows: np.ndarray,
    timestamps: pd.Index,
) -> None:
    """Mark an OB consumed when, after its break confirmation, price returns
    into the wick-inclusive zone."""
    n = len(highs)
    for ob in obs:
        start_scan = ob.break_bar + 1
        for j in range(start_scan, n):
            # Price re-entered the zone if any wick touches the zone
            if highs[j] >= ob.zone_low and lows[j] <= ob.zone_high:
                ob.consumed = True
                ob.consumed_at_bar = int(j)
                ob.consumed_at_ts = timestamps[j]
                break


# ============================================================================
# SUMMARIES & UTILITIES
# ============================================================================

def summarize_obs_dynamic(obs: list[DynamicOB]) -> dict:
    n_plus  = sum(1 for o in obs if o.type == 'OB+')
    n_minus = sum(1 for o in obs if o.type == 'OB-')
    n_active = sum(1 for o in obs if not o.consumed)
    return {
        'n_total': len(obs),
        'n_OB_plus': n_plus,
        'n_OB_minus': n_minus,
        'n_active_at_end': n_active,
        'n_consumed': len(obs) - n_active,
    }


def obs_to_dataframe(obs: list[DynamicOB]) -> pd.DataFrame:
    if not obs:
        return pd.DataFrame(columns=[
            'bar_index', 'timestamp_utc', 'ob_type',
            'wick_anchor_price', 'body_open', 'body_close',
            'wick_high', 'wick_low', 'zone_low', 'zone_high',
            'broke_structure_type', 'break_bar', 'break_ts',
            'n_bars_ob_to_break', 'has_fvg_after',
            'consec_same_color_count',
            'consumed', 'consumed_at_bar',
            'notes_algo',
        ])
    rows = []
    for ob in obs:
        anchor_kind = 'wick_low' if ob.type == 'OB-' else 'wick_high'
        rows.append({
            'bar_index': ob.bar_index,
            'timestamp_utc': ob.timestamp.isoformat(),
            'ob_type': ob.type,
            'wick_anchor_price': round(ob.wick_anchor_price, 6),
            'body_open': round(ob.body_open, 6),
            'body_close': round(ob.body_close, 6),
            'wick_high': round(ob.wick_high, 6),
            'wick_low': round(ob.wick_low, 6),
            'zone_low': round(ob.zone_low, 6),
            'zone_high': round(ob.zone_high, 6),
            'broke_structure_type': ob.structure_broken.type,
            'break_bar': ob.break_bar,
            'break_ts': ob.break_ts.isoformat(),
            'n_bars_ob_to_break': ob.n_bars_between_ob_and_break,
            'has_fvg_after': ob.has_fvg_after,
            'consec_same_color_count': ob.consec_same_color_count,
            'consumed': ob.consumed,
            'consumed_at_bar': ob.consumed_at_bar if ob.consumed_at_bar is not None else '',
            'notes_algo': (
                f"dyn:walk_back_to_break, anchor={anchor_kind}, "
                f"distance_to_break={ob.n_bars_between_ob_and_break}, "
                f"fvg={'yes' if ob.has_fvg_after else 'no'}, "
                f"consec={ob.consec_same_color_count}, "
                f"broke_{ob.structure_broken.type}"
            ),
        })
    return pd.DataFrame(rows)
