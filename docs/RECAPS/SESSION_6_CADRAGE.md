# CADRAGE Session 6 — Paper Trading Kraken

> **Document de référence pour le coding de Session 6.**
> Toutes les décisions structurelles ont été tranchées le 12 mai 2026.
> Quand tu reviens pour coder, relis ce doc + uploade-le à Claude.

---

## ⚡ TL;DR — Les 5 décisions verrouillées

| # | Décision | Choix | Conséquence |
|---|---|---|---|
| 1 | **Frequency** | H1 (1 décision/heure) | Aligné spec, conforme backtest |
| 2 | **Actifs** | Tous les 8 cryptos | Diversification max, philosophie Cas B |
| 3 | **Capital simulé** | $1,000 | Process > P&L, paramètre modifiable |
| 4 | **Stops auto** | DD 15% + Loss/jour 10% | Protection équilibrée |
| 5 | **Notifications** | Telegram (critique) + logs fichier (détail) | Cas B minimaliste |

---

## 🎯 Philosophie de la session

**Citation Badoun (12 mai 2026)** :
> *"Les premiers temps ce n'est pas pour gagner de l'argent mais m'assurer que la stratégie fonctionne et qu'il a une gestion rigoureuse du capital."*

C'est l'ADN de Session 6. **Process over P&L.** On valide l'exécution opérationnelle, pas la rentabilité.

**Cas B confirmé** : Badoun fait confiance au système, regarde les chiffres en fin de semaine. Le code doit respecter cette posture : ne pas spammer, ne pas inciter au monitoring constant, juste protéger et tracer.

---

## 📋 Détail des 5 décisions

### Décision 1 — Frequency : H1

**Choix** : le bot se réveille à chaque clôture de bougie H1 (XX:00 UTC).

**Workflow** :
1. À XX:00, récupère la bougie H1 qui vient de clôturer
2. Met à jour les structures ICC, OBs, états des setups
3. Décide : ouvrir / fermer / modifier SL / ne rien faire
4. Log toutes les décisions
5. Dort jusqu'à XX+1:00

**Pourquoi** : aligné avec TU#1 "Body close only — Jamais entrer sur bougie en cours". Aucune divergence backtest ↔ live.

**Conséquence technique** : pas besoin de gestion async complexe, pas de tick par tick, simple boucle horaire avec scheduler.

---

### Décision 2 — Actifs : Tous les 8

**Choix** : BTC, ETH, SOL, ADA, LINK, DOT, AVAX, LTC (tous backtests validés).

**Justification Badoun** : *"le backtest et le réel ce n'est jamais pareil, les plus faibles d'hier seront peut-être les plus forts demain"*. Mean reversion of strategy performance + diversification.

**Conséquence opérationnelle** :
- ~15-25 trades/mois attendus
- Dashboard auto-généré indispensable (vu volume)
- Logs structurés pour pouvoir reconstituer un trade post-mortem

**Pas de favoritisme** : chaque actif reçoit le même traitement, mêmes paramètres ICC (CONFIG A frozen).

---

### Décision 3 — Capital simulé : $1,000

**Choix** : capital virtuel total = $1,000, divisé en 8 actifs = $125/actif maximum par position.

**Justification** : Badoun veut **valider l'exécution** avant de risquer plus. 6 mois minimum de paper avant de scaler.

**Conséquence technique** :
- Paramètre `INITIAL_CAPITAL = 1000` dans la config
- **Facilement modifiable** sans changer le code (juste un paramètre)
- Sizing par actif = équipondéré (12.5% du capital par actif max)
- Slippage simulé à 0.10% (médiane de la fourchette 0.05-0.15%)
- Frais simulés à 0.16% par leg (Kraken maker/taker standard)

**Note importante** : à $1k, certaines positions seront fractionnelles bizarres. Pour BTC à $80k, 0.0015 BTC. C'est OK, Kraken supporte les fractions.

---

### Décision 4 — Stops automatiques : DD 15% + Loss/jour 10%

**Choix** : 2 niveaux de stop global qui s'ajoutent aux SL trade-by-trade existants.

**Pyramide de protection** :
```
Niveau 1 : SL structurel par trade (déjà codé Session 4)
Niveau 2 : Loss/jour 10%
Niveau 3 : DD max 15%
Niveau 4 : Stop manuel humain (override 24/7)
```

