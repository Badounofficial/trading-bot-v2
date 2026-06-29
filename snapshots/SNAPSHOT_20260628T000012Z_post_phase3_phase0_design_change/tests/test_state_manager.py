"""
Tests unitaires pour paper_trading/state_manager.py.

Couvre :
- Init de la DB (création des tables, schema_meta, bot_state singleton)
- Cycle / transaction management (open, close, rollback)
- CRUD sur open_positions
- CRUD sur closed_trades
- equity_snapshots
- bot_state (halt/resume)
- Crash recovery (simulation kill -9 mid-cycle)
- Persistance entre 2 instances StateManager (relance après crash)
- Refus d'opérer sans cycle ouvert (NoActiveCycleError)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from paper_trading.state_manager import (
    StateManager,
    OpenPosition,
    ClosedTrade,
    EquitySnapshot,
    BotState,
    NoActiveCycleError,
    StateManagerError,
    DatabaseCorruptError,
)


# ════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Path to a fresh temp SQLite file."""
    return tmp_path / "test_state.db"


@pytest.fixture
def sm(tmp_db: Path):
    """Fresh StateManager on a temp DB, auto-closed at teardown."""
    manager = StateManager(db_path=tmp_db)
    yield manager
    manager.close()


def _sample_position(pid: str = "BTC_T1", asset: str = "BTC") -> OpenPosition:
    return OpenPosition(
        position_id=pid,
        asset=asset,
        direction="BUY",
        entry_timestamp="2026-05-13T18:00:00Z",
        entry_price=80000.0,
        entry_fill_price=80080.0,
        units=0.001558,
        initial_capital_used=125.0,
        sl_price=78000.0,
        tp_price=84000.0,
        sl_source="V1_H1_close_prev_HL",
        tp_source="OB_H4",
    )


def _sample_closed(trade_id: str = "BTC_T1") -> ClosedTrade:
    return ClosedTrade(
        trade_id=trade_id, asset="BTC", direction="BUY",
        entry_timestamp="2026-05-13T18:00:00Z",
        exit_timestamp="2026-05-13T22:00:00Z",
        entry_price=80000.0, entry_fill_price=80080.0,
        exit_price=84000.0, exit_fill_price=83916.0,
        units=0.001558,
        pnl_dollars=5.57, pnl_pct=0.0446,
        total_fees=0.41, total_slippage=0.26,
        exit_reason="TP_HIT", held_bars=4,
    )


def _sample_snapshot(ts: str = "2026-05-13T18:00:00Z", equity: float = 1000.0) -> EquitySnapshot:
    return EquitySnapshot(
        timestamp=ts, cash=equity, open_positions_value=0.0,
        equity=equity, peak_equity=equity, drawdown_pct=0.0,
    )


# ════════════════════════════════════════════════════════════════
#  Init
# ════════════════════════════════════════════════════════════════

def test_init_creates_db(tmp_db: Path):
    assert not tmp_db.exists()
    sm = StateManager(db_path=tmp_db)
    assert tmp_db.exists()
    sm.close()


def test_init_creates_bot_state_singleton(sm):
    state = sm.get_bot_state()
    assert state.status == "RUNNING"
    assert state.halt_reason is None


def test_init_is_idempotent(tmp_db: Path):
    sm1 = StateManager(db_path=tmp_db)
    sm1.close()
    sm2 = StateManager(db_path=tmp_db)
    state = sm2.get_bot_state()
    assert state.status == "RUNNING"
    sm2.close()


def test_summary_works_on_empty_db(sm):
    s = sm.summary()
    assert s["open_positions"] == 0
    assert s["closed_trades"] == 0
    assert s["bot_status"] == "RUNNING"


# ════════════════════════════════════════════════════════════════
#  Cycle management
# ════════════════════════════════════════════════════════════════

def test_write_without_cycle_raises(sm):
    with pytest.raises(NoActiveCycleError):
        sm.open_position(_sample_position())


def test_open_close_cycle_basic(sm):
    sm.open_cycle()
    sm.open_position(_sample_position())
    sm.close_cycle()
    assert len(sm.get_open_positions()) == 1


def test_cannot_open_two_cycles(sm):
    sm.open_cycle()
    with pytest.raises(StateManagerError, match="already open"):
        sm.open_cycle()
    sm.rollback_cycle()


def test_rollback_discards_changes(sm):
    sm.open_cycle()
    sm.open_position(_sample_position())
    sm.rollback_cycle()
    assert len(sm.get_open_positions()) == 0


def test_context_manager_commits_on_success(sm):
    with sm.cycle():
        sm.open_position(_sample_position())
    assert len(sm.get_open_positions()) == 1


