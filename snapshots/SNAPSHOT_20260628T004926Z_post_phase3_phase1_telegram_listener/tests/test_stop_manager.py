"""
Tests unitaires pour paper_trading/stop_manager.py.

Couvre :
- compute_open_positions_value (sans positions, avec positions, prix manquant)
- maybe_anchor_new_day (premier jour, même jour, changement de date UTC)
- check_global_stops (verdict OK, DD breach, Daily loss breach)
- trigger_halt (ferme toutes positions, met bot en HALTED, atomicité)
- Cas tordus : positions sans prix, peak_equity calculation
"""
from __future__ import annotations

from pathlib import Path

import pytest

from paper_trading.state_manager import (
    StateManager,
    OpenPosition,
    EquitySnapshot,
)
from paper_trading.stop_manager import (
    compute_open_positions_value,
    compute_total_equity,
    maybe_anchor_new_day,
    check_global_stops,
    trigger_halt,
    StopManagerError,
    MissingPriceError,
    StopCheckResult,
)


# ════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test_stop.db"


@pytest.fixture
def sm(tmp_db: Path):
    manager = StateManager(db_path=tmp_db)
    yield manager
    manager.close()


def _position(pid: str, asset: str, units: float, entry_price: float = 100.0) -> OpenPosition:
    return OpenPosition(
        position_id=pid,
        asset=asset,
        direction="BUY",
        entry_timestamp="2026-05-13T18:00:00Z",
        entry_price=entry_price,
        entry_fill_price=entry_price * 1.001,
        units=units,
        initial_capital_used=units * entry_price * 1.0026,
        sl_price=entry_price * 0.95,
        tp_price=entry_price * 1.10,
    )


# ════════════════════════════════════════════════════════════════
#  compute_open_positions_value
# ════════════════════════════════════════════════════════════════

def test_value_empty_positions():
    assert compute_open_positions_value([], {}) == 0.0


def test_value_single_position():
    p = _position("BTC_T1", "BTC", units=2.0, entry_price=100.0)
    value = compute_open_positions_value([p], current_prices={"BTC": 110.0})
    assert value == pytest.approx(220.0)


def test_value_multiple_positions():
    p1 = _position("BTC_T1", "BTC", units=2.0, entry_price=100.0)
    p2 = _position("ETH_T1", "ETH", units=10.0, entry_price=50.0)
    value = compute_open_positions_value(
        [p1, p2],
        current_prices={"BTC": 110.0, "ETH": 55.0},
    )
    # 2 × 110 + 10 × 55 = 220 + 550 = 770
    assert value == pytest.approx(770.0)


def test_value_missing_price_raises():
    p = _position("BTC_T1", "BTC", units=2.0)
    with pytest.raises(MissingPriceError, match="BTC"):
        compute_open_positions_value([p], current_prices={"ETH": 100.0})


def test_value_negative_price_raises():
    p = _position("BTC_T1", "BTC", units=2.0)
    with pytest.raises(MissingPriceError):
        compute_open_positions_value([p], current_prices={"BTC": -50.0})


def test_total_equity_combines_cash_and_positions():
    p = _position("BTC_T1", "BTC", units=2.0)
    total = compute_total_equity(cash=500.0, positions=[p], current_prices={"BTC": 100.0})
    assert total == pytest.approx(700.0)


# ════════════════════════════════════════════════════════════════
#  maybe_anchor_new_day
# ════════════════════════════════════════════════════════════════

def test_anchor_first_day(sm):
    """First time we anchor — bot_state has no day yet."""
    with sm.cycle():
        anchored = maybe_anchor_new_day(sm, "2026-05-13T18:00:00Z", current_equity=1000.0)
    assert anchored is True
    state = sm.get_bot_state()
    assert state.day_start_timestamp == "2026-05-13T18:00:00Z"
    assert state.equity_at_day_start_utc == 1000.0


def test_anchor_same_day_no_change(sm):
    """Calling twice on the same UTC date doesn't re-anchor."""
    with sm.cycle():
        maybe_anchor_new_day(sm, "2026-05-13T18:00:00Z", current_equity=1000.0)
    with sm.cycle():
        anchored = maybe_anchor_new_day(sm, "2026-05-13T22:00:00Z", current_equity=950.0)
    assert anchored is False
    state = sm.get_bot_state()
    # Anchor should be unchanged
    assert state.equity_at_day_start_utc == 1000.0


def test_anchor_new_day_re_anchors(sm):
    """When UTC date changes, re-anchor."""
    with sm.cycle():
        maybe_anchor_new_day(sm, "2026-05-13T22:00:00Z", current_equity=1000.0)
    with sm.cycle():
        anchored = maybe_anchor_new_day(sm, "2026-05-14T00:00:00Z", current_equity=980.0)
    assert anchored is True
    state = sm.get_bot_state()
    assert state.day_start_timestamp == "2026-05-14T00:00:00Z"
    assert state.equity_at_day_start_utc == 980.0


