# AUDIT SESSION 5 — Walk-Forward Methodology

**Date** : 11 Mai 2026 (soir)
**Auditeur** : Claude Opus 4.7
**Statut audit** : ✅ VALIDÉ — Méthodologie solide, verdict défendable

---

## Méthodologie d'audit

Évaluation point par point de :
1. Le **schéma walk-forward** (anti-leak, anti-overfitting)
2. Les **critères de viabilité** (justification, pré-engagement)
3. Le **calcul des métriques** (correction mathématique)
4. La **portée du verdict** (limites assumées)

---

## 1. Walk-Forward — Anti-Leak Audit

| # | Critère | Vérif | Status |
|---|---|---|---|
| 1.1 | Test window strictement APRÈS train window | `test_start = train_end` (pas de chevauchement) | ✅ |
| 1.2 | Trades comptés uniquement si `entry_timestamp ∈ [test_start, test_end)` | `compute_window_metrics` filtre explicitement | ✅ |
| 1.3 | Pas de re-calibrage entre fenêtres | ICC n'a aucun paramètre fitté — purement règle-based | ✅ |
| 1.4 | Train sert uniquement de contexte historique | Pas de fit, juste contexte pour swing detection | ✅ |
| 1.5 | Pas de leakage via les Order Blocks détectés rétroactivement | Hérité du lag W de `icc_orderblocks.py` (Session 3) | ✅ |
| 1.6 | Aucune optimisation de paramètres au cours du run | Tous paramètres frozen (CONFIG A baseline) | ✅ |

**Score** : 6/6 ✅

**Note** : ICC est une stratégie **règle-based** sans paramètres ajustables critiques. Le walk-forward n'a donc pas la fonction de tester la généralisation d'un modèle fit, mais de tester la **robustesse de la règle** dans différents régimes. C'est valide et même plus propre qu'un walk-forward avec re-fit.

---

## 2. Critères de Viabilité — Pré-Engagement Audit

| # | Critère | Pré-décidé ? | Justification documentée ? |
|---|---|---|---|
| 2.1 | PF ≥ 1.5 (hard) | ✅ | "Standard quant : sous 1.5, edge insuffisant pour couvrir frais" |
| 2.2 | Max DD ≤ 35% (hard) | ✅ | "Au-delà, psychologiquement intenable + ruine probable" |
| 2.3 | ≥ 5/8 actifs profitables (hard) | ✅ | "1-2 actifs profitables = cherry-pick" |
| 2.4 | WR ≥ 50% (soft) | ✅ | "Sous 50% le PF doit être >2" |
| 2.5 | Sharpe ≥ 1.0 (soft) | ✅ | "Sous 1.0 = pas mieux qu'un bon ETF" |
| 2.6 | Trades/an ≥ 5 (soft) | ✅ | "Sous 5/an, stat trop faible" |
| 2.7 | Win.OK% ≥ 60% (soft) | ✅ | "Anti-luck dans la fenêtre" |

**Décision règle** : 3/3 hard + 3/4 soft = viable. Décidée AVANT tout run.

**Score** : 7/7 ✅

**Note critique** : la règle Hard/Soft a été préférée au 7/7 strict initial après discussion explicite avec l'utilisateur (Badoun). Le changement est documenté et antérieur aux runs.

---

## 3. Calcul des Métriques — Audit Mathématique

| # | Métrique | Formule | Vérif | Status |
|---|---|---|---|---|
| 3.1 | Profit Factor | `sum(wins) / abs(sum(losses))` | Standard, correct | ✅ |
| 3.2 | Win Rate | `len(wins) / len(trades)` | Standard, correct | ✅ |
| 3.3 | Sharpe annualisé | `mean(returns) / std(returns) * sqrt(26)` | Approximation (~26 trades/an), documenté | ⚠️ |
| 3.4 | Max DD | `max(peak - equity) / peak` sur equity chained | Correct, par fenêtre, agrégé par max | ✅ |
| 3.5 | Trades/an | `total_trades / total_test_years` | Correct, somme des test windows | ✅ |
| 3.6 | Cross-asset | `count(asset where cumulative_pnl > 0)` | Correct | ✅ |
| 3.7 | Win.OK% | `count(window where pnl > 0) / total_windows` | Correct | ✅ |

**Score** : 6/7 ✅ + 1 réserve

### Réserve sur le Sharpe (3.3)

Le Sharpe est calculé **per-trade** puis annualisé en multipliant par √26. Le 26 est une approximation (BTC fait 17 trades/an, ETH ~19, AVAX ~12.5, etc.). Le vrai annualisateur serait √(trades_per_year_actuel).

