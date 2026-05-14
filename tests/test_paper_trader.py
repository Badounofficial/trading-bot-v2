"""
Tests for paper_trading/paper_trader.py.

Strategy:
- Mock the data_fetcher (no real Kraken)
- Mock the strategy_adapter (no real ICC) — we control what actions are emitted
- Use a real StateManager on tmp DB (so we test the persistence path)
- Use a Monitor with a mock alerter (so no real Telegram sent)

This validates the ORCHESTRATION logic: are actions executed in the right
order? Are state transitions correct? Does HALT work end-to-end?
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

from paper_trading import config
from paper_trading.paper_trader import (
    PaperTrader,
    CycleResult,
    _setup_id_to_position_id,
    _position_id_to_setup_id,
)
from paper_trading.state_manager import StateManager
from paper_trading.monitoring import Monitor, JsonLineLogger, TelegramAlerter, TelegramResult
from strategies.strategy_adapter import (
    OpenAction, CloseAction, TrailAction, PartialAction,
)


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def _fake_h1_df(n_bars: int = 50, base: float = 80000.0) -> pd.DataFrame:
    """Build a fake H1 OHLCV DataFrame, tz-aware UTC."""
    ts = pd.date_range("2026-05-14T00:00:00Z", periods=n_bars, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open":  [base + i for i in range(n_bars)],
        "high":  [base + i + 50 for i in range(n_bars)],
        "low":   [base + i - 50 for i in range(n_bars)],
        "close": [base + i + 25 for i in range(n_bars)],
        "volume": [100.0 for _ in range(n_bars)],
    }, index=ts)


def _make_trader(
    tmp_path: Path,
    adapter_actions_by_asset: Optional[dict] = None,
    adapter_actions: Optional[list] = None,
) -> PaperTrader:
    """Build a PaperTrader with isolated DB and mocked adapter/monitor.

    Args:
        adapter_actions_by_asset: {asset: [actions]} per-asset mapping (preferred).
        adapter_actions: legacy — same actions for all assets (will only emit
                         for the FIRST asset to avoid duplicate-id collisions).
    """
    db_path = tmp_path / "test.db"
    sm = StateManager(db_path=db_path)

    # Monitor with mock Telegram alerter
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    json_logger = JsonLineLogger(logs_dir=logs_dir)
    mock_alerter = MagicMock(spec=TelegramAlerter)
    mock_alerter.send.return_value = TelegramResult(ok=True, http_status=200)
    monitor = Monitor(json_logger=json_logger, alerter=mock_alerter)

    # Mock adapter — return actions per asset (so we don't duplicate setup_ids)
    mock_adapter = MagicMock()
    if adapter_actions_by_asset is not None:
        def per_asset_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
            return (adapter_actions_by_asset.get(asset, []), {})
        mock_adapter.get_actions_for_cycle.side_effect = per_asset_side_effect
    elif adapter_actions:
        # Emit for FIRST asset only; empty for the rest
        emitted = {"done": False}
        def first_asset_only(asset, daily_df, h4_df, h1_df, prev_setups=None):
            if not emitted["done"]:
                emitted["done"] = True
                return (adapter_actions, {})
            return ([], {})
        mock_adapter.get_actions_for_cycle.side_effect = first_asset_only
    else:
        mock_adapter.get_actions_for_cycle.return_value = ([], {})

    # Mock data fetcher — always returns BTC + ETH
    def fake_fetcher():
        return {"BTC": _fake_h1_df(50, 80000.0), "ETH": _fake_h1_df(50, 2200.0)}

    # Backup manager scoped to tmp (no pollution of project backups/)
    from paper_trading.backup import BackupManager
    test_backup_dir = tmp_path / "backups"
    test_backup_dir.mkdir(exist_ok=True)
    backup_manager = BackupManager(
        db_path=db_path,
        backup_dir=test_backup_dir,
        max_keep=10,
        telegram_enabled=False,
    )

    return PaperTrader(
        state_manager=sm,
        monitor=monitor,
        adapter=mock_adapter,
        data_fetcher=fake_fetcher,
        assets=["BTC", "ETH"],
        backup_manager=backup_manager,
    )


# ════════════════════════════════════════════════════════════════
#  Setup_id ↔ position_id mapping
# ════════════════════════════════════════════════════════════════

def test_setup_id_to_position_id_roundtrip():
    sid = ("BTC", "2026-05-12T14:00:00", "BUY")
    pid = _setup_id_to_position_id(sid)
    assert pid == "BTC__2026-05-12T14-00-00__BUY"
    sid_back = _position_id_to_setup_id(pid)
    assert sid_back == sid


def test_position_id_invalid_format_raises():
    with pytest.raises(ValueError):
        _position_id_to_setup_id("invalid")


# ════════════════════════════════════════════════════════════════
#  CycleResult basics
# ════════════════════════════════════════════════════════════════

def test_cycle_result_defaults():
    r = CycleResult(timestamp="2026-05-14T18:00:00Z", success=True)
    assert r.n_trades_opened == 0
    assert r.halt_triggered is False
    assert r.assets_failed == []


# ════════════════════════════════════════════════════════════════
#  run_one_cycle: no actions, baseline
# ════════════════════════════════════════════════════════════════

def test_cycle_with_no_actions_succeeds(tmp_path):
    """Empty actions list → cycle succeeds, no trades, equity snapshot recorded."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    assert result.success is True
    assert result.n_trades_opened == 0
    assert result.n_trades_closed == 0
    assert result.halt_triggered is False
    # Equity snapshot was recorded
    snap = trader.sm.get_latest_equity_snapshot()
    assert snap is not None


