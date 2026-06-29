# IDEAS_PHASE_2 — Capture structurée des 10 directions Badoun

> **Statut** : capture, pas exécution. Toutes ces directions sont issues du
> message de Badoun du 22 mai 2026 (lecture du dossier de 77 pages). Elles
> sont **explicitement parquées pour Phase 2** — le gate du **12 août 2026**,
> conditionnel à la validation du paper trading et de la Phase 1 OOS+friction.
>
> **Pendant les 10 jours d'absence Badoun (22 mai → 2 juin)** : zéro
> exécution sur ces points. Le focus reste : daemon paper_funding_capture +
> watchdog + exercice d'alignement OB.

## Règles méta

Chaque idée suit le format `Question → Hypothèse → Test à mener`. Pas
d'implémentation prématurée, pas d'optimisation sur du sable.

Avant qu'une idée passe en exécution Phase 2, elle doit avoir :
- Une hypothèse falsifiable (chiffre cible ou comportement attendu)
- Un test walk-forward OOS+friction défini
- Un budget temps estimé
- Un critère de GO/NO-GO (Sharpe min, drawdown max, etc.)

---

## 1. OB averaging methodology

**Question** : peut-on apprendre un détecteur d'OB à partir d'exemples
manuels labellisés par Badoun, plutôt que des heuristiques codées en dur ?

**Hypothèse** : sur 90-300 OB labellisés (30-100 par actif × 3 actifs), la
distribution conjointe des features observables (range/ATR, body ratio,
FVG distance, push candles count, retracement count) sépare correctement
`OB+ validés` de `OB- validés` et de `failed`. Si oui, un classifier
simple (decision tree, logistic regression) suffit.

**Test à mener** :
1. Collecter labels via pipeline `data/ob_labels/` (déjà scaffolded)
2. Script `scripts/extract_ob_features.py` à coder
3. Analyse distributions + frontière de décision
4. Si frontière nette → seuils hard-codés ; sinon classifier
5. Walk-forward OOS+friction du nouveau détecteur

**GO** si F1 score > 0.75 sur OOS et Sharpe stratégie >= 1.0 sur l'univers
filtré.

**Budget estimé** : 3-5 jours après labels suffisants.

---

## 2. Multi-TF candidates

**Question** : ICC est-il optimal avec son cascade actuel (Daily / H4 / H1) ?
Ou d'autres combinaisons donnent un meilleur ratio signal/bruit ?

**Hypothèse** : `H4 / H1 / M30` ou `H8 / H4 / H1` peut surpasser le cascade
actuel sur les actifs liquides (BTC/ETH), mais moins sur les mid-caps où le
M30 est trop bruité.

**Test à mener** :
- `scripts/walkforward_tf_grid.py` à créer
- Bench les 3 combinaisons sur 2 régimes (bull 2024-25, bear 2022-23)
- Univers actuel filtré ETH/LTC/AVAX/SOL + extension BTC/Gold si Gold data
  fetched
- Métrique : Sharpe OOS+friction par TF combo, par actif

**GO** si une combinaison surclasse de >0.3 de Sharpe sur l'agrégat OOS.

**Budget estimé** : 2 jours en exécution, 1 jour analyse.

---

## 3. Corrélations multi-actifs

**Question** : peut-on détecter des paires d'actifs cointégrés
(stat-arb / pairs trading) qui offrent un edge complémentaire à ICC ?

**Hypothèse** : S&P/NAS, EUR/USD vs DXY (pas EUR/USD vs USD/EUR =
mathématiquement le même), Gold vs BTC en régimes risk-off, sont cointégrés
sur certaines fenêtres et offrent des entrées mean-reverting tradeable.

**Test à mener** :
1. Phase 1 : collecte de données multi-actifs en temps réel (à lancer
   début Phase 2, pas pendant l'absence — déjà parqué dans
   `docs/phase2_parked/correlation_logger.py.parked`)
2. Tests Engle-Granger, Johansen sur paires candidates
3. Stratégie spread-trading sur paires cointégrées, walk-forward OOS

**GO** si Sharpe > 1.0 sur la stratégie pairs trading OOS+friction.

**Budget estimé** : 2 semaines (collecte + analyse + walk-forward).

---

## 4. Divergences inter-actifs comme confluences d'entrée/sortie

**Question** : indépendamment du pairs trading pur, est-ce que des
divergences entre actifs corrélés (ex : BTC monte, ETH stagne) peuvent
servir de **confluence d'entrée ou de signal de sortie** sur ICC ?

**Hypothèse** : sur les actifs très corrélés (BTC/ETH/SOL), une divergence
> N écarts-types sur 4-8h est un signal de retournement imminent. Sur les
risk-on/risk-off (Gold vs BTC), une divergence est un signal de
changement de régime macro.

**Test à mener** :
- Réutilise les données collectées en idée #3
- Calcule la corrélation rolling 24h et identifie les ruptures
- Backtest : signaux de retournement déclenchés sur rupture corrélation,
  performance OOS+friction

**GO** si l'ajout de ce filtre améliore Sharpe ICC de >= 0.2.

**Budget estimé** : 1 semaine post-collecte data.

---

## 5. EMA experiments (147, 20, autres)

**Question** : ajouter une EMA comme filtre directionnel à ICC améliore-t-il
le ratio signal/bruit ?

**Hypothèse** : EMA 20 (court) ou 147 (long, suggéré par Badoun) comme
filtre — ne trader qu'avec la direction de l'EMA. Probable amélioration en
trending markets, dégradation en ranging.

**Test à mener** :
- `scripts/walkforward_ema_filter.py`
- Grid : EMA periods {10, 20, 50, 100, 147, 200}
- Trade qu'avec EMA-aligned setups, walk-forward OOS+friction
- Compare baseline ICC vs ICC + EMA filter

