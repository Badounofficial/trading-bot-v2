# Trading Bot V2 — Phase 3 Success Criteria (v2 — operator-validated 5-gate framework)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-27 01:35 UTC
**Version** : v2 (revised after Sebastien validation of marathon 365j + 5-gate framework)
**Previous version** : v1 preserved in `snapshots/SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`

**Purpose** : définir AVANT deployment les critères binaires (Pattern 7) du marathon 365 jours et les 5 gates strictes de promotion vers real capital. Aucune ajustement post-hoc autorisé.

**Discipline** : Pattern 7 (Binary Acceptance Defined Before Measurement), P30 (Evidence Density), P33 (No-Skip).

---

## 1. Marathon 365 jours — calendrier checkpoints

Sebastien engagement explicite : 365 jours paper observation marathon. Patience institutionnalisée. Quality over speed.

| Jalon | Date (relative T0) | Action |
|---|---|---|
| **T0 deployment** | Day 0 | Snapshot Storage Box manuel + main commit hash + état paper actuel |
| **T+30 jours** | Day 30 | Sanity check live vs backtest expected (±50 % tolerance) |
| **T+90 jours** | Day 90 | First checkpoint statistique exhaustif. Ajustements config si needed (avec validation Sebastien explicite) |
| **T+180 jours** | Day 180 | Mid-marathon evaluation. 5-gate framework appliqué preliminary. |
| **T+365 jours** | Day 365 | **Final evaluation. 5-gate strict. Real capital decision.** |

---

## 2. 5-Gate Framework — promotion vers real capital

**Tous 5 gates doivent pass simultanément** au Day 365 pour considérer scaling au-delà de paper. Si <5/5 → continuer observation 30j supplémentaires OU retour design (P32 repair-before-run).

### Gate 1 — Sharpe convergence (live vs backtest)

| Item | Cible strict |
|---|---|
| Backtest expected Sharpe (OOS 13.5 mois always-in BTC+ETH) | ~50+ (extremely high pour funding capture pure) |
| Live Phase 3 observed Sharpe (annualised, computed on funding accrued) | **≥ 80 % du backtest expected** |
| Sample size minimum | ≥ 200 trading days observed (~6 mois minimum) |
| Computation | Standard annualized Sharpe : (mean daily return × 365) / (std daily return × √365) |

**Justification du 80 % threshold** : tolérance pour live friction réelle > 10 bps modélisée, regime change, slippage exécution.

**Pass/Fail** : binary.

### Gate 2 — DD bounded (live vs backtest)

| Item | Cible strict |
|---|---|
| Backtest max DD (always-in BTC+ETH OOS) | -0.33 % |
| Live max DD over 365 days | **≤ 1.5 × backtest max DD = -0.50 %** |
| Computation | Underwater curve: (equity_t - cummax(equity_0..t)) / capital × 100, min over 365 days |

**Justification du 1.5× multiplier** : tolérance pour funding rate shock + market microstructure live.

**Pass/Fail** : binary.

### Gate 3 — Regime diversity observed

| Item | Cible strict |
|---|---|
| Funding regime shift observé | **≥ 1 regime shift** during 365 days |
| Definition "regime shift" | Funding APR mean changes sign OR compresses by > 50 % OR expands by > 100 % within 30-day rolling window |
| Sub-criteria | At least one of: funding sign flip, ATR compression episode, ATR expansion episode |

**Justification** : démontrer que la stratégie est robuste à différents régimes funding, pas dépendante d'un single state of the market.

**Pass/Fail** : binary (≥ 1 regime shift documented).

### Gate 4 — Friction match (live vs model)

| Item | Cible strict |
|---|---|
| Modeled slippage round-trip | 3.5 bps perp + ~3 bps spot = ~6 bps × 2 sides = ~12 bps RT |
| Modeled fees round-trip | 3.5 bps perp taker × 2 sides + spot fees = ~10 bps RT (HL standard) |
| Live observed slippage + fees round-trip | **Within ±20 % of modeled** |
| Sample size | All positions opened+closed during marathon (estimated 24 cycles minimum) |
| Source | Compare paper-modeled cost vs ratio of expected funding earned vs observed funding earned |