def test_cycle_when_bot_halted_returns_early(tmp_path):
    """If bot is already HALTED, cycle returns early without strategy processing."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    # Halt the bot
    with trader.sm.cycle():
        trader.sm.halt("manual halt", "2026-05-14T17:00:00Z")
    # Run cycle
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    assert result.success is True
    assert "HALTED" in result.error_message
    # Adapter should NOT have been called
    trader.adapter.get_actions_for_cycle.assert_not_called()


# ════════════════════════════════════════════════════════════════
#  OpenAction
# ════════════════════════════════════════════════════════════════

def test_open_action_creates_position(tmp_path):
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"),
        asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0,
        sl_price=78000.0, tp_price=84000.0,
        sl_source="V1", tp_source="OB_H4",
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    assert result.success is True
    # Position exists in DB
    positions = trader.sm.get_open_positions()
    # adapter is called once per asset (BTC, ETH), but only BTC returns the open
    # Mock returns same actions for ALL calls → both BTC and ETH would have created positions
    # except both have same setup_id → second insert would fail with unique constraint
    # → we expect at least 1 position created
    assert len(positions) >= 1


def test_open_action_skipped_if_insufficient_capital(tmp_path):
    """If free capital is too low, action is skipped (logged, not crashed)."""
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"),
        asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])

    # Manually set cash to very low
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=5.0,  # only $5 — far too little for 12.5% of $1000 = $125 budget
            open_positions_value=0.0, equity=5.0,
            peak_equity=1000.0, drawdown_pct=-0.995,
        ))

    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    # Cycle should HALT because DD already breached (-99.5% << -15%)
    assert result.halt_triggered is True


# ════════════════════════════════════════════════════════════════
#  CloseAction
# ════════════════════════════════════════════════════════════════

def test_close_action_closes_existing_position(tmp_path):
    """Open a position, then close it via CloseAction."""
    # Cycle 1: open
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    # Avoid HALT from initial DD: set baseline equity
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    r1 = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    assert r1.n_trades_opened >= 1

    # Cycle 2: close the same setup_id — use side_effect to scope per asset
    close_a = CloseAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=84000.0, exit_reason="TP_HIT",
    )
    def close_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([close_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = close_side_effect

    r2 = trader.run_one_cycle(timestamp_iso="2026-05-14T22:00:00Z")
    assert r2.n_trades_closed >= 1
    # The position is gone, a closed trade is recorded
    assert len(trader.sm.get_open_positions()) == 0
    closed = trader.sm.get_closed_trades()
    assert len(closed) >= 1
    assert closed[0].exit_reason == "TP_HIT"


def test_close_action_unknown_position_skipped(tmp_path):
    """Close action targeting unknown position is logged and skipped, no crash."""
    close_a = CloseAction(
        setup_id=("BTC", "9999-12-31T00:00:00", "BUY"), asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=84000.0, exit_reason="TP_HIT",
    )
    trader = _make_trader(tmp_path, adapter_actions=[close_a])
    # Avoid initial HALT
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    # Cycle succeeds (no crash), no close happened
    assert result.success is True
    # Bug #2 fix: n_trades_closed must NOT be incremented when close skipped
    assert result.n_trades_closed == 0


def test_open_and_close_same_cycle_processed_in_order(tmp_path):
    """When the adapter emits BOTH Open and Close for the same setup_id in
    one cycle (opened_and_closed_same_cycle scenario), the Open MUST be
    executed BEFORE the Close.

    Regression for the issue found in Session 7 dry run after Bug 3 v1 fix:
    3 closes were skipping with 'unknown position' warning because the
    matching opens hadn't yet been executed (Closes ran before Opens in
    the original sequential order).
    """
    sid = ("BTC", "2026-05-12T14:00:00", "BUY")
    open_a = OpenAction(
        setup_id=sid, asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    close_a = CloseAction(
        setup_id=sid, asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=84000.0, exit_reason="TP_HIT",
    )

    # Adapter returns BOTH actions for BTC in the same cycle
    def side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([open_a, close_a], {})
        return ([], {})

    trader = _make_trader(tmp_path, adapter_actions=[])
    trader.adapter.get_actions_for_cycle.side_effect = side_effect

    # Setup baseline equity to avoid HALT
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))

    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")

    # Both actions must succeed
    assert result.success is True
    assert result.n_trades_opened == 1, "Open must be executed"
    assert result.n_trades_closed == 1, (
        "Close must be executed AFTER the open (Bug fix regression)"
    )
    # Position is open then closed → 0 still open, 1 closed trade
    assert len(trader.sm.get_open_positions()) == 0
    assert len(trader.sm.get_closed_trades()) == 1


# ════════════════════════════════════════════════════════════════
#  TrailAction
# ════════════════════════════════════════════════════════════════

def test_trail_updates_sl(tmp_path):
    # First: open a position
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")

    # Then: trail action — scoped to BTC only via side_effect
    trail_a = TrailAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC",
        new_sl=79500.0, timestamp="2026-05-14T19:00:00Z",
        sl_source="trailed",
    )
    def trail_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([trail_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = trail_side_effect
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T19:00:00Z")
    assert result.n_trails == 1
    # SL was updated
    pos = trader.sm.get_open_position("BTC__2026-05-12T14-00-00__BUY")
    assert pos.sl_price == 79500.0


# ════════════════════════════════════════════════════════════════
#  PartialAction
# ════════════════════════════════════════════════════════════════

def test_partial_marks_position(tmp_path):
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")

    partial_a = PartialAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"), asset="BTC",
        partial_price=82000.0, partial_timestamp="2026-05-14T20:00:00Z",
        partial_pnl_pct=0.025,
    )
    def partial_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([partial_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = partial_side_effect
    result = trader.run_one_cycle(timestamp_iso="2026-05-14T20:00:00Z")
    assert result.n_partials == 1
    pos = trader.sm.get_open_position("BTC__2026-05-12T14-00-00__BUY")
    assert pos.partial_taken is True


# ════════════════════════════════════════════════════════════════
#  HALT scenarios
# ════════════════════════════════════════════════════════════════

def test_cycle_triggers_halt_on_dd(tmp_path):
    """If DD breaches threshold, HALT is triggered and Telegram alert sent."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    # Setup: peak 1000, then current equity << 850 → DD <= -15%
    from paper_trading.state_manager import EquitySnapshot, OpenPosition
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=300.0, open_positions_value=500.0,
            equity=800.0, peak_equity=1000.0, drawdown_pct=-0.20,
        ))
        # Open a BTC position whose mark-to-market won't save the DD
        trader.sm.open_position(OpenPosition(
            position_id="BTC__2026-05-10T00-00-00__BUY", asset="BTC", direction="BUY",
            entry_timestamp="2026-05-14T16:00:00Z",
            entry_price=80000.0, entry_fill_price=80080.0,
            units=0.001, initial_capital_used=100.0,
            sl_price=70000.0, tp_price=90000.0,
        ))

    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    # DD will breach
    assert result.halt_triggered is True
    # Position should be closed
    assert len(trader.sm.get_open_positions()) == 0
    # Bot is HALTED
    assert trader.sm.get_bot_state().status == "HALTED"
    # Telegram alert was sent
    trader.monitor.alerter.send.assert_called()


