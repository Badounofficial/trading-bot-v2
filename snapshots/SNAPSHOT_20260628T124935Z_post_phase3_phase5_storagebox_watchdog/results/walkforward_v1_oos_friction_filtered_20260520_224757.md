# V1 Walk-Forward OOS + Friction — Methodologically Qualified

**Run** : 20260520_224757 UTC

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
| bull_2024_2025 | OFF | 99 | 65.7% | 5.64 | +166.03pp | 4.3% | 2.92 |
| bull_2024_2025 | **ON** | 99 | 59.6% | 3.46 | +128.21pp | 10.4% | 2.22 |
| bear_recovery_2022_2023 | OFF | 74 | 58.1% | 4.63 | +100.67pp | 4.8% | 1.51 |
| bear_recovery_2022_2023 | **ON** | 74 | 51.4% | 2.73 | +71.39pp | 7.3% | 1.07 |

## Per-asset (with friction, OOS)

### bull_2024_2025

| Asset | Windows | Trades | WR | PF | ΣPnL pp | DD | %WindowsProfitable | Trades/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ETH | 2 | 24 | 83.3% | 26.94 | +59.14pp | 1.0% | 100% | 24.0 |
| LTC | 2 | 23 | 66.9% | 7.35 | +51.36pp | 3.7% | 100% | 23.0 |
| AVAX | 2 | 27 | 59.6% | 2.10 | +17.52pp | 5.1% | 100% | 27.0 |
| SOL | 2 | 25 | 31.5% | 1.01 | +0.20pp | 10.4% | 50% | 25.0 |

### bear_recovery_2022_2023

| Asset | Windows | Trades | WR | PF | ΣPnL pp | DD | %WindowsProfitable | Trades/yr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ETH | 2 | 14 | 58.3% | 4.68 | +21.00pp | 3.0% | 100% | 14.0 |
| LTC | 2 | 13 | 60.7% | 4.83 | +19.12pp | 2.7% | 50% | 13.0 |
| AVAX | 2 | 25 | 43.2% | 1.48 | +7.73pp | 5.1% | 100% | 25.0 |
| SOL | 2 | 22 | 49.1% | 2.61 | +23.53pp | 7.3% | 100% | 22.0 |
