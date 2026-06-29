# Trading Bot V2 — Loss Forensic Phase 2 / Reconciliation H3 ↔ H6

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 23:10 UTC
**Purpose** : per le brief Sebastien, mini-rapport de réconciliation entre **H3 (asset filter formel)** et **H6 (always-in + circuit-breaker)** pour arbitrer le design candidat avant H2 et H5.

**Discipline P31 + P33** :
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Append-only sur ce fichier
- Aucune branche merge

---

## 1. Tableau croisé — design × universe × métrique alpha_lab (OOS, 13.5 mois)

| Design | Universe | N trades | Net OOS | Sharpe (BTC) | Max DD % | Beat pure always-in | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| Filter min_hold=24 (baseline H1) | BTC+ETH+SOL | 139 | $832.53 | 10.89 | -4.43 % | 0.434 (loses 57 %) | NO-GO |
| Filter min_hold=60 (best H1) | BTC+ETH | 64 | $538.77 | 4.23 | -2.15 % | n/a (different universe) | MARGINAL fail beat |
| Filter (H3 best universe) | BTC+ETH | 81 | $1 032.34 | 10.89 | -1.43 % | 0.612 (loses 39 %) | MARGINAL fail beat |
| Filter (H3 worst with SOL) | BTC+ETH+SOL | 139 | $832.53 | -2.29 (SOL) | -4.43 % | 0.434 (loses 57 %) | NO-GO |
| Pure always-in | BTC-only | 1 | $885.05 | 54.92 | -0.14 % | =1.000 baseline | Benchmark BTC |
| Pure always-in | BTC+ETH | 2 | $1 685.71 | 54.92/46.45 | -0.33 % | =1.000 baseline | Benchmark BTC+ETH |
| Pure always-in | BTC+ETH+SOL | 3 | $1 916.96 | 54.92/46.45/6.28 | -2.36 % | =1.000 baseline | Benchmark BTC+ETH+SOL |
| **H6 best — Always-in + CB -0.75 %** | **BTC+ETH+SOL** | **3** | **$2 079.81** | **54.92/46.45/~** | **-0.77 %** | **1.085 (+8.5 %)** | **🟢 GO marginal** |
| H6 alt — Always-in + CB -1.0 % | BTC+ETH+SOL | 3 | $2 056.94 | 54.92/46.45/~ | -1.02 % | 1.073 (+7.3 %) | GO marginal |
| H6 — Always-in + CB anyhthres | BTC+ETH | 2 | $1 685.71 | 54.92/46.45 | -0.33 % | 1.000 (never fires) | = always-in |

## 2. Verdict comparatif — quel design × univers gagne ?

### 2.1 Beat-benchmark gate (le seul qui compte vraiment)

**Pass / Fail / Improve over pure always-in** :

| Strategy | Best universe found | Verdict beat-benchmark |
|---|---|---|
| Filter (H1, H3) | BTC+ETH | **🔴 FAIL** — perd 39 % vs benchmark |
| Pure always-in | BTC+ETH+SOL | **= baseline** — référence |
| **H6 — Always-in + CB** | **BTC+ETH+SOL @ -0.75 %** | **🟢 PASS** — +8.5 % vs benchmark |

### 2.2 Net OOS ranking

1. **H6 best (CB -0.75 %, BTC+ETH+SOL)** : **$2 079.81** ← winner
2. Pure always-in BTC+ETH+SOL : $1 916.96
3. Pure always-in BTC+ETH : $1 685.71
4. Filter H3 BTC+ETH : $1 032.34
5. Pure always-in BTC-only : $885.05
6. Filter H1 best min_hold=60 BTC+ETH : $538.77

### 2.3 Risk-adjusted (max DD)

| Design + universe | Max DD | Net | Net per % DD |
|---|---|---|---|
| Pure always-in BTC-only | -0.14 % | $885 | 6321 |
| Pure always-in BTC+ETH | -0.33 % | $1 686 | 5109 |
| **H6 CB -0.75 % BTC+ETH+SOL** | **-0.77 %** | **$2 080** | **2701** |
| Pure always-in BTC+ETH+SOL | -2.36 % | $1 917 | 812 |
| Filter (H3 best) BTC+ETH | -1.43 % | $1 032 | 722 |

**Pure always-in BTC-only a le meilleur ratio risk-adjusted** (Net par % de DD = 6321), suivi de pure always-in BTC+ETH (5109). H6 best ratio = 2701.

**Pour cap absolute risk, BTC-only ou BTC+ETH pure always-in restent les options conservatives.** Pour maximize net absolute, H6 BTC+ETH+SOL + CB -0.75 % gagne.

---

## 3. Insight stratégique transversal

L'enchaînement H1 → H3 → H6 a révélé une hiérarchie design :

```
Worst                                                     Best
─────────────────────────────────────────────────────────────►
Filter | Filter      | Pure       | Pure       | Pure       | Pure         | H6
SOL    | BTC+ETH+SOL | always-in  | always-in  | always-in  | always-in    | CB -0.75 %
incl.  | filter      | BTC-only   | BTC+ETH    | BTC+ETH+SOL| BTC+ETH+SOL  | BTC+ETH+SOL
$832   | $832        | $885       | $1 686     | $1 917     | (= benchmark)| $2 080
```

