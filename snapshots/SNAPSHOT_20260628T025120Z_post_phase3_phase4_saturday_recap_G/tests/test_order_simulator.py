"""
Tests unitaires pour paper_trading/order_simulator.py.

Couvre :
- Slippage (BUY paie plus, SELL reçoit moins)
- Fees (calcul correct sur gross value)
- Position sizing (equal weight strict)
- Simulation BUY (calcul units, cash_out)
- Simulation SELL (calcul cash_in)
- Insufficient capital handling
- Realized PnL (round-trip avec accounting cohérent)
- Conservation de l'énergie : ce qui sort = ce qui rentre dans le système
"""
from __future__ import annotations

import math

import pytest

from paper_trading import order_simulator as os_
from paper_trading import config


# ════════════════════════════════════════════════════════════════
#  apply_slippage
# ════════════════════════════════════════════════════════════════

def test_slippage_buy_pays_more():
    fill = os_.apply_slippage(100.0, "BUY", slippage_pct=0.01)
    assert fill == pytest.approx(101.0)


def test_slippage_sell_receives_less():
    fill = os_.apply_slippage(100.0, "SELL", slippage_pct=0.01)
    assert fill == pytest.approx(99.0)


def test_slippage_zero_means_no_change():
    assert os_.apply_slippage(100.0, "BUY", slippage_pct=0.0) == 100.0
    assert os_.apply_slippage(100.0, "SELL", slippage_pct=0.0) == 100.0


def test_slippage_invalid_side():
    with pytest.raises(ValueError, match="BUY"):
        os_.apply_slippage(100.0, "LONG", slippage_pct=0.01)


def test_slippage_negative_price():
    with pytest.raises(ValueError, match="positive"):
        os_.apply_slippage(-1.0, "BUY", slippage_pct=0.01)


def test_slippage_negative_pct():
    with pytest.raises(ValueError, match="slippage_pct"):
        os_.apply_slippage(100.0, "BUY", slippage_pct=-0.01)


# ════════════════════════════════════════════════════════════════
#  apply_fees
# ════════════════════════════════════════════════════════════════

def test_fees_basic():
    assert os_.apply_fees(1000.0, fee_pct=0.0016) == pytest.approx(1.6)


def test_fees_zero():
    assert os_.apply_fees(1000.0, fee_pct=0.0) == 0.0


def test_fees_negative_gross_raises():
    with pytest.raises(ValueError):
        os_.apply_fees(-100.0, fee_pct=0.001)


# ════════════════════════════════════════════════════════════════
#  compute_position_budget
# ════════════════════════════════════════════════════════════════

def test_budget_default():
    budget = os_.compute_position_budget()
    expected = config.INITIAL_CAPITAL * config.MAX_POSITION_PCT_PER_ASSET
    assert budget == pytest.approx(expected)


def test_budget_explicit():
    budget = os_.compute_position_budget(initial_capital=1000, max_pct_per_asset=0.125)
    assert budget == pytest.approx(125.0)


# ════════════════════════════════════════════════════════════════
#  compute_units_for_budget
# ════════════════════════════════════════════════════════════════

def test_units_basic_no_costs():
    # $1000 budget, $100 price, no slippage no fee → 10 units
    units = os_.compute_units_for_budget(1000.0, 100.0, slippage_pct=0.0, fee_pct=0.0)
    assert units == pytest.approx(10.0)


def test_units_with_slippage():
    # $1000 budget, $100 base price, 1% slippage → fill at $101 → 9.9009... units
    units = os_.compute_units_for_budget(1000.0, 100.0, slippage_pct=0.01, fee_pct=0.0)
    assert units == pytest.approx(1000.0 / 101.0)


def test_units_with_slippage_and_fees():
    # Round trip: spending budget exactly equals units × fill_price × (1 + fee)
    budget = 1000.0
    price = 100.0
    units = os_.compute_units_for_budget(budget, price, slippage_pct=0.01, fee_pct=0.0016)
    fill_price = 100.0 * 1.01
    actual_cost = units * fill_price * (1 + 0.0016)
    assert actual_cost == pytest.approx(budget, rel=1e-9)


def test_units_zero_budget():
    assert os_.compute_units_for_budget(0.0, 100.0) == 0.0


def test_units_invalid_price():
    with pytest.raises(ValueError):
        os_.compute_units_for_budget(1000.0, 0.0)


# ════════════════════════════════════════════════════════════════
#  simulate_market_order — BUY
# ════════════════════════════════════════════════════════════════

