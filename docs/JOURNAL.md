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

### Ce qu'on a fait
- ...

### Fichiers modifiés / créés
- ...

### Tests
- ...

### Problèmes rencontrés
- ...

### Solutions appliquées
- ...

### Décisions importantes
- ...

### À faire ensuite
- ...

### Bilan honnête
- ...
```

---

## Historique du projet

### Session 0 — 10 Mai 2026 — Initialisation et 4 stratégies testées (toutes négatives)

**Durée** : ~12h
**Objectif initial** : Construire un bot trading crypto rentable
**Statut final** : ❌ 4 stratégies invalidées par walk-forward rigoureux

#### Ce qu'on a fait

1. **Framework de backtest production-grade** construit de zéro :
   - `backtest/engine.py` (funding capture vectorisé)
   - `backtest/directional_engine.py` (long/short)
   - Calibration friction empirique : 0.87 bps slippage médian, 4.5 bps taker fee Hyperliquid

2. **4 stratégies testées avec walk-forward** :
   - ❌ Funding Capture Hyperliquid : marchait 2024 (+22.81% CAGR), morte 2026 (-0.41%)
   - ❌ Trend Following Donchian + MA147 : train +3.35%, test -25.90% (overfit)
   - ❌ Mean Reversion (BB+RSI) : train +15.19%, test -3.82%, MaxDD -118% (explosif)
   - ❌ Cross-Sectional Momentum : train -5.05%, test -22.85% (correlation crypto)

3. **Données collectées** :
   - Funding Hyperliquid : 28 mois BTC/ETH/SOL
   - Prices Hyperliquid : 7 mois hourly BTC/ETH/SOL
   - Daily Kraken via API : 9 cryptos × 2 ans

4. **Tests unitaires** : 31 tests passent (9 engine + 13 trend + 9 mr_xsec)

#### Décisions importantes

- Walk-forward systématique sur toute stratégie (non-négociable)
- Méthodologie : forensic + walk-forward + sanity check
- Stratégies retail crypto "classiques" → marché crypto 2024-2026 trop efficient

#### Bilan honnête

- **0 stratégie viable** trouvée parmi les 4 testées
- **Mais** : framework de validation détecté l'overfitting, économisant ~$19,500 de pertes potentielles
- Décision : pivoter vers ICC (méthodologie price action de TradesSAI)

---

### Session 1 — 10 Mai 2026 (suite) — ICC v1 simplifiée (rejetée)

**Durée** : ~2h
**Objectif** : Tester ICC sur Gold/NASDAQ et crypto
**Statut final** : ⚠ Première implémentation rejetée (trop simplifiée)

#### Ce qu'on a fait

- Code initial `strategies/icc.py` (250 lignes) avec logique state machine basique
- 9 tests unitaires
- Walk-forward rolling 5 fenêtres
- Test sur Gold/NASDAQ (5 ans yfinance) : 3/5 fenêtres profitables, CAGR moyen -0.10%
- Verdict : MARGINAL (pas un edge robuste)

#### Problème détecté

L'implémentation v1 ne reflétait **pas réellement ICC** :
- Pas de structure HH/HL/LH/LL séquence-aware
- Pas d'Order Blocks
- Pas de multi-timeframe Daily/H4/H1
- Détection de "correction" arbitraire (% Fib)

#### Solution

Badoun a fourni **5 Tests Unitaires PDFs + 1 doc DOCX complet** (Strategie_ICC_Complete.docx). Spec extrêmement précise.
Décision : **Reprendre proprement** avec sessions structurées.

---

### Session "Phase 1" — 10 Mai 2026 (soir) — Data pipeline multi-TF Kraken

**Durée** : ~2h
**Objectif** : Télécharger Daily + H4 + H1 pour 8-9 cryptos sur 5+ années
**Statut final** : ✅ Complète

#### Problème majeur découvert

**Kraken API publique limitée à 720 bars max par TF** (rolling, non-paginable). Donc :
- API : 30 jours de H1 max, 120 jours de H4 max → insuffisant pour ICC

#### Solution trouvée

**Kraken historical data dump** (gratuit, complet) :
- Page officielle : https://support.kraken.com/articles/360047124832
- ZIP "Complete Data" via Google Drive (7.3 GB)
- Contient toutes les paires × TF de 1m à 1440 (daily) depuis le début de chaque marché

#### Fichiers créés

- `data/fetch_multi_tf.py` — wrapper API Kraken (utile pour updates incrémentaux futurs)
- `data/parse_kraken_zip.py` — parser du dump historique (BTC, ETH, SOL, ADA, LINK, DOT, AVAX, LTC × 1d/4h/1h)
- `data/validate_data.py` — validateur de qualité des données
- `data/cache_cleanup.py` — nettoyage cache redondant

#### Données finales en cache

```
Kraken 1d  : 8 cryptos, jusqu'à 12 ans d'historique (BTC depuis 2013)
Kraken 4h  : 8 cryptos, 2 ans (limitation: archive Kraken H4 commence 2024-01)
Kraken 1h  : 8 cryptos, jusqu'à 12 ans (BTC : 96,381 bars)
```

#### Note importante sur DOGE

DOGE/USD n'existe pas sur Kraken (régulation US). Disponible uniquement en DOGEUR. → Décision : retirer DOGE du universe, garder 8 cryptos.

#### Bilan

- Passé de **209 jours Hyperliquid → 12 ans Kraken multi-TF**
- 27 fichiers parquet propres dans cache/
- Tous sanity checks validés

---

### Session 2 — 10 Mai 2026 (soir, suite) — ICC Structure Detection (TU#1 + TU#2)

**Durée** : ~3h
**Objectif** : Détection rigoureuse des structures de marché ICC (HH/HL/LH/LL/New H/L)
**Statut final** : ✅ Complète, 22/22 tests passent, validé sur 4 actifs réels

#### Approche utilisée

**Architecture 2-step propre** (après échec d'une v1 incrémentale) :
1. **Confirmation de swing avec lag W** : un swing à la bar i est confirmé à i+W (pas de lookahead)
2. **Classification ICC** : selon contexte (active high/low + trend state)

#### Règles ICC implémentées (fidèles aux TU)

- ✅ Body close only (TU#1) — wicks = liquidité, jamais structure
- ✅ Pivot = "origine d'impulse" (TU#2) — pas un pivot mathématique
- ✅ Sequence-aware : HH après HH dans bull trend, LH après LH dans bear trend
- ✅ New High / New Low = CHoCH (1er break direction opposée)
- ✅ HH/LL = reproduction dans même direction
- ✅ Active vs broken state tracking
- ✅ Confirmation lag = W bars (aucun lookahead)

#### Fichiers créés

- `strategies/icc_structure.py` (320 lignes, code propre)
- `tests/test_icc_structure.py` (22 tests, tous passent)
- `scripts/validate_icc_on_real_data.py` (script de validation visuelle)

#### Tests passés : 22/22

1-3. Primitives swing (peak, trough, edges)
4-5. Body close rule (wicks ignorés)
6-7. Initial structures (INITIAL_HIGH, INITIAL_LOW)
8-9. CHoCH (NEW_HIGH après bear, NEW_LOW après bull)
10-11. Reproduction (HH après NEW_HIGH, LL après NEW_LOW)
12. Pullback structures (HL)
13-14. Origin assignment
15-16. Active/broken tracking
17. Confirmation lag (no lookahead)
18-22. Stress / sanity (no crash, ordering, no duplicates, balance)

#### Validation sur vraies données

| Actif | Période | Bars | Structures | Ratio H/L | Sanity |
|---|---|---|---|---|---|
| BTC daily | 12.2 ans | 4457 | 542 | 1.01 | ✓ |
| ETH daily | 10.4 ans | 3794 | 468 | 1.05 | ✓ |
| BTC h4 | 2.0 ans | 4383 | 902 | 1.05 | ✓ |
| SOL daily | 4.5 ans | 1659 | 193 | 1.03 | ✓ |

#### Problèmes rencontrés

1. **v1 buggée** (approche en 1 passe) :
   - INITIAL_HIGH non marqué cassé après NEW_HIGH
   - Génération de HH/HL à chaque bougie qui monte (sans pullback)
   - **Solution** : recommencer en 2-step

2. **Tests avec numpy bool** :
   - `is True` retournait False car numpy bool ≠ Python bool
   - **Solution** : utiliser `assert result` au lieu de `assert result is True`

3. **Tests synthétiques trop courts** :
   - `is_swing` requiert `i + W < len(data)` → tests de 9 bars trop courts
   - **Solution** : allonger séquences à 25+ bars

#### Décisions importantes

- **swing_lookback=5 pour daily, 3 pour intraday** (compromis sensibilité/bruit)
- **Pas de paramètre arbitraire** : pas de min_correction_pct, max_correction_pct (overfitting risk)
- **Lookback contextuel** : origin = swing low juste avant le swing high (pas une fenêtre fixe)

#### À faire ensuite

**Session 3 — Order Blocks (TU#3)** :
- Détection OB- (dernière bougie haussière avant grand mouvement baissier)
- Détection OB+ (dernière bougie baissière avant grand mouvement haussier)
- Scoring force : VERY_STRONG / STRONG / MODERATE / WEAK
- Cassure structure obligatoire pour validation
- Discount/Premium (50% du range)
- Usage unique (consommation)

**Estimation** : 3-4h, 6-8 tests unitaires

#### Bilan honnête

- ✅ Fondation solide pour tout le reste du bot
- ✅ Code maintenable, testé, documenté
- ✅ Performance acceptable (3000 bars en 0.04s)
- ⚠ Pas encore connecté à logique de trading (Session 4)

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
- `docs/ICC_SPEC.md` — Résumé de la spec ICC (depuis Strategie_ICC_Complete.docx)
- `docs/AUDIT_TEMPLATE.md` — Checklist à faire à chaque fin de chapitre
- `docs/RECAPS/SESSION_N_RECAP.md` — Recap détaillé de chaque session
- `scripts/backup.sh` — Script de sauvegarde automatique

---

*Dernière mise à jour : 10 Mai 2026 — Fin Session 2*
