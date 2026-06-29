# Trading Bot V2 — Phase 2 Loss Forensic Session Digest

**Date** : 2026-06-26 / 2026-06-27 (transition)
**Author** : V2 agent (autonomous, Cowork)
**Operator** : Sebastien Assohou (via Dispatch coordination)
**Scope** : Portfolio-level reference for Phase 2 loss forensic analysis closure and Phase 3 transition decision.
**Discipline** : Pattern 14 (Recursive Acknowledgment), Pattern 17 (Permission to Brutality), Pattern 18 (Phrase that Closes), Principle 31 (Reversibility), Principle 33 (No-Skip / Empirical Humility).
**Format** : Logan Operating Standard adapted.

---

## 1. Context

V2 (Trading Bot V2) trades funding capture delta-neutre on Hyperliquid perpetuals via short perp + long spot. Initial design (pre-Phase 2) used a smoothed funding filter with parameters `min_hold_hours=24, entry_threshold_apr=0.005, exit_threshold_apr=-0.005, smooth_hours=24` on universe BTC+ETH+SOL.

Sebastien instructed in late June 2026 to conduct deep forensic analysis of V2 paper trading losses + backtest losses, transform losses into testable hypotheses, validate with alpha_lab discipline, recommend production design changes if warranted. Quality over speed mandated: *"prends le temps nécessaire je ne suis pas pressé je veux qqch de tres solide et serieux presque indestructible"*.

Phase 2 = analysis. Phase 3 = deployment if warranted. Production main `232b8835f1f336fa3507848a2a388a06e3c3d1cf` (commit `audit lookahead fix shift1 engine 55 plus phase B measurement report`) was the baseline at session start.

---

## 2. Hypothèses testées (chronological + verdict)

| # | Hypothesis | Verdict | Beat-benchmark | Key finding |
|---|---|---|---|---|
| **H4** | Friction realistic re-sim on 14 paper trades | **NO-GO universe complet** | n/a (Phase 1 sample) | Filter sim ignored fees; live would lose $9-19/trade. SOL identifié comme killer. |
| **H1** | min_hold_hours extension 24→36→48→60 | **MARGINAL with override** | 🔴 FAIL filter < always-in by 68 % | Monotonic improvement BUT filter fundamentally < always-in benchmark. Discovered structural domination. |
| **H3** | Asset filter formal (BTC-only, BTC+ETH, BTC+ETH+SOL) | **MARGINAL with override** | 🔴 FAIL on 3/3 universes | Filter loses 39-57 % vs benchmark. SOL inclusion costs $200 OOS per asset. |
| **H6** | Always-in + circuit-breaker DD | **GO marginal** | 🟢 PASS +8.5 % vs benchmark | Only meaningful improvement found. But SOL-specific. |
| **H6 Robustness** | 4-axis test on H6 finding | **MARGINAL leaning FRAGILE** | 1/4 axes pass | N=1 event over 28.5 months — edge-case-protector, not general mechanism. |
| **H2** | entry_threshold tightening 0.005→0.015 APR | **NO-GO family closure** | 🔴 FAIL all 5 thresholds | Confirmed filter family is empirically dominated regardless of parametric tuning. |
| **H5** | Delta-neutre hedge testing | **Archive — already resolved** | n/a | Code audit confirmed daemon IS delta-neutre by design (short perp + long spot). Question already answered. |
| **H7** | Entry threshold on H6 paradigm | **Archive — inherits H6 fragility** | n/a | Sebastien decision: not relevant given H6 robustness fail. |

**Total 8 hypotheses processed under strict P33 No-Skip discipline.**

---

## 3. Empirical hierarchy discovered (OOS 13.5 months 2025-03-15 → 2026-05-04, friction 20bps RT)

```
WORST                                                                  BEST
══════════════════════════════════════════════════════════════════════════►
Filter   Filter      Pure        Pure         Pure          H6
SOL incl.| BTC+ETH    | always-in  | always-in   | always-in    | CB -0.75%
$832     | $1 032     | BTC-only   | BTC+ETH     | BTC+ETH+SOL  | BTC+ETH+SOL
         |            | $885       | $1 686 ← Sebastien choice | $2 080
         |            |            | (max DD -0.33%)            | (max DD -0.77%)
```

**Findings consolidés** :
1. Filter funding capture empirically dominated by trivial always-in across all tested configurations
2. Pure always-in delta-neutre = superior baseline reference
3. H6 circuit-breaker improvement +8.5 % is fragile (N=1 event)
4. SOL universe inclusion = killer for filter design (-$200 OOS per asset)
5. Robust intermediate = BTC+ETH pure always-in: $1 686 OOS, max DD -0.33 %, design trivially simple

---

## 4. Décisions opérateur actées

### 4.1 Phase 2 closure decisions