def test_context_manager_rollbacks_on_exception(sm):
    with pytest.raises(RuntimeError):
        with sm.cycle():
            sm.open_position(_sample_position())
            raise RuntimeError("boom")
    assert len(sm.get_open_positions()) == 0


def test_close_cycle_without_open_raises(sm):
    with pytest.raises(NoActiveCycleError):
        sm.close_cycle()


# ════════════════════════════════════════════════════════════════
#  Open positions CRUD
# ════════════════════════════════════════════════════════════════

def test_open_and_read_position(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    fetched = sm.get_open_position(p.position_id)
    assert fetched is not None
    assert fetched.asset == "BTC"
    assert fetched.units == p.units


def test_open_position_persists_sl_history(sm):
    p = _sample_position()
    p.sl_history = [["2026-05-13T18:00:00Z", 78000.0]]
    with sm.cycle():
        sm.open_position(p)
    fetched = sm.get_open_position(p.position_id)
    assert fetched.sl_history == [["2026-05-13T18:00:00Z", 78000.0]]


def test_open_position_duplicate_id_fails(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        with sm.cycle():
            sm.open_position(p)


def test_open_position_check_constraint_direction(sm):
    p = _sample_position()
    p.direction = "LONG"  # invalid: only BUY or SELL accepted by CHECK
    with pytest.raises(Exception):
        with sm.cycle():
            sm.open_position(p)


def test_open_position_check_constraint_negative_units(sm):
    p = _sample_position()
    p.units = -1.0
    with pytest.raises(Exception):
        with sm.cycle():
            sm.open_position(p)


def test_update_position_sl(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    with sm.cycle():
        sm.update_position_sl(
            p.position_id, new_sl=79000.0,
            timestamp="2026-05-13T20:00:00Z",
        )
    fetched = sm.get_open_position(p.position_id)
    assert fetched.sl_price == 79000.0
    assert fetched.sl_history == [["2026-05-13T20:00:00Z", 79000.0]]


def test_update_position_sl_appends_history(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    # Two SL updates
    with sm.cycle():
        sm.update_position_sl(p.position_id, 79000.0, "2026-05-13T20:00:00Z")
    with sm.cycle():
        sm.update_position_sl(p.position_id, 80500.0, "2026-05-13T21:00:00Z")
    fetched = sm.get_open_position(p.position_id)
    assert fetched.sl_price == 80500.0
    assert len(fetched.sl_history) == 2


def test_update_nonexistent_position_raises(sm):
    with sm.cycle():
        with pytest.raises(StateManagerError, match="No open position"):
            sm.update_position_sl("GHOST", 100.0, "2026-05-13T18:00:00Z")


def test_mark_partial_taken(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    assert sm.get_open_position(p.position_id).partial_taken is False
    with sm.cycle():
        sm.mark_partial_taken(p.position_id)
    assert sm.get_open_position(p.position_id).partial_taken is True


def test_remove_open_position(sm):
    p = _sample_position()
    with sm.cycle():
        sm.open_position(p)
    assert len(sm.get_open_positions()) == 1
    with sm.cycle():
        sm.remove_open_position(p.position_id)
    assert len(sm.get_open_positions()) == 0


def test_get_open_positions_returns_list_in_order(sm):
    p1 = _sample_position(pid="BTC_T1")
    p2 = _sample_position(pid="ETH_T1", asset="ETH")
    p2.entry_timestamp = "2026-05-13T19:00:00Z"
    with sm.cycle():
        sm.open_position(p2)  # newer ts, inserted first
        sm.open_position(p1)
    positions = sm.get_open_positions()
    assert [p.position_id for p in positions] == ["BTC_T1", "ETH_T1"]


# ════════════════════════════════════════════════════════════════
#  Closed trades
# ════════════════════════════════════════════════════════════════

def test_record_and_read_closed_trade(sm):
    with sm.cycle():
        sm.record_closed_trade(_sample_closed())
    trades = sm.get_closed_trades()
    assert len(trades) == 1
    assert trades[0].pnl_dollars == pytest.approx(5.57)


def test_get_closed_trades_filtered_by_asset(sm):
    t1 = _sample_closed(trade_id="BTC_T1")
    t2 = _sample_closed(trade_id="ETH_T1")
    t2.asset = "ETH"
    with sm.cycle():
        sm.record_closed_trade(t1)
        sm.record_closed_trade(t2)
    btc_only = sm.get_closed_trades(asset="BTC")
    assert len(btc_only) == 1
    assert btc_only[0].asset == "BTC"


def test_get_closed_trades_with_limit(sm):
    with sm.cycle():
        for i in range(5):
            t = _sample_closed(trade_id=f"BTC_T{i}")
            t.exit_timestamp = f"2026-05-{13+i:02d}T22:00:00Z"
            sm.record_closed_trade(t)
    trades = sm.get_closed_trades(limit=3)
    assert len(trades) == 3


# ════════════════════════════════════════════════════════════════
#  Equity snapshots
# ════════════════════════════════════════════════════════════════

def test_record_equity_snapshot(sm):
    with sm.cycle():
        sm.record_equity_snapshot(_sample_snapshot())
    latest = sm.get_latest_equity_snapshot()
    assert latest is not None
    assert latest.equity == 1000.0


def test_get_peak_equity(sm):
    with sm.cycle():
        sm.record_equity_snapshot(_sample_snapshot(ts="2026-05-13T18:00:00Z", equity=1000.0))
        sm.record_equity_snapshot(_sample_snapshot(ts="2026-05-13T19:00:00Z", equity=1050.0))
        sm.record_equity_snapshot(_sample_snapshot(ts="2026-05-13T20:00:00Z", equity=1030.0))
    assert sm.get_peak_equity() == 1050.0


def test_get_latest_equity_snapshot_when_empty(sm):
    assert sm.get_latest_equity_snapshot() is None


# ════════════════════════════════════════════════════════════════
#  Bot state (halt / resume)
# ════════════════════════════════════════════════════════════════

def test_halt_bot(sm):
    with sm.cycle():
        sm.halt("Drawdown exceeded 15%", "2026-05-13T22:00:00Z")
    state = sm.get_bot_state()
    assert state.status == "HALTED"
    assert state.halt_reason == "Drawdown exceeded 15%"


def test_resume_bot(sm):
    with sm.cycle():
        sm.halt("Test", "2026-05-13T22:00:00Z")
    with sm.cycle():
        sm.resume()
    state = sm.get_bot_state()
    assert state.status == "RUNNING"
    assert state.halt_reason is None


def test_halt_check_constraint(sm):
    """Trying to set status outside of allowed values fails."""
    with sm.cycle():
        with pytest.raises(Exception):
            state = sm.get_bot_state()
            state.status = "INVALID_STATUS"
            sm.set_bot_state(state)


# ════════════════════════════════════════════════════════════════
#  CRASH RECOVERY : kill mid-cycle simulation
# ════════════════════════════════════════════════════════════════

def test_kill_mid_cycle_loses_only_in_progress_data(tmp_db: Path):
    """Simulate: cycle 1 commits, cycle 2 crashes mid-way.
    After 'restart' (= new StateManager on same DB), only cycle 1 survives.
    """
    # First instance: commit cycle 1, then 'crash' (close abruptly) during cycle 2
    sm1 = StateManager(db_path=tmp_db)
    with sm1.cycle():
        sm1.open_position(_sample_position(pid="BTC_T1"))

    # Open a 2nd cycle, add a position, but DON'T commit (= simulating kill -9)
    sm1.open_cycle()
    sm1.open_position(_sample_position(pid="ETH_T1", asset="ETH"))
    # The connection close should auto-rollback since cycle was open
    sm1.close()

    # Second instance: simulate restart
    sm2 = StateManager(db_path=tmp_db)
    positions = sm2.get_open_positions()
    # Only the FIRST trade (committed) should be there
    ids = [p.position_id for p in positions]
    assert "BTC_T1" in ids
    assert "ETH_T1" not in ids
    sm2.close()


def test_state_persists_between_instances(tmp_db: Path):
    sm1 = StateManager(db_path=tmp_db)
    with sm1.cycle():
        sm1.open_position(_sample_position())
        sm1.record_closed_trade(_sample_closed(trade_id="OLD_T1"))
        sm1.halt("Manual stop", "2026-05-13T23:00:00Z")
    sm1.close()

    sm2 = StateManager(db_path=tmp_db)
    assert len(sm2.get_open_positions()) == 1
    assert len(sm2.get_closed_trades()) == 1
    assert sm2.get_bot_state().status == "HALTED"
    sm2.close()


# ════════════════════════════════════════════════════════════════
#  CORRUPT DB detection
# ════════════════════════════════════════════════════════════════

def test_corrupt_schema_version_raises(tmp_db: Path):
    """If the DB has a different schema_version, refuse to start."""
    import sqlite3
    sm1 = StateManager(db_path=tmp_db)
    sm1.close()

    # Manually corrupt the schema version
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("UPDATE schema_meta SET value = '99' WHERE key = 'version'")
    conn.commit()
    conn.close()

    with pytest.raises(DatabaseCorruptError, match="Schema"):
        StateManager(db_path=tmp_db)