**Comportement quand un stop auto se déclenche** :
1. Bot ferme **toutes** les positions ouvertes immédiatement
2. Bot envoie alerte Telegram urgente
3. Bot passe en mode "HALT" (refuse d'ouvrir de nouvelles positions)
4. Bot reste en HALT jusqu'à ce que Badoun le relance manuellement (commande type `python paper_trader.py --resume`)
5. Logs détaillés écrits pour comprendre le déclenchement

**Calcul des seuils** :
- DD = (equity_actuelle - peak_equity) / peak_equity ≤ -15%
- Loss/jour = (equity_actuelle - equity_00h) / equity_00h ≤ -10%
- Reset journalier à 00:00 UTC

**Conséquence positive** : Badoun peut partir 1 semaine en vacances sans surveiller, le bot ne pourra pas dépasser ces seuils.

---

### Décision 5 — Notifications : Telegram + logs fichier

**Choix** : 2 canaux complémentaires.

#### Telegram — événements critiques uniquement
| Événement | Fréquence attendue | Contenu |
|---|---|---|
| 🚨 Stop auto déclenché | Rare (mois/jamais espéré) | DD% ou Loss/jour% atteint, positions fermées |
| 🚨 Crash technique du bot | Rare (mois/jamais) | Stack trace, last operation |
| ❤️ Heartbeat | 1x/jour (12h00 UTC) | "Bot alive, X trades aujourd'hui, equity $X" |
| 📊 Récap hebdo | 1x/semaine (dimanche 21h UTC) | PnL semaine, WR, trades par actif |

**Pas d'alerte par trade** : volontaire. Cas B → respect de l'attention.

#### Logs fichier — tout est tracé
- `logs/YYYY-MM-DD.log` (un fichier par jour)
- Format structuré (JSON par ligne) pour parsing ultérieur
- Chaque trade documenté : pourquoi entrée, indicateurs au moment de la décision, SL/TP, raison de sortie, PnL
- Badoun peut ouvrir n'importe quel log et reconstituer l'historique

#### Pré-requis Telegram (à faire AVANT la session de code)
1. Aller sur Telegram, chercher `@BotFather`
2. Envoyer `/newbot`, choisir un nom (ex: `BadounTradingBot`)
3. Récupérer le **token** (style `123456789:ABC-DEF...`)
4. Envoyer un message à ton nouveau bot
5. Visiter `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` pour récupérer ton **chat_id**
6. Stocker dans `.env` : 
   ```
   TELEGRAM_TOKEN=xxx
   TELEGRAM_CHAT_ID=xxx
   ```
7. Ajouter `.env` au `.gitignore`

---

## 🏗 ARCHITECTURE PROPOSÉE (à valider en début de Session 6 code)

```
trading-bot-v2/
└── paper_trading/                       # ⭐ NEW Session 6
    ├── __init__.py
    ├── data_stream.py                   # Kraken WebSocket H1 + buffer rolling
    ├── order_simulator.py               # Exécution simulée + frais + slippage
    ├── state_manager.py                 # SQLite persistence (positions, trades)
    ├── monitoring.py                    # Logs structurés + Telegram alerter
    ├── stop_manager.py                  # DD 15% + Loss/jour 10% checker
    ├── paper_trader.py                  # Boucle principale (orchestrateur)
    └── config.py                        # Tous les paramètres (capital, seuils, etc.)

scripts/
├── run_paper_trading.py                 # Entry point (cron-friendly)
├── resume_paper_trading.py              # Relance après HALT
└── inspect_paper_state.py               # Outil debug (lire state SQLite)

tests/
└── test_paper_trading.py                # Tests unitaires (15-20 tests)

docs/RECAPS/
├── SESSION_6_CADRAGE.md                 # ⭐ Ce document
├── SESSION_6_RECAP.md                   # À produire fin Session 6
└── AUDIT_SESSION_6.md                   # À produire fin Session 6
```

---

## 📊 DURÉE ESTIMÉE — Session 6 coding

| Bloc | Durée |
|---|---|
| 1. Setup config + pré-requis Telegram check | 30 min |
| 2. `data_stream.py` (Kraken WebSocket + resample) | 1h30 |
| 3. `order_simulator.py` (sim + frais + slippage) | 1h |
| 4. `state_manager.py` (SQLite persistence) | 1h |
| 5. `stop_manager.py` (DD + Loss/jour) | 45 min |
| 6. `monitoring.py` (logs + Telegram) | 1h |
| 7. `paper_trader.py` (boucle principale) | 1h |
| 8. Tests + dry run 1h sur data | 1h |
| 9. Audit + RECAP + commit | 45 min |
| **TOTAL** | **~7-8h** |

**Recommandation** : faire en **2 sessions** de ~4h chacune :
- Session 6a : Blocs 1-5 (data stream, simulator, persistence, stops)
- Session 6b : Blocs 6-9 (monitoring, orchestration, tests, audit)

Évite la fatigue cognitive d'une session 8h continue.

---

## ✅ PRÉ-REQUIS AVANT DE CODER SESSION 6

À vérifier dans l'ordre :

- [ ] Compte Kraken actif (n'importe quel niveau)
- [ ] API keys Kraken générées (read-only suffit pour paper)
- [ ] Bot Telegram créé via @BotFather
- [ ] Token Telegram + chat_id stockés dans `.env`
- [ ] `.env` ajouté à `.gitignore`
- [ ] Packages installés : `pip install websockets ccxt python-telegram-bot`
- [ ] Test rapide : envoyer un message manuel via le bot Telegram pour valider que ça marche
- [ ] Bloc de 4-5h ininterrompu dans l'agenda
- [ ] État physique : reposé, mangé
- [ ] Sessions 0-5 backup local + Lexar à jour

**Si UNE de ces cases n'est pas cochée → ne pas commencer**.

---

## 🎯 CRITÈRES DE SUCCÈS POUR SESSION 6

À la fin de Session 6, on doit pouvoir dire :

✅ Le bot tourne en mode paper depuis au moins 1 cycle H1 complet sur data live  
✅ Au moins un trade simulé a été ouvert + fermé proprement  
✅ Les logs contiennent tous les détails du trade  
✅ Une alerte Telegram test a été reçue avec succès  
✅ Le SQLite state survit à un kill -9 du process et relance  
✅ Tests unitaires passent (15-20 tests sur paper_trading)  
✅ Aucune fuite vers le code de stratégie (icc_cycle.py inchangé)  
✅ Documentation à jour (RECAP + AUDIT + JOURNAL)  
✅ Git commit + backup local + Lexar  

Si TOUT ça est vert → Session 7 (capital réel) possible après 2-3 mois minimum de paper.

---

## ⚠️ PIÈGES IDENTIFIÉS À ÉVITER

1. **Ne PAS modifier `strategies/icc_cycle.py`** pendant Session 6. La stratégie est validée Session 5. Session 6 = wrapper, pas refactor.

2. **Ne PAS commit le `.env`**. Token Telegram et API Kraken doivent rester locaux.

3. **Tester d'abord avec mock data**, puis passer au live. Pas de "first run sur Kraken WebSocket" sans avoir validé en local.

4. **Le SQLite doit être crash-safe**. Tester en faisant `kill -9` pendant un trade ouvert : le bot doit pouvoir reprendre proprement.

5. **Timezone hell** : Kraken sert en UTC, Mac en local. Tout doit être en UTC dans le code, pas de fuseaux mélangés.

6. **Latence Kraken** : la bougie H1 ne ferme pas exactement à XX:00:00. Il faut attendre 5-10 secondes que Kraken la close, puis fetch. Pas de race condition.

7. **Heartbeat doit être robuste** : si le bot crashe, il ne peut pas envoyer son heartbeat. Donc absence de heartbeat = crash. Faut un watchdog externe (cron qui vérifie le heartbeat).

---

## 🔄 ÉVOLUTIONS POSSIBLES (backlog, pas Session 6)

Si paper trading marche bien après 2-4 semaines :
- Élargir capital simulé à $10k pour tester sizing à grande échelle
- Ajouter dashboard web local (Flask, 1h de code)
- Implémenter Telegram commands (`/status`, `/halt`, `/resume`)
- Notifications enrichies (graphes PnL en PNG dans Telegram)

Si paper trading révèle des problèmes :
- Raffiner les 2 réserves Session 4 (invalidations H4 / OB cassé)
- Ajuster les paramètres slippage selon ce que tu observes
- Repartir en Session 5 avec critères ajustés

---

## 📜 STATUT — 12 mai 2026, 11h XX

✅ Cadrage Session 6 terminé en 1h tout pile  
✅ 5/5 décisions verrouillées et justifiées  
✅ Document de cadrage produit  
🔨 Pré-requis Telegram à faire par Badoun (hors session)  
🔨 Bloc 4-5h à planifier pour coding Session 6  

---

*Document créé le 12 mai 2026 par cadrage discipliné avant tout code.*
*Conservation : `docs/RECAPS/SESSION_6_CADRAGE.md`*
*Le code Session 6 doit respecter ligne par ligne ce qui est ici.*
