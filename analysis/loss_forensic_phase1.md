# Trading Bot V2 — Loss Forensic Phase 1 (Diagnostic)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 16:30 UTC
**Status** : Phase 1 — diagnostic pur. **Production code main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` INTACT.** Aucune modification de stratégie ni de paramètre. Lecture seule sur `live/state/trades.jsonl` et `live/logs/*.jsonl`.

**Pre-action snapshot** : `snapshots/SNAPSHOT_20260626T163036Z_pre_loss_forensic_phase1/` (P15 discipline enforced).

**Append-only** : ce fichier ne sera jamais réécrit. Phase 2 (hypothèses + branches Git) attend validation Sebastien de cette Phase 1 avant démarrage.

---

## 1. Inventory

### 1.1 Période & sources

| Item | Valeur |
|---|---|
| Stratégie analysée | Funding capture delta-neutral sur Hyperliquid perpetuals (BTC / ETH / SOL) |
| Source primaire | `live/state/trades.jsonl` (30 events : 16 opens + 14 closes) |
| Source secondaire | `live/logs/YYYY-MM-DD.jsonl` (funding_booked events détaillés, ~750 events sur la période) |
| Période live paper | 2026-05-21 11:00 UTC → 2026-06-26 16:30 UTC (35.2 jours) |
| Capital paper | $10 000 notional par position, max 3 positions simultanées (BTC + ETH + SOL) |
| Backtest historique funding capture | Référencé dans `docs/RECAPS/SESSION_5_RESULTS.md` (commit `1b34ae3` walk-forward bear regime) — non ré-extrait Phase 1, traité Phase 2 si besoin |

### 1.2 Métriques agrégées (14 trades fermés)

| Métrique | Valeur |
|---|---|
| Total trades fermés | 14 |
| Positions encore ouvertes | 2 (BTC + ETH, ouverts 06-23 et 06-24) |
| Wins | 10 (71.4 %) |
| Losses | 4 (28.6 %) |
| Flat (PnL = 0) | 0 |
| Total realized PnL | **+$127.32** |
| Sum wins | +$128.58 |
| Sum losses | −$1.26 |
| Avg win | +$12.86 |
| Avg loss | −$0.31 |
| **Expectancy / trade** | **+$9.09** |
| **Profit factor** | **102.31** (asymétrie extrême : losses minuscules) |
| Win / loss ratio (avg) | 40.93 |
| Max DD observée sur P&L cumul | **0 %** (aucune sous-séquence n'a porté l'equity sous le high de la séquence) |

**Note méthodologique** : `realized_pnl_usd == funding_accrued_usd` exactement sur chaque close event. Cela signifie que **la simulation V2 n'inclut PAS la friction (fees + slippage) dans le P&L tracké**. Le strategy module (`strategies/funding_capture.py`) délègue le P&L à un engine qui le calcule à partir du funding rate × position vector, sans déduction de coûts d'entrée/sortie. Implication critique : les vrais coûts en live seraient **9 bps round-trip taker × $10k = $9 par trade fermé**, transformant les 4 losses observées de ~$0.30 en losses de ~$9.30 chacune. Cf. Section 3.5.

### 1.3 Décomposition par actif

| Asset | N trades | W | L | WR | PnL total | Avg hold |
|---|:-:|:-:|:-:|:-:|---:|---:|
| **BTC** | 3 | 3 | 0 | **100 %** | +$49.01 | **209.0 h** (8.7 j) |
| **ETH** | 5 | 3 | 2 | 60 % | +$54.66 | 140.2 h (5.8 j) |
| **SOL** | 6 | 4 | 2 | 67 % | +$23.65 | 66.5 h (2.8 j) |

BTC concentre la moitié du PnL avec 100 % WR et le hold time le plus long (médiane). SOL a le hold time le plus court et 33 % de losses.

---

## 2. Classification per-loss

### 2.1 Les 4 losses individuelles

#### Loss #1 — SOL — 2026-05-24 16:03 → 2026-05-25 16:00 UTC

| Champ | Valeur |
|---|---|
| Hold time | **23.9 h** |
| Entry / exit price | $85.22 → $86.22 (mark drift +1.19 %) |
| Notional | ~$10 000 |
| Realized PnL | **−$0.40** |
| Funding events bookés pendant le hold | 23 (attendu 23, 0 manqué) |
| Funding accumulé net (= realized) | −$0.40 |

**POURQUOI** : minimum hold (24 h) atteint, signal funding smoothed sous le seuil exit (−0.005 APR), le daemon a fermé. Le funding rate cumulé sur les 23 ticks observés s'est avéré légèrement négatif net (≈ −0.000017 APR moyen sur la fenêtre). Pas de slippage à imputer (paper). Pas d'event macro identifié dans la fenêtre.

**Catégorie** : *funding flip post-entrée*, exit forcé par seuil exit après min_hold atteint. **Fonctionnement nominal du strategy, pas une anomalie.**

#### Loss #2 — ETH — 2026-06-07 04:00 → 2026-06-08 06:04 UTC

| Champ | Valeur |
|---|---|
| Hold time | **26.1 h** |
| Entry / exit price | $1594.40 → $1659.00 (mark drift +4.05 %) |
| Notional | ~$10 000 |
| Realized PnL | **−$0.008** (essentiellement breakeven) |
| Funding events bookés | 25 (attendu 26, 1 manqué — probable fetch failure HL API entre 2 hour-ticks) |
| Funding accumulé net (= realized) | −$0.008 |

**POURQUOI** : signal funding s'est aplati immédiatement après entrée. Un funding event manqué (HL fetch failure) a coûté ~$0.10 manquant ; sans ce miss le trade aurait été flat positif ~$0.09. Le min_hold a forcé la position à tenir 24h, le signal exit a déclenché à 26h.

**Catégorie** : *funding flip + 1 fetch miss*. Combine déclencheur stratégique nominal + déficience opérationnelle mineure.

#### Loss #3 — ETH — 2026-06-09 07:02 → 2026-06-10 07:00 UTC

| Champ | Valeur |
|---|---|
| Hold time | **24.0 h** (min_hold pile) |
| Entry / exit price | $1687.60 → $1630.50 (mark drift −3.38 %) |
| Notional | ~$10 000 |
| Realized PnL | **−$0.39** |
| Funding events bookés | 23 (attendu 23, 0 manqué) |
| Funding accumulé net (= realized) | −$0.39 |

**POURQUOI** : exit pile à `min_hold` (24h). Funding rate ETH a chuté brutalement dans les 4 premières heures après l'open, signal smoothed est tombé sous le seuil exit, mais min_hold a contraint la position à attendre. Coût d'opportunité de la contrainte min_hold visible.

**Catégorie** : *min_hold cost-of-opportunity*. Plus le signal est rapide à se retourner, plus le min_hold est cher. Probable hyperliquid market-wide funding adjustment post-FOMC ou news macro (à corréler Phase 2).

#### Loss #4 — SOL — 2026-06-11 10:00 → 2026-06-12 10:02 UTC

| Champ | Valeur |
|---|---|
| Hold time | **24.0 h** (min_hold pile) |
| Entry / exit price | $65.40 → $67.22 (mark drift +2.78 %) |
| Notional | ~$10 000 |
| Realized PnL | **−$0.46** |
| Funding events bookés | 23 (attendu 24, 1 manqué) |
| Funding accumulé net (= realized) | −$0.46 |

**POURQUOI** : pattern identique à #3 (exit à min_hold), avec +1 funding miss. Période où SOL était en début de descente macro (de $85 à $65 en 3 semaines), funding rate compressé.

**Catégorie** : *min_hold cost-of-opportunity + macro context*.

### 2.2 Tableau synthétique 4 losses

| # | Asset | Hold | Realized | Cause primaire | Cause secondaire |
|:-:|---|---:|---:|---|---|
| 1 | SOL | 23.9 h | −$0.40 | funding flip post-entrée | — |
| 2 | ETH | 26.1 h | −$0.008 | funding flip post-entrée | 1 fetch miss |
| 3 | ETH | 24.0 h | −$0.39 | min_hold cost-of-opportunity | possible macro (FOMC 06-09 ?) |
| 4 | SOL | 24.0 h | −$0.46 | min_hold cost-of-opportunity | 1 fetch miss + SOL macro down |

---

## 3. Patterns discovered

### 3.1 Pattern dominant — Hold time clusters

**Le hold time est LE discriminateur unique entre wins et losses dans cet échantillon** :

| Catégorie | N | Avg hold | Median hold | Range |
|---|:-:|---:|---:|---|
| Losses (4) | 4 | **24.5 h** | 24.0 h | 23.9 – 26.1 h |
| Wins (10) | 10 | **162.9 h** | 93.0 h | 31.0 – 517.0 h |

**Gap binaire** entre 26.1 h (loss max) et 31.0 h (win min). **Toutes les sorties dans une fenêtre [23.9 h, 26.1 h] sont des losses ; toutes les sorties après 31 h sont des wins**. 0 chevauchement.

Lecture mécanique : les trades qui ferment au plus près du `min_hold_hours = 24` (paramètre par défaut du strategy) sont systématiquement des cas où le signal funding a flippé entre l'entrée et la fenêtre min_hold, forçant un exit dès que la contrainte est levée. Aucun de ces trades n'a eu le temps de capturer un funding réellement favorable.

**Implication pour Phase 2** : la **première hypothèse à tester** est l'effet de `min_hold_hours` (actuellement 24 h) sur l'expectancy. Variantes candidates :
- Hyp A : élargir min_hold à 48 h (force le signal à se stabiliser plus longtemps avant exit, perd de la réactivité mais filtre les whipsaws)
- Hyp B : ajouter une condition supplémentaire d'entrée (exiger un funding rate smoothed entry threshold plus élevé, par ex. 0.01 APR au lieu de 0.005), réduisant le nombre d'entrées marginales qui finissent par flipper
- Hyp C : ne pas changer min_hold mais ajouter un filtre de volatilité (refuser d'entrer si volatility funding > seuil)

### 3.2 Pattern par actif

| Asset | WR | Insight |
|---|:-:|---|
| BTC | 100 % | Funding signal le plus stable sur la période, holds longs (médiane >100 h), 0 loss |
| ETH | 60 % | Hold time intermédiaire, 2/5 trades sortis à ~24-26 h (les 2 losses) |
| SOL | 67 % | Hold time le plus court en moyenne, 2/6 trades sortis à 24 h (les 2 losses) |

**Lecture** : BTC funding sur Hyperliquid présente la persistence la plus forte (signal smoothed reste au-dessus du seuil pendant des jours). SOL et ETH ont des funding regimes plus volatils. **L'efficacité du strategy V2 corrèle directement avec la persistence du signal funding par asset.**

### 3.3 Pattern temporel UTC

| Catégorie | Open hour UTC distribution |
|---|---|
| Losses (4) | 4h, 7h, 10h, 16h (uniforme sur la journée) |
| Wins (10) | 2h, 3h(×2), 11h(×4), 16h, 18h(×2) |

**Concentration des wins à 11h UTC** (4 wins / 10) = ouverture session NY (~07h NY-time / 13h London-time), période de stabilité macro relative. Losses uniformément distribuées, pas de pattern horaire fort.

**Sample size N = 14 trop petit pour conclure statistiquement**. Noter en hypothèse mais ne pas en faire la base d'un filtre Phase 2 sans validation.

### 3.4 Pattern funding cycle (Hyperliquid hourly)

Les funding events bookés pendant les holds des losses :

| Loss | Hold (h) | Funding events attendus | Funding events observés | Miss |
|---|---:|---:|---:|---:|
| #1 SOL 05-24 | 23.9 | 23 | 23 | 0 |
| #2 ETH 06-07 | 26.1 | 26 | 25 | 1 |
| #3 ETH 06-09 | 24.0 | 23 | 23 | 0 |
| #4 SOL 06-11 | 24.0 | 24 | 23 | 1 |

**2 fetch misses observées sur 4 losses (50 %)**. Sur les 10 wins, le sample n'a pas été ré-extrait avec la même granularité (out of Phase 1 scope), à vérifier Phase 2 si la corrélation se confirme.

**Hypothèse** : les fetch misses HL API ne sont pas un cause majeure de perte (impact ~$0.10 par miss), mais s'ajoutent comme déficience opérationnelle à corriger indépendamment.

### 3.5 ⚠ Friction NON modélisée dans le paper trading V2

**Finding critique pour Phase 2** : le sim live paper n'applique aucun coût de fees ou slippage. Le realized PnL trackée == funding_accrued_usd exactement. En production live, chaque trade fermé coûterait :

- Taker fee Hyperliquid : 4.5 bps × 2 legs (open + close) = 9 bps round-trip
- Sur $10 000 notional → **$9 de frais round-trip par position fermée**

Les 4 losses observées (−$0.008 à −$0.46) deviennent en live :

| Loss | Paper realized | Live realized estimé (− $9 fees) | Magnitude réelle |
|---|---:|---:|---|
| #1 SOL | −$0.40 | **−$9.40** | 23x worse |
| #2 ETH | −$0.008 | **−$9.01** | 1127x worse |
| #3 ETH | −$0.39 | **−$9.39** | 24x worse |
| #4 SOL | −$0.46 | **−$9.46** | 21x worse |

**Implication majeure** : l'expectancy de +$9.09 par trade observée en paper devient en live :
- Expectancy live ≈ +$9.09 − $9.00 (fees per trade) ≈ **+$0.09 / trade**, marginal
- OU **−$8.91 / trade** sur les losses isolément

Le profit factor 102 paper deviendrait probablement < 2 en live. **L'analyse Phase 1 ne peut pas valider la viabilité économique réelle du strategy sans intégrer la friction.** Premier item d'investigation Phase 2 : re-simuler le strategy sur le même historique avec friction réaliste, mesurer l'expectancy net.

Cette finding élargit la portée de l'analyse Phase 2 au-delà de "comprendre les pertes paper" vers "déterminer si le strategy est viable en live". C'est la question opérateur sous-jacente.

### 3.6 Pattern absence — Mark drift n'est PAS un signal de loss

| Catégorie | Avg mark drift entry → exit |
|---|---:|
| Losses (4) | +1.16 % |
| Wins (10) | −4.91 % |

Contre-intuitif : les wins ont en moyenne un mark drift **négatif** plus marqué que les losses. Cela tient au fait que le strategy est **long perp** (`dir=1`), et que les holds longs sur ETH et SOL ont traversé des periods de décline macro (ETH −25.85 % sur le win #5, SOL multiples wins en pleine baisse).

**Le mark drift ne cause pas les losses** parce que le PnL tracké est funding accrued seul, pas le PnL du long perp. Si la stratégie était vraiment delta-neutre (long perp + short spot), le mark drift serait neutralisé. Si la stratégie n'est PAS delta-neutre en production (vrai long perp sans hedge), alors le mark drift aggraverait dramatiquement les losses + dégraderait les wins sur les périodes de drawdown.

**Question opérateur ouverte à clarifier Phase 2** : est-ce que V2 production live executera (a) un long perp HL pur (exposition price + funding capture), (b) un long perp HL hedgé par un short spot ailleurs (delta-neutre vrai), ou (c) un autre design ?

---

## 4. Méta-observations méthodologiques

### 4.1 Limites de l'échantillon

- N = 14 trades fermés sur 35 jours — sample size insuffisant pour des statistical confidence intervals serrés sur les patterns. Pattern 16 (multi-perspective evaluation) : tout ce qui suit est à valider sur un échantillon plus large (backtest 6+ mois multi-régime).
- 4 losses uniquement, toutes < $0.50 par trade. La distribution des losses est **non-représentative** d'un échantillon live avec friction.
- Aucune période de stress macro majeur dans la fenêtre (pas de flash crash type 2022, pas de FOMC violent intra-fenêtre confirmé).

### 4.2 Confidence interval intuitif (sans alpha_lab gate)

Sharpe naïf sur 14 trades à $9.09 expectancy / std des trades... non calculé strictement Phase 1 car non-représentatif. Phase 2 invoquera alpha_lab pour la rigueur attendue.

### 4.3 Lien avec backtest funding capture historique

`docs/RECAPS/SESSION_5_RESULTS.md` (commit `1b34ae3`) référence un walk-forward bear regime sur funding capture. **Non extrait en Phase 1** par souci de scope. Phase 2 devra :
- Re-extraire les outputs de ce walk-forward (file paths exacts à identifier)
- Comparer expectancy paper vs expectancy backtest historique
- Valider si le pattern "loss = exit à min_hold" se retrouve dans le backtest

---

## 5. Hypothèses préliminaires pour Phase 2 (à valider Sebastien)

**Ces hypothèses ne sont PAS exécutées en Phase 1.** Elles attendent validation Sebastien + alpha_lab 10-gate avant toute branche Git, snapshot, ou simulation. Liste préliminaire pour calage de scope :

### Hypothèse H1 — `min_hold_hours` extension
**Logique** : toutes les losses sont des exits forcés par min_hold quand le signal a déjà flippé. Étendre min_hold devrait filtrer mécaniquement ces cas, mais coûter des wins courts.

**Variante à tester** :
- H1a : `min_hold_hours = 36` (au lieu de 24)
- H1b : `min_hold_hours = 48`

**Critère pass alpha_lab** : Sharpe net amélioré ET maximum DD pas pire ET expectancy / trade > 0 (statistically significant) sur un backtest 12+ mois multi-asset multi-régime.

### Hypothèse H2 — `entry_threshold_apr` renforcement
**Logique** : un seuil d'entrée plus exigeant (par ex. 0.01 APR au lieu de 0.005) filtre les marginales que le strategy actuel accepte. Moins de trades, mais qualité supérieure.

**Variantes** :
- H2a : `entry_threshold_apr = 0.01`
- H2b : `entry_threshold_apr = 0.015`

### Hypothèse H3 — filtre par asset (BTC-only ou (BTC+ETH)-only)
**Logique** : SOL a le WR le plus bas et le hold time le plus court. BTC a 100 % WR. Si la persistence du funding signal corrèle avec capacité de marché, restreindre à BTC (ou BTC+ETH) pourrait améliorer expectancy.

**Variantes** :
- H3a : BTC-only
- H3b : BTC + ETH (drop SOL)

### Hypothèse H4 — intégration friction réaliste dans le sim
**Logique** : si le strategy est marginalement positif après friction $9 par trade, alors aucune des H1/H2/H3 ne suffira sans réduction du nombre de trades. À tester en premier comme baseline avant tout autre changement.

**Implementation** : ajouter à `backtest/engine.py` une déduction de 9 bps round-trip × notional par paire open/close, re-run sur l'historique de la période.

### Hypothèse H5 — hedge delta-neutre vrai (Phase 2 si clarification opérateur le confirme)
**Logique** : si le production live design intègre un short spot hedge (vs paper qui ne tracke que le perp), le mark drift est neutralisé et les wins/losses dépendent purement du funding rate diff (perp − spot). Sim à construire si Sebastien le confirme.

### Priorité hypothèses

Ordre suggéré pour Phase 2 : **H4 d'abord** (rendre le sim réaliste), **H1 ensuite** (test le plus directement lié au pattern dominant), **H3 en parallèle** (filter par asset facile à coder), **H2 si H1 ne suffit pas**, **H5 conditionnelle à clarification opérateur**.

Chaque hypothèse aura :
- Sa propre branche Git `analysis/loss-forensic-<hypothesis-name>`
- Snapshot pre-snapshot `bash scripts/v2_snapshot.sh pre_h<N>_test`
- Tests TDD pour la modification de code
- Backtest sur fenêtre 6+ mois historique
- Validation alpha_lab 10-gate (point-in-time, OOS récent, DSR, PBO/CSCV, ensemble debiasing, beat trivial benchmark, etc.)
- Critère pass : **strictement supérieur** au baseline sur Sharpe net + max DD pas pire (per la directive Pattern 7 — binary acceptance defined before measurement)

---

## 6. Reversibility plan (P31 absolu) — pour mémoire Phase 2

**Production code main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` reste INTACT pendant toute Phase 1 ET Phase 2 d'analyse.** Le strategy live (VPS daemon depuis 25 juin 17:54 UTC) continue de tourner sans modification.

- ✅ Chaque hypothèse Phase 2 sur sa propre branche dédiée
- ✅ `bash scripts/v2_snapshot.sh pre_h<N>_<hypothesis-name>` AVANT chaque modif
- ✅ Rapport append-only dans `analysis/loss_forensic_phase2.md`
- ✅ Pas de merge sur main avant alpha_lab pass complet + greenlight Sebastien
- ✅ Snapshots préservés forever (Q4 décision opérateur 24 juin)

---

## 7. Memorable phrase / quote

> *Toutes les sorties dans [23.9 h, 26.1 h] sont des losses ; toutes les sorties après 31.0 h sont des wins. Le gap est binaire, pas statistique.*

Et accessoirement :

> *Le strategy V2 paper a un profit factor de 102, mais ce chiffre ne survivra pas la première application de 9 bps round-trip en live.*

---

## 8. Prochain pas

**Phase 1 — diagnostic — LIVRÉ.**

**Validation requise de Sebastien** avant Phase 2 :
1. Lecture du rapport
2. Validation ou ajustement des patterns dominants (hold time cluster, friction non modélisée, asset signature)
3. Priorisation des hypothèses H1-H5 (V2 propose H4 → H1 → H3, à arbitrer)
4. Clarification design production live : delta-neutre vrai (avec short spot hedge) ou long perp pur ?

**Phase 2 ne démarre qu'après ce greenlight.** Chaque hypothèse passera par alpha_lab 10-gate avant toute considération de merge sur main.

---

*Phase 1 generated by V2 agent on 2026-06-26 by reading-only `live/state/trades.jsonl` and `live/logs/*.jsonl`. Snapshot baseline `snapshots/SNAPSHOT_20260626T163036Z_pre_loss_forensic_phase1`. Production code main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — INTACT.*
