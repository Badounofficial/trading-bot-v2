# JOURNAL — Trading Bot v2 (ICC Implementation)

> **Single source of truth pour le projet.**
> Chronologie complète, problèmes rencontrés, solutions, décisions.
> Toute personne (ou toute future instance de Claude) doit pouvoir lire ce
> fichier et comprendre où on en est.

---

## Format obligatoire pour chaque session

```
## Session N — YYYY-MM-DD — [titre court]

**Durée** : Xh
**Objectif** : ...
**Statut final** : ✅ Complète | ⚠ Partielle | ❌ Bloquée
```

---

## Historique du projet

### Session 0 — 10 Mai 2026 — Initialisation et 4 stratégies testées (toutes négatives)

**Durée** : ~12h | **Statut** : ❌ 4 stratégies invalidées par walk-forward

- Framework de backtest production-grade (engine + directional_engine)
- 4 stratégies testées : Funding Capture, Trend Following, Mean Reversion, Cross-Sec Momentum
- **0 stratégie viable** mais framework de validation a évité ~$19,500 de pertes potentielles
- Décision : pivoter vers ICC (méthodologie TradesSAI)
- 31 tests unitaires passent

---

### Session 1 — 10 Mai 2026 (suite) — ICC v1 simplifiée (rejetée)

**Durée** : ~2h | **Statut** : ⚠ Rejetée car pas fidèle à la spec

- `strategies/icc.py` v1 (250 lignes, state machine basique)
- Gold/NASDAQ : 3/5 fenêtres profitables, CAGR moyen -0.10% → MARGINAL
- Problème : pas séquence-aware, pas d'OB, pas multi-TF
- Solution : Badoun fournit 5 TUs PDFs + DOCX complet → reprendre proprement

---

### Phase 1 — 10 Mai 2026 (soir) — Data pipeline multi-TF Kraken

**Durée** : ~2h | **Statut** : ✅ Complète