# ════════════════════════════════════════════════════════════════
#  check_global_stops — verdict only
# ════════════════════════════════════════════════════════════════

def test_check_no_positions_no_halt(sm):
    """Empty portfolio shouldn't trigger halt."""
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={},
            current_timestamp="2026-05-13T18:00:00Z",
            cash=1000.0,
        )
    assert result.should_halt is False
    assert result.current_equity == 1000.0


def test_check_small_loss_no_halt(sm):
    """Small loss within limits → no halt."""
    with sm.cycle():
        sm.open_position(_position("BTC_T1", "BTC", units=0.001558, entry_price=80000.0))
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=875.0, open_positions_value=125.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={"BTC": 78000.0},  # small drop
            current_timestamp="2026-05-13T19:00:00Z",
            cash=875.0,
        )
    assert result.should_halt is False
    # Small DD < 15% threshold
    assert result.drawdown_pct > -0.05


def test_check_dd_breach_halts(sm):
    """DD exceeds -15% → halt with DD reason."""
    # Setup: peak equity at $1,000
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=1000.0, open_positions_value=0.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
        sm.open_position(_position("BTC_T1", "BTC", units=0.01, entry_price=80000.0))
    # Now crash BTC to make equity drop > 15%
    # Cash 200, position 0.01 BTC @ $50,000 = $500 → equity $700, DD -30%
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={"BTC": 50000.0},
            current_timestamp="2026-05-13T19:00:00Z",
            cash=200.0,
        )
    assert result.should_halt is True
    assert "Drawdown" in result.halt_reason
    assert result.drawdown_pct <= -0.15


def test_check_daily_loss_breach_halts(sm):
    """Daily loss exceeds -10% → halt with daily_loss reason.

    Critical: DD must NOT breach (else DD wins). So we need:
    - Day starts at $1,000 (no historical peak above)
    - Current equity drops to $890 → daily_loss = -11%, DD = -11%
    DD has -15% threshold, daily loss has -10% threshold.
    -11% breaches daily but not DD.
    """
    # Day 1: anchor at $1,000
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T00:00:00Z",
            cash=1000.0, open_positions_value=0.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
        maybe_anchor_new_day(sm, "2026-05-13T00:00:00Z", current_equity=1000.0)
        sm.open_position(_position("BTC_T1", "BTC", units=0.001, entry_price=80000.0))
    # Drop to $890 equity: cash 800, position 0.001 BTC @ $90,000 = $90, total $890
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={"BTC": 90000.0},
            current_timestamp="2026-05-13T22:00:00Z",
            cash=800.0,
        )
    assert result.should_halt is True
    assert "Daily" in result.halt_reason
    assert result.daily_loss_pct <= -0.10
    # DD should NOT breach (peak only $1000)
    assert result.drawdown_pct > -0.15


def test_check_at_exact_threshold_halts(sm):
    """Exactly -15% DD: should halt (boundary case)."""
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=1000.0, open_positions_value=0.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={},
            current_timestamp="2026-05-13T19:00:00Z",
            cash=850.0,  # exactly -15%
        )
    assert result.should_halt is True


def test_check_first_cycle_uses_initial_capital(sm):
    """If no equity snapshot exists yet, use INITIAL_CAPITAL as cash baseline."""
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={},
            current_timestamp="2026-05-13T18:00:00Z",
        )
    # Default config.INITIAL_CAPITAL is 1000
    assert result.current_equity == 1000.0


def test_check_day_anchor_recorded(sm):
    """check_global_stops should anchor a new day when applicable."""
    with sm.cycle():
        result = check_global_stops(
            sm,
            current_prices={},
            current_timestamp="2026-05-13T18:00:00Z",
            cash=1000.0,
        )
    assert result.day_start_anchored_now is True
    state = sm.get_bot_state()
    assert state.day_start_timestamp == "2026-05-13T18:00:00Z"


# ════════════════════════════════════════════════════════════════
#  trigger_halt — active action
# ════════════════════════════════════════════════════════════════

def test_trigger_halt_requires_cycle(sm):
    with pytest.raises(StopManagerError, match="cycle"):
        trigger_halt(sm, reason="test", current_prices={})


def test_trigger_halt_no_positions(sm):
    """HALT with no open positions just marks bot HALTED."""
    with sm.cycle():
        closed = trigger_halt(
            sm,
            reason="test no positions",
            current_prices={},
            current_timestamp="2026-05-13T18:00:00Z",
        )
    assert closed == []
    state = sm.get_bot_state()
    assert state.status == "HALTED"
    assert state.halt_reason == "test no positions"