**Impact** : surestime légèrement le Sharpe pour les actifs avec < 26 trades/an. Pour BTC (17/an) : facteur correct serait √17 = 4.12 au lieu de √26 = 5.10. Donc le Sharpe affiché surestime de ~20%.

**Conséquence sur le verdict** : aurait pu changer le verdict si on était proche du seuil 1.0. Sharpe affiché = 1.86 → corrigé ~1.50. **Toujours largement au-dessus du seuil 1.0**. Pas d'impact sur le verdict.

**À corriger pour publication** : passer à `sharpe_per_trade * sqrt(trades_per_year_actuel)`. Pas urgent.

---

## 4. Portée du Verdict — Limites Audit

| # | Limite | Documentée ? | Impact |
|---|---|---|---|
| 4.1 | PnL = somme returns (pas composé) | ✅ Dans le code + RECAP | Modéré — l'ordre des trades pourrait diverger |
| 4.2 | Frais & slippage non inclus | ✅ Dans le RECAP | ~10-15% du PnL gross |
| 4.3 | H4 resamplé ≠ H4 natif | ✅ Dans le RECAP | Faible — cohérent par construction |
| 4.4 | SOL/AVAX = 11-13 fenêtres seulement | ✅ Dans le RECAP | Stat plus étroite sur ces actifs |
| 4.5 | Partial 85% empiriquement non validé | ✅ Réserve Session 4 héritée | Faible — partial est conservateur |
| 4.6 | Invalidations partielles (réserves Session 4) | ✅ Réserve héritée | Faible — couverte indirectement |
| 4.7 | Pas de Gold/NAS100 dans le périmètre | ✅ Décision explicite | Aucun (hors scope) |

**Score** : 7/7 limites documentées ✅

---

## 5. Reproductibilité

| # | Critère | Status |
|---|---|---|
| 5.1 | Run reproductible 1:1 (pas de randomness) | ✅ ICC est déterministe |
| 5.2 | Quick mode → verdict identique au Full | ✅ Confirmé empiriquement |
| 5.3 | Tous les paramètres documentés dans le code | ✅ CONFIG section explicite |
| 5.4 | Données sources identifiées (chemins, dates) | ✅ Output du script |
| 5.5 | Verdict réplicable en relançant le script | ✅ Pas de seed, pas d'aléa |

**Score** : 5/5 ✅

---

## 6. Bilan global

| Section | Score | Notes |
|---|---|---|
| 1. Walk-Forward anti-leak | 6/6 | Méthodologie propre |
| 2. Critères pré-engagement | 7/7 | Hard/Soft décidée AVANT |
| 3. Calcul métriques | 6/7 | Sharpe légère surestime, sans impact |
| 4. Limites documentées | 7/7 | Honnêteté maintenue |
| 5. Reproductibilité | 5/5 | Run déterministe |
| **TOTAL** | **31/32** | **97% — Audit validé** |

---

## 7. Verdict de l'audit

✅ **La méthodologie Session 5 est défendable.**

Le verdict "ICC est VIABLE" est :
- Basé sur des critères chiffrés **décidés à l'avance**
- Testé sur 12 ans de données réelles
- Couvre 8 actifs avec 1,968 trades
- Réplicable par tout utilisateur du repo
- Robuste à la granularité (quick vs full)
- Avec limitations **documentées et raisonnables**

**Recommandation paper trading** : ✅ approuvée sous réserve de :
1. Réintégrer les frais Kraken (0.32%) et slippage (~0.1%) dans le simulateur live
2. Surveiller spécifiquement BTC (plus marginal)
3. Limiter le capital initial (suggestion : 1-2% du capital total)
4. Plan d'exit si performance live < 50% du backtest cumulé sur 3 mois

---

## 8. Risques résiduels à monitorer en paper trading

1. **Régime change** : ICC sous-performe en bear marqué (vu sur BTC 2015). Surveiller le bias Daily : si BEAR prolongé sur BTC, réduire taille.

2. **Slippage réel** : peut diverger de l'estimation 0.05-0.15% sur exécutions en période volatile.

3. **Partial 85% en live** : Kraken supporte-t-il bien le partial close ? À tester explicitement.

4. **Trailing structurel en live** : timing de placement du SL après détection HL/LH — latence Kraken à mesurer.

5. **Multi-trade simultané** : code permet plusieurs setups SAME direction, à tester en charge live.

---

*Audit clos le 11 Mai 2026, 19h12. Méthodologie 31/32. Verdict défendable.*