**Justification** : si live friction > modeled by 20 %+, le backtest était optimiste, ré-évaluation nécessaire.

**Pass/Fail** : binary.

### Gate 5 — Operational integrity

| Item | Cible strict |
|---|---|
| Uptime daemon | **≥ 99 %** over 365 days (= ≤ 3.65 days downtime total) |
| Watchdog miss (primary OR secondary) | **≤ 1 per month** average (= ≤ 12 total over 365 days) |
| Unplanned downtime events | **0 zero** (any unscheduled crash, OOM, kill counts) |
| API errors persistent | **0 episodes > 24h with > 50 errors** |
| Telegram delivery rate (daily reconciliation) | **≥ 95 %** delivered |

**Justification** : pour Phase 4 (real capital), l'infrastructure doit être production-grade. Pas de tolérance sur unplanned downtime.

**Pass/Fail** : binary, conjunction of all 5 sub-items.

---

## 3. Métriques monitored daily (Telegram)

Daily reconciliation 12:05 UTC envoie Telegram avec ces métriques :

| Métrique | Source | Threshold attention | Threshold alarme |
|---|---|---|---|
| Day N / 365 | Marathon counter | N/A | N/A |
| **Net P&L cumul** | `realized_pnl_usd + Σ funding_accrued_usd` | N/A | N/A |
| **Net P&L 24h** | Delta vs yesterday | < $0 / 24h | < $0 / 7 jours consec |
| **Max DD 24h** | Computed | > -0.50 % | > -0.80 % |
| **Max DD cumul** | Computed | > -0.50 % | **kill switch at -1.00 %** |
| **Funding APR moyen 7j** | `mean(funding_rate × 8760)` | < 4 % APR | < 2 % APR |
| **Position state** | from daemon_state.json | hors {BTC, ETH} | hors {BTC, ETH} |
| **Total notional** | sum positions | ≠ $2 000 | ≠ $2 000 |
| **Cycle count progress** | delta/24h | < 12 cycles/h | < 5 cycles/h |
| **API errors 24h** | counter | > 5 | > 20 (alarme) |
| **Restart count** | from state | > 0 in 30j | > 1 in 7j |
| **Telegram heartbeat** | last delivery | > 30min | > 2h |

---

## 4. Threshold de promotion summary (Day 365)

**Promotion = OUI ssi tous 5 gates pass strict.** Aucune compensation entre gates.

| Gate | Threshold strict | Computation |
|---|---|---|
| 1 Sharpe convergence | ≥ 80 % du backtest expected | Live annualised Sharpe / Backtest expected Sharpe ≥ 0.80 |
| 2 DD bounded | ≤ 1.5 × backtest max DD (-0.50 %) | Live max DD ≥ -0.50 % over 365j |
| 3 Regime diversity | ≥ 1 regime shift observed | Documented funding regime change |
| 4 Friction match | within ±20 % of modeled | Live friction / Modeled friction ∈ [0.80, 1.20] |
| 5 Operational integrity | ≥ 99 % uptime + ≤ 1 watchdog miss/mois + 0 unplanned downtime | All 3 sub-criteria pass |

---

## 5. Threshold d'alarme (during marathon)

Trigger Telegram alert immédiat si pendant marathon :

| Trigger | Threshold | Action |
|---|---|---|
| **Kill switch DD** | < -1 % rolling 24h | **Auto-flat positions + state PENDING_USER_VALIDATION** (safeguard A + F) |
| Net P&L < -$50 cumul | sur 14 jours consec | Telegram alert, no auto action |
| API errors > 20/24h pendant 2j consec | persistent | Telegram alert urgent |
| Watchdog primary fail > 2h | stale heartbeat | Telegram alert via secondary watchdog (safeguard B) |
| Position state divergence | asset hors {BTC, ETH} | Telegram alert + auto-flat that position |
| Funding rate inversion > 7j consec | net funding < 0 sur 7j | Telegram alert, opérateur judgment call |
| Restart count > 3 / 24h | crash loop | Telegram alert + PENDING_USER_VALIDATION |

---

## 6. Threshold de rollback (immediate revert)

