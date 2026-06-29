# CADRAGE Session 6 — Paper Trading 100% LOCAL (v2)

> **Document de référence final pour le coding de Session 6.**
> 
> ⚠️ **Cette version remplace le v1** qui prévoyait un broker (Kraken/OANDA).
> Après réflexion, on valide en **100% local** pendant 3-6 mois avant de toucher
> à un broker. Zéro capital immobilisé, zéro engagement.
>
> Décisions verrouillées le 12 mai 2026.

---

## ⚡ TL;DR — Les 5 décisions finales

| # | Décision | Choix | Conséquence |
|---|---|---|---|
| 1 | **Frequency** | H1 (1 décision/heure) | Aligné spec, conforme backtest |
| 2 | **Actifs** | Tous les 8 cryptos | Diversification max |
| 3 | **Capital simulé** | $1,000 (variable Python) | Process > P&L, modifiable |
| 4 | **Stops auto** | DD 15% + Loss/jour 10% | Protection équilibrée |
| 5 | **Notifications** | Telegram (critique) + logs fichier | Minimaliste, Cas B |
| **6** | **Source data** ⭐ | **Binance API publique (gratuit)** | **Aucun broker, aucun compte** |
| **7** | **Mode** ⭐ | **100% local, paper simulé** | **Zéro engagement financier** |

⭐ = décisions ajoutées le 12 mai après réflexion sur OANDA vs Kraken.

---

## 🎯 Philosophie de la session

**Citation Badoun (12 mai 2026)** :
> *"Les premiers temps ce n'est pas pour gagner de l'argent mais m'assurer que la stratégie fonctionne et qu'il a une gestion rigoureuse du capital."*

**Évolution du plan (12 mai après-midi)** :
> *"Si on valide la logique du bot 6 mois sans broker, je gagne en sérénité."*

C'est l'ADN de Session 6. **Process over P&L. Local-first.**

Validation phasée :
- **Phase 1 (Session 6)** : 100% local, 3-6 mois → valider la logique opérationnelle
- **Phase 2 (Session 7+)** : choisir broker en connaissance de cause
- **Phase 3** : capital réel petit après 1-2 mois broker démo

---

## 📋 Détail des 7 décisions

### Décision 1 — Frequency : H1 (inchangé)

Le bot se réveille à chaque clôture de bougie H1 (XX:00 UTC).

### Décision 2 — Actifs : Tous les 8 (inchangé)

BTC, ETH, SOL, ADA, LINK, DOT, AVAX, LTC.

Justification Badoun : *"le backtest et le réel ce n'est jamais pareil, les plus faibles d'hier seront peut-être les plus forts demain"*.

### Décision 3 — Capital simulé : $1,000 (variable Python)

Avant : capital déposé sur Kraken pour avoir l'API.
**Maintenant** : c'est juste `INITIAL_CAPITAL = 1000` dans `config.py`. Aucun argent réel impliqué.

### Décision 4 — Stops auto : DD 15% + Loss/jour 10% (inchangé)

Pyramide de protection :
```
1. SL par trade (existing)
2. Loss/jour 10%
3. DD max 15%
4. Stop manuel humain
```

### Décision 5 — Notifications : Telegram + logs (inchangé)

- Telegram = stops auto + crashes + heartbeat quotidien + récap hebdo
- Logs fichier = tout détail trade-by-trade

### Décision 6 ⭐ — Source data : Binance API publique

**Pourquoi Binance et pas Kraken** :
- Endpoint REST + WebSocket entièrement publics, **aucun compte requis**
- Les 8 cryptos qu'on a backtestés y sont (BTC, ETH, SOL, ADA, LINK, DOT, AVAX, LTC tradent en USDT)
- Rate limits très généreux (1200 requêtes/minute en REST, gratuit)
- Format OHLCV standard, facile à parser

**Implémentation** :
```python
# REST endpoint pour récupérer les bougies H1
GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=200

# WebSocket pour streaming temps réel (optionnel, on peut polling REST)
wss://stream.binance.com:9443/ws/btcusdt@kline_1h
```