def test_trigger_halt_closes_open_positions(sm):
    """HALT closes positions, records ClosedTrade, removes OpenPosition."""
    p = _position("BTC_T1", "BTC", units=0.001558, entry_price=80000.0)
    with sm.cycle():
        sm.open_position(p)
    assert len(sm.get_open_positions()) == 1

    with sm.cycle():
        closed = trigger_halt(
            sm,
            reason="DD breach",
            current_prices={"BTC": 79000.0},
            current_timestamp="2026-05-13T20:00:00Z",
            current_bar_index=2,
        )

    # No more open positions
    assert len(sm.get_open_positions()) == 0
    # One closed trade recorded
    assert len(closed) == 1
    ct = closed[0]
    assert ct.asset == "BTC"
    assert ct.exit_reason == "HALT_FORCED"
    assert ct.exit_price == 79000.0
    assert ct.held_bars == 2
    # Bot state
    state = sm.get_bot_state()
    assert state.status == "HALTED"


def test_trigger_halt_handles_missing_price(sm):
    """If price missing for an asset, that position stays open BUT bot still HALTs."""
    p1 = _position("BTC_T1", "BTC", units=0.001, entry_price=80000.0)
    p2 = _position("ETH_T1", "ETH", units=0.05, entry_price=2200.0)
    with sm.cycle():
        sm.open_position(p1)
        sm.open_position(p2)

    # We provide BTC price but not ETH
    with sm.cycle():
        closed = trigger_halt(
            sm,
            reason="DD breach",
            current_prices={"BTC": 79000.0},
            current_timestamp="2026-05-13T20:00:00Z",
        )

    # BTC closed, ETH still open
    assert len(closed) == 1
    assert closed[0].asset == "BTC"
    remaining = sm.get_open_positions()
    assert len(remaining) == 1
    assert remaining[0].asset == "ETH"
    # Bot is HALTED regardless
    assert sm.get_bot_state().status == "HALTED"


def test_trigger_halt_atomicity_on_exception(sm):
    """If an exception happens mid-HALT, the whole cycle rolls back.

    We simulate by passing a bad current_bar_index — actually that's not enough
    to trigger an error. Instead we'll test that rollback works at the cycle level.
    """
    p = _position("BTC_T1", "BTC", units=0.001, entry_price=80000.0)
    with sm.cycle():
        sm.open_position(p)

    # Force a rollback by raising mid-cycle
    with pytest.raises(RuntimeError):
        with sm.cycle():
            closed = trigger_halt(
                sm, reason="test",
                current_prices={"BTC": 79000.0},
            )
            raise RuntimeError("simulated post-halt error")

    # After rollback, the position should still be OPEN (no closed trade either)
    assert len(sm.get_open_positions()) == 1
    assert len(sm.get_closed_trades()) == 0
    # And the bot status should NOT be HALTED (rollback)
    state = sm.get_bot_state()
    assert state.status == "RUNNING"


def test_trigger_halt_multiple_positions_all_closed(sm):
    """Multiple positions all close correctly."""
    p1 = _position("BTC_T1", "BTC", units=0.001, entry_price=80000.0)
    p2 = _position("ETH_T1", "ETH", units=0.05, entry_price=2200.0)
    p3 = _position("SOL_T1", "SOL", units=1.0, entry_price=100.0)
    with sm.cycle():
        sm.open_position(p1)
        sm.open_position(p2)
        sm.open_position(p3)

    with sm.cycle():
        closed = trigger_halt(
            sm, reason="DD",
            current_prices={"BTC": 79000.0, "ETH": 2150.0, "SOL": 95.0},
            current_timestamp="2026-05-13T20:00:00Z",
        )

    assert len(closed) == 3
    assert {c.asset for c in closed} == {"BTC", "ETH", "SOL"}
    assert len(sm.get_open_positions()) == 0


# ════════════════════════════════════════════════════════════════
#  Sanity: peak_equity stays correct across cycles
# ════════════════════════════════════════════════════════════════

def test_peak_equity_only_grows_upward(sm):
    """If equity goes up, peak follows. If equity goes down, peak stays."""
    with sm.cycle():
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=1000.0, open_positions_value=0.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T19:00:00Z",
            cash=1100.0, open_positions_value=0.0,
            equity=1100.0, peak_equity=1100.0, drawdown_pct=0.0,
        ))
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T20:00:00Z",
            cash=1050.0, open_positions_value=0.0,
            equity=1050.0, peak_equity=1100.0, drawdown_pct=-0.0454,
        ))
    assert sm.get_peak_equity() == 1100.0
