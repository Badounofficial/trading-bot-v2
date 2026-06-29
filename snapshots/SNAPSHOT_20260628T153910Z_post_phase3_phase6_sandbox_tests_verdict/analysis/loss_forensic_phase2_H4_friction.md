# Trading Bot V2 — Loss Forensic Phase 2 / H4 (Friction Realistic)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 16:55 UTC
**Hypothesis tested** : **H4 — Re-simulate the live paper sample (14 closed trades, 21 mai → 26 juin 2026) with realistic Hyperliquid friction applied. Determine whether the strategy is economically viable in production.**

**Discipline** :
- Branch dédiée : `analysis/loss-forensic-H4-friction-realistic` ✓
- Pre-snapshot : `snapshots/SNAPSHOT_20260626T165329Z_pre_H4_friction_realistic/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Post-snapshot : sera créé en fin de session H4
- Append-only sur ce fichier

**Note méthodologique** : H4 est une analyse rétrospective sur le sample paper existant (N=14), pas un nouveau backtest. Sample size insuffisant pour des intervalles de confiance serrés au sens alpha_lab strict. Le verdict est qualifié explicitement par cette limite ; H1 et H3 (Phase 2 ultérieures) appelleront le backtest 6+ mois multi-régime + alpha_lab 10-gate pour validation rigoureuse.

---

## 1. Friction model utilisé

### 1.1 Hyperliquid taker fees (perpetuals, public schedule)

| Item | Valeur | Source |
|---|---|---|
| Taker fee per side | **3.5 bps** (0.035 %) | HL fee schedule publique |
| Round-trip taker (open + close) | **7 bps** | 2 × 3.5 bps |
| Notional par position V2 | $10 000 | `live/paper_funding_capture.py` config |
| Fee absolu round-trip | **$7** par trade fermé | 7 bps × $10 000 |

### 1.2 Slippage modeling — différencié par asset

Basé sur crypto perp microstructure (orderbook depth, taker market impact) :

| Asset | Slippage par side | Round-trip | Justification |
|---|---|---|---|
| BTC | 1-2 bps | 2-4 bps | Asset le plus profond (>$100M orderbook) |
| ETH | 1-2 bps | 2-4 bps | Second plus profond |
| SOL | 3-5 bps | 6-10 bps | Mid-cap, depth significativement inférieure aux majors |

### 1.3 Total friction par trade

| Scenario | BTC | ETH | SOL | Comment |
|---|---:|---:|---:|---|
| **Optimistic** | $9 (7+2 bps) | $9 (7+2 bps) | $13 (7+6 bps) | Best-case slippage, taker only |
| **Median** | $10 (7+3 bps) | $10 (7+3 bps) | $15 (7+8 bps) | Realistic average HL execution |
| **Conservative** | $11 (7+4 bps) | $11 (7+4 bps) | $17 (7+10 bps) | Worst-case slippage normal (hors stress events) |

### 1.4 Cross-asset uniform (per user canonical brief)

| Scenario | Friction / trade |
|---|---:|
| Optimistic | $11 |
| Median | $15 |
| Conservative | $19 |

Le rapport présente les **deux modélisations** (uniform et per-asset) pour transparence ; le verdict s'appuie sur la per-asset comme plus rigoureuse.

---

## 2. Résultats — 14 trades fermés, full universe (BTC + ETH + SOL)

### 2.1 Baseline (Phase 1, sans friction)

| Métrique | Valeur |
|---|---|
| N trades | 14 |
| Wins | 10 (71.4 %) |
| Losses | 4 (28.6 %) |
| Total PnL | **+$127.32** |
| Expectancy / trade | **+$9.09** |
| Profit factor | 102.31 |
| Avg win | +$12.86 |
| Avg loss | −$0.31 |
| Max DD | $0.86 |

### 2.2 Friction uniforme (3 scenarios)

| Scenario | Friction | Total PnL | Expectancy / trade | WR | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Optimistic | $11 | **−$26.68** | **−$1.91** | 21.4 % | 0.71 | $58.82 |
| Median | $15 | **−$82.68** | **−$5.91** | 21.4 % | 0.39 | $98.82 |
| Conservative | $19 | **−$138.68** | **−$9.91** | 21.4 % | 0.23 | $142.76 |

Le passage de 10 wins → 3 wins / 4 losses → 11 losses confirme l'inversion catastrophique du WR de 71.4 % à 21.4 % : 7 trades qui étaient marginalement positifs en paper (winners avec funding accrued ≤ $15) basculent en losers nets après friction.

### 2.3 Friction per-asset (3 scenarios)

| Scenario | BTC fees ($) | ETH fees ($) | SOL fees ($) | Total PnL | Expectancy | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Optimistic | 27 (3×9) | 45 (5×9) | 78 (6×13) | **−$22.68** | **−$1.62** | 0.76 | $58.82 |
| Median | 30 (3×10) | 50 (5×10) | 90 (6×15) | **−$42.68** | **−$3.05** | 0.62 | $73.82 |
| Conservative | 33 (3×11) | 55 (5×11) | 102 (6×17) | **−$62.68** | **−$4.48** | 0.51 | $88.82 |

### 2.4 Critère de viabilité (per brief Sebastien)

| Bande | Expectancy net | Décision |
|---|---|---|
| **GO** | > +$5 / trade | Continue à H1, H3 |
| **MARGINAL** | $0 à +$5 / trade | Option A/B opérateur |
| **NO-GO** | ≤ $0 / trade | Pause V2, revoir design |

**Tous les scenarios full universe = NO-GO.** Le moins pessimiste (per-asset optimistic) donne −$1.62/trade — encore largement négatif.

---

## 3. Résultats — analyse per-asset standalone (median friction)

Critique pour comprendre QUEL asset est responsable de l'inversion catastrophique.

| Asset | N | Gross PnL (paper) | Fees (median) | Net PnL | Expectancy / trade | PF | Décision standalone |
|---|:-:|---:|---:|---:|---:|---:|---|
| **BTC** | 3 | +$49.01 | $30 | **+$19.01** | **+$6.34** | 2.29 | **GO** (au-dessus de $5 seuil) |
| **ETH** | 5 | +$54.66 | $50 | **+$4.66** | **+$0.93** | 1.15 | MARGINAL (seuil $0–$5) |
| **SOL** | 6 | +$23.65 | $90 | **−$66.35** | **−$11.06** | 0.00 | **STRONG NO-GO** (catastrophique) |

### 3.1 Lecture critique

**SOL est le killer du strategy.** Le gross PnL paper de +$23.65 sur 6 trades (≈ +$3.94/trade) est largement insuffisant pour couvrir les $15 de friction/trade. SOL accumule un net de **−$66.35**, ce qui à lui seul transforme l'expectancy positive du portfolio en négative.

**BTC est rentable même avec friction.** Expectancy net +$6.34/trade (au-dessus du seuil GO de $5), profit factor 2.29 (acceptable). Hold time médian de 209h (= ~9 jours) permet d'accumuler suffisamment de funding pour amortir les fees.

**ETH est dans la bande MARGINAL.** Expectancy +$0.93/trade, profit factor 1.15 — fragile, sensible à toute hausse de slippage ou à un sample plus large incluant des trades moins favorables.

### 3.2 Implication directe pour H3 (asset filter)

Cette finding **valide quantitativement l'hypothèse H3** avant même son test formel :
- Univers réduit à **BTC-only** → expectancy ~+$6/trade, GO clair
- Univers réduit à **BTC + ETH** → expectancy moyenne pondérée ≈ +$2.96/trade ((19.01 + 4.66) / 8) = MARGINAL mais positif
- Univers actuel (BTC + ETH + SOL) → NO-GO

**Recommandation V2** : H3 doit être priorisé immédiatement après H4 dans le sprint Phase 2. Plus précisément, **drop SOL** est l'action la plus impactante quantitativement parmi toutes les hypothèses Phase 2 candidates.

---

## 4. Positions ouvertes au moment de l'analyse

2 positions encore ouvertes (BTC 2026-06-23 + ETH 2026-06-24) ne sont pas dans les 14 closures. Pour intégrité du verdict :

- Ces 2 positions n'ont payé que le fee d'ouverture (~$5 chacune, 50 % du round-trip)
- Total fees uncrystallized : ~$10
- Funding accumulé pour ces 2 positions n'apparaît pas encore dans `realized_pnl_usd` (encore dans `funding_accrued_usd` per-position)
- Quand elles se fermeront, leur impact sera : (funding_accrued_final − round_trip_fee_full)
- Pour le BTC ouvert : si funding accrued à close > $10-11 → win net ; sinon loss net
- Pour l'ETH ouvert : idem

Ces 2 positions ne changent pas le verdict directionnel d'H4 (BTC favorable, ETH marginal, full universe NO-GO).

---

## 5. Caveat statistique — N=14

**Le sample size de 14 trades est insuffisant pour des intervalles de confiance serrés au sens alpha_lab strict** :

- Per-asset N : BTC=3, ETH=5, SOL=6
- La conclusion "BTC est GO" repose sur 3 observations. Probabilité non-négligeable que sur un sample plus large (N≥50 par asset), un BTC trade puisse coûter sa rentabilité. Pas de Sharpe annualisé reportable proprement.
- La conclusion "SOL est NO-GO" est plus robuste qualitativement : le ratio gross PnL / fees est 0.26, structurellement déficitaire indépendamment du sample size.

Le verdict H4 est **directionnellement valide** mais **doit être confirmé sur un backtest 6-12 mois multi-régime** avant tout déploiement live. C'est le rôle de l'enchaînement H1 + H3 + alpha_lab Phase 2 à venir.

---

## 6. Verdict GO / MARGINAL / NO-GO

### 6.1 Pour la stratégie ACTUELLE (full universe BTC + ETH + SOL, paramètres `min_hold=24h, entry_threshold=0.005 APR`)

| Scenario | Expectancy net | Verdict H4 |
|---|---:|---|
| Per-asset optimistic | −$1.62 / trade | **NO-GO** |
| Per-asset median | −$3.05 / trade | **NO-GO** |
| Per-asset conservative | −$4.48 / trade | **NO-GO** |
| Uniform $11 | −$1.91 / trade | NO-GO |
| Uniform $15 | −$5.91 / trade | NO-GO |
| Uniform $19 | −$9.91 / trade | NO-GO |

**Verdict consolidé H4 sur la stratégie actuelle = NO-GO sur les 3 scenarios.** Intervalle de confiance large à cause de N=14, mais directionnellement non-ambigu : aucun des 6 scenarios testés ne montre une expectancy positive sur l'univers complet.

### 6.2 Verdict conditionnel — restriction à BTC-only

| Scenario | Expectancy net | Verdict H4 conditionnel |
|---|---:|---|
| Per-asset median (BTC standalone) | +$6.34 / trade | **GO** |

Sous-réserve de validation backtest 6+ mois sur BTC perp HL, **BTC-only en isolation est viable économiquement post-friction**.

### 6.3 Verdict conditionnel — restriction à BTC + ETH

| Scenario | Expectancy net | Verdict H4 conditionnel |
|---|---:|---|
| Per-asset median (BTC+ETH, drop SOL) | +$2.96 / trade | **MARGINAL** |

**Décision opérateur** : tradeable mais fragile, sensible à la qualité d'exécution réelle vs modélisée.

---

## 7. Recommendations actionnables

### 7.1 Suggestion immédiate Phase 2

**Bypass H1, prioriser H3 directement.** H4 a déjà prouvé quantitativement que :
- L'univers actuel est NO-GO post-friction
- Drop SOL ramène l'univers en zone GO/MARGINAL
- L'effet drop SOL (asset filter) > l'effet `min_hold_hours` extension (H1) en magnitude attendue

Ordre révisé Phase 2 :
1. **H3 (asset filter)** — backtest 6 mois BTC-only et BTC+ETH avec friction réaliste, alpha_lab 10-gate
2. **H1 (min_hold_hours)** — sur l'univers H3-restrict si pass H3
3. **H2 (entry_threshold)** — backup si H1 marginal
4. **H5 (delta-neutre hedge)** — conditionnel à clarification opérateur sur design production

### 7.2 Question opérateur critique pour décision

La conclusion H4 dépend partiellement de la modélisation slippage SOL ($6-10 bps round-trip vs $2-4 bps BTC/ETH). Cette valeur est dérivée de l'analyse microstructure générique, pas mesurée empiriquement sur les exécutions réelles V2 (puisqu'on est en paper).

**Si Sebastien a des données HL real-execution sur la période** (executions log, fill prices vs mark prices), le modèle slippage SOL peut être affiné. Si non, le scenario médian $15 reste le baseline raisonnable.

### 7.3 Statement final

**H4 verdict = NO-GO sur l'univers actuel.** L'expectancy paper de +$9.09/trade ne survit pas la friction réaliste sur les 3 scenarios. **Le killer identifié est SOL.** BTC-only redonne une viabilité. ETH-only est marginale. **L'asset filter est l'action H3 à prioriser avant toute autre.**

---

## 8. Memorable phrase / quote

> *Le profit factor 102 paper s'effondre à 0.51-0.76 sous friction réaliste. SOL coûte plus en fees ($90) qu'il ne rapporte en funding ($23.65). Drop SOL ramène le strategy en zone GO sur BTC, MARGINAL sur ETH.*

---

## 9. Prochain pas

**Phase 2 H4 — LIVRÉ. Aucun code production modifié. Aucun merge sur main.**

- Branche `analysis/loss-forensic-H4-friction-realistic` créée, contient ce livrable seul (pas de code change)
- Snapshot post-H4 à créer en fin de session
- Validation requise Sebastien sur :
  1. Le verdict NO-GO universe complet acceptable comme baseline
  2. La priorité pivot vers H3 (asset filter) confirmée
  3. La modélisation slippage SOL ($6-10 bps RT) acceptable ou à ajuster
- **Pas de merge sur main avant alpha_lab pass complet de H3** (qui sera la prochaine hypothèse exécutée)

---

*Phase 2 H4 generated by V2 agent on 2026-06-26 by read-only analysis of `analysis/_trades_matched.json` (Phase 1 cache). Snapshot pre-H4 `snapshots/SNAPSHOT_20260626T165329Z_pre_H4_friction_realistic`. Snapshot post-H4 à créer. Production code main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — INTACT.*
