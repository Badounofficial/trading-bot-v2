# SL Anchor Comparison — V1 (current) vs V2 (H4 swing) — Honest Analysis

**Date** : 2026-05-12  
**Author** : automated audit + applied fix  
**Period tested** : 2024-01-01 → 2025-12-31 (~2 years, full overlap window for all 8 assets)  
**Assets tested** : BTC, ETH, SOL, ADA, AVAX, DOT, LINK, LTC  
**Pipeline** : `strategies/icc_cycle.run_icc_cycle()` — SWING mode, all defaults except `sl_mode`.

## Context — why this experiment ran

The same fix was previously validated on a sibling project (**ICC Trading Bot**, 5.3 years of data, 4 assets): moving the initial stop-loss from the H1 confirmation timeframe to the H4 reference timeframe improved WR by 1–2pp, PF on all assets, and total PnL by ~7% on average. Hypothesis: in SWING mode the H4 is the *real* structural reference, and the H1-anchored SL is too tight — normal H1 noise stops out trades that are still structurally valid.

This document reports the same experiment on this codebase (`trading-bot-v2`).

## The variants tested

| Variant | Initial SL anchor | Trailing SL anchor |
|---|---|---|
| **V1** (current) | last HL/LH on **H1**, on the **close** + 0.1% buffer | new HL/LH on H1 (close) |
| **V2b** | last unbroken HL/LH on **H4**, on the **close** + 0.1% buffer | new HL/LH on H4 (close) |
| **V2** | last unbroken HL/LH on **H4**, on the **wick** + 0.1% buffer | new HL/LH on H4 (wick) |

