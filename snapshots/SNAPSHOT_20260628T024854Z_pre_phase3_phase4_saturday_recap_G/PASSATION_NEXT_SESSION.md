# PASSATION — Trading Bot v2 — Reprise prochaine session

> **À toi, Badoun, futur-toi qui revient sur le projet.**
> **Et au prochain Claude qui n'a aucune mémoire de ce qu'on a fait.**
>
> Ce document contient tout ce qu'il faut pour reprendre proprement.

---

## ⚡ TL;DR — Comment reprendre en 2 minutes

### 1. Message d'ouverture à Claude

Copie-colle ceci dans ta nouvelle conversation :

```
Salut Claude, je reprends trading-bot-v2 (ICC).

Contexte : j'ai un bot de trading ICC en Python pour crypto sur Kraken.
Sessions 0-5 complètes. ICC officiellement VIABLE après walk-forward
(7/7 critères, 1968 trades sur 12 ans, PF 3.22, Sharpe 1.86, 8/8 actifs profitables).

Aujourd'hui je veux : [REMPLIR ICI ton objectif du jour]

Je te partage :
- JOURNAL.md (chronologie complète du projet)
- ICC_SPEC.md (spec ICC de référence)
- SESSION_5_RECAP.md (dernier verdict)
- SESSION_5_RESULTS.md (chiffres détaillés)

Les règles d'or non-négociables :
1. Pas de rafistolage — si on dévie de la spec ICC, on s'arrête
2. Tests unitaires obligatoires
3. Audit avant chaque clôture de session
4. Body close uniquement (TU#1)
5. No lookahead
6. Backup auto à chaque fin de session

Lis les docs et propose-moi un plan pour aujourd'hui.
```

### 2. Fichiers à uploader

Toujours ces 4 minimum :
- `docs/JOURNAL.md` (chronologie)
- `docs/ICC_SPEC.md` (spec)
- `docs/RECAPS/SESSION_5_RECAP.md` (dernier statut)
- `docs/RECAPS/SESSION_5_RESULTS.md` (chiffres)

Selon ce que tu veux faire :
- **Reprendre Session 6 paper trading** : ajoute `strategies/icc_cycle.py` + `strategies/walkforward_icc.py`
- **Modifier la stratégie** : ajoute le fichier concerné
- **Ajouter Gold** : ajoute aussi `data/parse_kraken_zip.py` et `data/resample_h1_to_h4.py`

---

## 📍 ÉTAT ACTUEL DU PROJET (11 Mai 2026, 19h)

### Statut sessions
```
✅ Phase 1     — Données (24 parquet, 12 ans crypto)
✅ Session 0   — Setup + 4 stratégies invalidées
✅ Session 1   — ICC v1 (rejetée)
✅ Session 2   — Structure ICC (22/22 tests)
✅ Session 3   — Order Blocks (23/23 tests)
✅ Session 4   — Cycle ICC complet (18/18 tests)
✅ Session 5   — Walk-Forward (VIABLE, 7/7 critères)
🔨 Session 6   — Paper trading Kraken (À FAIRE)
🔨 Session 7   — Capital réel (après 2 mois paper minimum)
```

### Verdict ICC

```
✅ VIABLE — proceed to paper trading

HARD (3/3) :
  ✓ Profit Factor : 3.22
  ✓ Max Drawdown  : 28.5%
  ✓ Actifs OK     : 8/8

SOFT (4/4) :
  ✓ Win Rate      : 57.7%
  ✓ Sharpe        : 1.86
  ✓ Trades/an     : 20.3
  ✓ Fenêtres OK   : 86.0%
```

### Tests
**63/63 ICC** (22 structure + 23 OBs + 18 cycle)

### Git
```
7800d3b Session 5 COMPLETE - ICC VIABLE
e97bf35 Session 4 COMPLETE - ICC Cycle (TU#4)
f775099 Session 4 - 3 configs compared
27c01af Session 3 complete - Order Blocks
77ebec3 Initial commit - Sessions 0-2
```

---

## 🛣️ CE QU'IL RESTE À FAIRE (par ordre de priorité)

### 🥇 PRIORITÉ 1 — Session 6 : Paper Trading Kraken (1-2 sessions de 4-6h)

**Objectif** : valider ICC en conditions live, sans risquer un seul euro.

**Composants à coder** :

1. **Ingestion data live**
   - WebSocket Kraken pour cotations temps réel (OHLCV H1)
   - Buffer rolling pour maintenir N derniers bars
   - Resampling temps réel H1 → H4

2. **Order routing (mode paper)**
   - Simulation interne : pas de vraie order sur Kraken
   - Track positions virtuelles avec exécution au prix de close H1
   - Slippage simulé (~0.05-0.15%)
   - Frais simulés (0.16% × 2 par trade)

3. **Monitoring & alerts**
   - Dashboard live (terminal ou web simple)
   - Alertes Telegram/email sur entries/exits
   - Logs structurés (JSON par trade)

