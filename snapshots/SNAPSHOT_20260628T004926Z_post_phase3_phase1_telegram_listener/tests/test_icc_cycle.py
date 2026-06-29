"""
test_icc_cycle.py — Session 4 Unit Tests for ICC Cycle (TU#4)
==============================================================
18 tests covering:
  - Group A: compute_daily_bias              (3 tests)
  - Group B: try_create_setup                (3 tests)
  - Group C: State transitions               (4 tests)
  - Group D: Invalidations                   (3 tests)
  - Group E: Money management (SL/TP)        (3 tests)
  - Group F: Trailing SL                     (2 tests)

Design principles (lessons from Sessions 2 & 3):
  - Synthetic, DETERMINISTIC data only (no random walks)
  - Direct unit-function calls (no full pipeline) where possible
  - Inline fixtures via factories for clarity
  - One concept per test
  - Explicit assert messages for fast debugging
"""
from __future__ import annotations
import pytest
import pandas as pd
import numpy as np

from strategies.icc_cycle import (
    TradeSetup, TradeState, Direction, BiasState, TradeMode, ExitReason,
    compute_daily_bias,
    try_create_setup,
    update_setup_state,
    _close_setup,
    _monitor_in_trade,
    _compute_initial_sl,
    _compute_initial_tp,
    _find_last_micro_during_correction,
)
from strategies.icc_structure import StructurePoint
from strategies.icc_orderblocks import OrderBlock


# ============================================================================
# FACTORIES — minimal fixtures for synthetic tests
# ============================================================================

def make_struct(
    type: str,
    price: float,
    confirmed_at_bar: int,
    bar_index: int = None,
    origin_price: float = None,
    origin_bar_index: int = None,
    broken: bool = False,
    broken_at_bar: int = None,
) -> StructurePoint:
    """Build a StructurePoint with sensible defaults."""
    if bar_index is None:
        bar_index = max(0, confirmed_at_bar - 3)
    return StructurePoint(
        type=type,
        price=price,
        timestamp=pd.Timestamp('2026-01-01') + pd.Timedelta(hours=bar_index),
        bar_index=bar_index,
        confirmed_at_bar=confirmed_at_bar,
        confirmed_at_ts=pd.Timestamp('2026-01-01') + pd.Timedelta(hours=confirmed_at_bar),
        origin_bar_index=origin_bar_index,
        origin_price=origin_price,
        broken=broken,
        broken_at_bar=broken_at_bar,
        broken_at_ts=(pd.Timestamp('2026-01-01') + pd.Timedelta(hours=broken_at_bar))
                     if broken_at_bar is not None else None,
    )


def make_ob(
    type: str,
    zone_low: float,
    zone_high: float,
    structure_broken: StructurePoint,
    bar_index: int = 10,
    detected_at_bar: int = 13,
    consumed: bool = False,
    strength: str = 'VERY_STRONG',
) -> OrderBlock:
    """Build an OrderBlock with sensible defaults."""
    return OrderBlock(
        type=type,
        zone_high=zone_high,
        zone_low=zone_low,
        timestamp=pd.Timestamp('2026-01-01') + pd.Timedelta(hours=bar_index),
        bar_index=bar_index,
        detected_at_bar=detected_at_bar,
        detected_at_ts=pd.Timestamp('2026-01-01') + pd.Timedelta(hours=detected_at_bar),
        structure_broken=structure_broken,
        n_candles_in_move=4,
        has_fvg=True,
        strength=strength,
        consumed=consumed,
    )


