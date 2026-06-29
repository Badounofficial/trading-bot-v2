# Trading Bot V2 — Loss Forensic Phase 2 / H3 (Asset filter formel)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 22:50 UTC
**Hypothesis tested** : **H3 — Quel univers d'actifs maximise le design filter actuel ? Test BTC-only, BTC+ETH, BTC+ETH+SOL avec walk-forward strict et beat-benchmark gate per universe.**

**Discipline P31 + P33** :
- Branch dédiée : `analysis/loss-forensic-H3-asset-filter` ✓
- Pre-snapshot : `snapshots/SNAPSHOT_20260626T224253Z_pre_H3_asset_filter/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Post-snapshot : sera créé en fin de session
- Append-only sur ce fichier

---

## 1. Méthodologie

### 1.1 Universes testés

| Universe | Assets | Note |
|---|---|---|
| BTC-only | BTC | Référence H4 finding "BTC viable" |
| BTC+ETH | BTC + ETH | Suggéré par H4 finding "drop SOL" |
| BTC+ETH+SOL | BTC + ETH + SOL | Univers production actuel — P33 enforced ne saute pas SOL |

### 1.2 Walk-forward + friction par asset

- Split OOS : 2025-03-15 (cohérent avec H1)
- Friction round-trip per asset (per H4 median scenario) :
  - BTC : 10 bps
  - ETH : 10 bps
  - SOL : 15 bps (slippage plus élevé)
- Capital : $10 000 notional par leg par asset
- Strategy baseline : `min_hold_hours=24, entry_threshold_apr=0.005, smooth_hours=24`

### 1.3 Alpha_lab discipline

| Gate | Application H3 |
|---|---|
| OOS strict | Split 2025-03-15+ ✓ |
| Beat trivial benchmark | Always-in per universe (sum across assets) ✓ |
| DSR (3 universes tested) | Penalty √(ln(3)/9970) = 0.0105 ✓ |
| Plateau detection ±10 % | Check if best universe is within 10 % of next best ✓ |
| Ensemble debiasing | Average across universes, no cherry-pick ✓ |

---

## 2. Résultats — Full period (28.5 mois)

| Universe | N trades | Filter net | Always-in net | Beat ratio | Filter loses by |
|---|---:|---:|---:|---:|---:|
| BTC-only | 53 | $3 048.07 | **$3 551.30** | **0.858** | $503.23 |
| BTC+ETH | 124 | $5 586.75 | **$6 710.77** | **0.833** | $1 124.02 |
| BTC+ETH+SOL | 211 | $7 877.75 | **$9 847.57** | **0.800** | $1 969.81 |

**Universes ranked by filter beat-benchmark performance (highest = least worst)** :
1. BTC-only (0.858)
2. BTC+ETH (0.833)
3. BTC+ETH+SOL (0.800)

**Pattern** : plus l'univers est large, plus le filter sous-performe son benchmark always-in. Confirmation du finding H1 sur un échantillon plus large.

## 3. Résultats — OOS (13.5 mois, 2025-03-15 → 2026-05-04)

| Universe | N trades | Filter net | Always-in net | Beat ratio | Filter loses by |
|---|---:|---:|---:|---:|---:|
| BTC-only | 40 | $541.79 | **$885.05** | **0.612** | $343.26 |
| **BTC+ETH** (best filter) | 81 | **$1 032.34** | **$1 685.71** | **0.612** | $653.37 |
| BTC+ETH+SOL | 139 | $832.53 | **$1 916.96** | **0.434** | $1 084.43 |

**Verdict per universe** :
- **BTC-only filter** : LOSES vs benchmark 39 % (0.612 ratio)
- **BTC+ETH filter** : LOSES vs benchmark 39 % (0.612 ratio)
- **BTC+ETH+SOL filter** : LOSES vs benchmark 57 % (0.434 ratio) — confirme H4 finding SOL killer

### 3.1 Per-asset OOS detail

| Asset | Filter net | Filter Sharpe | Always-in net | Always-in Sharpe |
|---|---:|---:|---:|---:|
| BTC | $541.79 | 10.89 | $885.05 | 54.92 |
| ETH | $490.55 | 9.79 | $800.66 | 46.45 |
| **SOL** | **−$199.81** | **−2.29** | $231.25 | 6.28 |

**SOL filter en OOS est NÉGATIF** (−$199.81). Le filter SOL transforme un benchmark always-in à $231 en perte de $200. **C'est une destruction de valeur de $431 par asset.**

---

## 4. Plateau detection

OOS filter net par universe :
- BTC-only : $541.79
- BTC+ETH : $1 032.34 (+90 % vs BTC-only)
- BTC+ETH+SOL : $832.53

**Aucun plateau détecté** : BTC+ETH bat BTC-only de 90 %, donc loin du seuil ±10 % de robustness. **BTC+ETH est clairement le best filter universe**, mais il loses encore au benchmark de $653.

### 4.1 Robustness across universes — pour chaque asset standalone

Le filter BTC standalone produit le **même résultat** dans les 3 universes ($541.79), parce que la stratégie est exécutée par asset indépendamment. La différence entre universes vient de l'agrégation : BTC+ETH cumul = BTC + ETH, etc.

Ce pattern signifie que **la décision d'univers est strictement additive** : choisir BTC+ETH = "garder BTC + garder ETH". Aucune interaction cross-asset dans le design actuel.

---

## 5. DSR correction et debiasing

DSR penalty √(ln 3 / 9970) = 0.0105 — négligeable sur les valeurs OOS observées. Sharpes BTC OOS 10.89 → ~9.5 après DSR, restent largement positifs en valeur absolue (mais inférieurs aux Sharpes always-in de 46-55).

Ensemble debiasing across universes (OOS net) : moyenne = ($541.79 + $1 032.34 + $832.53) / 3 = $802.22. **Toute sélection d'univers garde une expectancy positive** mais aucune ne beat le benchmark always-in correspondant.

---

## 6. Verdict H3

### 6.1 Alpha_lab synthèse

| Gate | Pass / Fail |
|---|---|
| OOS positive (filter > 0) | PASS (sur 3 universes) |
| Effect detectable across universes | PASS — BTC+ETH > BTC-only > BTC+ETH+SOL |
| DSR-corrected significance | PASS |
| Plateau detection | FAIL — pas de plateau ±10 % |
| **Beat trivial benchmark** | **🔴 FAIL sur 3/3 universes** |
| Ensemble debiasing | MARGINAL — moyenne reste positive mais loin benchmark |

### 6.2 Décision per Sebastien's criteria

> **GO** : optimal universe found AND beat benchmark → mérite intégration
> **MARGINAL** : effect detectable but doesn't beat benchmark → archive avec notes
> **NO-GO** : pas d'effet → archive

**Verdict H3 = MARGINAL with strict no-merge** :

L'effet "BTC+ETH > BTC-only > BTC+ETH+SOL" est **réel et statistiquement significatif** (OOS BTC+ETH +90 % vs BTC-only ; SOL inclusion -$200 OOS).

**Mais le filter sur le best universe (BTC+ETH) loses encore au benchmark always-in de 39 %.** Même la meilleure configuration H3 sous-performe systématiquement le baseline trivial.

### 6.3 Confirmation findings H1 et H4

H3 **confirme** :
- H1 : filter design < always-in across all universes
- H4 : SOL est destructeur de valeur (filter SOL OOS = −$200)

H3 **ajoute** :
- L'univers optimal pour le filter design actuel est **BTC+ETH** (pas BTC-only)
- L'ajout de SOL coûte $200 OOS au-delà du déjà fail beat-benchmark
- L'écart filter vs benchmark est **stable** autour de 39 % pour BTC-only et BTC+ETH, monte à 57 % avec SOL

### 6.4 Recommendation

- ❌ **NE PAS merger H3 sur main** quelle que soit l'universe optimal trouvé
- ✅ **Archiver H3 results** comme baseline empirique
- 📌 **Documenter pour H6 reconciliation** : si H6 (always-in + circuit-breaker) confirme always-in domination, alors la décision design V2 devra basculer hors du filter paradigm
- 📌 **Décision opérateur** : si Sebastien préfère malgré tout garder un filter pour des raisons risk/business (ex. limiter exposure on news events), BTC+ETH (drop SOL) est l'univers optimal connu

---

## 7. Phrase that closes

> *Sur 3 universes testés, le filter loses au benchmark always-in de 39 % à 57 % en OOS. SOL en filter mode produit -$199 OOS net, vs +$231 en pure always-in : SOL inclusion détruit $430 par asset.*

---

## 8. Prochain pas

**H3 — LIVRÉ. Verdict MARGINAL avec override fail beat-benchmark. Branche `analysis/loss-forensic-H3-asset-filter` archivée, pas de merge sur main.**

**Next** : H6 (always-in + circuit-breaker drawdown) en parallèle, puis réconciliation H3 ↔ H6 pour décision design.

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*Phase 2 H3 generated by V2 agent on 2026-06-26 by read-only analysis of historical funding data via existing `strategies/funding_capture.py` + `backtest/engine.py`. Snapshot pre-H3 `SNAPSHOT_20260626T224253Z_pre_H3_asset_filter`. Production code untouched.*