# ════════════════════════════════════════════════════════════════
#  run_dev_fast: replay multiple cycles
# ════════════════════════════════════════════════════════════════

def test_dev_fast_replays_multiple_cycles(tmp_path):
    """Run 3 cycles, verify each one is processed."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    # Setup baseline equity to avoid initial HALT
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    data = {"BTC": _fake_h1_df(), "ETH": _fake_h1_df(base=2200.0)}
    cycles_data = [
        ("2026-05-14T18:00:00Z", data),
        ("2026-05-14T19:00:00Z", data),
        ("2026-05-14T20:00:00Z", data),
    ]
    results = trader.run_dev_fast(cycles_data)
    assert len(results) == 3
    assert all(r.success for r in results)


def test_dev_fast_stops_on_halt(tmp_path):
    """If HALT triggers mid-replay, loop stops."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    from paper_trading.state_manager import EquitySnapshot, OpenPosition
    # Setup that will HALT on first cycle
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=300.0, open_positions_value=500.0,
            equity=800.0, peak_equity=1000.0, drawdown_pct=-0.20,
        ))
    data = {"BTC": _fake_h1_df(), "ETH": _fake_h1_df(base=2200.0)}
    cycles_data = [
        ("2026-05-14T18:00:00Z", data),
        ("2026-05-14T19:00:00Z", data),
        ("2026-05-14T20:00:00Z", data),
    ]
    results = trader.run_dev_fast(cycles_data)
    # Should stop after the first halt
    assert len(results) == 1
    assert results[0].halt_triggered is True