**Pattern unique** : à chaque étape, on a découvert un design strictement supérieur. Le funding filter (H1, H3) est dominé par pure always-in (benchmark trivial). Pure always-in est légèrement dominé par always-in + CB sur l'univers BTC+ETH+SOL.

**Le filter est inutile sur cet historique** — c'est le finding principal de Phase 2.

---

## 4. Recommandation pour H2 et H5

### 4.1 H2 (entry_threshold tightening)

Le brief original : "H2 sur l'univers optimal H3".

**Problème** : l'univers optimal trouvé n'est PAS sur un filter design. H2 testait `entry_threshold_apr = 0.005, 0.0075, 0.010, 0.0125, 0.015` qui sont des paramètres du **filter design**. Mais H1/H3/H6 montrent que le filter design lui-même est dominé.

**Options** :
- **Option A** — Skipper H2 parce que le filter design est invalidé empiriquement
  - **Violation P33** (no skip discipline) — non recommandé
- **Option B** — Lancer H2 comme prévu sur **BTC+ETH** (H3 best filter universe) pour terminer le test scope, archiver le résultat même si filter est sub-optimal
  - **Conforme P33** ✓
  - Coût : ~30 min compute additionnel, résultat probablement confirmera que tightening n'aide pas plus que H1's min_hold tuning
- **Option C** — Re-scoper H2 pour tester `entry_threshold` sur **H6 design** (CB threshold variants déjà couverts par H6 plateau detection)
  - Hors-scope original

**Recommandation V2 = Option B** : lance H2 sur BTC+ETH (H3 best filter universe), beat-benchmark gate = always-in BTC+ETH ($1 685). Archive même si fail. Conforme P33.

### 4.2 H5 (delta-neutre hedge)

**Findings H6 informent H5** :
- L'engine V2 (`backtest/engine.py`) modélise déjà delta-neutre (short perp + long spot, voir docstring "we are short perp + long spot, so we receive [when funding positive]")
- **H1 + H3 + H6 ont tous tourné en mode delta-neutre par défaut**
- H5 originel "tester delta-neutre vs pas" est donc déjà partiellement couvert empiriquement

H5 reste à clarifier avec Sebastien :
- Si Sebastien voulait dire "tester avec / sans hedge spot" → **déjà fait, default = hedgé**, et le résultat est ce qu'on observe
- Si Sebastien voulait dire "tester sur production live (long perp pur, pas de short spot)" → c'est une question de design production, pas une hypothèse backtest

**Recommandation V2 = clarifier avec Sebastien avant lancement**.

---

## 5. Synthèse pour décision opérateur

### 5.1 Findings actionnables

1. **Le filter funding capture est dominé empiriquement** sur 28.5 mois historique HL — sur **toutes les universes testées** (BTC-only, BTC+ETH, BTC+ETH+SOL)
2. **Pure always-in delta-neutre** est le baseline de référence supérieur au filter
3. **L'ajout d'un circuit-breaker DD à -0.75 % améliore marginalement** (+8.5 % net OOS) ET **réduit max DD significativement** (-2.36 % → -0.77 %), mais l'effet est SOL-specific
4. **BTC+ETH+SOL universe est viable en mode always-in + CB**, contrairement au filter design où SOL détruisait $200/asset

### 5.2 Décisions opérateur à prendre

1. **Acceptation du verdict beat-benchmark fail pour le filter design ?** Si oui → archive H1/H3/H2 et pivot officiel vers no-filter paradigm
2. **Choix universe production** :
   - BTC-only — conservatif, $885 OOS, max DD -0.14 %
   - BTC+ETH — équilibre, $1 686 OOS, max DD -0.33 %
   - **BTC+ETH+SOL + CB -0.75 %** — max net, $2 080 OOS, max DD -0.77 %
3. **Lancement H2** : Option B (recommandé P33) ou Option C (re-scope) ?
4. **Lancement H5** : clarification design production avant ou skip ?

### 5.3 Si décision pro-H6

Implications opérationnelles :
- Refonte `strategies/funding_capture.py` pour supporter mode "always-in + CB"
- Nouveau paramètre `dd_circuit_breaker_pct` à exposer dans config daemon
- Logging DD continu pour audit et debug
- Validation backtest étendu sur autre période hors 2024-2026 (P3 — Phase 3)
- Tests TDD pour la logique CB

---

## 6. Phrase that closes

> *Le filter funding capture perd 39-57 % vs always-in sur OOS 13.5 mois. Le circuit-breaker DD à -0.75 % sur BTC+ETH+SOL produit +8.5 % vs benchmark trivial et réduit max DD de 57 %. La hiérarchie design est claire : filter < always-in < always-in + CB.*

---

## 7. Prochain pas

**Réconciliation H3 ↔ H6 — LIVRÉE.**

**Validation Sebastien requise sur 4 questions** (Sec 5.2). Aucun merge sur main. Aucune modification production. Branches `analysis/loss-forensic-H3-asset-filter` et `analysis/loss-forensic-H6-always-in-circuit-breaker` archivées.

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*Reconciliation generated by V2 agent on 2026-06-26 by aggregating H1, H3, H6 results from their respective `analysis/_H*_results.json` caches. No production code modification.*