def make_setup_in_trade(
    direction: Direction = Direction.BUY,
    entry_price: float = 100.0,
    sl_initial: float = 95.0,
    sl_current: float = None,
    tp_target: float = 110.0,
    impulse_low: float = 90.0,
    impulse_high: float = 110.0,
    entry_bar: int = 15,
) -> TradeSetup:
    """Build a TradeSetup already in IN_TRADE state."""
    if sl_current is None:
        sl_current = sl_initial
    indication = make_struct(
        'NEW_HIGH' if direction == Direction.BUY else 'NEW_LOW',
        impulse_high if direction == Direction.BUY else impulse_low,
        confirmed_at_bar=10,
        origin_price=impulse_low if direction == Direction.BUY else impulse_high,
        origin_bar_index=2,
    )
    ob = make_ob(
        'OB+' if direction == Direction.BUY else 'OB-',
        zone_low=92, zone_high=94,
        structure_broken=indication,
    )
    return TradeSetup(
        asset='BTC',
        mode=TradeMode.SWING,
        direction=direction,
        state=TradeState.IN_TRADE,
        created_at_bar=10,
        daily_bias=BiasState.BULL if direction == Direction.BUY else BiasState.BEAR,
        h4_indication=indication,
        h4_ob=ob,
        impulse_low=impulse_low,
        impulse_high=impulse_high,
        fibo_50=(impulse_low + impulse_high) / 2,
        entry_bar=entry_bar,
        entry_price=entry_price,
        entry_timestamp=pd.Timestamp('2026-01-01') + pd.Timedelta(hours=entry_bar),
        sl_initial=sl_initial,
        sl_current=sl_current,
        sl_history=[(entry_bar, sl_initial)],
        tp_target=tp_target,
    )


def make_h1_df(n_bars: int, base_price: float = 100.0) -> pd.DataFrame:
    """Build a flat synthetic H1 DataFrame of n_bars."""
    return pd.DataFrame({
        'open':  [base_price] * n_bars,
        'high':  [base_price + 1.0] * n_bars,
        'low':   [base_price - 1.0] * n_bars,
        'close': [base_price] * n_bars,
    }, index=pd.date_range('2026-01-01', periods=n_bars, freq='h'))


# ============================================================================
# GROUP A — compute_daily_bias (3 tests)
# ============================================================================

class TestDailyBias:
    
    def test_bull_from_active_hh(self):
        """Most recent active structure is HH → BULL."""
        structs = [
            make_struct('INITIAL_LOW', 100, confirmed_at_bar=0),
            make_struct('HL', 95, confirmed_at_bar=5),
            make_struct('HH', 120, confirmed_at_bar=10),
        ]
        assert compute_daily_bias(structs, at_bar=15) == BiasState.BULL
    
    def test_bear_from_active_ll(self):
        """Most recent active structure is LL → BEAR."""
        structs = [
            make_struct('INITIAL_HIGH', 120, confirmed_at_bar=0),
            make_struct('LH', 115, confirmed_at_bar=5),
            make_struct('LL', 90, confirmed_at_bar=10),
        ]
        assert compute_daily_bias(structs, at_bar=15) == BiasState.BEAR
    
    def test_broken_structure_skipped_returns_previous(self):
        """A more recent BROKEN structure should be ignored — last ACTIVE wins."""
        structs = [
            make_struct('HL', 95, confirmed_at_bar=5),
            make_struct('HH', 120, confirmed_at_bar=10),
            # This LL is more recent but broken before at_bar=20
            make_struct('LL', 80, confirmed_at_bar=12,
                        broken=True, broken_at_bar=15),
        ]
        # At bar 20: LL is broken (since bar 15), so last active = HH → BULL
        assert compute_daily_bias(structs, at_bar=20) == BiasState.BULL


# ============================================================================
# GROUP B — try_create_setup (3 tests)
# ============================================================================