4. **Persistence**
   - SQLite ou simple parquet pour stocker chaque trade
   - Possibilité de relancer après crash sans perdre l'état

5. **Plan d'exit clair**
   - Si performance live < 50% du backtest cumulé sur 3 mois → STOP
   - Si DD > 35% → STOP
   - Si bug technique → STOP immédiat

**Estimation** : 6-10h en 1-2 sessions. Mieux vaut 2 sessions de 5h propres qu'1 nuit de 10h baclée.

**Documents de référence à relire** :
- `SESSION_5_RECAP.md` section "Risques résiduels à monitorer en paper trading"
- `AUDIT_SESSION_5.md` section 8 "Risques résiduels"

---

### 🥈 PRIORITÉ 2 — Gold spot (Session 6.5 ou parallèle)

**Pourquoi c'est intéressant** : TradesSAI publie 88% WR sur Gold. Si ICC marche aussi sur Gold spot, ça valide cross-market class.

**Ce qu'il faut** :

1. **Source de données** (choisir 1) :
   - **Yahoo Finance** (gratuit, qualité OK pour daily, limité intraday)
     ```python
     import yfinance as yf
     gold = yf.download("GC=F", period="max", interval="1d")
     ```
   - **Polygon.io** (~$30/mois, qualité pro, intraday OK)
   - **Dukascopy** (gratuit, mais format binaire à parser)
   - **Alpha Vantage** (gratuit avec rate limit)

2. **Adapter le code** :
   - Nouveau parser dans `data/fetch_gold.py`
   - Gérer les **gaps weekend** (Gold ferme samedi-dimanche)
   - Adapter `find_h1_bar_for_h4_timestamp` pour timestamps non-contigus

3. **Reproduire Session 5 sur Gold uniquement** :
   - Walk-forward avec mêmes critères Hard/Soft
   - Comparer Win Rate Gold vs Win Rate crypto

**Estimation** : 3-5h. À faire APRÈS le paper trading crypto fonctionne, pas avant.

**Pourquoi pas avant ?** : tu veux d'abord prouver en live ce qui marche en backtest crypto. Si paper trading crypto déçoit, Gold devient secondaire.

---

### 🥉 PRIORITÉ 3 — Réserves Session 4 (à raffiner si besoin)

Ces 2 réserves sont documentées dans `AUDIT_SESSION_4.md` :

1. **Invalidation H4 NEW_HIGH/NEW_LOW opposé** : actuellement couvert indirectement via Daily flip. Peut manquer des cas où H4 reverse mais Daily reste neutre.

2. **Invalidation OB cassé directement** : actuellement couvert par CORRECTION_TOO_DEEP. Peut manquer des cas où l'OB est cassé sans atteindre l'origine.

**Quand les régler** : SEULEMENT si paper trading révèle des trades qui auraient dû être invalidés plus tôt. Sinon, leave it alone — anti-overfitting.

---

### 4️⃣ PRIORITÉ 4 — Améliorations potentielles (long terme)

- **Mode INTRADAY** : déjà codé dans `icc_cycle.py` (TradeMode.INTRADAY), jamais testé. M5/M15 entry, H1 confirmation.
- **Mode SCALPING** : aussi codé, jamais testé. Pour day trading actif.
- **Position sizing dynamique** : Kelly criterion ou volatility-based.
- **Régime detection** : réduire taille en bear marqué (BTC 2015 a montré ICC souffre en bear).
- **Multi-asset portfolio** : si paper trading montre que les 8 actifs sont décorrélés, allocation entre eux.

---

## 🔧 COMMANDES UTILES À CONNAÎTRE

### Run les tests
```bash
cd ~/Desktop/trading-bot-v2
source ~/Desktop/trading-bot/venv/bin/activate
python -m pytest tests/ -v
```

### Re-run le walk-forward (verdict)
```bash
python scripts/run_session_5_verdict.py          # Full (~3 min)
python scripts/run_session_5_verdict.py --quick  # Quick (~1.5 min)
python scripts/run_session_5_verdict.py --asset BTC  # 1 actif debug
```

### Comparer 3 configs ICC (Session 4)
```bash
python scripts/compare_icc_configs.py BTC
```

### Vérifier état git + tests
```bash
git status
git log --oneline -5
bash scripts/verify_session_4.sh
```

### Backup
```bash
bash scripts/backup.sh "Message du backup"
cp backups/$(ls -t backups/ | head -1) "/Volumes/Lexar/trading-bot-backups/"
```

---

## 📁 STRUCTURE DU PROJET

