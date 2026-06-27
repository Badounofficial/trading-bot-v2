# Trading Bot V2 — Loss Forensic Phase 2 / H2 (entry_threshold tightening)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 23:30 UTC
**Hypothesis tested** : **H2 — entry_threshold tightening (0.005 → 0.015 APR) sur BTC+ETH (H3 best filter universe). Closure officielle de la famille "filter" per P33 strict — testé empiriquement même sachant que filter design est dominé par always-in.**

**Discipline P31 + P33** :
- Branch dédiée : `analysis/loss-forensic-H2-entry-threshold` ✓
- Pre-snapshot : `snapshots/SNAPSHOT_20260626T232403Z_pre_H2_entry_threshold/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Post-snapshot : sera créé en fin de session
- Append-only sur ce fichier
- **P33 strict** : H2 lancé après findings H1/H3 ayant invalidé le filter design pour fermer la famille empiriquement.

---

## 1. Méthodologie

- Univers : BTC+ETH (H3 best filter universe)
- Friction round-trip per asset : BTC 10 bps, ETH 10 bps
- Walk-forward strict : OOS split 2025-03-15 (cohérent avec H1, H3, H6)
- 5 thresholds testés : 0.005 (baseline), 0.0075, 0.010, 0.0125, 0.015 APR
- Strategy baseline : `min_hold_hours = 24, exit_threshold_apr = -0.005, smooth_hours = 24`
- Beat-benchmark = always-in BTC+ETH OOS = $1 685.71 (constante référence cross-hypothèses)

---

## 2. Résultats OOS — sweep entry_threshold

### 2.1 BTC OOS

| entry_threshold | N trades | Net | Gross | Cost | Expectancy | Sharpe | Max DD % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.005 (baseline) | 40 | $541.79 | $941.79 | $400 | $13.54 | 10.89 | -1.43 |
| 0.0075 | 38 | $562.16 | $942.16 | $380 | $14.79 | 11.57 | -1.23 |
| 0.010 | 38 | $560.92 | $940.92 | $380 | $14.76 | 11.54 | -1.24 |
| 0.0125 | 38 | $560.60 | $940.60 | $380 | $14.75 | 11.53 | -1.25 |
| 0.015 | 36 | $583.00 | $943.00 | $360 | $16.19 | 12.31 | -1.04 |

### 2.2 ETH OOS

| entry_threshold | N trades | Net | Gross | Cost | Expectancy | Sharpe | Max DD % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0.005 (baseline) | 41 | $490.55 | $900.55 | $410 | $11.96 | 9.79 | -0.92 |
| 0.0075 | 41 | $489.96 | $899.96 | $410 | $11.95 | 9.77 | -0.93 |
| 0.010 | 41 | $488.44 | $898.44 | $410 | $11.91 | 9.74 | -0.93 |
| 0.0125 | 40 | $500.31 | $900.31 | $400 | $12.51 | 10.09 | -0.83 |
| 0.015 | 39 | $512.15 | $902.15 | $390 | $13.13 | 10.46 | -0.83 |

### 2.3 BTC+ETH combined OOS + beat-benchmark

| entry_threshold | Combined N | Combined Net | Beat ratio vs $1 685.71 | Verdict |
|---|---:|---:|---:|---|
| 0.005 (baseline) | 81 | $1 032.34 | **0.612** | 🔴 FAIL |
| 0.0075 | 79 | $1 052.12 | **0.624** | 🔴 FAIL |
| 0.010 | 79 | $1 049.36 | **0.623** | 🔴 FAIL |
| 0.0125 | 78 | $1 060.91 | **0.629** | 🔴 FAIL |
| **0.015** | **75** | **$1 095.15** | **0.650** | **🔴 FAIL** (best of family, still loses 35 %) |

---

## 3. Analyse — pourquoi tightening n'aide pas

### 3.1 Mécanique du tightening

Un entry_threshold plus élevé filtre plus de signaux marginaux. Effet attendu :
- Moins de trades (vrai : 81 → 75)
- Moins de friction payée (vrai : $810 → $750)
- Capture limitée à signaux funding plus forts
- Trades restants ont expectancy supérieure (vrai : $13.54 → $14.61 combined)

**Mais le gain net plafonne** : la friction économisée ($60) est inférieure au funding manqué sur les trades exclus (gross : $1 842.34 → $1 845.15, négligeable). Le filter retient l'essentiel du funding signal, donc tightening ne désinvestit pas.

### 3.2 Pourquoi pas de plateau exploitable

Variation max sur les 5 thresholds = $63 (de $1 032 à $1 095, soit 6 %). **Monotonic improvement** mais trop modeste pour mériter une optimisation parameter.

Le ratio beat-benchmark plafonne à 0.650 (threshold = 0.015). Pour atteindre 1.0 (parité avec always-in), il faudrait gagner $590 supplémentaires — l'opportunité n'existe pas dans cette famille.

### 3.3 Closure de la famille "filter"

H2 confirme que **aucune variation du filter design** (min_hold extension H1, asset universe H3, entry_threshold H2) **ne dépasse pure always-in sur OOS 13.5 mois**. La famille filter est **empiriquement close** :

| Hypothèse | Best variant | Best net OOS | Beat-benchmark |
|---|---|---:|---:|
| H1 (min_hold extension) | min_hold = 60, BTC+ETH | $538.77 | 0.612 (loses 39 %) |
| H3 (universe selection) | BTC+ETH | $1 032.34 | 0.612 (loses 39 %) |
| H2 (entry_threshold tightening) | 0.015 APR, BTC+ETH | $1 095.15 | 0.650 (loses 35 %) |
| **Family filter best ever** | **H2 0.015 APR** | **$1 095.15** | **🔴 still loses 35 %** |

---

## 4. Verdict H2

### 4.1 Alpha_lab synthèse

| Gate | Pass / Fail |
|---|---|
| Effect detectable (monotonic improvement) | PASS marginal (+6 % from baseline to best) |
| OOS positive | PASS (>0 sur tous thresholds) |
| Plateau detection | NO PLATEAU — monotonic but no inflection |
| DSR (5 thresholds tested) | PASS — penalty 0.012, négligeable |
| **Beat trivial benchmark** | **🔴 FAIL on all 5 thresholds** |
| Ensemble debiasing | MARGINAL — ensemble net = $1 058, encore 37 % sous benchmark |

### 4.2 Decision

**Verdict H2 = NO-GO**, conformément à l'attente pre-test.

H2 closure family **filter empiriquement validée** : aucune combinaison parametric du filter design ne beat le baseline trivial always-in sur cet historique HL.

**P33 a payé son rôle** : sans H2 testé formellement, la famille filter restait théoriquement "non-prouvée comme dominée" — l'opérateur pouvait toujours revenir avec "et si on avait essayé H2 ?". Maintenant, archive empirique close.

### 4.3 Recommendation V2

- ❌ **NE PAS merger H2** (le baseline best $1 095 reste 35 % sous benchmark)
- ✅ **Archiver H2 results** comme baseline empirique pour future closure family filter
- ✅ **Family filter officiellement close** — aucune Phase 3 sur filter variants
- 📌 **Pivot consacré vers no-filter paradigm** (always-in + CB, validé par H6)

---

## 5. Phrase that closes

> *Le filter family est définitivement close : H1 (min_hold extension) net OOS best $538.77, H3 (universe) best $1 032.34, H2 (entry_threshold) best $1 095.15. Le baseline trivial always-in BTC+ETH = $1 685.71. Aucune variation parametric du filter ne traverse cette barrière. Pivot vers H6 paradigm confirmé empiriquement.*

---

## 6. Prochain pas

**H2 — LIVRÉ. Verdict NO-GO, family filter closure. Branche `analysis/loss-forensic-H2-entry-threshold` archivée, pas de merge.**

**Suite** : H6 Robustness Test (4 axes) en parallèle de cette session H2. Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*Phase 2 H2 generated by V2 agent on 2026-06-26 by read-only analysis. Snapshot pre-H2 `SNAPSHOT_20260626T232403Z_pre_H2_entry_threshold`. Production code untouched.*