- **Problème** : Kraken API limitée à 720 bars rolling (insuffisant)
- **Solution** : Kraken historical dump 7.3 GB via Google Drive
- 24 fichiers parquet : 8 cryptos × (1d, 4h, 1h)
- BTC daily : 12 ans, BTC H1 : 12 ans, H4 : 2 ans (limitation Kraken)
- DOGE retiré (DOGE/USD n'existe pas sur Kraken)

Fichiers : `data/parse_kraken_zip.py`, `data/fetch_multi_tf.py`, `data/validate_data.py`, `data/cache_cleanup.py`

---

### Session 2 — 10 Mai 2026 (soir) — ICC Structure Detection (TU#1 + TU#2)

**Durée** : ~3h | **Statut** : ✅ Complète, 22/22 tests

#### Approche : architecture 2-step

1. **Confirmation swing avec lag W** : pas de lookahead
2. **Classification ICC** : selon contexte (active high/low + trend)

#### Validation sur vraies données

| Actif | Période | Bars | Structures | Ratio H/L | Sanity |
|---|---|---|---|---|---|
| BTC daily | 12.2 ans | 4457 | 542 | 1.01 | ✓ |
| ETH daily | 10.4 ans | 3794 | 468 | 1.05 | ✓ |
| BTC h4 | 2.0 ans | 4383 | 902 | 1.05 | ✓ |
| SOL daily | 4.5 ans | 1659 | 193 | 1.03 | ✓ |

#### Décisions importantes

- swing_lookback=5 daily, 3 intraday
- Pas de paramètre arbitraire (anti-overfitting)
- Origin = swing low juste avant le swing high (contextuel)

Fichiers : `strategies/icc_structure.py` (320 l.), `tests/test_icc_structure.py` (22 tests), `scripts/validate_icc_on_real_data.py`

Détails complets : `docs/RECAPS/SESSION_2_RECAP.md`

---

### Session 3 — 11 Mai 2026 (matin) — ICC Order Blocks Detection (TU#3)

**Durée** : ~2h | **Statut** : ✅ Complète, 23/23 tests

#### Approche : pipeline rétrospectif

Pour chaque structure de break (NEW_HIGH/NEW_LOW/HH/LL) :
1. Cherche rétrospectivement la dernière bougie opposée = OB candle
2. Compte les bougies same-direction dans le mouvement
3. Détecte FVG (Fair Value Gap)
4. Score force : VERY_STRONG / STRONG / MODERATE / rejected
5. Marque consommation quand prix retouche zone

#### Règles TU#3 implémentées (toutes)

- ✅ OB- = dernière bougie haussière avant grand mouvement baissier
- ✅ OB+ = dernière bougie baissière avant grand mouvement haussier
- ✅ Zone OB = [open, close] (body only, pas wicks)
- ✅ Cassure structure obligatoire
- ✅ Min 3 bougies + FVG OU 5+ bougies sans FVG
- ✅ FVG bullish/bearish détectés
- ✅ Usage unique (consommation tracked)
- ✅ Discount/Premium classification

#### Validation sur vraies données

| Actif | Bars | OBs | VERY_STRONG | Consumed | Favorable | Sanity |
|---|---|---|---|---|---|---|
| BTC daily | 4457 | 100 | 97% | 92% | 72% | 5/5 ✓ |
| ETH daily | 3794 | 88 | 100% | 86% | 76% | 5/5 ✓ |
| BTC H4 | 4383 | 153 | 98% | 95% | 93% | 5/5 ✓ |

**Quantité** : ~10 OBs/an = sélectivité élevée pour swing trading.
**Qualité** : 97-100% des OBs sont VERY_STRONG = élite uniquement.

#### Décisions importantes (validées avant codage)

- Q1 : "Grand mouvement" = mouvement qui casse une structure (output Session 2)
- Q2 : Détection rétrospective au lag W (pas de lookahead)
- Q3 : Cassure structure du sens opposé (OB+ casse LH/LL)
- Q4 : Scoring strict spec, pas de paramètre arbitraire

#### Problèmes rencontrés

1. Random walk → 84% rejet (inquiétant). Validé sur crypto-like (50%) puis BTC (61%) → sain.
2. 2 tests synthétiques mal construits → corrigés.

Fichiers : `strategies/icc_orderblocks.py` (370 l.), `tests/test_icc_orderblocks.py` (23 tests), `scripts/validate_obs_on_real_data.py`

Détails complets : `docs/RECAPS/SESSION_3_RECAP.md` + `docs/RECAPS/AUDIT_SESSION_3.md`
### Session 4 — 11 Mai 2026 — ICC Cycle Complet (TU#4)

**Durée** : ~6h | **Statut** : ✅ Complète, 18/18 tests, 63/63 ICC total

#### Approche : machine à états multi-TF + money management complet

1. **Multi-TF cascade** : Daily → H4 → H1, alignement strict
2. **Machine à états** : SCANNING → INDICATION → CORRECTION → READY → IN_TRADE → COOLDOWN
3. **Correction Path A/B** : deep (touche OB H4) ou shallow (Fibo 50%)
4. **Money management** : SL avant-dernier HL/LH, TP=OB opposé RR≥2.5 OU measured RR 3.0, trailing structurel, partial 85%
5. **TRAILING_HIT vs SL_HIT** : exit reason discriminé (sémantique propre)

#### Validation sur vraies données (CONFIG A, 2 ans)

| Actif | Trades | Win rate | PnL total | Avg win | Avg loss |
|---|---|---|---|---|---|
| BTC | 34 | 52.9% | +25.69% | +2.24% | -0.92% |
| ETH | 39 | **82.1%** | **+89.11%** | +2.65% | -0.45% |
| SOL | 43 | 53.5% | +72.46% | +2.95% | -0.75% |
| **Moy** | **39** | **62.8%** | **+62.42%** | +2.61% | -0.71% |

**+62% moyen sur 2 ans avec 39 trades/an. Ratio gain/perte ~3.7x.**

#### Comparaison 3 configs (faite via Cowork)

- **CONFIG A** (Daily + TP measured 1:2) = baseline → meilleure
- **CONFIG B** (Daily + TP=OB ou measured 1:3) = identique à A (peu d'OBs utilisables)
- **CONFIG C** (sans Daily filter) = dégrade fortement (BTC devient négatif)

**Verdict** : le filtre Daily est crucial. Garder CONFIG A.

#### Décisions importantes

- Path A vs Path B exclusifs dans la condition de re-entry
- TP=OB filtre RR ≥ 2.5, sinon fallback measured move
- Partial 85% au TP, 15% trailing
- Pas de break-even (règle TradesSAI)
- TRAILING_HIT séparé de SL_HIT (sémantique propre)

#### Problèmes rencontrés

1. **`icc_cycle_v2.py` mal nommé** (en réalité version pré-refactor) → archivé proprement.
2. **Test Path A pur initial mal construit** (OB déclenchait Path B automatiquement) → corrigé en plaçant OB au-dessus du fibo_50.
3. **`pytest` manquant dans venv** → installé.

#### Réserves documentées (à raffiner Session 5)

- Invalidation H4 NEW_HIGH/LOW opposé : couvert indirectement via Daily flip
- Invalidation OB cassé directement : couvert partiellement par CORRECTION_TOO_DEEP
- Partial 85% pas encore validé empiriquement en backtest

Fichiers :
- `strategies/icc_cycle.py` (887 l.)
- `tests/test_icc_cycle.py` (530 l., 18 tests)
- `scripts/compare_icc_configs.py` (~250 l.)
- `scripts/validate_icc_cycle_on_real_data.py` (~150 l.)
- `scripts/verify_session_4.sh` (validation 1 commande)
- `archive/session_4_experiments/` (anciens fichiers archivés)

Détails complets : `docs/RECAPS/SESSION_4_RECAP.md` + `docs/RECAPS/AUDIT_SESSION_4.md`
### Session 5 — 11 Mai 2026 (soir) — Walk-Forward + Verdict Final

**Durée** : ~3h30 | **Statut** : ✅ Complète — VERDICT DÉFINITIF

#### Objectif

Répondre à la question critique : *"ICC est-il statistiquement viable pour passer en paper trading ?"*

#### Méthodologie (décidée AVANT les runs — anti-overfitting)

- **Schéma** : Walk-forward glissant — train 12mo / test 6mo / step 3mo
- **Actifs** : 8 cryptos Kraken (BTC, ETH, SOL, ADA, LINK, DOT, AVAX, LTC)
- **Données** : Daily natif + H4 resamplé depuis H1 (étend 2 ans → 4-12 ans selon actif)
- **Verdict Hard/Soft** : 3/3 hard + 3/4 soft = VIABLE

#### Critères verrouillés à l'avance

**HARD (3/3 mandatory)** :
- Profit Factor ≥ 1.5
- Max Drawdown ≤ 35%
- ≥ 5/8 actifs profitables

**SOFT (3/4 needed)** :
- Win Rate ≥ 50%
- Sharpe annualisé ≥ 1.0
- Trades/an ≥ 5
- ≥ 60% fenêtres profitables

#### Résultats — Full run (step 3mo, 159s)

| Actif | Fenêtres | Trades | WR % | PF | PnL cumulé | Max DD |
|---|---|---|---|---|---|---|
| LTC | 43 | 333 | 55.2% | 3.65 | **+608%** | 8.6% |
| ETH | 36 | 345 | 63.7% | 4.25 | **+561%** | 17.4% |
| LINK | 20 | 234 | 61.4% | 3.45 | +389% | 9.6% |
| ADA | 24 | 261 | 53.1% | 2.75 | +361% | 14.5% |
| AVAX | 11 | 137 | 67.7% | 6.29 | +278% | 7.6% |
| SOL | 13 | 145 | 54.8% | 4.12 | +276% | 7.2% |
| DOT | 16 | 147 | 58.1% | 2.84 | +191% | 10.3% |
| BTC | 43 | 366 | 48.0% | 1.65 | +171% | 28.5% |

**Total : 226 fenêtres, 1,968 trades sur 12 ans.**

#### VERDICT FINAL ✅ VIABLE

```
HARD : 3/3 ✓✓✓
  ✓ PF agrégé             : 3.22
  ✓ Max DD worst          : 28.5%
  ✓ Actifs profitables    : 8/8

SOFT : 4/4 ✓✓✓✓
  ✓ Win Rate moyen        : 57.7%
  ✓ Sharpe annualisé      : 1.86
  ✓ Trades/an             : 20.3
  ✓ Fenêtres profitables  : 86.0%
```

#### Cohérence Quick vs Full

| Métrique | Quick (step 6mo) | Full (step 3mo) |
|---|---|---|
| PF agrégé | 3.21 | 3.22 |
| Verdict | ✅ VIABLE | ✅ VIABLE |

**Robustesse statistique confirmée.**

#### Décisions et leçons

- **Règle Hard/Soft > 7/7 strict** : préserve la rigueur sur les vrais killers tout en acceptant qu'un soft trébuche
- **Resampling H1→H4** : indispensable pour stat power (BTC : 3 fenêtres natif → 43 fenêtres resamplé)
- **ICC est cross-asset robuste** : 8/8 profitables, PF 1.65-6.29
- **BTC = plancher** : marché efficient, moins d'edge, mais reste rentable
- **Bear markets** : ICC souffre (BTC 2015) — à monitorer en live

#### Limites assumées (documentées dans RECAP)

- PnL = somme returns (pas composé)
- Frais & slippage non inclus → estimation -10-15% net
- H4 resamplé (cohérent par construction, ≠ H4 natif Kraken)
- SOL/AVAX = stat plus étroite (11-13 fenêtres)
- 2 réserves Session 4 toujours actives (invalidations partielles)

Fichiers :
- `data/resample_h1_to_h4.py` (200 l.)
- `strategies/walkforward_icc.py` (400 l.)
- `scripts/run_session_5_verdict.py` (280 l.)

Détails complets : `docs/RECAPS/SESSION_5_RESULTS.md`, `SESSION_5_RECAP.md`, `AUDIT_SESSION_5.md`

#### Prochaine étape

**Session 6 — Paper trading Kraken**
- Sandbox / paper trading 1-2 mois minimum avant capital réel
- Ingestion data live + order routing SL/TP
- Monitoring + alerting
- Plan d'exit si performance live < 50% du backtest cumulé sur 3 mois

---

---
---

## Règles d'or du projet (non-négociables)

1. **Pas de rafistolage** : si on dévie de la spec ICC, on s'arrête et on re-discute
2. **Audit avant chaque clôture** de chapitre (voir `AUDIT_TEMPLATE.md`)
3. **Tests unitaires obligatoires** pour chaque fichier de stratégie
4. **Walk-forward systématique** pour valider toute stratégie
5. **Body close uniquement** pour les cassures (règle ICC fondamentale)
6. **No lookahead** : aucune utilisation du futur dans la détection
7. **Sauvegarde automatique** à chaque fin de session (`scripts/backup.sh`)
8. **Récap quotidien obligatoire** dans `docs/RECAPS/`

---

## Index des documents

- `README.md` — Point d'entrée du projet (lis ça en premier)
- `docs/JOURNAL.md` — Ce fichier (chronologie complète)
- `docs/ARCHITECTURE.md` — Carte du projet (fichiers, dépendances)
- `docs/ICC_SPEC.md` — Résumé de la spec ICC
- `docs/AUDIT_TEMPLATE.md` — Checklist à faire à chaque fin de chapitre
- `docs/RECAPS/SESSION_N_RECAP.md` — Recap détaillé de chaque session
- `docs/RECAPS/AUDIT_SESSION_N.md` — Audit fin de chapitre
- `scripts/backup.sh` — Script de sauvegarde automatique

---

## Statut global du projet (au 11 Mai 2026)

✅ Phase 1 — Données            (24 fichiers parquet, 12 ans crypto)
✅ Session 2 — Structure ICC    (22/22 tests, validé sur 4 actifs)
✅ Session 3 — Order Blocks     (23/23 tests, validé sur 3 actifs)
✅ Session 4 — Cycle ICC complet (18/18 tests, +62% moyen 2 ans BTC/ETH/SOL)
🔨 Session 5 — Walk-forward     (à venir — 8 cryptos × 12 ans)

**Tests totaux ICC** : 45/45 passent (22 structure + 23 OBs)
**Couverture spec ICC** : TU#1 + TU#2 + TU#3 ✅ (60% des TUs)

---

*Dernière mise à jour : 11 Mai 2026 — Fin Session 3*