**Fallback prévu** : si Binance API down, switch vers Kraken public endpoints (mêmes données, autre source).

**Note importante** : on récupère les prix **spot Binance**, qui peuvent légèrement différer des prix Kraken qu'on a backtestés. Différence attendue : <0.5% sur cryptos liquides. Acceptable pour validation logique.

### Décision 7 ⭐ — Mode 100% local

**Aucun ordre réel n'est passé nulle part.** Le bot :
1. Récupère les bougies via Binance public
2. Calcule en interne : "à ce prix, j'aurais acheté X BTC à $Y"
3. Stocke la position dans SQLite
4. Applique slippage simulé (0.10%) + frais simulés (0.16% × 2)
5. Suit le P&L théorique
6. Log + Telegram

**Avantages** :
- $0 immobilisé
- $0 dépensé
- Aucun agreement à signer
- Aucun risque de termination
- Peut tourner 1 an si besoin

**Limites** :
- Pas de test du passage d'ordres réel (acceptable en phase validation)
- Latence réelle différente (slippage simulé = estimation)
- Liquidité réelle non testée

---

## 🏗 ARCHITECTURE PROPOSÉE

```
trading-bot-v2/
└── paper_trading/                       # ⭐ NEW Session 6
    ├── __init__.py
    ├── data_source.py                   # Binance public API + fallback Kraken
    ├── order_simulator.py               # Exécution simulée + frais + slippage
    ├── state_manager.py                 # SQLite persistence
    ├── monitoring.py                    # Logs JSON + Telegram alerter
    ├── stop_manager.py                  # DD 15% + Loss/jour 10%
    ├── paper_trader.py                  # Boucle principale
    └── config.py                        # Paramètres (capital, seuils, etc.)

scripts/
├── run_paper_trading.py                 # Entry point
├── resume_paper_trading.py              # Relance après HALT
└── inspect_paper_state.py               # Debug

tests/
└── test_paper_trading.py                # 15-20 tests

docs/RECAPS/
├── SESSION_6_CADRAGE.md                 # ⭐ Ce document
├── SESSION_6_RECAP.md                   # À produire fin Session 6
└── AUDIT_SESSION_6.md                   # À produire fin Session 6
```

---

## 📊 DURÉE ESTIMÉE — Session 6 coding

| Bloc | Durée |
|---|---|
| 1. Setup config + Telegram bot | 30 min |
| 2. `data_source.py` (Binance API + polling H1) | 1h |
| 3. `order_simulator.py` | 1h |
| 4. `state_manager.py` (SQLite) | 1h |
| 5. `stop_manager.py` | 45 min |
| 6. `monitoring.py` (logs + Telegram) | 1h |
| 7. `paper_trader.py` (orchestrateur) | 1h |
| 8. Tests + dry run 1h sur data | 1h |
| 9. Audit + RECAP + commit | 45 min |
| **TOTAL** | **~7-8h** |

**Recommandation** : 2 sessions de ~4h
- Session 6a : Blocs 1-5
- Session 6b : Blocs 6-9

---

## ✅ PRÉ-REQUIS AVANT DE CODER SESSION 6 (version locale)

À vérifier dans l'ordre :

- [ ] Bot Telegram créé via @BotFather + token + chat_id
- [ ] `.env` créé avec les tokens (ajouté à `.gitignore`)
- [ ] Packages : `pip install requests pandas python-telegram-bot websockets`
- [ ] Test : envoyer un message manuel via le bot Telegram
- [ ] Test connexion Binance : `curl https://api.binance.com/api/v3/ping` (doit renvoyer `{}`)
- [ ] Bloc de 4-5h ininterrompu dans l'agenda
- [ ] État physique : reposé, mangé

**Plus besoin de** :
- ❌ Compte broker
- ❌ API keys broker
- ❌ Capital déposé
- ❌ Agreement signé

**Si UNE des cases obligatoires manque → ne pas commencer.**

