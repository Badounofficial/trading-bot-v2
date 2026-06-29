"""
order_simulator.py — Simulation d'exécution d'ordres pour paper trading.

Aucun ordre réel n'est jamais passé. Ce module calcule :
- Combien d'unités on peut acheter avec un budget donné
- Le prix d'exécution réaliste (slippage défavorable au trader)
- Les frais (Kraken standard 0.16% par leg)
- Le PnL net à la sortie (après tous coûts)

DESIGN CHOICES (Session 6, locked):
1. Slippage = fixed 0.10% on every order, applied unfavorably to trader
2. Equal weight sizing: each trade = MAX_POSITION_PCT_PER_ASSET (12.5%) of INITIAL capital
3. If not enough free capital → skip trade with warning log (no partial fills)

These choices are paper-trading specific and unrelated to the ICC strategy logic.
They can be refined in Phase 2 (broker demo) with real market microstructure data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from paper_trading import config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    EXCEPTIONS
# ════════════════════════════════════════════════════════════════

class OrderSimulationError(Exception):
    """Generic simulator error."""


class InsufficientCapitalError(OrderSimulationError):
    """Not enough free capital to open the trade as requested.

    The bot should LOG this and SKIP the trade — never try a smaller size,
    never halt the bot. This is the agreed Session 6 design.
    """


# ════════════════════════════════════════════════════════════════
#                    DATACLASSES
# ════════════════════════════════════════════════════════════════

@dataclass
class SimulatedFill:
    """Result of a simulated market order (entry OR exit).

    All values are POSITIVE numbers. The interpretation depends on side:
    - For a BUY entry: 'units_filled' goes IN the position, 'cash_out' leaves account
    - For a SELL exit: 'units_filled' leaves position, 'cash_in' = gross - fees - slippage_cost

    Attributes:
        side: "BUY" or "SELL"
        requested_price: the price the strategy saw (e.g. H1 close)
        fill_price: actual price after slippage (always less favorable than requested)
        units: quantity of asset filled (e.g. 0.005 BTC)
        gross_value: units × fill_price (before fees)
        fee_paid: dollar fees deducted (always positive)
        slippage_cost: how much was lost to slippage vs requested_price (positive)
        cash_delta: net cash movement (negative for BUY, positive for SELL)
    """
    side: str
    requested_price: float
    fill_price: float
    units: float
    gross_value: float
    fee_paid: float
    slippage_cost: float
    cash_delta: float


@dataclass
class RealizedTrade:
    """Result of a closed trade: entry + exit + accounting.

    All values are POSITIVE for amounts (use 'pnl_dollars' sign for direction).
    """
    asset: str
    direction: str  # "BUY" (long) or "SELL" (short — N/A on spot for now)
    entry_fill: SimulatedFill
    exit_fill: SimulatedFill
    pnl_dollars: float  # signed (can be negative)
    pnl_pct: float       # signed (can be negative), relative to entry gross
    total_fees: float    # entry fee + exit fee
    total_slippage: float  # entry slippage + exit slippage
    held_bars: int       # how many H1 bars the trade was open


# ════════════════════════════════════════════════════════════════
#                    LOW-LEVEL : SLIPPAGE & FEES
# ════════════════════════════════════════════════════════════════

def apply_slippage(
    requested_price: float,
    side: str,
    slippage_pct: float = config.SLIPPAGE_PCT,
) -> float:
    """Apply slippage in the unfavorable direction for the trader.

    BUY:  fill_price = requested * (1 + slippage)    [we pay more]
    SELL: fill_price = requested * (1 - slippage)    [we receive less]

    Args:
        requested_price: the price the strategy decided on (e.g. H1 close)
        side: "BUY" or "SELL"
        slippage_pct: as a decimal (0.001 = 0.10%)

    Returns:
        Filled price (always worse than requested for the trader).
    """
    if requested_price <= 0:
        raise ValueError(f"requested_price must be positive, got {requested_price}")
    if slippage_pct < 0:
        raise ValueError(f"slippage_pct must be >= 0, got {slippage_pct}")
    side = side.upper()
    if side == "BUY":
        return requested_price * (1.0 + slippage_pct)
    if side == "SELL":
        return requested_price * (1.0 - slippage_pct)
    raise ValueError(f"side must be 'BUY' or 'SELL', got '{side}'")


def apply_fees(
    gross_value: float,
    fee_pct: float = config.FEE_PCT_PER_LEG,
) -> float:
    """Compute fees on a notional gross value.

    Kraken charges a flat % on the notional value (no maker/taker distinction
    in paper since we always assume taker for conservatism).

    Args:
        gross_value: units × fill_price (always positive)
        fee_pct: as a decimal (0.0016 = 0.16%)

    Returns:
        Fee amount in dollars (always >= 0).
    """
    if gross_value < 0:
        raise ValueError(f"gross_value must be >= 0, got {gross_value}")
    if fee_pct < 0:
        raise ValueError(f"fee_pct must be >= 0, got {fee_pct}")
    return gross_value * fee_pct


# ════════════════════════════════════════════════════════════════
#                    POSITION SIZING
# ════════════════════════════════════════════════════════════════

def compute_position_budget(
    initial_capital: float = config.INITIAL_CAPITAL,
    max_pct_per_asset: float = config.MAX_POSITION_PCT_PER_ASSET,
) -> float:
    """Equal-weight strict: each trade gets MAX_PCT × INITIAL capital.

    Design choice locked Session 6: budget is fixed to INITIAL capital
    (not current equity). This makes sizing predictable and simple.

    Returns:
        Dollar budget per trade (e.g. $125 on $1000 with 12.5% allocation).
    """
    return initial_capital * max_pct_per_asset


def compute_units_for_budget(
    budget_dollars: float,
    price: float,
    slippage_pct: float = config.SLIPPAGE_PCT,
    fee_pct: float = config.FEE_PCT_PER_LEG,
) -> float:
    """Compute how many units we can buy with a given dollar budget,
    accounting for slippage AND entry fees.

    Algebra:
        budget = units × fill_price × (1 + fee_pct)
        where fill_price = price × (1 + slippage_pct) for BUY

    Solving for units:
        units = budget / (price × (1 + slippage_pct) × (1 + fee_pct))

    Args:
        budget_dollars: max dollars we're willing to spend (must be > 0)
        price: requested entry price (e.g. H1 close)
        slippage_pct, fee_pct: as decimals

    Returns:
        Units (can be fractional, e.g. 0.0015 BTC).
        Returns 0.0 if budget too small to be meaningful.
    """
    if budget_dollars < 0:
        raise ValueError(f"budget_dollars must be >= 0, got {budget_dollars}")
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if budget_dollars == 0:
        return 0.0
    fill_price = price * (1.0 + slippage_pct)
    cost_per_unit = fill_price * (1.0 + fee_pct)
    return budget_dollars / cost_per_unit


# ════════════════════════════════════════════════════════════════
#                    HIGH-LEVEL : SIMULATE MARKET ORDER
# ════════════════════════════════════════════════════════════════

def simulate_market_order(
    side: str,
    requested_price: float,
    budget_dollars: Optional[float] = None,
    units: Optional[float] = None,
    free_capital: Optional[float] = None,
    slippage_pct: float = config.SLIPPAGE_PCT,
    fee_pct: float = config.FEE_PCT_PER_LEG,
) -> SimulatedFill:
    """Simulate the execution of a market order at the next-bar open price.

    Two modes:
      1) BUY with a dollar budget → we compute units, check capital
      2) SELL with units already in position → we compute proceeds

    Args:
        side: "BUY" (open long) or "SELL" (close long)
        requested_price: the price the strategy targeted (typically H1 close)
        budget_dollars: only for BUY. How much $ to spend (pre-slippage).
        units: only for SELL. How many units to sell (must be > 0).
        free_capital: only for BUY. Capital currently available. If provided
                      and < required, raises InsufficientCapitalError.
        slippage_pct, fee_pct: overrides for testing; default from config

    Returns:
        SimulatedFill with all the accounting details.

    Raises:
        ValueError : inconsistent args (BUY without budget, SELL without units, etc.)
        InsufficientCapitalError : free_capital provided and insufficient
    """
    side = side.upper()

    if side == "BUY":
        if budget_dollars is None:
            raise ValueError("BUY requires budget_dollars")
        if units is not None:
            raise ValueError("Don't specify 'units' for BUY (computed from budget)")
        if budget_dollars <= 0:
            raise ValueError(f"budget_dollars must be > 0, got {budget_dollars}")

        # Compute fill price after slippage
        fill_price = apply_slippage(requested_price, "BUY", slippage_pct)
        # Compute units before final accounting
        units_filled = compute_units_for_budget(
            budget_dollars, requested_price, slippage_pct, fee_pct,
        )
        gross_value = units_filled * fill_price
        fee_paid = apply_fees(gross_value, fee_pct)
        total_cash_out = gross_value + fee_paid

        # Check free capital if provided
        if free_capital is not None and total_cash_out > free_capital + 1e-9:
            raise InsufficientCapitalError(
                f"BUY at ${requested_price:.2f} with budget ${budget_dollars:.2f} "
                f"would cost ${total_cash_out:.2f} but only ${free_capital:.2f} free"
            )

        # Slippage cost = what we paid extra vs what the strategy saw
        slippage_cost = units_filled * (fill_price - requested_price)

        return SimulatedFill(
            side="BUY",
            requested_price=requested_price,
            fill_price=fill_price,
            units=units_filled,
            gross_value=gross_value,
            fee_paid=fee_paid,
            slippage_cost=slippage_cost,
            cash_delta=-total_cash_out,  # money leaves account
        )

    if side == "SELL":
        if units is None or units <= 0:
            raise ValueError(f"SELL requires units > 0, got {units}")
        if budget_dollars is not None:
            raise ValueError("Don't specify 'budget_dollars' for SELL")
        if free_capital is not None:
            raise ValueError("free_capital is only meaningful for BUY")

        fill_price = apply_slippage(requested_price, "SELL", slippage_pct)
        gross_value = units * fill_price
        fee_paid = apply_fees(gross_value, fee_pct)
        total_cash_in = gross_value - fee_paid

        # Slippage cost = what we lost in proceeds vs what strategy saw
        slippage_cost = units * (requested_price - fill_price)

        return SimulatedFill(
            side="SELL",
            requested_price=requested_price,
            fill_price=fill_price,
            units=units,
            gross_value=gross_value,
            fee_paid=fee_paid,
            slippage_cost=slippage_cost,
            cash_delta=total_cash_in,  # money enters account
        )

    raise ValueError(f"side must be 'BUY' or 'SELL', got '{side}'")


# ════════════════════════════════════════════════════════════════
#                    SAFE WRAPPER : try, catch insufficient, skip
# ════════════════════════════════════════════════════════════════

def try_open_trade(
    asset: str,
    requested_price: float,
    free_capital: float,
    initial_capital: float = config.INITIAL_CAPITAL,
    max_pct_per_asset: float = config.MAX_POSITION_PCT_PER_ASSET,
    slippage_pct: float = config.SLIPPAGE_PCT,
    fee_pct: float = config.FEE_PCT_PER_LEG,
) -> Optional[SimulatedFill]:
    """Attempt to open a long position using the agreed sizing policy.

    Implements the "skip on insufficient capital" decision: if there's
    not enough free cash, return None and log a warning (no exception).

    Args:
        asset: for logging only (e.g. "BTC")
        requested_price: target entry price (H1 close)
        free_capital: current available cash (capital - already engaged)
        initial_capital, max_pct_per_asset: sizing parameters
        slippage_pct, fee_pct: cost parameters

    Returns:
        SimulatedFill if successful, None if skipped due to insufficient capital.
    """
    budget = compute_position_budget(initial_capital, max_pct_per_asset)
    try:
        fill = simulate_market_order(
            side="BUY",
            requested_price=requested_price,
            budget_dollars=budget,
            free_capital=free_capital,
            slippage_pct=slippage_pct,
            fee_pct=fee_pct,
        )
        logger.info(
            "OPEN %s @ $%.4f → %.6f units (cost $%.2f, fee $%.4f)",
            asset, fill.fill_price, fill.units, -fill.cash_delta, fill.fee_paid,
        )
        return fill
    except InsufficientCapitalError as e:
        logger.warning("SKIP %s: %s", asset, e)
        return None


# ════════════════════════════════════════════════════════════════
#                    REALIZED PNL : entry + exit → trade outcome
# ════════════════════════════════════════════════════════════════

def compute_realized_trade(
    asset: str,
    entry_fill: SimulatedFill,
    exit_fill: SimulatedFill,
    held_bars: int,
    direction: str = "BUY",
) -> RealizedTrade:
    """Combine entry + exit fills into a final trade outcome.

    pnl_dollars = exit.cash_delta + entry.cash_delta
                = (gross_in - exit_fees) + (-gross_out - entry_fees)
                = (units × exit_fill_price) - (units × entry_fill_price)
                  - all_fees - all_slippage
    """
    if direction.upper() != "BUY":
        # Short trades not supported yet on spot
        raise NotImplementedError("Only long trades (BUY entry) supported in Session 6")

    if entry_fill.side != "BUY" or exit_fill.side != "SELL":
        raise ValueError(
            f"Expected BUY entry and SELL exit, got {entry_fill.side}/{exit_fill.side}"
        )

    # Cash flow: out at entry, in at exit
    pnl_dollars = entry_fill.cash_delta + exit_fill.cash_delta
    # pnl_pct relative to gross entry cost (so user sees % return on capital deployed)
    base = entry_fill.gross_value
    pnl_pct = (pnl_dollars / base) if base > 0 else 0.0

    total_fees = entry_fill.fee_paid + exit_fill.fee_paid
    total_slippage = entry_fill.slippage_cost + exit_fill.slippage_cost

    return RealizedTrade(
        asset=asset,
        direction="BUY",
        entry_fill=entry_fill,
        exit_fill=exit_fill,
        pnl_dollars=pnl_dollars,
        pnl_pct=pnl_pct,
        total_fees=total_fees,
        total_slippage=total_slippage,
        held_bars=held_bars,
    )


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : quick demo
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 64)
    print("  order_simulator.py — démo")
    print("=" * 64)

    print(f"\nCapital initial      : ${config.INITIAL_CAPITAL:,.2f}")
    print(f"Budget par trade     : ${compute_position_budget():.2f}")
    print(f"Slippage simulé      : {config.SLIPPAGE_PCT*100:.2f}%")
    print(f"Fees Kraken simulés  : {config.FEE_PCT_PER_LEG*100:.2f}% par leg")
    print()

    # Simulation : on ouvre un trade BTC à $80,000
    print("--- Scenario : BUY BTC @ $80,000 ---")
    entry = try_open_trade(
        asset="BTC",
        requested_price=80000.0,
        free_capital=config.INITIAL_CAPITAL,
    )
    print(f"  Fill price      : ${entry.fill_price:,.4f}  "
          f"(vs requested ${entry.requested_price:,.2f})")
    print(f"  Units filled    : {entry.units:.6f} BTC")
    print(f"  Gross           : ${entry.gross_value:.4f}")
    print(f"  Fee paid        : ${entry.fee_paid:.4f}")
    print(f"  Slippage cost   : ${entry.slippage_cost:.4f}")
    print(f"  Cash out        : ${-entry.cash_delta:.4f}")
    print()

    # Simulation : sortie 5% plus haut (TP)
    print("--- Scenario : SELL BTC @ $84,000 (5% TP) ---")
    exit_fill = simulate_market_order(
        side="SELL",
        requested_price=84000.0,
        units=entry.units,
    )
    print(f"  Fill price      : ${exit_fill.fill_price:,.4f}  "
          f"(vs requested ${exit_fill.requested_price:,.2f})")
    print(f"  Gross           : ${exit_fill.gross_value:.4f}")
    print(f"  Fee paid        : ${exit_fill.fee_paid:.4f}")
    print(f"  Slippage cost   : ${exit_fill.slippage_cost:.4f}")
    print(f"  Cash in         : ${exit_fill.cash_delta:.4f}")
    print()

    # Bilan
    print("--- Trade closed ---")
    trade = compute_realized_trade(
        asset="BTC",
        entry_fill=entry,
        exit_fill=exit_fill,
        held_bars=10,
    )
    sign = "+" if trade.pnl_dollars >= 0 else ""
    print(f"  PnL             : {sign}${trade.pnl_dollars:.4f} "
          f"({sign}{trade.pnl_pct*100:.2f}%)")
    print(f"  Total fees      : ${trade.total_fees:.4f}")
    print(f"  Total slippage  : ${trade.total_slippage:.4f}")
    print(f"  Held            : {trade.held_bars} H1 bars")

    # Test insufficient capital
    print()
    print("--- Scenario : capital insuffisant ---")
    skipped = try_open_trade(
        asset="BTC",
        requested_price=80000.0,
        free_capital=10.0,  # only $10 free, can't open $125 trade
    )
    print(f"  Result: {skipped}  (should be None)")

    print()
    print("=" * 64)
    print("  order_simulator.py OK")
    print("=" * 64)