**GO** si une EMA period >= +0.15 Sharpe sans dégrader bear regime.

**Budget estimé** : 2 jours.

---

## 6. Stratégies différenciées Buy vs Sell

**Question** : ICC est-il symétriquement efficace sur Buy et Sell, ou
asymétriquement plus performant dans une direction ?

**Hypothèse** : ICC excelle en buy markets crypto (cycles haussiers
naturels) et sous-performe en sell. Une stratégie alternative (mean
reversion ou breakout) pourrait être plus adaptée aux sells.

**Test à mener** :
- Décompose les OOS+friction par direction (buy_only, sell_only) sur le
  filtered universe
- Si gap significatif > 0.4 Sharpe, identifier alternatives sell-side
  (ex : `strategies/mean_reversion.py` existe déjà)
- Combine ICC-buy + alternative-sell, walk-forward

**GO** si la combinaison surclasse ICC pur de >= 0.25 Sharpe.

**Budget estimé** : 3 jours.

---

## 7. Multi-stratégies par session (NY / London / Asia)

**Question** : les sessions ont des comportements différents — peut-on
allouer des stratégies différentes selon la session active ?

**Hypothèse** : NY = volatilité directionnelle (ICC efficient) ; Asia =
range-bound (mean reversion préférable) ; London = breakouts.

**Test à mener** :
1. Segment les OOS+friction par session de session-open
2. Quantifie le edge de chaque stratégie par session
3. Construit une stratégie "session-aware" qui pick le bon modèle par
   plage horaire

**GO** si la stratégie session-aware > ICC standalone de >= 0.2 Sharpe.

**Budget estimé** : 4 jours.

---

## 8. Funding capture extensions

**Question** : la stratégie funding_capture actuelle ne tourne que sur
BTC/ETH/SOL en perp HL. Peut-on l'étendre à plus d'actifs, ou la
basculer sur Gold/forex (en mode synthetic via cash-carry) ?

**Hypothèse** : sur Hyperliquid, les funding rates extrêmes (>30% APR)
sur tier-2 perps (DOGE, WIF, LINK) offrent un edge même après friction
augmentée. Sur Gold/forex, le funding capture est conceptuellement
différent (basis spot/futures, pas perp funding).

**Test à mener** :
- Phase 1 : extension HL perp universe au tier-2, paper trading 30 jours
- Phase 2 : analyse Gold futures contango/backwardation, simuler cash-carry

**GO** Phase 1 si edge tier-2 > tier-1 sans dégrader Sharpe global.

**Budget estimé** : 2 semaines Phase 1, 4 semaines Phase 2.

---

## 9. Macro events correlation

**Question** : peut-on lier les mouvements de marché à des événements macro
identifiables (FOMC, CPI, NFP, Q2 sorcières, tweets Fed/POTUS) pour adapter
le risque ou la stratégie ?

**Hypothèse** : la volatilité 4h autour des annonces dépasse 2x la
volatilité normale ; certains setups ICC ont taux d'invalidation plus
élevé sur ces fenêtres ; un filtre "no-trade 1h avant / 1h après majeur"
améliore le Sharpe net.

**Test à mener** :
1. Scrape un calendrier économique (Forex Factory ou similaire) — à faire
   en début Phase 2
2. Tag les trades historiques par proximité à des annonces
3. Compare performance proximity-tagged vs control
4. Conclure : filtre, surveillance, ou non-impact

**GO** si le filtre macro améliore Sharpe de >= 0.15 sans réduire trade
count de plus de 30%.

**Budget estimé** : 1 semaine.

---

## 10. Question profonde "formes vs chiffres" — interface humain-bot

**Question** : comment construire un protocole pérenne pour que Badoun
puisse communiquer ses intuitions visuelles à V2 dans un format que V2
peut directement intégrer en code ?

**Hypothèse** : un workflow note-vocale → transcription → extraction de
spécification (features quantifiables) → génération de code de test est
faisable. Boucle de feedback : Badoun valide ou rejette, V2 itère.

**Test à mener** :
1. Pipeline `scripts/voice_to_spec.py` :
   - Note vocale Badoun (Whisper transcription)
   - LLM parsing pour extraire features quantifiables
   - Output : spec en JSON / code skeleton
2. Test sur 5 spécifications libres de Badoun, mesure le taux
   d'extraction correct (validation Badoun ≥ 80% des extractions)
3. Si OK, c'est l'interface de tous les futurs ajustements de stratégie

**GO** si extraction utile ≥ 80% des cas et boucle de feedback < 5 min
par itération.

**Budget estimé** : 1 semaine MVP.

---

## Gate Phase 2 — 12 août 2026

**Conditions de bascule Phase 1 → Phase 2** :

| Critère | Cible |
|---|---|
| Paper trading propre | 60+ jours, drawdown max < 12%, daemon stable (heartbeat > 95% temps) |
| OOS+friction validé | Sharpe > 1.0 sur 1 régime OOS minimum (univers filtré) |
| Alignement OB | F1 score V2 vs Badoun > 0.65 (exercice du 22 mai consolidé le 3 juin) |
| Capital propre live | $5-10k déployé sur 30 jours, drawdown max < 10% |
| Operationnel | Watchdog + alertes + ledger append-only verified through 1 incident drill |

Si tous OK le 12 août, on ouvre Phase 2 et on commence à exécuter cette
liste (priorisée à ce moment-là selon les résultats Phase 1).

Si certains critères en retard, on étend Phase 1 d'un cycle de 30 jours et
on réévalue.

---

*Document de capture stratégique — créé le 22 mai 2026 par V2 avant départ
de Badoun. À NE PAS exécuter pendant l'absence. À revisiter le 3 juin
ensemble, puis à priorisé pour le gate du 12 août.*