Different from alarme — rollback est l'action ultime, déclenchée quand l'alarme ne suffit pas. Per `phase3_rollback_protocol.md`.

| Trigger | Threshold | Action |
|---|---|---|
| Net P&L < -$100 cumul | depuis deploy | Rollback immédiat per protocol |
| Max DD réalisé > -2 % | observed any time | Rollback immédiat |
| API errors > 100 / 24h pendant 3j | Hyperliquid major outage | Rollback à filter design (peut être plus résilient ou cleanup state) |
| Sebastien explicit decision | manual via Telegram `/v2_rollback YES` ou Cowork message | Rollback immédiat |
| Operational integrity gate failure projection | < 95 % uptime at Day 180 mid-marathon | Rollback ou re-design |

---

## 7. Daily Telegram heartbeat — Phase 3 format

```
📊 V2 Phase 3 Day {N}/365
Cycle #{cycle_count}, uptime {uptime}d, restarts 24h: {n_restart}

💰 P&L Marathon
   Net cumul       : ${net_pnl:.2f} (target $300-450/mois pro-rata)
   Net 24h         : ${pnl_24h:+.2f}
   Funding accrued : ${funding_accrued:.2f}
   Max DD cumul    : {max_dd:.2f}% (kill switch -1.0%, alarme -0.5%)
   Max DD 24h      : {dd_24h:.2f}%

📈 Positions (target = 2 always)
   BTC: $1k notional, entry ${btc_entry}, funding ${btc_fund:.2f}
   ETH: $1k notional, entry ${eth_entry}, funding ${eth_fund:.2f}

🛡 Safeguards
   Kill switch     : ARMED (threshold -1%)
   2nd watchdog    : {2nd_status}
   Daily reconcil. : OK
   OB forward      : {ob_fw_status}

📊 vs Backtest expected
   Live / Modeled ratio: {ratio:.2f} (target 0.80-1.20)

⚠ Anomalies 24h
   API errors      : {n_api_errors} (alarme > 5)
   Telegram delivery: {tg_rate:.0f}% (alarme < 95%)
```

Format à valider Sebastien (Sec 9 question 3).

---

## 8. Reporting cadence

| Cadence | Format | Source |
|---|---|---|
| Daily 12:05 UTC | Telegram heartbeat (Sec 7) | `live/daily_reconciliation.py` |
| Weekly Saturday 12:05 UTC | Saturday Recap + Phase 3 metrics summary | `scripts/generate_saturday_recap.py` |
| Monthly | Comprehensive PDF report (TBD) | Manual or scripted |
| At checkpoints (T+30/90/180/365) | Deliverable `analysis/phase3_observation_day_<N>.md` | V2 agent autonomous |

---

## 9. Décisions opérateur requises sur cette spec v2

1. **5-gate thresholds** : toutes strictes acceptables (80 % Sharpe, 1.5× DD, ≥1 regime, ±20 % friction, 99 % uptime), ou ajuster ?
2. **Net P&L threshold alarme** : -$50 / 14j adéquat sur $2k notional ? Plus serré ?
3. **Daily Telegram format Sec 7** : ok ou changements ?
4. **Scaling path Day 365** : si 5/5 gates pass, plan scaling :
   - Phase 4.0 : start $500 réel — observe 30j zero surprise
   - Phase 4.1 : scale 5-10× après 30j zero surprise = $2.5k-$5k réel
   - Phase 4.2 : continue scaling per cycle vérifié, **cap X % portfolio Sebastien** (à définir)
5. **Si <5/5 gates pass at Day 365** : extend 90j supplémentaires, ou retour design avec P32 ?

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

## 10. Phrase that closes

> *Marathon 365 jours, 5 gates strict (Sharpe ≥80% backtest, DD ≤-0.50% live, ≥1 regime shift, friction ±20%, ops 99% uptime). Daily Telegram reconciliation 12:05 UTC. Pattern 7 enforced : tous critères mesurables, fixés AVANT observation. Aucune compensation entre gates. Promotion vers real capital ssi 5/5 pass simultanément Day 365.*

---

*Phase 3 Success Criteria v2 generated by V2 agent on 2026-06-27. v1 preserved `SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`. Production code untouched.*