---

## 🎯 CRITÈRES DE SUCCÈS SESSION 6

À la fin de Session 6, on doit pouvoir dire :

✅ Le bot tourne en mode paper depuis au moins 1 cycle H1 complet sur Binance data live  
✅ Au moins un trade simulé a été ouvert + fermé proprement  
✅ Les logs contiennent tous les détails du trade  
✅ Une alerte Telegram test a été reçue  
✅ Le SQLite state survit à un `kill -9` du process et relance  
✅ Tests unitaires passent (15-20 tests)  
✅ Aucune modification de `strategies/icc_cycle.py` (frozen Session 4)  
✅ Documentation à jour (RECAP + AUDIT + JOURNAL)  
✅ Git commit + backup local + Lexar  

Si TOUT ça est vert → Phase 2 (broker choice) accessible après 3-6 mois.

---

## ⚠️ PIÈGES IDENTIFIÉS

1. **Ne PAS modifier `strategies/icc_cycle.py`**. Stratégie validée Session 5. Session 6 = wrapper.
2. **Ne PAS commit `.env`**. Token Telegram doit rester local.
3. **Tester avec mock data d'abord**, puis Binance live.
4. **SQLite crash-safe** : tester `kill -9` pendant trade ouvert.
5. **Timezone hell** : tout en UTC dans le code.
6. **Latence Binance** : ne pas fetch exactement à XX:00:00 (attendre 5-10s la close).
7. **Heartbeat watchdog** : si bot crashe, pas de heartbeat → faut un cron externe.
8. **Rate limit Binance** : 1200 req/min en REST. Pour 8 actifs × 1 req/h = trivial.
9. **Prix Binance ≠ Kraken backtest** : différence <0.5% attendue, acceptable.

---

## 🔄 ÉVOLUTIONS POSSIBLES (backlog post-Session 6)

**Court terme (Session 6.5)** :
- Ajouter Gold via Yahoo Finance (yfinance lib)
- Ajouter NAS100 via Yahoo Finance
- Tester si ICC marche sur ces actifs aussi (Session 5 bis local)

**Moyen terme (Session 7)** :
- Choisir broker (Kraken ou autre) après 3-6 mois de paper local
- Démo broker pour tester passage d'ordres réel (mais simulé côté broker)
- Comparer résultats Binance public vs broker pour valider la différence

**Long terme (Session 8+)** :
- Capital réel petit ($500-1k) après 1-2 mois broker démo
- Dashboard web local (Flask)
- Telegram commands (`/status`, `/halt`, `/resume`)

---

## 🚫 CE QU'ON N'AURA PAS APPRIS EN PHASE LOCALE

Honnêteté assumée :

1. **Le passage d'ordres réel** (latence broker, slippage réel)
2. **Le carnet d'ordres** (liquidité disponible aux prix décidés)
3. **Les fees réels** (peuvent varier selon volume mensuel)
4. **Le comportement broker en cas de crash flash**

**Tout ça se découvrira en Phase 2 (broker démo).** Mais on saura déjà que **la logique du bot est correcte**, ce qui est 80% du chemin.

---

## 📜 STATUT — 12 mai 2026, midi

✅ Cadrage Session 6 v2 finalisé  
✅ 7 décisions verrouillées et justifiées  
✅ Stratégie 100% local validée (pas de broker en phase 1)  
🔨 Pré-requis Telegram à faire par Badoun (10 min)  
🔨 Bloc 4-5h à planifier pour coding Session 6a  

**Important** : ce document v2 remplace le v1 du matin. Si tu retrouves
le v1, ignore-le. Les décisions 6 et 7 (data source + mode local) sont
les ajouts qui changent tout.

---

*Document v2 créé le 12 mai 2026 après réflexion approfondie sur*
*la question "comment valider sans immobiliser de capital ?"*
*Conservation : `docs/RECAPS/SESSION_6_CADRAGE.md`*
*Le code Session 6 doit respecter ligne par ligne ce qui est ici.*