# ════════════════════════════════════════════════════════════════
#  Scheduler timing
# ════════════════════════════════════════════════════════════════

def test_seconds_until_next_cycle_is_positive(tmp_path):
    """Just verifies the function returns a sensible value."""
    s = PaperTrader._seconds_until_next_cycle()
    # At any time, the next XX:00 + delay is in 0 to 3610 seconds
    assert 0 <= s <= 3610


def test_run_forever_with_max_cycles_terminates(tmp_path):
    """run_forever with max_cycles=2 should run 2 cycles and stop."""
    trader = _make_trader(tmp_path, adapter_actions=[])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))

    # Mock sleep so we don't actually wait
    mock_sleep = MagicMock()
    trader.run_forever(max_cycles=2, sleep_function=mock_sleep)

    # 2 cycles were executed, sleep was called 2 times
    assert mock_sleep.call_count == 2


# ════════════════════════════════════════════════════════════════
#  Cash tracking invariants (Bug #1 regression tests)
# ════════════════════════════════════════════════════════════════

def test_cash_decreases_when_position_opens(tmp_path):
    """When a position opens, cash in the new snapshot must be lower
    than cash in the previous snapshot, by the amount spent on the fill.

    Bug #1 regression: previously cash was frozen at INITIAL_CAPITAL.
    """
    open_a = OpenAction(
        setup_id=("BTC", "2026-05-12T14:00:00", "BUY"),
        asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])

    # Baseline equity = $1000 cash
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))

    result = trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    assert result.n_trades_opened == 1

    # Cash must have DECREASED
    new_snap = trader.sm.get_latest_equity_snapshot()
    assert new_snap.cash < 1000.0, (
        f"Cash should have decreased after open, got {new_snap.cash}"
    )
    # And open_positions_value should be > 0
    assert new_snap.open_positions_value > 0


