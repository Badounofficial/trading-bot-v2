# V1 Walk-Forward OOS + Friction — Methodologically Qualified

**Run** : 20260520_165346 UTC

## Mandatory 4-qualifier header

| Qualifier | Value |
|---|---|
| **Methodo**  | Walk-forward (12 m train / 6 m test / 3 m step, sliding, strict OOS) |
| **Friction** | Hyperliquid taker 4.5 bps × 2 legs + asset-tiered slippage (probabilistic, lognormal) + funding 0.001 %/h |
| **Window**   | A: 2024-01-01 → 2025-12-31 (bull) · B: 2022-01-01 → 2023-12-31 (bear→recovery) |
| **Regime**   | A: BTC +120 % in 2025 (bull) · B: Terra/Luna + FTX crashes + 2023 recovery (bear) |

## Aggregate results (V1 = SL on H1 close + 0.1 % buffer)

| Window | Friction | Trades | WR | PF | ΣPnL pp | Max DD | Sharpe (ann.) |
|---|---|---:|---:|---:|---:|---:|---:|
| bull_2024_2025 | OFF | 167 | 57.5% | 2.48 | +154.60pp | 10.3% | 1.47 |
| bull_2024_2025 | **ON** | 167 | 49.1% | 1.64 | +89.27pp | 12.7% | 0.84 |
| bear_recovery_2022_2023 | OFF | 142 | 56.3% | 4.10 | +180.47pp | 5.4% | 1.59 |
| bear_recovery_2022_2023 | **ON** | 142 | 50.0% | 2.54 | +126.93pp | 7.3% | 1.11 |

## Per-asset (with friction, OOS)

### bull_2024_2025

| Asset | Windows | Trades | WR | PF | ΣPnL pp | DD | %WindowsProfitable | Trades/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 2 | 9 | 55.0% | 0.53 | -1.56pp | 2.9% | 50% | 9.0 |
| ETH | 2 | 24 | 83.3% | 26.63 | +58.98pp | 1.0% | 100% | 24.0 |
| SOL | 2 | 25 | 31.5% | 1.06 | +1.45pp | 9.4% | 50% | 25.0 |
| ADA | 2 | 19 | 26.1% | 0.46 | -16.08pp | 11.9% | 0% | 19.0 |
| AVAX | 2 | 27 | 55.8% | 2.04 | +17.07pp | 5.2% | 100% | 27.0 |
| DOT | 2 | 14 | 46.7% | 0.35 | -13.41pp | 12.6% | 0% | 14.0 |
| LINK | 2 | 26 | 30.8% | 0.73 | -8.85pp | 12.7% | 0% | 26.0 |
| LTC | 2 | 23 | 66.9% | 7.09 | +51.68pp | 3.7% | 100% | 23.0 |

### bear_recovery_2022_2023

| Asset | Windows | Trades | WR | PF | ΣPnL pp | DD | %WindowsProfitable | Trades/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 2 | 13 | 22.5% | 0.80 | -0.82pp | 1.2% | 0% | 13.0 |
| ETH | 2 | 14 | 58.3% | 4.69 | +21.04pp | 3.0% | 100% | 14.0 |
| SOL | 2 | 22 | 43.6% | 2.77 | +24.58pp | 7.1% | 100% | 22.0 |
| ADA | 2 | 18 | 38.8% | 0.96 | -0.86pp | 7.3% | 50% | 18.0 |
| AVAX | 2 | 25 | 43.2% | 1.49 | +8.04pp | 5.0% | 100% | 25.0 |
| DOT | 2 | 17 | 53.6% | 2.28 | +11.42pp | 4.0% | 100% | 17.0 |
| LINK | 2 | 20 | 73.2% | 6.70 | +44.28pp | 5.0% | 100% | 20.0 |
| LTC | 2 | 13 | 60.7% | 4.90 | +19.24pp | 2.5% | 50% | 13.0 |
