"""
Tests for strategies/strategy_adapter.py.

REAL ICC state machine (verified by reading strategies/icc_cycle.py):

  SCANNING → INDICATION → CORRECTION → READY → IN_TRADE → COOLDOWN

A setup is in OPEN POSITION iff state == IN_TRADE.
A setup is a CLOSED TRADE iff state == COOLDOWN AND entry_price is not None.
A setup in COOLDOWN with entry_price=None = died pre-entry, NOT a trade.

IDENTITY (Bug #3 fix from Session 6b dry run E2E):
setup_id is now based on h4_indication.confirmed_at_ts (a timestamp)
NOT on bar_index (a DataFrame position). confirmed_at_ts is stable
across cycles even when the H1 window slides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import pytest

from strategies.strategy_adapter import (
    IccStrategyAdapter,
    OpenAction,
    CloseAction,
    TrailAction,
    PartialAction,
    setup_id,
)
from strategies.icc_cycle import (
    TradeState,
    Direction,
    TradeMode,
    ExitReason,
    TradeSetup,
)


# Default canonical timestamp used in fixtures
_DEFAULT_TS = pd.Timestamp("2026-05-12T14:00:00")


def _fake_h4_indication(bar_index: int = 100,
                       confirmed_at_ts: pd.Timestamp = _DEFAULT_TS):
    """Build a fake StructurePoint with both bar_index (for ICC internals)
    and confirmed_at_ts (the new stable identifier).
    """
    @dataclass
    class FakeStructurePoint:
        bar_index: int = 0
        type: str = "NEW_HIGH"
        confirmed_at_ts: pd.Timestamp = _DEFAULT_TS
    return FakeStructurePoint(bar_index=bar_index, confirmed_at_ts=confirmed_at_ts)


def _fake_h4_ob():
    @dataclass
    class FakeOB: pass
    return FakeOB()


def _scanning_setup(asset="BTC", h4_bar=100, direction=Direction.BUY,
                     confirmed_at_ts=_DEFAULT_TS) -> TradeSetup:
    return TradeSetup(
        asset=asset, mode=TradeMode.SWING, direction=direction,
        state=TradeState.SCANNING, created_at_bar=h4_bar,
        daily_bias=None,
        h4_indication=_fake_h4_indication(h4_bar, confirmed_at_ts),
        h4_ob=_fake_h4_ob(),
        impulse_low=80000.0, impulse_high=82000.0, fibo_50=81000.0,
    )


def _in_trade_setup(asset="BTC", h4_bar=100, entry_price=81500.0,
                     sl=80500.0, tp=84000.0, direction=Direction.BUY,
                     confirmed_at_ts=_DEFAULT_TS) -> TradeSetup:
    s = _scanning_setup(asset=asset, h4_bar=h4_bar, direction=direction,
                         confirmed_at_ts=confirmed_at_ts)
    s.state = TradeState.IN_TRADE
    s.entry_bar = 105
    s.entry_price = entry_price
    s.entry_timestamp = pd.Timestamp("2026-05-14T18:00:00Z")
    s.sl_initial = sl
    s.sl_current = sl
    s.sl_history = [(105, sl)]
    s.sl_source = "V1_H1_close_prev_HL"
    s.tp_target = tp
    s.tp_source = "OB_H4"
    return s


def _closed_trade_setup(asset="BTC", h4_bar=100, entry_price=81500.0,
                        exit_price=84000.0, exit_reason=ExitReason.TP_HIT,
                        direction=Direction.BUY,
                        confirmed_at_ts=_DEFAULT_TS) -> TradeSetup:
    """COOLDOWN with entry_price filled = real closed trade."""
    s = _in_trade_setup(asset=asset, h4_bar=h4_bar,
                        entry_price=entry_price, direction=direction,
                        confirmed_at_ts=confirmed_at_ts)
    s.state = TradeState.COOLDOWN
    s.exit_bar = 130
    s.exit_price = exit_price
    s.exit_timestamp = pd.Timestamp("2026-05-14T22:00:00Z")
    s.exit_reason = exit_reason
    return s


def _dead_pre_entry_setup(asset="BTC", h4_bar=100, direction=Direction.BUY,
                          confirmed_at_ts=_DEFAULT_TS) -> TradeSetup:
    """COOLDOWN without entry — setup died before triggering. NOT a trade."""
    s = _scanning_setup(asset=asset, h4_bar=h4_bar, direction=direction,
                         confirmed_at_ts=confirmed_at_ts)
    s.state = TradeState.COOLDOWN
    s.exit_bar = 130
    s.exit_timestamp = pd.Timestamp("2026-05-14T22:00:00Z")
    s.exit_reason = ExitReason.SL_HIT
    return s


# ════════════════════════════════════════════════════════════════
#  setup_id (NEW FORMAT: tuple[str, str, str] with timestamp)
# ════════════════════════════════════════════════════════════════

def test_setup_id_is_tuple_with_timestamp():
    """New format: (asset, confirmed_at_ts ISO, direction)."""
    ts = pd.Timestamp("2026-05-12T14:00:00")
    s = _scanning_setup(asset="BTC", confirmed_at_ts=ts, direction=Direction.BUY)
    sid = setup_id(s)
    assert sid == ("BTC", "2026-05-12T14:00:00", "BUY")


def test_setup_id_strips_timezone():
    """A tz-aware timestamp should produce the same identifier as its tz-naive."""
    ts_aware = pd.Timestamp("2026-05-12T14:00:00Z")
    ts_naive = pd.Timestamp("2026-05-12T14:00:00")
    s_aware = _scanning_setup(asset="BTC", confirmed_at_ts=ts_aware)
    s_naive = _scanning_setup(asset="BTC", confirmed_at_ts=ts_naive)
    assert setup_id(s_aware) == setup_id(s_naive)


def test_setup_id_distinguishes_assets():
    assert setup_id(_scanning_setup("BTC", 100)) != setup_id(_scanning_setup("ETH", 100))


def test_setup_id_distinguishes_timestamps():
    """Different confirmed_at_ts → different setup_id."""
    ts_a = pd.Timestamp("2026-05-12T14:00:00")
    ts_b = pd.Timestamp("2026-05-12T18:00:00")
    s_a = _scanning_setup("BTC", confirmed_at_ts=ts_a)
    s_b = _scanning_setup("BTC", confirmed_at_ts=ts_b)
    assert setup_id(s_a) != setup_id(s_b)


def test_setup_id_distinguishes_directions():
    a = _scanning_setup("BTC", 100, Direction.BUY)
    b = _scanning_setup("BTC", 100, Direction.SELL)
    assert setup_id(a) != setup_id(b)


# ════════════════════════════════════════════════════════════════
#  CRITICAL REGRESSION TEST — Bug #3 specifically
# ════════════════════════════════════════════════════════════════

def test_setup_id_stable_when_bar_index_changes():
    """Regression test for Bug #3 found in Session 6b dry run E2E.

    When the H1 window slides by 1 bar between cycles, the bar_index
    of the same real structure SHIFTS (e.g. from 152 to 151) because
    bar_index is a POSITION in the DataFrame, not an absolute identifier.

    The setup_id MUST remain identical across cycles, otherwise the
    adapter creates duplicate Opens and emits Closes for non-existent
    positions.

    This test simulates the exact scenario observed in the dry run
    where 12 Opens and 12 Closes happened without ever closing a trade.
    """
    confirmed_ts = pd.Timestamp("2026-05-12T14:00:00")

    # Cycle T: same real structure, position 152 in the DataFrame
    setup_at_t = _in_trade_setup(asset="BTC", direction=Direction.BUY,
                                  h4_bar=152, confirmed_at_ts=confirmed_ts)

    # Cycle T+1: SAME real structure but window slid → position 151
    setup_at_t1 = _in_trade_setup(asset="BTC", direction=Direction.BUY,
                                   h4_bar=151, confirmed_at_ts=confirmed_ts)

    # The setup_ids MUST be identical (same real-world structure)
    assert setup_id(setup_at_t) == setup_id(setup_at_t1), (
        "Setup identity must be stable across cycles even when "
        "bar_index changes (Bug #3 regression)"
    )


# ════════════════════════════════════════════════════════════════
#  Predicates
# ════════════════════════════════════════════════════════════════

def test_predicate_in_trade_is_open():
    s = _in_trade_setup()
    assert IccStrategyAdapter._is_open_position(s) is True
    assert IccStrategyAdapter._is_closed_trade(s) is False


def test_predicate_cooldown_with_entry_is_closed_trade():
    s = _closed_trade_setup()
    assert IccStrategyAdapter._is_open_position(s) is False
    assert IccStrategyAdapter._is_closed_trade(s) is True


def test_predicate_cooldown_without_entry_is_neither():
    s = _dead_pre_entry_setup()
    assert IccStrategyAdapter._is_open_position(s) is False
    assert IccStrategyAdapter._is_closed_trade(s) is False


def test_predicate_scanning_is_neither():
    s = _scanning_setup()
    assert IccStrategyAdapter._is_open_position(s) is False
    assert IccStrategyAdapter._is_closed_trade(s) is False


# ════════════════════════════════════════════════════════════════
#  diff: OPEN
# ════════════════════════════════════════════════════════════════

def test_diff_empty_to_empty_no_actions():
    assert IccStrategyAdapter.diff_setups({}, {}, "BTC") == []


def test_diff_new_in_trade_emits_open_action():
    s = _in_trade_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({}, {sid: s}, "BTC")
    opens = [a for a in actions if isinstance(a, OpenAction)]
    assert len(opens) == 1
    oa = opens[0]
    assert oa.entry_price == 81500.0
    assert oa.sl_price == 80500.0
    assert oa.tp_price == 84000.0
    assert oa.direction == "BUY"


def test_diff_scanning_setup_no_open_action():
    s = _scanning_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, OpenAction)] == []


def test_diff_setup_already_in_trade_no_open_action():
    s = _in_trade_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({sid: s}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, OpenAction)] == []


def test_diff_dead_pre_entry_no_open():
    s = _dead_pre_entry_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, OpenAction)] == []


# ════════════════════════════════════════════════════════════════
#  diff: CLOSE
# ════════════════════════════════════════════════════════════════

def test_diff_in_trade_to_closed_emits_close():
    prev_s = _in_trade_setup()
    curr_s = _closed_trade_setup()
    sid = setup_id(prev_s)
    # Same confirmed_at_ts → same setup_id
    assert setup_id(curr_s) == sid
    actions = IccStrategyAdapter.diff_setups({sid: prev_s}, {sid: curr_s}, "BTC")
    closes = [a for a in actions if isinstance(a, CloseAction)]
    assert len(closes) == 1
    assert closes[0].exit_price == 84000.0
    assert closes[0].exit_reason == "TP_HIT"


def test_diff_setup_opened_and_closed_same_cycle():
    s = _closed_trade_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({}, {sid: s}, "BTC")
    opens = [a for a in actions if isinstance(a, OpenAction)]
    closes = [a for a in actions if isinstance(a, CloseAction)]
    assert len(opens) == 1
    assert len(closes) == 1


def test_diff_already_closed_no_duplicate_close():
    s = _closed_trade_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({sid: s}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, CloseAction)] == []


def test_diff_dead_pre_entry_no_close():
    s = _dead_pre_entry_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, CloseAction)] == []


def test_diff_scanning_to_dead_no_action():
    prev = _scanning_setup()
    curr = _dead_pre_entry_setup()
    sid = setup_id(prev)
    actions = IccStrategyAdapter.diff_setups({sid: prev}, {sid: curr}, "BTC")
    assert actions == []


# ════════════════════════════════════════════════════════════════
#  diff: TRAIL
# ════════════════════════════════════════════════════════════════

def test_diff_sl_unchanged_no_trail():
    s = _in_trade_setup()
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({sid: s}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, TrailAction)] == []


def test_diff_sl_changed_emits_trail():
    prev_s = _in_trade_setup(sl=80500.0)
    curr_s = _in_trade_setup(sl=80500.0)
    curr_s.sl_current = 81200.0
    curr_s.sl_history = [(105, 80500.0), (110, 81200.0)]
    sid = setup_id(prev_s)
    actions = IccStrategyAdapter.diff_setups({sid: prev_s}, {sid: curr_s}, "BTC")
    trails = [a for a in actions if isinstance(a, TrailAction)]
    assert len(trails) == 1
    assert trails[0].new_sl == 81200.0


def test_diff_no_trail_after_close():
    prev_s = _in_trade_setup(sl=80500.0)
    curr_s = _closed_trade_setup()
    curr_s.sl_current = 83500.0
    sid = setup_id(prev_s)
    actions = IccStrategyAdapter.diff_setups({sid: prev_s}, {sid: curr_s}, "BTC")
    assert [a for a in actions if isinstance(a, TrailAction)] == []


# ════════════════════════════════════════════════════════════════
#  diff: PARTIAL
# ════════════════════════════════════════════════════════════════

def test_diff_partial_false_to_true_emits_partial():
    prev_s = _in_trade_setup()
    prev_s.partial_closed = False
    curr_s = _in_trade_setup()
    curr_s.partial_closed = True
    curr_s.partial_close_price = 83500.0
    curr_s.partial_closed_at_bar = 120
    curr_s.partial_pnl_pct = 0.025
    sid = setup_id(prev_s)
    actions = IccStrategyAdapter.diff_setups({sid: prev_s}, {sid: curr_s}, "BTC")
    partials = [a for a in actions if isinstance(a, PartialAction)]
    assert len(partials) == 1
    assert partials[0].partial_price == 83500.0


def test_diff_partial_already_true_no_duplicate():
    s = _in_trade_setup()
    s.partial_closed = True
    s.partial_close_price = 83500.0
    sid = setup_id(s)
    actions = IccStrategyAdapter.diff_setups({sid: s}, {sid: s}, "BTC")
    assert [a for a in actions if isinstance(a, PartialAction)] == []


# ════════════════════════════════════════════════════════════════
#  diff: combined transitions
# ════════════════════════════════════════════════════════════════

def test_diff_complex_scenario():
    """Multiple setups in different transitions emit the right actions."""
    ts_a = pd.Timestamp("2026-05-12T08:00:00")
    ts_b = pd.Timestamp("2026-05-12T16:00:00")
    ts_c = pd.Timestamp("2026-05-13T00:00:00")
    ts_d = pd.Timestamp("2026-05-13T08:00:00")

    prev_a = _in_trade_setup(h4_bar=100, confirmed_at_ts=ts_a)
    curr_a = _closed_trade_setup(h4_bar=100, confirmed_at_ts=ts_a)
    sid_a = setup_id(prev_a)

    curr_b = _in_trade_setup(h4_bar=200, confirmed_at_ts=ts_b)
    sid_b = setup_id(curr_b)

    prev_c = _in_trade_setup(h4_bar=300, sl=80500.0, confirmed_at_ts=ts_c)
    curr_c = _in_trade_setup(h4_bar=300, sl=80500.0, confirmed_at_ts=ts_c)
    curr_c.sl_current = 81500.0
    sid_c = setup_id(prev_c)

    curr_d = _dead_pre_entry_setup(h4_bar=400, confirmed_at_ts=ts_d)
    sid_d = setup_id(curr_d)

    prev = {sid_a: prev_a, sid_c: prev_c}
    curr = {sid_a: curr_a, sid_b: curr_b, sid_c: curr_c, sid_d: curr_d}

    actions = IccStrategyAdapter.diff_setups(prev, curr, "BTC")
    closes = [a for a in actions if isinstance(a, CloseAction)]
    opens = [a for a in actions if isinstance(a, OpenAction)]
    trails = [a for a in actions if isinstance(a, TrailAction)]

    assert len(opens) == 1
    assert len(closes) == 1
    assert len(trails) == 1
    assert all(a.setup_id != sid_d for a in actions)


# ════════════════════════════════════════════════════════════════
#  Adapter caching
# ════════════════════════════════════════════════════════════════

def test_adapter_uses_internal_cache_across_calls(monkeypatch):
    adapter = IccStrategyAdapter()
    seqs = [
        [_scanning_setup(asset="BTC", h4_bar=100)],
        [_in_trade_setup(asset="BTC", h4_bar=100)],
    ]
    i = {"n": 0}
    def fake_call(asset, d, h4, h1):
        idx = i["n"]; i["n"] += 1
        return seqs[idx]
    monkeypatch.setattr(adapter, "_call_icc", fake_call)

    df = pd.DataFrame()
    a1, _ = adapter.get_actions_for_cycle("BTC", df, df, df)
    assert all(not isinstance(a, OpenAction) for a in a1)

    a2, _ = adapter.get_actions_for_cycle("BTC", df, df, df)
    assert any(isinstance(a, OpenAction) for a in a2)


def test_adapter_independent_caches_per_asset(monkeypatch):
    adapter = IccStrategyAdapter()
    monkeypatch.setattr(adapter, "_call_icc",
                        lambda asset, d, h4, h1: [_in_trade_setup(asset=asset)])
    df = pd.DataFrame()
    btc_a, _ = adapter.get_actions_for_cycle("BTC", df, df, df)
    eth_a, _ = adapter.get_actions_for_cycle("ETH", df, df, df)
    assert any(isinstance(a, OpenAction) for a in btc_a)
    assert any(isinstance(a, OpenAction) for a in eth_a)


def test_adapter_explicit_prev_setups_overrides_cache(monkeypatch):
    adapter = IccStrategyAdapter()
    s = _in_trade_setup()
    sid = setup_id(s)
    monkeypatch.setattr(adapter, "_call_icc", lambda asset, d, h4, h1: [s])
    df = pd.DataFrame()
    actions, _ = adapter.get_actions_for_cycle("BTC", df, df, df, prev_setups={sid: s})
    assert [a for a in actions if isinstance(a, OpenAction)] == []


# ════════════════════════════════════════════════════════════════
#  Session 5 defaults regression
# ════════════════════════════════════════════════════════════════

def test_adapter_defaults_match_session5(monkeypatch):
    adapter = IccStrategyAdapter()
    captured = {}
    def spy(asset, daily_prices, h4_prices, h1_prices,
            mode, daily_lookback, h4_lookback, h1_lookback,
            verbose, skip_daily_filter, min_rr_for_ob_tp,
            measured_move_rr, sl_mode):
        captured.update(dict(mode=mode, daily_lookback=daily_lookback,
                             h4_lookback=h4_lookback, h1_lookback=h1_lookback,
                             skip_daily_filter=skip_daily_filter,
                             min_rr_for_ob_tp=min_rr_for_ob_tp,
                             measured_move_rr=measured_move_rr, sl_mode=sl_mode))
        return []
    monkeypatch.setattr("strategies.strategy_adapter.run_icc_cycle", spy)
    df = pd.DataFrame()
    adapter.get_actions_for_cycle("BTC", df, df, df)
    assert captured["mode"] == TradeMode.SWING
    assert captured["daily_lookback"] == 5
    assert captured["h4_lookback"] == 3
    assert captured["h1_lookback"] == 3
    assert captured["skip_daily_filter"] is False
    assert captured["min_rr_for_ob_tp"] == 2.5
    assert captured["measured_move_rr"] == 3.0
    assert captured["sl_mode"] == "v1_h1_close"