def test_buy_basic():
    fill = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=1000.0,
    )
    assert fill.side == "BUY"
    assert fill.requested_price == 100.0
    assert fill.fill_price > 100.0  # slippage made it worse
    assert fill.units > 0
    assert fill.fee_paid > 0
    assert fill.slippage_cost > 0
    assert fill.cash_delta < 0  # money LEAVES the account


def test_buy_cash_out_equals_budget_approximately():
    # The whole point of compute_units_for_budget: spending exactly budget
    budget = 500.0
    fill = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=budget,
    )
    # Cash out = gross + fees
    cash_out = -fill.cash_delta
    assert cash_out == pytest.approx(budget, rel=1e-9)


def test_buy_insufficient_capital_raises():
    with pytest.raises(os_.InsufficientCapitalError):
        os_.simulate_market_order(
            side="BUY",
            requested_price=100.0,
            budget_dollars=1000.0,
            free_capital=500.0,  # not enough!
        )


def test_buy_sufficient_capital_passes():
    fill = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=500.0,
        free_capital=10000.0,  # plenty
    )
    assert fill.units > 0


def test_buy_missing_budget():
    with pytest.raises(ValueError, match="BUY requires"):
        os_.simulate_market_order(side="BUY", requested_price=100.0)


def test_buy_units_not_allowed():
    with pytest.raises(ValueError, match="units"):
        os_.simulate_market_order(
            side="BUY",
            requested_price=100.0,
            budget_dollars=1000.0,
            units=5.0,
        )


# ════════════════════════════════════════════════════════════════
#  simulate_market_order — SELL
# ════════════════════════════════════════════════════════════════

def test_sell_basic():
    fill = os_.simulate_market_order(
        side="SELL",
        requested_price=100.0,
        units=5.0,
    )
    assert fill.side == "SELL"
    assert fill.fill_price < 100.0  # slippage made it worse
    assert fill.units == 5.0
    assert fill.fee_paid > 0
    assert fill.slippage_cost > 0
    assert fill.cash_delta > 0  # money ENTERS the account


def test_sell_cash_in_equals_gross_minus_fees():
    fill = os_.simulate_market_order(
        side="SELL",
        requested_price=100.0,
        units=10.0,
    )
    expected = fill.gross_value - fill.fee_paid
    assert fill.cash_delta == pytest.approx(expected)


def test_sell_missing_units():
    with pytest.raises(ValueError, match="units"):
        os_.simulate_market_order(side="SELL", requested_price=100.0)


def test_sell_zero_units():
    with pytest.raises(ValueError):
        os_.simulate_market_order(side="SELL", requested_price=100.0, units=0)


def test_sell_with_budget_raises():
    with pytest.raises(ValueError, match="budget_dollars"):
        os_.simulate_market_order(
            side="SELL", requested_price=100.0, units=5.0, budget_dollars=500.0,
        )


# ════════════════════════════════════════════════════════════════
#  try_open_trade — safe wrapper
# ════════════════════════════════════════════════════════════════

def test_try_open_trade_success():
    fill = os_.try_open_trade(
        asset="BTC",
        requested_price=80000.0,
        free_capital=10000.0,
        initial_capital=1000.0,
        max_pct_per_asset=0.125,
    )
    assert fill is not None
    assert fill.units > 0


def test_try_open_trade_skips_on_insufficient():
    # Trying to use 12.5% of 1000 = $125, but only $50 free
    fill = os_.try_open_trade(
        asset="BTC",
        requested_price=80000.0,
        free_capital=50.0,
        initial_capital=1000.0,
        max_pct_per_asset=0.125,
    )
    assert fill is None  # SKIPPED, not raised


# ════════════════════════════════════════════════════════════════
#  compute_realized_trade — full round-trip
# ════════════════════════════════════════════════════════════════

def test_realized_trade_winner():
    """Open at 100, close at 110, no fees/slippage → ~10% PnL."""
    entry = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=1000.0,
        slippage_pct=0.0,
        fee_pct=0.0,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL",
        requested_price=110.0,
        units=entry.units,
        slippage_pct=0.0,
        fee_pct=0.0,
    )
    trade = os_.compute_realized_trade(
        asset="BTC", entry_fill=entry, exit_fill=exit_fill, held_bars=5,
    )
    assert trade.pnl_dollars == pytest.approx(100.0, rel=1e-9)  # 10 units × $10 gain
    assert trade.pnl_pct == pytest.approx(0.10, rel=1e-9)
    assert trade.total_fees == 0.0
    assert trade.total_slippage == 0.0