V2 is the spec the user gave (matching the other project's fix). V2b is added as a controlled intermediate to isolate the *timeframe* change from the *wick vs close* change.

Implementation: `strategies/icc_cycle.py`, function `_compute_initial_sl_h4()` + a single `sl_mode` flag on `run_icc_cycle()`. The legacy V1 path is unchanged and remains the default, so existing tests (63/63) still pass.

## Results — per asset

| Asset | Trd | WR V1 | WR V2b | WR V2 | PF V1 | PF V2b | PF V2 | PnL V1 | PnL V2b | PnL V2 | DD V1 | DD V2b | DD V2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC  | 34 | 52.9% | 29.4% | 35.3% | 2.75 | 0.63 | 0.91 | **+25.7%** | -18.7% | -4.8% | 4.8% | 21.5% | 16.1% |
| ETH  | 39 | 79.5% | 48.7% | 51.3% | 12.11 | 1.72 | 2.57 | **+89.3%** | +35.0% | +79.4% | 2.8% | 18.1% | 19.2% |
| SOL  | 43 | 48.8% | 39.5% | 41.9% | 3.76 | 1.35 | 1.28 | **+72.2%** | +25.0% | +22.5% | 5.3% | 26.4% | 27.2% |
| ADA  | 47 | 51.1% | 38.3% | 38.3% | 1.87 | 1.25 | 1.17 | **+34.6%** | +28.0% | +21.7% | 11.7% | 45.5% | 52.4% |
| AVAX | 53 | 69.8% | 41.5% | 49.1% | 5.98 | 1.04 | 1.41 | **+101.9%** | +5.3% | +47.6% | 7.6% | 39.2% | 37.2% |
| DOT  | 28 | 57.1% | 50.0% | 57.1% | 2.84 | 2.07 | 3.03 | +34.4% | +49.0% | **+92.8%** | 10.3% | 16.3% | 18.5% |
| LINK | 53 | 62.3% | 34.0% | 34.0% | 3.79 | 0.92 | 1.17 | **+89.1%** | -9.9% | +20.1% | 9.6% | 43.1% | 29.8% |
| LTC  | 35 | 60.0% | 34.3% | 37.1% | 4.28 | 1.13 | 1.22 | **+53.9%** | +7.0% | +13.0% | 2.9% | 14.9% | 15.0% |

**Aggregates** (`Σ` over all 8 assets, equal-weighted, ~332 trades each variant):

| Variant | Trades | Win Rate | Profit Factor | Σ Total PnL |
|---|---:|---:|---:|---:|
| V1 (current)   | 332 | **60.5%** | **3.84** | **+501.2pp** |
| V2b (H4 close) | 332 | 39.2% | 1.19 | +120.6pp |
| V2 (H4 wick)   | 332 | 42.5% | 1.44 | +292.3pp |

**Verdict — V1 dominates on 7 out of 8 assets.** Only DOT improves under V2 (+58pp PnL, same WR, better PF).

## Why the fix doesn't transfer here

The mechanism the fix is *supposed* to provide *does* show up in the metrics:

| Effect | Observed? |
|---|---|
| Fewer SL_HIT, more TRAILING_HIT (= fewer noise stop-outs) | **Yes**, across every asset |
| Bigger average win | **Yes**, AvgWin roughly doubles (e.g. BTC 2.24% → 4.13%, ETH 3.14% → 6.49%) |
| Longer hold time | **Yes**, avg duration 7–9h → 40–80h |

But the *cost* of widening the SL also shows up:

| Effect | Observed? |
|---|---|
| Bigger average loss | **Yes**, AvgLoss roughly 2-3x (e.g. BTC -0.92% → -2.47%, ADA -1.74% → -4.53%) |
| Bigger max drawdown | **Yes**, on every asset (ADA: 11.7% → 52.4%, AVAX: 7.6% → 37.2%) |
| Lower planned RR | **Yes**, the TP is computed relative to risk (entry-SL distance), so widening SL pushes TP further and degrades realised RR |

Net: the **bigger losses overwhelm the bigger wins**. The "few extra winners saved from noise" gain is real but smaller than the "every loser is now 2-3x bigger" cost.

### Why the result differs from the ICC Trading Bot project

The two codebases have a different V1 baseline:

| | ICC Trading Bot (other project) | trading-bot-v2 (this codebase) |
|---|---|---|
| V1 anchor | H1 swing **wick** | H1 swing **close** (already tighter) |
| Distance from price | wider | tighter |
| Headroom for V2 to improve | meaningful | smaller (already tight) |

In the sibling project, V1→V2 was a single change (TF only: H1→H4). Here, V1→V2 simultaneously changes the TF (H1→H4) **and** the anchor (close→wick). V2b above isolates the TF-only change; even that version (a strictly more conservative widening than full V2) still underperforms V1 on 7/8 assets.

The most plausible underlying reason: the entry filter in `icc_cycle.py` is already very selective (deep correction OR shallow correction via Fibo discount/premium, AND a body close past a micro structure, AND Daily-bias aligned, AND active OB H4). By the time we enter, the H1-close SL is rarely hit by random noise — it's hit by genuine reversals, which is exactly when you *want* to exit fast. Widening the SL keeps you in those genuine reversals longer.

## Recommendation

**Keep V1 as the default** for trading-bot-v2. The fix that worked elsewhere does not improve this codebase.

What the changeset adds is useful as a building block, not as a default:

- The new `sl_mode` parameter is wired through `run_icc_cycle()` and `walkforward_icc.py` — defaulting to `'v1_h1_close'`. No behaviour change in scripts that don't set the flag.
- V2 (`'v2_h4_wick'`) and V2b (`'v2b_h4_close'`) are available for opt-in experimentation. If the user wants to try this on DOT specifically (the one asset where V2 helped) or to run further sensitivity studies (e.g. tighter buffer, hybrid trailing), the plumbing is there.
- All 63 ICC unit tests still pass (V1 unchanged).

I do **not** recommend a per-asset opt-in for V2 either. With only 1/8 assets improving (DOT), the improvement looks more like noise than a robust effect — N=28 trades on DOT is well below the bar for a "ship it" decision.

## Files touched

- `strategies/icc_cycle.py` : added `sl_mode` param, new `_compute_initial_sl_h4()`, V2 trailing branch in `_monitor_in_trade()`, plumbed parameters through `update_setup_state` / `_trigger_entry` / `run_icc_cycle`. Default `sl_mode='v1_h1_close'` keeps legacy behaviour.
- `strategies/walkforward_icc.py` : `sl_mode` plumbed into `run_walkforward_asset()`, defaults to V1.
- `scripts/compare_sl_v1_v2.py` : new — runs all 3 variants on all 8 assets, emits JSON + Markdown.
- `results/sl_v1_vs_v2_<ts>.{json,md}` : raw data for this analysis.

## How to re-run

```bash
cd ~/Desktop/trading-bot-v2
python scripts/compare_sl_v1_v2.py
```

~30 seconds total. Writes a fresh JSON + Markdown into `results/`.

## Possible follow-ups (not done here)

1. **Walk-forward the comparison** rather than full-period in-sample — but with only 2 years of data and a 6-month test window, the result would mostly mirror the in-sample picture. The sample is small for that.
2. **Hybrid SL**: use the **tighter** of (V1 H1-close, V2 H4-wick) — gives the best of both. Speculative but cheap to try; flag would be e.g. `'tighter_of_v1_v2'`.
3. **Per-asset volatility filter**: only use V2 when realised vol > threshold. Worth testing only after a stable theory is in place — premature here.
4. **Re-run the sibling-project (ICC Trading Bot) comparison with V2b (H4 close)** to verify the wick vs close distinction also matters there. That would close the loop on understanding *why* the two codebases diverge.
