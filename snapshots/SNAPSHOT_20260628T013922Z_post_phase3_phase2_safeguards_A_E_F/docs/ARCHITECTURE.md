# ARCHITECTURE — Trading Bot v2 (ICC Implementation)

> Carte complète du projet. À lire en complément de `JOURNAL.md`.

---

## Vue d'ensemble

```
trading-bot-v2/
│
├── README.md                  ← Point d'entrée — lis ça en premier
├── .gitignore                 ← Fichiers exclus de Git (cache, parquet, etc.)
│
├── config.yaml                ← Configuration centralisée (symboles, frictions)
├── config.py                  ← Loader de config
│
├── docs/                      ← Documentation complète
│   ├── JOURNAL.md             ← Chronologie cumulative (single source of truth)
│   ├── ARCHITECTURE.md        ← Ce fichier
│   ├── ICC_SPEC.md            ← Résumé spec ICC (depuis Strategie_ICC_Complete.docx)
│   ├── AUDIT_TEMPLATE.md      ← Checklist pour clôturer chaque chapitre
│   └── RECAPS/                ← Recap détaillé de chaque session
│       └── SESSION_N_RECAP.md
│
├── data/                      ← Pipeline de données
│   ├── fetch.py               ← Hyperliquid (legacy, garde pour funding data)
│   ├── fetch_extended.py      ← Kraken BTC daily via API (legacy)
│   ├── fetch_universe.py      ← Kraken multi-actifs daily via API (legacy)
│   ├── fetch_multi_tf.py      ← Wrapper API Kraken multi-TF (limité à 720 bars)
│   ├── fetch_yfinance.py      ← Gold + NASDAQ via yfinance
│   ├── parse_kraken_zip.py    ← Parser du dump historique Kraken (CRITIQUE)
│   ├── validate_data.py       ← Validateur qualité données
│   └── cache_cleanup.py       ← Nettoyage cache redondant
│
├── strategies/                ← Logique de trading
│   ├── funding_capture.py     ← Stratégie 1 (rejetée — funding mort)
│   ├── trend_following.py     ← Stratégie 2 (rejetée — overfit)
│   ├── mean_reversion.py      ← Stratégie 3 (rejetée — MaxDD explosif)
│   ├── momentum_xsec.py       ← Stratégie 4 (rejetée — corrélation crypto)
│   ├── icc.py                 ← Stratégie 5 v1 (rejetée — pas fidèle aux TU)
│   ├── icc_structure.py       ← ICC fondation : détection structures (TU#1+TU#2) ✅
│   ├── icc_orderblocks.py     ← À coder Session 3 (TU#3)
│   └── icc_cycle.py           ← À coder Session 4 (TU#4 - cycle complet)
│
├── backtest/                  ← Moteurs de backtest
│   ├── engine.py              ← Funding capture vectorisé (9 tests ✓)
│   └── directional_engine.py  ← Long/short générique (13 tests ✓)
│
├── tests/                     ← Tests unitaires
│   ├── test_engine.py         ← 9 tests funding engine
│   ├── test_trend.py          ← 13 tests trend strategy
│   ├── test_mr_xsec.py        ← 9 tests MR + XSec
│   ├── test_icc.py            ← 9 tests ICC v1 (legacy)
│   └── test_icc_structure.py  ← 22 tests structure detection (TU#1+TU#2) ✅
│
├── scripts/                   ← Scripts utilitaires
│   ├── backup.sh              ← Sauvegarde automatique (Git + ZIP)
│   └── validate_icc_on_real_data.py  ← Validation visuelle ICC
│
├── results/                   ← Outputs des backtests (JSON timestamped)
│
├── cache/                     ← Données téléchargées (NOT in git, 530+ MB)
│   ├── kraken_1d_*.parquet    ← 8 cryptos, jusqu'à 12 ans
│   ├── kraken_4h_*.parquet    ← 8 cryptos, 2 ans
│   ├── kraken_1h_*.parquet    ← 8 cryptos, jusqu'à 12 ans
│   ├── funding_hyperliquid_*.parquet  ← Funding 28 mois
│   └── prices_1h_hyperliquid_*.parquet  ← Prices 7 mois
│
└── backups/                   ← ZIP de sauvegarde datés (NOT in git)
```

---

## Dépendances entre fichiers

### Pour la détection ICC (chaîne propre)

```
icc_structure.py    ← Fondation (TU#1 + TU#2)
       ↓
icc_orderblocks.py  ← Utilise icc_structure pour détecter OB (TU#3)
       ↓
icc_cycle.py        ← Utilise structure + OB pour cycle complet (TU#4)
       ↓
icc_main.py         ← Wrapper exécutable (futur)
```

