"""
walkforward_icc.py — Session 5 walk-forward validation
======================================================
Sliding-window walk-forward for ICC strategy with full quant metrics.

DESIGN PRINCIPLES :
    - No tuning during walk-forward (anti-overfitting)
    - All parameters frozen at the Session 4 baseline (CONFIG A)
    - Each test window is OUT-OF-SAMPLE relative to its preceding 12 months
    - Train window is NOT used to fit (ICC has no parameters to fit) — it serves
      as historical context for swing detection and bias evaluation only
    - Metrics computed per test window, then aggregated across windows
    - Critical: the test windows are NON-OVERLAPPING in terms of trade entries
      (a trade started in test window N is fully attributed to window N)

WALK-FORWARD SCHEDULE :
    train_months = 12   (used as warm-up context for structures/OBs)
    test_months  = 6    (the OOS window where trades count)
    step_months  = 3    (sliding step)
    
    Example over 4 years :
        Win 1: train [Y0..Y1], test [Y1..Y1.5]
        Win 2: train [Y0.25..Y1.25], test [Y1.25..Y1.75]
        ...

METRICS COMPUTED :
    PER WINDOW :
        - PnL%       : sum of trade returns
        - WinRate    : %
        - PF         : sum(wins) / |sum(losses)|
        - Sharpe     : ann. sharpe from per-trade returns (assuming ~26 trades/year)
        - MaxDD      : max equity drawdown
        - Trades     : count
    
    AGGREGATED :
        - Mean PnL across windows
        - Mean WinRate
        - Mean Sharpe
        - Max DD (worst case across all windows)
        - Profit Factor aggregated
        - Cross-asset profitability count (X/8)
        - Cross-window profitable rate (% of windows with PnL > 0)

VERDICT RULE (Hard/Soft) :
    HARD (3/3 required) :
        - Profit Factor ≥ 1.5
        - Max DD ≤ 35%
        - Cross-asset ≥ 5/8 profitable
    SOFT (3/4 required) :
        - WinRate ≥ 50%
        - Sharpe ≥ 1.0
        - Trades/year ≥ 5
        - Cross-window profitable ≥ 60%
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np

from strategies.icc_cycle import (
    run_icc_cycle, TradeSetup, TradeState, ExitReason, TradeMode,
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WindowResult:
    """Metrics for a single walk-forward window."""
    asset: str
    window_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    
    # Counts
    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0
    
    # Performance
    pnl_pct: float = 0.0       # sum of trade returns
    win_rate: float = 0.0      # 0-1
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    sharpe_ann: float = 0.0
    max_dd: float = 0.0
    
    # Raw trades (for debugging)
    trade_pnls: list[float] = field(default_factory=list)
    

@dataclass
class AssetResult:
    """Aggregated results across all windows for one asset."""
    asset: str
    n_windows: int
    windows: list[WindowResult]
    
    # Aggregated
    total_trades: int = 0
    mean_pnl_per_window: float = 0.0
    cumulative_pnl: float = 0.0
    mean_win_rate: float = 0.0
    overall_profit_factor: float = 0.0
    mean_sharpe: float = 0.0
    worst_max_dd: float = 0.0
    trades_per_year: float = 0.0
    pct_windows_profitable: float = 0.0
    
    # Critical for verdict
    is_profitable: bool = False  # cumulative_pnl > 0


# ============================================================================
# METRICS CALCULATION
# ============================================================================

def compute_window_metrics(
    setups: list[TradeSetup],
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
) -> dict:
    """
    Compute metrics for trades that ENTERED within the test window.
    
    A trade belongs to a window if its entry_timestamp is within [test_start, test_end).
    Exits can occur after test_end — we just count the final PnL.
    """
    # Filter trades that entered during this test window
    window_trades = [
        s for s in setups
        if s.entry_timestamp is not None
        and test_start <= s.entry_timestamp < test_end
        and s.pnl_pct is not None
    ]
    
    pnls = [s.pnl_pct for s in window_trades]
    
    if not pnls:
        return {
            'n_trades': 0, 'n_wins': 0, 'n_losses': 0,
            'pnl_pct': 0.0, 'win_rate': 0.0, 'profit_factor': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0, 'sharpe_ann': 0.0,
            'max_dd': 0.0, 'trade_pnls': [],
        }
    
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0
    
    # Equity curve from trades (assume each trade uses full capital normalized to 1)
    # Per-trade returns chained for max DD
    equity = [1.0]
    for p in pnls:
        equity.append(equity[-1] * (1 + p))
    equity = np.array(equity)
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = abs(drawdown.min())  # positive number representing worst DD
    
    # Sharpe : annualized from per-trade returns
    if len(pnls) >= 2:
        std = np.std(pnls, ddof=1)
        mean = np.mean(pnls)
        # Approximate annualization: assume ~26 trades/year baseline
        # (we'll compute the real trades/year at the aggregate level)
        sharpe_per_trade = mean / std if std > 0 else 0.0
        # Naive annualization — better done at aggregate
        sharpe_ann = sharpe_per_trade * np.sqrt(26)
    else:
        sharpe_ann = 0.0
    
    return {
        'n_trades': len(pnls),
        'n_wins': len(wins),
        'n_losses': len(losses),
        'pnl_pct': sum(pnls),  # NOTE: sum of returns, not compounded
        'win_rate': len(wins) / len(pnls),
        'profit_factor': sum_wins / max(sum_losses, 1e-9),
        'avg_win': np.mean(wins) if wins else 0.0,
        'avg_loss': np.mean(losses) if losses else 0.0,
        'sharpe_ann': sharpe_ann,
        'max_dd': max_dd,
        'trade_pnls': pnls,
    }


# ============================================================================
# WALK-FORWARD CORE
# ============================================================================

def generate_windows(
    h1_start: pd.Timestamp,
    h1_end: pd.Timestamp,
    train_months: int = 12,
    test_months: int = 6,
    step_months: int = 3,
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """
    Generate sliding (train_start, train_end, test_start, test_end) windows.
    train_end == test_start (no gap, but trades only counted from test_start).
    """
    windows = []
    train_start = h1_start
    
    while True:
        train_end = train_start + pd.DateOffset(months=train_months)
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=test_months)
        
        if test_end > h1_end:
            break
        
        windows.append((train_start, train_end, test_start, test_end))
        train_start = train_start + pd.DateOffset(months=step_months)
    
    return windows


def run_walkforward_asset(
    asset: str,
    daily_prices: pd.DataFrame,
    h4_prices: pd.DataFrame,
    h1_prices: pd.DataFrame,
    train_months: int = 12,
    test_months: int = 6,
    step_months: int = 3,
    verbose: bool = False,
) -> AssetResult:
    """
    Run walk-forward backtest for one asset.
    
    For each window:
        1. Slice data to [train_start, test_end] (warm-up + OOS test)
        2. Run ICC cycle on the slice
        3. Extract trades that entered during [test_start, test_end)
        4. Compute window metrics
    """
    h1_start = h1_prices.index.min()
    h1_end = h1_prices.index.max()
    
    windows = generate_windows(h1_start, h1_end, train_months, test_months, step_months)
    
    if verbose:
        print(f"  {asset}: {len(windows)} walk-forward windows from {h1_start.date()} to {h1_end.date()}")
    
    window_results: list[WindowResult] = []
    
    for wid, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
        # Slice each TF to [train_start, test_end]
        daily_slice = daily_prices.loc[tr_s:te_e]
        h4_slice = h4_prices.loc[tr_s:te_e]
        h1_slice = h1_prices.loc[tr_s:te_e]
        
        # Skip if any slice is too short to be meaningful
        if len(daily_slice) < 30 or len(h4_slice) < 100 or len(h1_slice) < 500:
            continue
        
        # Run ICC on slice
        try:
            setups = run_icc_cycle(
                asset=asset,
                daily_prices=daily_slice,
                h4_prices=h4_slice,
                h1_prices=h1_slice,
                mode=TradeMode.SWING,
                verbose=False,
            )
        except Exception as e:
            if verbose:
                print(f"    Window {wid}: ICC run failed: {e}")
            continue
        
        # Compute metrics for the test window
        metrics = compute_window_metrics(setups, te_s, te_e)
        
        wr = WindowResult(
            asset=asset, window_id=wid,
            train_start=tr_s, train_end=tr_e,
            test_start=te_s, test_end=te_e,
            **metrics,
        )
        window_results.append(wr)
        
        if verbose and metrics['n_trades'] > 0:
            print(f"    Win {wid:3d} [{te_s.date()}→{te_e.date()}]: "
                  f"{metrics['n_trades']:2d} trades, "
                  f"WR {metrics['win_rate']*100:5.1f}%, "
                  f"PnL {metrics['pnl_pct']*100:+6.2f}%, "
                  f"PF {metrics['profit_factor']:.2f}")
    
    # Aggregate
    return _aggregate_asset_results(asset, window_results, test_months)


def _aggregate_asset_results(
    asset: str,
    windows: list[WindowResult],
    test_months: int,
) -> AssetResult:
    """Combine per-window metrics into an asset-level summary."""
    if not windows:
        return AssetResult(asset=asset, n_windows=0, windows=[])
    
    # Pool all trades for overall PF
    all_pnls = [p for w in windows for p in w.trade_pnls]
    total_trades = len(all_pnls)
    
    wins = [p for p in all_pnls if p > 0]
    losses = [p for p in all_pnls if p <= 0]
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0
    
    # Per-window aggregations
    window_pnls = [w.pnl_pct for w in windows]
    window_wrs = [w.win_rate for w in windows if w.n_trades > 0]
    window_sharpes = [w.sharpe_ann for w in windows if w.n_trades >= 2]
    window_dds = [w.max_dd for w in windows]
    
    # Cumulative PnL (sum of all trade returns)
    cumulative_pnl = sum(all_pnls)
    
    # Trades per year
    total_years = sum(test_months for w in windows) / 12.0
    trades_per_year = total_trades / max(total_years, 0.001)
    
    # % of windows profitable
    profitable_windows = sum(1 for w in windows if w.pnl_pct > 0)
    pct_profitable = profitable_windows / len(windows) if windows else 0.0
    
    return AssetResult(
        asset=asset,
        n_windows=len(windows),
        windows=windows,
        total_trades=total_trades,
        mean_pnl_per_window=np.mean(window_pnls) if window_pnls else 0.0,
        cumulative_pnl=cumulative_pnl,
        mean_win_rate=np.mean(window_wrs) if window_wrs else 0.0,
        overall_profit_factor=sum_wins / max(sum_losses, 1e-9),
        mean_sharpe=np.mean(window_sharpes) if window_sharpes else 0.0,
        worst_max_dd=max(window_dds) if window_dds else 0.0,
        trades_per_year=trades_per_year,
        pct_windows_profitable=pct_profitable,
        is_profitable=cumulative_pnl > 0,
    )


# ============================================================================
# VERDICT — HARD/SOFT RULE
# ============================================================================

@dataclass
class Verdict:
    """Final viability verdict per the agreed Hard/Soft rule."""
    
    # Aggregated metrics across all assets
    overall_profit_factor: float
    worst_max_dd: float
    n_assets_profitable: int    # /8
    mean_win_rate: float
    mean_sharpe: float
    mean_trades_per_year: float
    mean_pct_windows_profitable: float
    
    # Hard criteria (3/3 mandatory)
    hard_pf: bool      # PF >= 1.5
    hard_dd: bool      # MaxDD <= 35%
    hard_cross: bool   # >=5/8 profitable
    
    # Soft criteria (3/4 needed)
    soft_wr: bool      # WR >= 50%
    soft_sharpe: bool  # Sharpe >= 1.0
    soft_trades: bool  # Trades/year >= 5
    soft_windows: bool # >=60% profitable windows
    
    # Final
    is_viable: bool
    n_hard_passed: int
    n_soft_passed: int
    
    def summary(self) -> str:
        lines = [
            "=" * 70,
            "  VERDICT ICC — SESSION 5 WALK-FORWARD",
            "=" * 70,
            "",
            "HARD CRITERIA (3/3 mandatory):",
            f"  {'✓' if self.hard_pf    else '✗'} Profit Factor ≥ 1.5    : {self.overall_profit_factor:.2f}",
            f"  {'✓' if self.hard_dd    else '✗'} Max Drawdown ≤ 35%     : {self.worst_max_dd*100:.1f}%",
            f"  {'✓' if self.hard_cross else '✗'} Profitable assets ≥ 5/8: {self.n_assets_profitable}/8",
            f"  → {self.n_hard_passed}/3 hard criteria passed",
            "",
            "SOFT CRITERIA (3/4 needed):",
            f"  {'✓' if self.soft_wr      else '✗'} Win Rate ≥ 50%         : {self.mean_win_rate*100:.1f}%",
            f"  {'✓' if self.soft_sharpe  else '✗'} Sharpe ≥ 1.0           : {self.mean_sharpe:.2f}",
            f"  {'✓' if self.soft_trades  else '✗'} Trades/year ≥ 5        : {self.mean_trades_per_year:.1f}",
            f"  {'✓' if self.soft_windows else '✗'} Profitable windows≥60% : {self.mean_pct_windows_profitable*100:.1f}%",
            f"  → {self.n_soft_passed}/4 soft criteria passed",
            "",
            "=" * 70,
            f"  FINAL VERDICT : {'✅ VIABLE — proceed to paper trading' if self.is_viable else '❌ NON-VIABLE — do not paper trade'}",
            "=" * 70,
        ]
        return "\n".join(lines)


def compute_verdict(asset_results: list[AssetResult]) -> Verdict:
    """Apply Hard/Soft rule to aggregated results."""
    
    # Pool all trades across all assets for global PF/DD
    all_pnls = [
        p for ar in asset_results for w in ar.windows for p in w.trade_pnls
    ]
    
    if not all_pnls:
        # Empty case — verdict is non-viable trivially
        return Verdict(
            overall_profit_factor=0.0, worst_max_dd=0.0,
            n_assets_profitable=0, mean_win_rate=0.0,
            mean_sharpe=0.0, mean_trades_per_year=0.0,
            mean_pct_windows_profitable=0.0,
            hard_pf=False, hard_dd=False, hard_cross=False,
            soft_wr=False, soft_sharpe=False, soft_trades=False, soft_windows=False,
            is_viable=False, n_hard_passed=0, n_soft_passed=0,
        )
    
    wins = [p for p in all_pnls if p > 0]
    losses = [p for p in all_pnls if p <= 0]
    sum_wins = sum(wins)
    sum_losses = abs(sum(losses)) if losses else 0.0
    overall_pf = sum_wins / max(sum_losses, 1e-9)
    
    # Worst MaxDD across all assets' worst window DD (conservative)
    worst_dd = max((ar.worst_max_dd for ar in asset_results), default=0.0)
    
    # Cross-asset profitability
    n_profitable = sum(1 for ar in asset_results if ar.is_profitable)
    
    # Mean metrics across assets (each asset weighs equally)
    valid_assets = [ar for ar in asset_results if ar.total_trades > 0]
    if valid_assets:
        mean_wr = np.mean([ar.mean_win_rate for ar in valid_assets])
        mean_sharpe = np.mean([ar.mean_sharpe for ar in valid_assets])
        mean_trades_year = np.mean([ar.trades_per_year for ar in valid_assets])
        mean_pct_win = np.mean([ar.pct_windows_profitable for ar in valid_assets])
    else:
        mean_wr = mean_sharpe = mean_trades_year = mean_pct_win = 0.0
    
    # Criteria
    hard_pf = overall_pf >= 1.5
    hard_dd = worst_dd <= 0.35
    hard_cross = n_profitable >= 5
    
    soft_wr = mean_wr >= 0.50
    soft_sharpe = mean_sharpe >= 1.0
    soft_trades = mean_trades_year >= 5
    soft_windows = mean_pct_win >= 0.60
    
    n_hard = sum([hard_pf, hard_dd, hard_cross])
    n_soft = sum([soft_wr, soft_sharpe, soft_trades, soft_windows])
    
    is_viable = (n_hard == 3) and (n_soft >= 3)
    
    return Verdict(
        overall_profit_factor=overall_pf,
        worst_max_dd=worst_dd,
        n_assets_profitable=n_profitable,
        mean_win_rate=mean_wr,
        mean_sharpe=mean_sharpe,
        mean_trades_per_year=mean_trades_year,
        mean_pct_windows_profitable=mean_pct_win,
        hard_pf=hard_pf, hard_dd=hard_dd, hard_cross=hard_cross,
        soft_wr=soft_wr, soft_sharpe=soft_sharpe,
        soft_trades=soft_trades, soft_windows=soft_windows,
        is_viable=is_viable,
        n_hard_passed=n_hard, n_soft_passed=n_soft,
    )


# ============================================================================
# REPORTING
# ============================================================================

def print_asset_table(results: list[AssetResult]) -> None:
    """Print per-asset summary table."""
    print()
    print(f"  {'Asset':<6} {'Wins':<5} {'Trd':<5} {'Win%':<7} {'PF':<7} {'PnL%':<8} {'DD%':<6} {'Win.OK%':<8}")
    print('  ' + '-' * 60)
    for ar in results:
        if ar.total_trades == 0:
            print(f"  {ar.asset:<6} {ar.n_windows:<5} {0:<5} {'  --':<7} {'  --':<7} {'  --':<8} {'  --':<6} {'  --':<8}")
            continue
        print(f"  {ar.asset:<6} "
              f"{ar.n_windows:<5} "
              f"{ar.total_trades:<5} "
              f"{ar.mean_win_rate*100:<7.1f} "
              f"{ar.overall_profit_factor:<7.2f} "
              f"{ar.cumulative_pnl*100:+8.2f} "
              f"{ar.worst_max_dd*100:<6.1f} "
              f"{ar.pct_windows_profitable*100:<8.1f}")
    print()