def test_realized_trade_loser():
    """Open at 100, close at 95, no fees/slippage → ~5% loss."""
    entry = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=1000.0,
        slippage_pct=0.0,
        fee_pct=0.0,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL",
        requested_price=95.0,
        units=entry.units,
        slippage_pct=0.0,
        fee_pct=0.0,
    )
    trade = os_.compute_realized_trade(
        asset="BTC", entry_fill=entry, exit_fill=exit_fill, held_bars=5,
    )
    assert trade.pnl_dollars == pytest.approx(-50.0, rel=1e-9)
    assert trade.pnl_pct == pytest.approx(-0.05, rel=1e-9)


def test_realized_trade_with_realistic_costs():
    """Realistic round-trip: slippage 0.10%, fees 0.16% × 2 legs."""
    entry = os_.simulate_market_order(
        side="BUY",
        requested_price=80000.0,
        budget_dollars=125.0,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL",
        requested_price=84000.0,  # 5% gain on paper
        units=entry.units,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    trade = os_.compute_realized_trade(
        asset="BTC", entry_fill=entry, exit_fill=exit_fill, held_bars=10,
    )

    # Expected costs: ~0.20% slippage + ~0.32% fees = ~0.52% total drag
    # On a 5% gross gain → net ~4.5%
    assert 0.04 < trade.pnl_pct < 0.046
    assert trade.total_fees > 0
    assert trade.total_slippage > 0


def test_realized_trade_breakeven_with_costs_is_negative():
    """If we open and close at the same price, we LOSE the round-trip costs."""
    entry = os_.simulate_market_order(
        side="BUY", requested_price=100.0, budget_dollars=125.0,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL", requested_price=100.0, units=entry.units,
    )
    trade = os_.compute_realized_trade(
        asset="BTC", entry_fill=entry, exit_fill=exit_fill, held_bars=5,
    )
    assert trade.pnl_dollars < 0  # we lost to costs


def test_realized_trade_wrong_side_order_raises():
    entry = os_.simulate_market_order(
        side="BUY", requested_price=100.0, budget_dollars=100.0,
    )
    # Swap the order: try to use entry as exit
    with pytest.raises(ValueError, match="BUY entry and SELL exit"):
        os_.compute_realized_trade(
            asset="BTC", entry_fill=entry, exit_fill=entry, held_bars=5,
        )


def test_realized_trade_short_not_supported():
    entry = os_.simulate_market_order(
        side="BUY", requested_price=100.0, budget_dollars=100.0,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL", requested_price=100.0, units=entry.units,
    )
    with pytest.raises(NotImplementedError):
        os_.compute_realized_trade(
            asset="BTC", entry_fill=entry, exit_fill=exit_fill,
            held_bars=5, direction="SELL",
        )


# ════════════════════════════════════════════════════════════════
#  Conservation : argent qui sort = argent qui rentre (avec coûts)
# ════════════════════════════════════════════════════════════════

def test_conservation_of_money():
    """Sum of all cash_deltas + costs = 0 (energy conservation)."""
    entry = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=125.0,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL",
        requested_price=105.0,
        units=entry.units,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    # Money out of account = entry.cash_delta (negative)
    # Money into account = exit_fill.cash_delta (positive)
    # PnL = sum
    pnl_computed = entry.cash_delta + exit_fill.cash_delta

    # Manual recomputation: gross_in - gross_out - all_fees - all_slippage_losses
    # But actually slippage is already in gross prices, so simpler:
    # PnL = (units × exit_fill_price - units × entry_fill_price) - exit_fees - entry_fees
    units = entry.units
    gross_diff = units * (exit_fill.fill_price - entry.fill_price)
    pnl_manual = gross_diff - entry.fee_paid - exit_fill.fee_paid

    assert pnl_computed == pytest.approx(pnl_manual, rel=1e-9)


def test_buy_then_sell_breakeven_loss_equals_costs():
    """Buy and immediately sell at the same requested_price: loss should
    equal entry_fees + exit_fees + slippage on both sides."""
    entry = os_.simulate_market_order(
        side="BUY",
        requested_price=100.0,
        budget_dollars=125.0,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    exit_fill = os_.simulate_market_order(
        side="SELL",
        requested_price=100.0,  # same!
        units=entry.units,
        slippage_pct=0.001,
        fee_pct=0.0016,
    )
    trade = os_.compute_realized_trade(
        asset="BTC", entry_fill=entry, exit_fill=exit_fill, held_bars=1,
    )
    # The loss should be (approximately) entry_fees + exit_fees + slippage_losses
    expected_loss = -(entry.fee_paid + exit_fill.fee_paid +
                      entry.slippage_cost + exit_fill.slippage_cost)
    assert trade.pnl_dollars == pytest.approx(expected_loss, rel=1e-6)