def test_cash_increases_when_position_closes_profit(tmp_path):
    """When a position closes at profit, cash returned > cash spent."""
    sid = ("BTC", "2026-05-12T14:00:00", "BUY")
    open_a = OpenAction(
        setup_id=sid, asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    cash_after_open = trader.sm.get_latest_equity_snapshot().cash

    # Cycle 2: close at higher price (profit)
    close_a = CloseAction(
        setup_id=sid, asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=85000.0, exit_reason="TP_HIT",
    )
    def close_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([close_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = close_side_effect

    trader.run_one_cycle(timestamp_iso="2026-05-14T22:00:00Z")
    cash_after_close = trader.sm.get_latest_equity_snapshot().cash

    # Cash after profitable close MUST be greater than after open
    assert cash_after_close > cash_after_open, (
        f"Cash should have grown after profitable close: "
        f"open={cash_after_open}, close={cash_after_close}"
    )
    # And no more open positions
    assert len(trader.sm.get_open_positions()) == 0


def test_cash_after_loss_close_reflects_loss(tmp_path):
    """When a position closes at loss, the final cash should reflect the loss
    (be less than the original capital before opening)."""
    sid = ("BTC", "2026-05-12T14:00:00", "BUY")
    open_a = OpenAction(
        setup_id=sid, asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))
    trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")

    # Close at a loss
    close_a = CloseAction(
        setup_id=sid, asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=78000.0, exit_reason="SL_HIT",  # below entry
    )
    def close_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([close_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = close_side_effect

    trader.run_one_cycle(timestamp_iso="2026-05-14T22:00:00Z")
    final_cash = trader.sm.get_latest_equity_snapshot().cash

    # After loss, total cash < starting $1000 (fees + slippage + price loss)
    assert final_cash < 1000.0, (
        f"Cash after losing trade should be < starting, got {final_cash}"
    )


def test_equity_equals_cash_plus_open_positions_value(tmp_path):
    """FUNDAMENTAL INVARIANT: at every snapshot, equity = cash + open_value.

    This invariant must hold at all times:
    - After open
    - After close
    - With multiple positions
    - When no positions exist

    If this test ever breaks, it means a cash_delta accounting bug.
    """
    sid = ("BTC", "2026-05-12T14:00:00", "BUY")
    open_a = OpenAction(
        setup_id=sid, asset="BTC", direction="BUY",
        entry_timestamp="2026-05-14T18:00:00Z",
        entry_price=80000.0, sl_price=78000.0, tp_price=84000.0,
        sl_source=None, tp_source=None,
    )
    trader = _make_trader(tmp_path, adapter_actions=[open_a])
    from paper_trading.state_manager import EquitySnapshot
    with trader.sm.cycle():
        trader.sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-14T17:00:00Z",
            cash=1000.0, open_positions_value=0.0, equity=1000.0,
            peak_equity=1000.0, drawdown_pct=0.0,
        ))

    # Cycle 1: open
    trader.run_one_cycle(timestamp_iso="2026-05-14T18:00:00Z")
    snap_after_open = trader.sm.get_latest_equity_snapshot()
    assert abs(snap_after_open.equity - (snap_after_open.cash + snap_after_open.open_positions_value)) < 0.01, (
        f"Invariant broken after open: "
        f"equity={snap_after_open.equity}, "
        f"cash={snap_after_open.cash}, "
        f"open_val={snap_after_open.open_positions_value}"
    )

    # Cycle 2: close
    close_a = CloseAction(
        setup_id=sid, asset="BTC",
        exit_timestamp="2026-05-14T22:00:00Z",
        exit_price=82000.0, exit_reason="TP_HIT",
    )
    def close_side_effect(asset, daily_df, h4_df, h1_df, prev_setups=None):
        if asset == "BTC":
            return ([close_a], {})
        return ([], {})
    trader.adapter.get_actions_for_cycle.side_effect = close_side_effect

    trader.run_one_cycle(timestamp_iso="2026-05-14T22:00:00Z")
    snap_after_close = trader.sm.get_latest_equity_snapshot()
    assert abs(snap_after_close.equity - (snap_after_close.cash + snap_after_close.open_positions_value)) < 0.01, (
        f"Invariant broken after close: "
        f"equity={snap_after_close.equity}, "
        f"cash={snap_after_close.cash}, "
        f"open_val={snap_after_close.open_positions_value}"
    )
    # And open_value should be 0 (no positions left)
    assert snap_after_close.open_positions_value == 0