class TestTryCreateSetup:
    
    def test_buy_setup_created_on_new_high_with_bull_daily(self):
        """NEW_HIGH on H4 + Daily BULL → BUY setup created in INDICATION state."""
        indication = make_struct(
            'NEW_HIGH', price=110.0, confirmed_at_bar=20,
            origin_price=90.0, origin_bar_index=12,
        )
        ob = make_ob('OB+', zone_low=92, zone_high=94, structure_broken=indication)
        h1 = make_h1_df(30)
        
        setup = try_create_setup(
            asset='BTC', mode=TradeMode.SWING,
            h4_indication=indication, h4_ob=ob,
            daily_bias=BiasState.BULL,
            h1_bar=20, h1_prices=h1,
        )
        
        assert setup is not None
        assert setup.direction == Direction.BUY
        assert setup.state == TradeState.INDICATION
        assert setup.impulse_low == 90.0
        assert setup.impulse_high == 110.0
        assert setup.fibo_50 == 100.0  # (90+110)/2
    
    def test_rejected_when_daily_misaligned(self):
        """NEW_HIGH (bullish) + Daily BEAR → REJECTED. Critical TradesSAI rule."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=20,
                                  origin_price=90, origin_bar_index=12)
        ob = make_ob('OB+', zone_low=92, zone_high=94, structure_broken=indication)
        h1 = make_h1_df(30)
        
        setup = try_create_setup(
            asset='BTC', mode=TradeMode.SWING,
            h4_indication=indication, h4_ob=ob,
            daily_bias=BiasState.BEAR,  # misalignment
            h1_bar=20, h1_prices=h1,
        )
        
        assert setup is None, "Setup must be None when Daily opposes indication direction"
    
    def test_rejected_when_origin_missing(self):
        """No origin on the broken structure → cannot compute Fibo → reject."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=20)  # no origin
        ob = make_ob('OB+', zone_low=92, zone_high=94, structure_broken=indication)
        h1 = make_h1_df(30)
        
        setup = try_create_setup(
            asset='BTC', mode=TradeMode.SWING,
            h4_indication=indication, h4_ob=ob,
            daily_bias=BiasState.BULL,
            h1_bar=20, h1_prices=h1,
        )
        
        assert setup is None


# ============================================================================
# GROUP C — State transitions (4 tests)
# ============================================================================