| Decision | Validated |
|---|---|
| Filter design empirically archived | ✅ |
| Pivot to no-filter paradigm | ✅ |
| Universe Phase 3 = **BTC+ETH only** (drop SOL) | ✅ |
| Design Phase 3 = **always-in pure delta-neutre** | ✅ |
| H5 archive (already resolved by code audit) | ✅ |
| H7 archive (inherits H6 fragility) | ✅ |

### 4.2 Phase 3 deployment decisions

| Decision | Value validated |
|---|---|
| Position sizing | **$1 000 BTC + $1 000 ETH = $2 000 total, equal weight, hardcoded** |
| Observation period | **365 jours paper marathon** |
| Promotion framework | **5-gate strict** (Sharpe convergence ≥80% backtest, DD ≤1.5× backtest, regime diversity, friction match ±20 %, ops integrity ≥99 % uptime) |
| Operational safeguards | **7 mandatory A→G** (kill switch, 2nd watchdog, daily reconciliation, manual override, position cap, sanity check on restart, OB forward verified weekly) |

### 4.3 Backup decisions

| Decision | Status |
|---|---|
| Working tree files preserved | ✅ (intact at sandbox EOL) |
| Git commit of Phase 2 archive | ⏸ blocked by sandbox lock — pending Sebastien unlock OR manual Mac commit |
| GitHub remote push | ⏸ pending Sebastien URL provision |

---

## 5. Méthodologie et discipline

### 5.1 Principles enforced through Phase 2

| Principle | Application |
|---|---|
| P1 — No look-ahead bias | Backtests walk-forward OOS strict (split 2025-03-15) |
| P2 — Friction realistic | H4 quantified; subsequent backtests used 10 bps per leg (20 bps RT) |
| P3 — Walk-forward OOS gating | All H1-H6 results reported on OOS only |
| P7 — Pattern naming | "Filter dominated by always-in" became reusable shorthand |
| P14 — Look-ahead SL exclusion | Maintained throughout (no SL placement involved in funding capture but discipline upheld for parameter timing) |
| P15 — Backup-Before-Action | 21 snapshots created across Phase 2 (1 per hypothesis pre+post + transitions) |
| **P30 — Evidence density preserved** | 1 deliverable per hypothesis + 1 reconciliation + 1 robustness — 8 forensic docs total |
| **P32 — Repair-Before-Run** | Mac silent crash incident (June 25) treated as learning, watchdog redundancy added to safeguards |
| **P33 — No-Skip / Empirical Humility** | V2 proposed bypass H1→H3 after H4 findings. Sebastien refused. H1 then revealed filter < always-in (the single most important finding of Phase 2). **P33 paid for itself.** |

### 5.2 Lessons learned (operator-side and agent-side)

**Operator-side** :
- P33 codification prevented sub-optimization on a fundamentally flawed family. Without forced H1 test, V2 would have spent days optimizing within filter design.
- Trust grant + verification cycle worked: Sebastien validated each verdict before pivot, but trusted V2 to execute under defined discipline.
- 365-day marathon mindset = institutional patience. Avoids the typical "1 month paper then live" trap.

**Agent-side (V2 self-reflection per Pattern 20)** :
- Phase 1 mistakenly described daemon as "long perp pur" when it was actually delta-neutre. Code audit during H5 closure corrected the error.
- Asymmetric plateau detection (one-sided cliff) is a real failure mode that simple "±25 % robust" tests miss. Need to look at curve shape, not just neighborhood values.
- N=1 event in backtest is NOT statistical evidence — even with perfect timing stability (AXE 4 robust). Sample size matters more than perturbation stability.

---

## 6. Confidence calibration

### 6.1 V2's confidence in Phase 3 design

| Dimension | Confidence | Justification |
|---|---|---|
| Filter family is empirically dominated | **High** | 3 hypotheses confirm (H1, H2, H3), all 5 entry thresholds × 3 universes × multiple min_hold values |
| Always-in BTC+ETH is robust choice | **High** | Simple design, no parameter to over-fit, $1 686 OOS on 13.5 months |
| Always-in BTC+ETH will produce expected $300-450/month live | **Medium** | Backtest is delta-neutre model; live friction may exceed 20 bps assumption; regime change risk over 365 days |
| 5-gate promotion framework is calibrated | **Medium** | Pattern 7 binary criteria fixed before observation; tolerance bands +20 % seem reasonable but untested |
| 7 safeguards are implementable in ~15 lines + Telegram bot extension | **Medium** | Kill switch + position cap = trivial; 2nd watchdog requires infra decision; manual override Telegram requires polling/webhook setup |

### 6.2 Risks acknowledged

- 365-day funding rate regime may differ from 2024-2026 backtest training/OOS periods
- Hyperliquid perp+spot basis may compress (reduces funding rate available)
- Major macro event (FOMC, regulatory) could trigger unprecedented funding flips
- Mac → VPS migration introduces operational risk in addition to strategy risk