```
trading-bot-v2/
├── archive/
│   └── session_4_experiments/    # Anciens fichiers archivés
├── backups/                       # ZIP backups locaux
├── cache/                         # Données parquet (BTC, ETH, ...)
├── data/
│   ├── parse_kraken_zip.py
│   ├── fetch_multi_tf.py
│   ├── validate_data.py
│   └── resample_h1_to_h4.py      # ⭐ Session 5
├── docs/
│   ├── JOURNAL.md                # ⭐ Chronologie complète
│   ├── ICC_SPEC.md               # ⭐ Spec de référence
│   ├── ARCHITECTURE.md
│   ├── AUDIT_TEMPLATE.md
│   └── RECAPS/
│       ├── SESSION_2_RECAP.md
│       ├── SESSION_3_RECAP.md
│       ├── AUDIT_SESSION_3.md
│       ├── SESSION_4_RECAP.md
│       ├── AUDIT_SESSION_4.md
│       ├── SESSION_5_RECAP.md    # ⭐ Dernier verdict
│       ├── AUDIT_SESSION_5.md
│       └── SESSION_5_RESULTS.md  # ⭐ Auto-généré
├── scripts/
│   ├── backup.sh
│   ├── verify_session_4.sh
│   ├── compare_icc_configs.py
│   ├── validate_icc_cycle_on_real_data.py
│   └── run_session_5_verdict.py  # ⭐ Session 5
├── strategies/
│   ├── icc_structure.py          # TU#2
│   ├── icc_orderblocks.py        # TU#3
│   ├── icc_cycle.py              # TU#4 ⭐
│   └── walkforward_icc.py        # Session 5 ⭐
└── tests/
    ├── test_icc_structure.py     # 22 tests
    ├── test_icc_orderblocks.py   # 23 tests
    └── test_icc_cycle.py         # 18 tests
```

---

## ⚠️ PIÈGES CONNUS À ÉVITER

### Lors de la reprise

1. **Mauvais venv** : Le venv est dans `~/Desktop/trading-bot/venv/` (l'ancien projet), pas dans trading-bot-v2/. Toujours :
   ```bash
   source ~/Desktop/trading-bot/venv/bin/activate
   ```

2. **Data dans `cache/`, pas `data/`** : les parquet sont dans `cache/kraken_TF_ASSET_USD.parquet` (pas dans `data/`). Le dossier `data/` ne contient que les scripts.

3. **H4 natif = 2 ans seulement** : pour walk-forward étendu, utiliser `resample_h1_to_h4.py` (Session 5).

4. **Ne pas oublier pytest** : `pip install pytest` si nouvelle install.

### Lors du code

1. **Body close uniquement** : `current_close`, pas `current_high`/`current_low` pour les cassures de structure.

2. **No lookahead** : tout filtre doit avoir `if s.confirmed_at_bar > h1_bar: continue`.

3. **swing_lookback** : 5 daily, 3 intraday. Fixé. Ne pas tuner.

4. **SL = avant-dernier HL/LH**, pas le dernier. `found[1]`, pas `found[0]`.

5. **Pas de break-even** : règle TradesSAI absolue.

---

## 🎯 SI TU VEUX FAIRE SESSION 6 (PAPER TRADING)

### Pré-requis avant de coder

1. **Compte Kraken actif** avec API keys (peu importe le niveau pour paper trading)
2. **Choix du mode paper** :
   - Mode A : simulation 100% locale (pas de vraies orders)
   - Mode B : compte Kraken testnet/sandbox si Kraken en propose un
3. **Décision** : combien de capital simulé ? (Recommandation : $1000-10000 pour avoir des chiffres réalistes mais pas écrasants)

### Architecture proposée

```
strategies/paper_trader.py        # Boucle principale paper trading
strategies/kraken_data_stream.py  # WebSocket Kraken H1
strategies/order_simulator.py     # Simule exécution + frais + slippage
strategies/state_persistence.py   # SQLite pour positions/trades
strategies/monitoring.py           # Logs + alerts
scripts/run_paper_trading.py       # Entry point
```

### Questions à se poser AVANT de coder Session 6

1. Quelle frequency de tick : H1 (1 décision/heure) ou plus rapide ?
2. Combien d'actifs en parallèle : tous les 8 ou top 3 (ETH, LTC, BTC) ?
3. Quel capital simulé par actif ?
4. Quel critère d'arrêt automatique (drawdown max, perte consécutive max) ?
5. Notification : Telegram / email / juste logs ?

---

## 💌 NOTE FINALE

Tu as construit un système de trading qui :
- Passe **7/7 critères de viabilité statistique**
- Sur **12 ans de données réelles**
- Avec **1968 trades** dans 226 fenêtres out-of-sample
- Sur **8 actifs** dont aucun n'est perdant
- Avec une **méthodologie auditée 31/32**
- Et **63/63 tests unitaires passants**

C'est ton travail. Pas celui d'un outil IA.
L'IA t'aide à coder vite et structurer. Toi tu apportes la rigueur,
la discipline, et la décision stratégique.

Quand tu reprendras, relis ce document, ouvre les RECAPS,
et reprends là où tu t'es arrêté. Le projet est documenté
pour exactement ce cas-là.

Bon courage pour la suite. Le vrai test commence en paper trading.

---

*Document créé le 11 Mai 2026, 19h15.*
*Conservation : à la racine du projet ou dans docs/.*
