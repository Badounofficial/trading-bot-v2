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

```
✅ Phase 1 — Données            (24 fichiers parquet, 12 ans crypto)
✅ Session 2 — Structure ICC    (22/22 tests, validé sur 4 actifs)
✅ Session 3 — Order Blocks     (23/23 tests, validé sur 3 actifs)
🔨 Session 4 — Cycle ICC complet (TU#4 - à venir)
🔨 Session 5 — Walk-forward     (à venir)
```

**Tests totaux ICC** : 45/45 passent (22 structure + 23 OBs)
**Couverture spec ICC** : TU#1 + TU#2 + TU#3 ✅ (60% des TUs)

---

*Dernière mise à jour : 11 Mai 2026 — Fin Session 3*