---

## 7. Phase 3 plan synthesis

### 7.1 Spec deliverables (status)

| Doc | v1 status | v2 revision needed |
|---|---|---|
| `production/phase3_deployment_spec.md` | ✓ written (10 sections, 234 lines) | YES — incorporate $1000 sizing, BTC+ETH only universe, 7 safeguards detailed spec |
| `production/phase3_rollback_protocol.md` | ✓ written (9 sections, 302 lines) | YES — confirm 5-gate framework references, add daily reconciliation source orthogonality |
| `production/phase3_success_criteria.md` | ✓ written (11 sections, 188 lines) | YES — change to 365-day timeline, integrate 5-gate strict thresholds, daily Telegram format |

### 7.2 Sequencing (per Sebastien)

```
Phase 2 closure (this digest) ✓
    ↓
Phase 3 spec docs v2 revision (Étape C in progress) ⏳
    ↓
Sebastien validates spec docs v2
    ↓
Sandbox test (rollback procedure + safeguards) — mandatory
    ↓
Code change application on branch production/phase3-... (~15 lines)
    ↓
Tests pytest + alpha_lab gates
    ↓
Sebastien explicit GO for merge to main
    ↓
VPS deployment cutover (atomic <5 min, hors funding hours)
    ↓
Day 0 → Day 365 observation marathon
    ↓
Day 365: 5-gate evaluation → Phase 4 promotion decision (real capital) or extension/abort
```

### 7.3 Coordination across projects

Per Operator Methodology Section V (Cross-Project Application Table) :
- Synapse main project: independent, parallel observation
- Synapse BTC: independent
- Trading Bot V2 (this project): Phase 3 paper marathon engaged
- Frozen projects: unaffected

---

## 8. Open questions / pending operator decisions

1. **GitHub URL for remote push** — Sebastien to provide
2. **Sandbox unlock for git commit Phase 2 archive** — Sebastien to `rm -f .git/index.lock` on Mac (30 sec)
3. **2nd watchdog infra choice** — same VPS different process, or different infra (Storage Box cron, other VPS) ?
4. **Daily reconciliation Telegram message format** — confirm or adjust V2's proposed format
5. **Manual override `/v2_flat YES` syntax** — confirm Telegram command or change

---

## 9. Memorable phrase

> *"P33 a fait son travail : H1 a passé tous les gates sauf le seul qui compte (beat trivial benchmark). Si j'avais bypassé H1 per ma proposition post-H4, ce finding serait resté caché."* — V2 self-reflection, H1 deliverable
>
> *"Ce sera un marathon mais ça vaut le coup. On ne doit pas perdre l'intensité que l'on met dessus."* — Sebastien Assohou, transition Phase 2 → Phase 3

---

## 10. Artefacts inventory

| Type | Count | Location |
|---|---:|---|
| Forensic deliverables | 8 | `analysis/loss_forensic_*.md` |
| Result caches JSON | 5 | `analysis/_*.json` |
| Phase 3 spec docs v1 | 3 | `production/phase3_*.md` |
| Snapshots P31 | 21 | `snapshots/SNAPSHOT_*` |
| Branches conceptuelles | 9 | `analysis/loss-forensic-*` + `production/phase3-...` + `audit/lookahead-fix` (all @ 232b883) |
| Weekly reports | 1 | `weekly_reports/weekly_report_2026-06-22.md` |
| Backup folder | 1 | `live/state.pre_vps_cutover_backup_25juin_mac_dead/` |
| **Total artifacts** | **48** | all under `~/Desktop/trading-bot-v2/` |

---

## 11. Closing

**Phase 2 Loss Forensic Analysis — COMPLETE.**

8 hypothèses testées sous P33 No-Skip discipline. Filter design family empirically closed. Pivot vers BTC+ETH always-in pure delta-neutre validated by Sebastien. Phase 3 = 365-day paper marathon avec 5-gate promotion framework + 7 mandatory safeguards.

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT throughout Phase 2**. All work archived in working tree pending git commit + GitHub push (operator action required).

**Phrase that closes** :
> *Sur 8 hypothèses testées, le filter funding capture est empiriquement dominé sur toutes ses variantes par le baseline trivial always-in. Le H6 circuit-breaker, seul à dépasser le benchmark, est fragile (1/4 axes robustness). Le design Phase 3 retenu = BTC+ETH always-in pure delta-neutre, marathon 365 jours, 5-gate framework strict, 7 safeguards mandatory. Production main 232b883 INTACT throughout. P33 paid its way — H1 forcé révèle le finding stratégique principal.*

---

*Session digest generated by V2 agent on 2026-06-27 by aggregating all Phase 2 deliverables and operator decisions. Snapshot baseline `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup`. Production code untouched. Append-only.*