class TestStateTransitions:
    
    def test_indication_to_correction_on_first_opposite_bar(self):
        """INDICATION → CORRECTION when current bar closes against indication direction."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=10,
                                  origin_price=90, origin_bar_index=2)
        ob = make_ob('OB+', zone_low=92, zone_high=94, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.INDICATION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
        )
        
        # H1 bar 11: clearly bearish (close < open)
        h1 = pd.DataFrame({
            'open':  [108.0] * 20,
            'high':  [109.0] * 20,
            'low':   [105.0] * 20,
            'close': [106.0] * 20,  # close < open → retracing
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        update_setup_state(setup, h1_bar=11, h1_prices=h1, h1_structs=[],
                            daily_bias_now=BiasState.BULL)
        
        assert setup.state == TradeState.CORRECTION
        assert setup.correction_started_at_bar == 11
    
    def test_correction_to_in_trade_path_a_deep(self):
        """
        Path A: price drops to OB H4, then a micro LH forms,
        then body close breaks past LH AND re-enters above OB → ENTRY.
        """
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
            correction_started_at_bar=11,
            deep_correction_reached=True,  # already touched OB zone
        )
        
        # A micro LH at 97 formed during correction
        micro_lh = make_struct('LH', 97, confirmed_at_bar=15)
        
        # H1 bar 17: body close at 99 → above LH (97) AND above OB.zone_high (95)
        h1 = pd.DataFrame({
            'open':  [97.5] * 20,
            'high':  [99.5] * 20,
            'low':   [96.5] * 20,
            'close': [97.0] * 17 + [99.0] * 3,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        update_setup_state(setup, h1_bar=17, h1_prices=h1, h1_structs=[micro_lh],
                            daily_bias_now=BiasState.BULL,
                            h4_obs=[], daily_obs=[])
        
        assert setup.state == TradeState.IN_TRADE, (
            f"Expected IN_TRADE after Path A entry, got {setup.state}"
        )
        assert setup.entry_price == 99.0
    
    def test_correction_to_in_trade_path_b_shallow_via_fibo(self):
        """
        Path B: price corrects but doesn't reach OB, hits 50% Fibo,
        micro LH forms, body close past LH → ENTRY (even if OB never touched).
        """
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
            correction_started_at_bar=11,
            # Note: deep_correction_reached stays False — Path B only
        )
        
        micro_lh = make_struct('LH', 103, confirmed_at_bar=15)
        
        # H1 bar 17: low touched fibo 50 (=100), close > LH (=103)
        h1 = pd.DataFrame({
            'open':  [102.0] * 20,
            'high':  [105.0] * 20,
            'low':   [99.5]  * 13 + [99.5] + [101.0] * 6,  # bar 13 hit fibo
            'close': [101.0] * 17 + [104.0] * 3,            # bar 17 close past LH
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        # First make bar 13 update to set shallow_via_fibo
        update_setup_state(setup, h1_bar=13, h1_prices=h1, h1_structs=[],
                            daily_bias_now=BiasState.BULL,
                            h4_obs=[], daily_obs=[])
        assert setup.shallow_via_fibo is True
        
        # Then bar 17 with the breakout
        update_setup_state(setup, h1_bar=17, h1_prices=h1, h1_structs=[micro_lh],
                            daily_bias_now=BiasState.BULL,
                            h4_obs=[], daily_obs=[])
        
        assert setup.state == TradeState.IN_TRADE
        assert setup.entry_price == 104.0
    
    def test_path_a_entry_refused_if_close_still_below_ob(self):
        """
        Path A active + micro LH break BUT close still below OB.zone_high
        → NO entry (price must re-enter above OB for Path A).
        
        Note: to isolate Path A from Path B, the OB must be ABOVE fibo_50
              (so touching OB does NOT auto-trigger Path B via fibo cross).
        Here: impulse 90→110, fibo_50=100, OB at [104, 107] (above midpoint).
        """
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        # OB placed ABOVE fibo_50 to keep Path B inactive
        ob = make_ob('OB+', zone_low=104, zone_high=107, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
            correction_started_at_bar=11,
            deep_correction_reached=True,
            shallow_via_fibo=False,  # only Path A
        )
        
        # Micro LH at 105 (between OB.zone_low and zone_high)
        micro_lh = make_struct('LH', 105, confirmed_at_bar=15)
        
        # Bar 17: close at 106 → above LH (105) BUT below OB.zone_high (107)
        # Critical: low stays ABOVE fibo_50 (100) to keep Path B inactive
        h1 = pd.DataFrame({
            'open':  [104.0] * 20,
            'high':  [106.5] * 20,
            'low':   [103.5] * 20,  # stays above fibo_50=100
            'close': [104.5] * 17 + [106.0] * 3,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        update_setup_state(setup, h1_bar=17, h1_prices=h1, h1_structs=[micro_lh],
                            daily_bias_now=BiasState.BULL,
                            h4_obs=[], daily_obs=[])
        
        # Sanity: confirm Path B did NOT get auto-activated
        assert setup.shallow_via_fibo is False, (
            "Test setup invalid: Path B got activated, can't isolate Path A"
        )
        
        assert setup.state == TradeState.CORRECTION, (
            "Path A must require close BACK above OB.zone_high, not just past LH"
        )


# ============================================================================
# GROUP D — Invalidations (3 tests)
# ============================================================================

class TestInvalidations:
    
    def test_daily_flip_invalidates_setup(self):
        """If Daily flips from BULL → BEAR during a BUY setup → DAILY_REVERSAL exit."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
        )
        
        h1 = make_h1_df(20, base_price=100)
        
        update_setup_state(setup, h1_bar=15, h1_prices=h1, h1_structs=[],
                            daily_bias_now=BiasState.BEAR)
        
        assert setup.state == TradeState.COOLDOWN
        assert setup.exit_reason == ExitReason.DAILY_REVERSAL
    
    def test_close_below_impulse_origin_triggers_too_deep(self):
        """BUY setup: body close < impulse_low → CORRECTION_TOO_DEEP."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
        )
        
        # Bar 15: body close at 88 → below impulse_low (90)
        h1 = pd.DataFrame({
            'open':  [95.0] * 20,
            'high':  [96.0] * 20,
            'low':   [87.0] * 20,
            'close': [94.0] * 15 + [88.0] * 5,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        update_setup_state(setup, h1_bar=15, h1_prices=h1, h1_structs=[],
                            daily_bias_now=BiasState.BULL)
        
        assert setup.state == TradeState.COOLDOWN
        assert setup.exit_reason == ExitReason.CORRECTION_TOO_DEEP
    
    def test_wick_pierces_impulse_origin_but_body_closes_above(self):
        """
        BODY CLOSE RULE (TU#1): wick pierces impulse_low, body closes above → setup stays.
        Critical: ICC fundamental rule "Body close only".
        """
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
        )
        
        # Bar 15: low=87 (wick pierces 90), close=92 (body above 90) → SETUP MUST SURVIVE
        h1 = pd.DataFrame({
            'open':  [95.0] * 20,
            'high':  [96.0] * 20,
            'low':   [94.0] * 15 + [87.0] + [94.0] * 4,
            'close': [95.0] * 15 + [92.0] + [95.0] * 4,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        update_setup_state(setup, h1_bar=15, h1_prices=h1, h1_structs=[],
                            daily_bias_now=BiasState.BULL)
        
        assert setup.state != TradeState.COOLDOWN, (
            "Wick piercing origin must NOT close setup if body remains above (TU#1 body close rule)"
        )


# ============================================================================
# GROUP E — Money management (3 tests)
# ============================================================================

class TestMoneyManagement:
    
    def test_sl_uses_avant_dernier_hl_for_buy(self):
        """
        SL must be the SECOND-to-last HL on H1, NOT the most recent one.
        Critical TradesSAI rule: 'avant-dernier HL'.
        """
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.CORRECTION,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
        )
        
        # H1 structs: 2 HLs visible — at bars 10 (price 98) and 15 (price 102)
        h1_structs = [
            make_struct('HL', 98, confirmed_at_bar=10),
            make_struct('HL', 102, confirmed_at_bar=15),  # most recent
        ]
        
        sl = _compute_initial_sl(setup, h1_bar=20, h1_structs=h1_structs)
        
        # Must use the OLDER HL (98), not the most recent (102)
        expected = 98.0 * 0.999
        assert abs(sl - expected) < 1e-6, (
            f"SL must be at avant-dernier HL (98 * 0.999 = {expected:.4f}), got {sl}"
        )
    
    def test_tp_uses_opposite_ob_when_rr_sufficient(self):
        """TP = closest opposite OB if RR ≥ 2.5 (default min_rr_for_ob)."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob_entry = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        # Opposite OB- well above entry → RR > 2.5
        opposite_indication = make_struct('NEW_LOW', 120, confirmed_at_bar=8,
                                           origin_price=130, origin_bar_index=3)
        opposite_ob = make_ob('OB-', zone_low=115, zone_high=118,
                                structure_broken=opposite_indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.IN_TRADE,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob_entry,
            impulse_low=90, impulse_high=110, fibo_50=100,
            entry_price=100.0, sl_current=96.0,  # risk = 4 → RR to 115 = 3.75 ✓
        )
        
        tp, source = _compute_initial_tp(setup, h1_bar=20,
                                           h4_obs=[opposite_ob], daily_obs=[])
        
        assert tp == 115.0, f"TP must be opposite OB.zone_low (115), got {tp}"
        assert source.startswith('OB_OPPOSITE'), f"Source must indicate OB, got {source}"
    
    def test_tp_falls_back_to_measured_move_when_no_good_ob(self):
        """No opposite OB available → fallback to measured move at RR 3.0."""
        indication = make_struct('NEW_HIGH', 110, confirmed_at_bar=5,
                                  origin_price=90, origin_bar_index=0)
        ob = make_ob('OB+', zone_low=92, zone_high=95, structure_broken=indication)
        
        setup = TradeSetup(
            asset='BTC', mode=TradeMode.SWING,
            direction=Direction.BUY, state=TradeState.IN_TRADE,
            created_at_bar=10,
            daily_bias=BiasState.BULL,
            h4_indication=indication, h4_ob=ob,
            impulse_low=90, impulse_high=110, fibo_50=100,
            entry_price=100.0, sl_current=96.0,  # risk = 4
        )
        
        tp, source = _compute_initial_tp(setup, h1_bar=20, h4_obs=[], daily_obs=[])
        
        # Measured move = entry + 3 * risk = 100 + 12 = 112
        assert tp == 112.0, f"Fallback measured move = 112, got {tp}"
        assert 'MEASURED_MOVE' in source


# ============================================================================
# GROUP F — Trailing SL & TRAILING_HIT discrimination (2 tests)
# ============================================================================

class TestTrailingSL:
    
    def test_sl_hit_named_trailing_when_sl_has_moved(self):
        """
        RÉSERVE A fix: when sl_current != sl_initial and price hits SL,
        exit reason must be TRAILING_HIT (not SL_HIT).
        Critical: SL_HIT = true loss; TRAILING_HIT = trailing took us out.
        """
        setup = make_setup_in_trade(
            direction=Direction.BUY,
            entry_price=100.0,
            sl_initial=95.0,
            sl_current=98.0,  # trailing moved from 95 → 98
            tp_target=110.0,
        )
        
        h1 = pd.DataFrame({
            'open':  [100.0] * 20,
            'high':  [102.0] * 20,
            'low':   [99.0]  * 19 + [97.5],  # bar 19: low pierces 98
            'close': [101.0] * 20,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        _monitor_in_trade(
            setup=setup, h1_bar=19, h1_prices=h1, h1_structs=[],
            current_close=101.0, current_high=102.0, current_low=97.5,
            current_ts=h1.index[19],
        )
        
        assert setup.state == TradeState.COOLDOWN
        assert setup.exit_reason == ExitReason.TRAILING_HIT, (
            f"Expected TRAILING_HIT (sl moved 95→98 before hit), got {setup.exit_reason}"
        )
    
    def test_initial_sl_hit_is_sl_hit_not_trailing(self):
        """
        When sl_current == sl_initial (trailing never moved) and price hits SL,
        exit must be SL_HIT (true loss).
        """
        setup = make_setup_in_trade(
            direction=Direction.BUY,
            entry_price=100.0,
            sl_initial=95.0,
            sl_current=95.0,  # NO trailing — still at initial
            tp_target=110.0,
        )
        
        h1 = pd.DataFrame({
            'open':  [100.0] * 20,
            'high':  [102.0] * 20,
            'low':   [99.0]  * 19 + [94.5],
            'close': [101.0] * 20,
        }, index=pd.date_range('2026-01-01', periods=20, freq='h'))
        
        _monitor_in_trade(
            setup=setup, h1_bar=19, h1_prices=h1, h1_structs=[],
            current_close=101.0, current_high=102.0, current_low=94.5,
            current_ts=h1.index[19],
        )
        
        assert setup.exit_reason == ExitReason.SL_HIT, (
            f"Expected SL_HIT (initial SL never moved), got {setup.exit_reason}"
        )
        # And PnL must be negative (true loss)
        assert setup.pnl_pct is not None and setup.pnl_pct < 0, (
            f"True SL_HIT must yield negative PnL, got {setup.pnl_pct}"
        )


# ============================================================================
# Run with: pytest -xvs tests/test_icc_cycle.py
# ============================================================================