### Pour le backtest

```
directional_engine.py  ← Moteur générique
        ↑
        │ accepte position vector -1/0/+1
        │
icc_cycle.py  → genère position vector
```

### Pour les données

```
parse_kraken_zip.py  → cache/kraken_*.parquet
                                ↓
                          Lu par : icc_structure.py, scripts/validate_*.py
```

---

## État actuel des stratégies

| Stratégie | Statut | Tests | Performance |
|---|---|---|---|
| Funding Capture | ❌ Rejetée | 9 ✓ | 2024 +22%, 2026 -0.4% (mort) |
| Trend Following | ❌ Rejetée | 13 ✓ | Train +3%, Test -26% (overfit) |
| Mean Reversion | ❌ Rejetée | 9 ✓ | MaxDD -118% (explosif) |
| Momentum X-Sec | ❌ Rejetée | 9 ✓ | Train -5%, Test -23% |
| ICC v1 (simple) | ❌ Rejetée | 9 ✓ | Gold 3/5 fenêtres profitables (MARGINAL) |
| **ICC v2 (TU-faithful)** | 🔨 En cours | 22 ✓ | Session 2 done, Session 3+ à venir |

---

## Décisions architecturales clés

### 1. Pourquoi cache parquet et pas CSV/SQLite ?
- Parquet = 5-10× plus compact que CSV
- Lecture pandas ultra-rapide
- Préserve les types (datetime, float)
- Format colonnaire = bon pour les analyses

### 2. Pourquoi tests unitaires obligatoires ?
- Détectent les régressions tôt
- Documentent le comportement attendu
- Permettent de refactorer en confiance
- Règle d'or : pas de code stratégie sans tests

### 3. Pourquoi pas de paramètre configurable arbitraire ?
- ICC est explicitement "no indicators" — on reste fidèle
- Chaque paramètre = risque d'overfitting via grid search
- Les seuls "paramètres" admis : swing_lookback (W=3 ou 5) parce que c'est une question de TF, pas d'optimisation

### 4. Pourquoi walk-forward systématique ?
- Backtest in-sample = ment souvent
- 4 stratégies aujourd'hui ont eu des backtests "positifs" puis échoué OOS
- Seul walk-forward (split train/test ou rolling) donne une vraie estimation

### 5. Pourquoi Kraken historical dump et pas API ?
- API publique limitée à 720 bars rolling (insuffisant pour ICC multi-année)
- Dump gratuit, complet, depuis 2013
- US-friendly (vs Binance bloqué)

---

## Outils / Plateformes utilisés

| Quoi | Pourquoi | Coût |
|---|---|---|
| Python 3.9 | Langage principal | Gratuit |
| pandas + numpy | Manipulation données | Gratuit |
| pyarrow | Parquet I/O | Gratuit |
| ccxt | API exchanges | Gratuit |
| yfinance | Gold + NASDAQ | Gratuit |
| Kraken (data + future trading) | US-friendly | Gratuit (data), commissions standard (trading) |
| Hyperliquid | Funding capture (legacy) | Commissions perp 4.5 bps |
| Git (local) | Versioning | Gratuit |
| Disque externe Badoun | Backup données 7.3 GB | Possédé |

---

## Performance benchmarks

| Opération | Volume | Temps |
|---|---|---|
| `detect_structures` (daily) | 3000 bars | 0.04 sec |
| `detect_structures` (H1) | 100,000 bars | ~1.5 sec |
| `parse_kraken_zip` (24 CSV) | ~150 MB extraits | 2-3 min |
| `walk_forward_trend` | 200 bars × 7 MAs | ~5 sec |

---

## Notes pour reprise rapide

**Si tu reviens dans 2 jours / 2 semaines** :

1. Lis `docs/JOURNAL.md` → tu sauras tout l'historique
2. Lis le dernier `docs/RECAPS/SESSION_N_RECAP.md` → où on s'est arrêté
3. Vérifie `cache/` → données toujours là
4. Lance `python tests/test_icc_structure.py` → vérifie que tout marche encore
5. Dis à Claude : "Reprends Session N+1" et donne-lui le JOURNAL

**Si tu changes d'ordinateur** :
1. Clone le dossier `trading-bot-v2/` depuis ton disque externe
2. Installe les dépendances : `pip install -r requirements.txt`
3. Vérifie cache (sinon, re-parser depuis Kraken ZIP)
4. Lance les tests

---

*Dernière mise à jour : 10 Mai 2026 — Fin Session 2*
