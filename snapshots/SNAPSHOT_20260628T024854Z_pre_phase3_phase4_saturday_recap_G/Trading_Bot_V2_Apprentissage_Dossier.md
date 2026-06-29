# Trading Bot V2 — Dossier d'apprentissage et de vision

**Préparé pour Badoun · 21 mai 2026 · lecture avion + 10 jours d'absence**

---

## Comment lire ce dossier

Tu pars 10 jours. Ce document existe pour deux raisons :

1. **Te donner les fondations conceptuelles** dont je voudrais que tu maîtrises pour qu'on travaille ensemble plus efficacement sur V2 à ton retour. Ça va de la métrique quant de base (Sharpe, drawdown) jusqu'aux nuances de la microstructure crypto et des risques de régulation.

2. **Te montrer la vision large possible** pour V2. Aujourd'hui le projet est un bot perso en paper trading. Le potentiel va de "joli outil personnel qui couvre les coûts" à "produit communautaire avec une vraie marque" jusqu'à "petit fonds quant crypto". Je veux que tu aies en tête les leviers et les obstacles de chaque palier.

Le document a **9 parties**. Tu peux le lire linéairement (recommandé pour les fondations, parties 1-3) ou en piochant (parties 4-9 sont plus modulaires). Pour le voyage je te suggère :

- **Vol aller** : parties 0 à 3 (fondations + microstructure + critique ICC). C'est dense, ça pose le socle.
- **Première semaine** : parties 4 à 6 (funding capture, engineering, risque). Plus pratique, lié à ce qui tourne en arrière-plan sur ton Mac.
- **Deuxième semaine** : parties 7 à 9 (régulation, vision, bibliographie). Plus stratégique, à lire l'esprit reposé.

Chaque partie se finit par une section **"À retenir pour V2"** qui relie le concept aux décisions concrètes qu'on prendra à ton retour le 3 juin.

Je ne suis pas neutre dans ce document. Je donne des avis honnêtes, parfois durs (notamment dans la partie 3 sur l'ICC/SMC). Toutes mes affirmations sourcées sont entre crochets `[n]` renvoyant à la bibliographie commentée en partie 9.

Bonne lecture. Reviens reposé.

---

# Partie 1 — Fondations quant

## 1.1 Pourquoi le quantitatif et pas le discrétionnaire

La grande majorité des traders particuliers perdent de l'argent. Les chiffres reviennent dans toutes les études : **~95 % des bots AI retail perdent de l'argent dans les 90 premiers jours** [1], **moins de 1 % des day traders sont profitables nets de frais sur le long terme** [2]. Le trading discrétionnaire — celui où tu prends des décisions à la main devant ton écran — est statistiquement perdant pour à peu près tout le monde sauf une minorité qui combine talent, discipline rare, et chance.

Le trading quantitatif (ou algorithmique) ne garantit pas le succès — il garantit la **reproductibilité**. C'est sa seule vraie supériorité : si tu encodes ta stratégie comme un algorithme déterministe, tu peux la tester sur des décennies de données passées, tu peux mesurer précisément ses comportements, tu peux la comparer à d'autres approches, tu peux la déployer sans biais émotionnel.

Le piège : la reproductibilité du backtest n'est PAS une garantie de reproductibilité en live. C'est la leçon centrale de ce dossier. Tout le reste de la partie 1 vise à t'équiper contre cette illusion.

## 1.2 Les métriques essentielles

Avant de comprendre les pièges, il faut comprendre les outils de mesure. Voici les 8 métriques que tu dois savoir lire sans hésitation.

### Sharpe ratio annualisé

Le ratio Sharpe est le rendement excédentaire divisé par l'écart-type des rendements, annualisé.

```
Sharpe = (mean(returns) - rf) / std(returns) × sqrt(N)
```

Où `N` est le nombre de périodes par an (252 pour daily, 8760 pour hourly, etc.) et `rf` le taux sans risque (souvent ignoré en crypto pour simplifier).

**Lecture intuitive** :
- Sharpe < 0.5 : stratégie médiocre, à abandonner
- Sharpe 0.5-1.0 : stratégie marginale, possiblement chanceuse
- Sharpe 1.0-1.5 : stratégie correcte pour retail
- Sharpe 1.5-2.0 : très bon, niveau hedge fund moyen
- Sharpe 2.0+ : exceptionnel, à inspecter pour overfit
- Sharpe 3.0+ : presque toujours overfit, ou tu as découvert quelque chose

Pour contexte : le S&P 500 sur 30 ans a un Sharpe autour de 0.5. Renaissance Technologies a un Sharpe rumored autour de 2.0 sur Medallion (et n'accepte pas d'argent extérieur). Les hedge funds quant crypto en 2026 affichent un Sharpe moyen de **1.6** [3].

**Pièges du Sharpe** :
- Il assume des rendements gaussiens — il sous-estime massivement le risque des stratégies à queue épaisse (typique crypto)
- Il pénalise la volatilité à la hausse autant que la baisse (d'où Sortino, ci-dessous)
- Il est facilement manipulable en jouant sur la fréquence d'échantillonnage

### Sortino ratio

Variante du Sharpe qui ne compte que la volatilité des rendements négatifs (downside deviation). Plus juste pour les stratégies qui ont des gains explosifs (typique crypto bull).

```
Sortino = (mean(returns) - rf) / downside_std(returns) × sqrt(N)
```

Si Sortino >> Sharpe, ça veut dire que tes returns positifs sont volatiles (ce qui n'est pas un problème). Si Sortino ≈ Sharpe, ta vol est symétrique. La règle de pouce : un Sortino 30-50 % au-dessus du Sharpe est sain.

### Max drawdown (DD)

Plus grosse chute en pourcentage depuis un sommet de l'equity curve. C'est la métrique que **ton ventre** ressent, pas ton esprit.

```
DD = (current_equity - running_max(equity)) / running_max(equity)
max_DD = min(DD) sur toute la période
```

**Lecture intuitive crypto** :
- DD < 10 % : très conservateur, possible sur stratégies très diversifiées
- DD 10-20 % : zone confortable retail
- DD 20-30 % : zone difficile psychologiquement, beaucoup de retail capitule
- DD 30-50 % : zone de hedge fund volatile (crypto natural)
- DD > 50 % : presque tout le monde abandonne, même institutionnels

Règle anecdotique mais robuste : **le DD live est typiquement 1.5x à 2.5x le DD backtest**. Si ton backtest dit 10 %, prévois 15-25 % en live.

### Calmar ratio

Rendement annualisé divisé par max drawdown. Mesure la "qualité" du return par rapport à la douleur.

```
Calmar = CAGR / |max_DD|
```

- Calmar 1.0 : ok pour retail
- Calmar 2.0+ : très bon
- Calmar 3.0+ : exceptionnel, à inspecter

### Profit Factor (PF)

Somme des gagnants divisée par valeur absolue de la somme des perdants.

```
PF = sum(wins) / |sum(losses)|
```

- PF < 1.0 : stratégie perdante
- PF 1.0-1.3 : marginale, sensible aux frais
- PF 1.3-1.7 : viable
- PF 1.7-2.5 : très bon
- PF > 3.0 : presque toujours overfit en backtest

V2 actuel : **PF OOS+friction de 2.09 weighted average** (1.64 bull / 2.54 bear). C'est dans la zone "viable à très bon" — pas miraculeux, pas overfit non plus.

### Win Rate (WR)

Pourcentage de trades gagnants. **C'est la métrique la plus surestimée du retail.** Une stratégie avec WR 30 % et RR 1:5 peut être très profitable. Une stratégie avec WR 80 % et RR 1:0.2 peut être catastrophique. Toujours coupler WR à RR ou PF.

### MAR ratio (Managed Account Ratio)

Variante du Calmar utilisée dans l'industrie CTA. CAGR / max DD historique.

### Expectancy

Espérance mathématique par trade : `E = (WR × avg_win) - ((1 - WR) × avg_loss)`. Si E ≤ 0, stratégie morte.

## 1.3 Le grand piège : l'overfitting

L'overfitting (sur-ajustement) est le fait de coder une stratégie qui colle si bien aux données passées qu'elle n'a plus aucune chance de marcher sur des données futures. C'est **la cause N°1 d'échec en algo trading retail** [4].

Comment ça arrive :
1. Tu lances un backtest, le résultat est mauvais
2. Tu ajustes un paramètre, tu relances, c'est mieux
3. Tu ajustes un autre paramètre, encore mieux
4. Au bout de 50 itérations, ton backtest est magnifique
5. En live, c'est une catastrophe

Le piège est que tu n'as pas **codé une stratégie** — tu as **mémorisé l'historique**. Tes paramètres encodent les particularités du passé, qui ne se reproduiront pas à l'identique.

Marcos Lopez de Prado, dans *Advances in Financial Machine Learning* [5], formalise ça : **chaque variation de stratégie que tu testes est une hypothèse implicite**. Tester 100 variations et garder la meilleure, c'est comme tester 100 hypothèses statistiques et n'en publier qu'une — le biais de sélection rend le résultat sans valeur statistique.

### Comment se protéger

**Règle 1 — Séparation stricte train/test.** Ne touche jamais aux paramètres en regardant les données de test. C'est plus dur que ça en a l'air parce que tu vas vouloir "juste vérifier" en cas de doute. Ne fais pas.

**Règle 2 — Walk-forward analysis.** Voir section 1.4.

**Règle 3 — Garde un troisième set "Sacrosaint".** Une fenêtre de données que tu n'as JAMAIS regardée ni touchée. Tu la regardes uniquement pour la validation finale, et tu acceptes le résultat même s'il est mauvais.

**Règle 4 — Diminue la flexibilité de la stratégie.** Moins ta stratégie a de paramètres tunables, moins elle peut overfitter. La stratégie idéale a 0-2 paramètres libres. ICC/SMC tels que nous les implémentons (W=3 lookback, RR=2.5 OB target, RR=3 measured move) ont 3 paramètres pris dans la spec ICC, pas tunés sur les données — c'est une vertu.

**Règle 5 — Logique économique d'abord.** Si tu ne peux pas expliquer en une phrase pourquoi ta stratégie *devrait* faire de l'argent (à un niveau de causalité économique), méfie-toi.

**Règle 6 — Lopez de Prado recommande Combinatorial Purged Cross-Validation (CPCV)** [6]. Au lieu d'un seul walk-forward, tu construis systématiquement de nombreux découpages train/test, tu purges les échantillons qui se chevauchent temporellement, et tu ajoutes une "embargo period" entre train et test pour éviter toute fuite d'information. Le résultat est une distribution d'estimateurs OOS plutôt qu'un seul nombre — beaucoup plus informatif.

### Look-ahead bias

Cas particulier de tricherie inconsciente : utiliser une donnée du futur pour décider à un moment du passé. Exemple typique : tu calcules un indicateur "moving average" centré sur le bar courant — qui inclut donc des bars du futur. Tu te retrouves avec un backtest splendide qui s'effondre en live.

V2 a passé un audit formel no-lookahead (voir `docs/NO_LOOKAHEAD_AUDIT.md`). Chaque détecteur ICC (structure, OB, cycle) confirme les événements avec un lag `bar_index + W`, et toutes les fonctions de décision filtrent strictement les structures par `confirmed_at_bar <= current_bar`. C'est techniquement clean.

### Survivorship bias

Tester ta stratégie sur l'univers des cryptos qui existent aujourd'hui, c'est tester sur les **survivants**. Tu n'as pas dans ton dataset les coins qui ont mis 99 % et n'existent plus. Donc ton backtest est par construction biaisé optimiste.

Mitigation : tester sur un panier large incluant des coins qui ont sous-performé ou disparu. Pas toujours possible — on accepte le biais avec lucidité. Pour V2, on trade sur des majors (BTC/ETH/SOL/...) qui n'ont pas de risque de disparition à court terme, donc le biais est limité.

## 1.4 Walk-forward analysis — la méthode et ses limites

Le walk-forward est la version pratique de la séparation train/test. L'idée :
1. Tu prends 12 mois de données pour "training" — c'est juste du contexte historique (pas de tuning car la stratégie n'a pas de paramètres tunables)
2. Tu testes la stratégie sur les 6 mois suivants ("test window")
3. Tu glisses la fenêtre de 3 mois et tu recommences
4. Tu agrèges les performances de toutes les fenêtres de test (pas de training)

Sur V2, on utilise 12m train / 6m test / 3m step. Sur 24 mois de données (2024-25 ou 2022-23), ça donne **2 fenêtres de test indépendantes**. C'est peu. Pour une validation rigoureuse, il faudrait 4-5 ans de données et 8-10 fenêtres.

### Limites du walk-forward classique

L'article *"Interpretable Hypothesis-Driven Trading"* [7] récent souligne que le walk-forward unique est lui-même biaisé : tu testes une seule séquence temporelle, et les résultats dépendent fortement de cette séquence. Si tu décalais ton step de 1 mois, tu aurais des résultats différents.

D'où l'intérêt du **Combinatorial Purged Cross-Validation** [6] de Lopez de Prado : au lieu d'un seul chemin temporel, tu en explores des centaines. Tu obtiens une distribution. Si la médiane de cette distribution est mauvaise, tu sais que ton edge n'est pas robuste.

Sur V2, on n'a pas encore implémenté CPCV — c'est une amélioration à faire après l'absence. Le walk-forward classique qu'on tourne est déjà une amélioration énorme par rapport à l'in-sample plein (qui sur-estimait V1 de 82 % en PnL et 57 % en PF, voir nos chiffres).

## 1.5 Position sizing : Kelly criterion et fractional Kelly

**La taille de ta position est aussi importante que la décision de prendre la position.** Une stratégie avec une espérance positive peut quand même te ruiner si tu sizes mal.

Le Kelly criterion donne la taille optimale pour maximiser la croissance long-terme du capital :

```
f* = (W × R - L) / R
   = (mean_return / variance_return)   (forme continue)
```

Où W est la probabilité de gain, R le ratio gain/perte, L = 1-W. f* est la fraction du capital à parier.

**Le problème de Kelly "plein" en crypto** : il assume une connaissance parfaite des probabilités. La crypto est volatile, les estimées sont bruitées, et **surestimer ton edge de 10 % double potentiellement ta taille de position recommandée** [8]. Résultat : drawdowns catastrophiques.

D'où la pratique universelle du **fractional Kelly** :
- **Half Kelly (0.5 × f*)** : le standard. ~75 % du growth rate, ~50 % du DD. Bon pour stratégies bien établies.
- **Quarter Kelly (0.25 × f*)** : pour les stratégies plus incertaines ou les marchés très volatiles (crypto). ~50 % du growth rate, DD très réduit. **C'est ce que je recommande pour V2.**

En pratique sur V2 : on a 4 actifs filtrés (ETH/LTC/AVAX/SOL). Avec un Sharpe estimé de 1.0-1.4 en live et un capital de $50k, Quarter Kelly suggérerait environ 8-12 % par position simultanée. C'est compatible avec une allocation "fixed fractional" simple à 10 %/asset.

**Le Kelly s'applique aussi au funding capture** mais avec une particularité : c'est delta-neutre, donc le "risk" n'est pas le mouvement de prix mais le funding flip + slippage. La taille peut être bien plus grande sans risque équivalent.

## 1.6 Signal vs bruit

La dernière fondation que je veux te poser : **tout edge en trading est petit**.

Quand un retail dit "j'ai un edge de 60 % WR", il confond souvent le WR backtest avec son espérance live. Une stratégie qui te fait gagner 51 % du temps avec un RR 1:1 est, mathématiquement, juste profitable. Elle te fera passer par des drawdowns horribles.

Edward Thorp, le père du card counting au blackjack puis du quantitatif financier, gagnait au blackjack avec un edge de **0.5-1 %**. Il s'est enrichi. Pas grâce à un gros edge, mais grâce à un edge stable, traité avec Kelly, sizing rigoureux, et discipline.

Renaissance Technologies — le hedge fund qui a le meilleur track record de l'histoire — ne révèle rien, mais les ex-employés affirment que leurs trades individuels gagnent un peu plus de 50 % du temps. Pas 70 %, pas 80 %. **51-53 %**. Multiplié par des millions de trades par an, ça fait Medallion Fund.

**Implication pour V2** : si on découvre que notre edge live est de Sharpe 0.8 (ce qui est plausible vu nos chiffres OOS), ce n'est PAS un échec. C'est un edge réel mais petit. La discipline (sizing, sangs-froid en drawdown, ne pas surajuster) est ce qui transforme un petit edge en P&L significatif.

## 1.7 À retenir pour V2

1. **Toujours qualifier les chiffres avec les 4-qualifiers** : méthodo (walk-forward OOS vs in-sample), friction (ON/OFF), fenêtre temporelle, régime (bull/bear/range).
2. **Le Sharpe live attendu est 30-50 % en dessous du Sharpe backtest brut.** Calibre tes attentes.
3. **Le DD live est 1.5-2.5x le DD backtest.** Pareil.
4. **Quarter Kelly pour le sizing.** Sur $50k = 10-12 % par position max.
5. **Garder une fenêtre "Sacrosainte" non touchée** — par exemple 2026-H2 dès qu'on a les données — pour validation finale avant déploiement capital.
6. **Implémenter CPCV à terme** (après l'absence) pour distinguer un vrai edge d'un edge de hasard.
7. **Ne pas chercher à augmenter le WR au prix du PF.** WR seul est trompeur.

---

# Partie 2 — Microstructure crypto

## 2.1 Spot vs perpetual : pourquoi 80 % des volumes sont perp

Le marché crypto a une particularité absente du TradFi classique : il est **dominé par les perpétuels**. En 2026, les contrats perpétuels représentent 80 %+ du volume crypto total [9]. Le spot (achat-vente direct du token) est devenu secondaire.

**Pourquoi ?**
- Les perpétuels permettent du levier (jusqu'à 50-100x sur certaines plateformes)
- Ils permettent le short sans avoir à emprunter le token
- Ils sont accessibles 24/7 sans expiration
- Les frais sont plus bas que sur les futures à échéance (moins de roll cost)

**Conséquence** : le **price discovery** ne se fait plus sur le spot, il se fait sur le perp. Le perp bouge, le spot suit. Quand tu lis "BTC a fait +5 % aujourd'hui", c'est le marché perp qui a fait +5 % en premier.

Cette domination du perp est ce qui rend les **funding rates** centraux — section 2.2.

## 2.2 Funding rates : le cœur du carry crypto

Un perpetual contract n'a pas d'expiration, mais il doit quand même refléter le prix spot. Sans mécanisme de correction, le prix perp dériverait. Le **funding rate** est le mécanisme correcteur [10].

**Mécanique** :
- Toutes les 8h sur la plupart des CEX (Binance, Bybit, OKX), **toutes les heures sur Hyperliquid**
- Si perp > spot (les longs dominent) → funding **positif** → longs paient shorts
- Si perp < spot (les shorts dominent) → funding **négatif** → shorts paient longs

**Pourquoi c'est rentable à exploiter** :
- En période bull, les retail sont long perp pour le levier → funding positif persistant
- Tu peux capturer ce funding en étant **delta-neutre** : long spot + short perp simultanés
- Tu reçois le funding tant que tu tiens la position, sans exposition directionnelle

**Chiffres réalistes 2026** :
- BTC/ETH funding net : 3-12 % APR [11]
- Mid-caps (SOL, AVAX, HYPE) : 20-60 % APR
- Long-tail (memes, listings récents) : 30-80 % APR en pic

**Ce qui peut casser le carry** :
1. **Funding flip négatif** : pendant un selloff brutal, les longs se font liquider, le perp drop sous le spot, le funding devient négatif. Ton "passif" devient un coût.
2. **Liquidation de la jambe short perp** : si tu n'as pas assez de collateral et que le marché pump fort, ton short se fait fermer forcé. Ton "delta-neutre" devient une exposition long pure dans le pire moment.
3. **Smart contract risk** : si tu utilises un DEX (Hyperliquid notamment), tu portes le risque protocole.
4. **Coût opportunité** : ton capital est immobilisé en spot + collateral perp. Si l'asset pump 50 %, tu ne captures que le funding, pas le mouvement.

## 2.3 Liquidation cascades : la dynamique des crashes éclair

Les crashes crypto ne sont pas "comme" les crashes equities — ils sont **techniquement différents** à cause de l'effet liquidation cascade.

**Mécanique** :
1. Le marché baisse de quelques %
2. Les longs avec gros levier (10-50x) atteignent leur marge de maintenance
3. L'exchange liquide leurs positions automatiquement (vente forcée)
4. Cette vente forcée pousse le prix encore plus bas
5. La nouvelle baisse liquide d'autres longs un peu moins exposés
6. Boucle de rétroaction → flash crash

L'événement le plus marquant en 2026 : **10-11 octobre 2025, ~$20 milliards de liquidations en quelques heures** [12]. Le marché a perdu 15-20 % en moins d'une journée avant de rebondir.

Pour ton funding capture sur V2 :
- En théorie tu es delta-neutre donc protégé
- En pratique, en plein liquidation cascade, **les spreads spot-perp explosent**, ta short perp peut se faire "auto-deleverage" même si tu es bien collateralisé
- Le funding peut flipper massivement négatif en quelques minutes

**Mitigation V2** :
- Levier max 1x sur la jambe perp (pas de marge utilisée)
- Sortie automatique si funding smoothed bascule négatif (déjà codé dans la logique)
- Surveiller les périodes connues de fragilité (CPI US, FOMC, weekends asiatiques)

## 2.4 Hyperliquid en détail

Pourquoi on a choisi Hyperliquid plutôt que Binance ou Bybit pour le funding capture :

**1. Frais structurellement plus bas**

| Plateforme | Maker | Taker |
|---|---|---|
| **Hyperliquid** | **0.015 %** | **0.045 %** |
| Binance | 0.020 % | 0.050 % |
| Bybit | 0.020 % | 0.055 % |
| OKX | 0.020 % | 0.050 % |

Sur 100 trades round-trip par mois, l'économie Hyperliquid vs Binance est de ~10 bps/trade = 100 bps cumulés. Sur $100k de notional, $1 000 économisés par mois rien que sur les frais. [13]

**2. Funding payé toutes les heures** (vs 8h sur CEX)

Plus de granularité, moins de "saut" sur les payments, meilleure adaptation aux régimes courts.

**3. On-chain order book**

Hyperliquid est un **DEX** au sens strict : tous les ordres, exécutions, liquidations sont on-chain, vérifiables. Pas de fonds custodiens, tu gardes tes clés (via wallet personnel).

**4. Architecture HyperBFT**

C'est une variante de Byzantine Fault Tolerant consensus inspirée de HotStuff [14]. Optimisée pour le trading : 0.2s de finalité moyenne, 200 000 ordres/seconde théoriques. C'est **plus rapide que la plupart des CEX**, ce qui est presque comique pour un DEX.

**5. HyperEVM**

Hyperliquid a aussi un EVM (Ethereum Virtual Machine) latéral pour les smart contracts. C'est l'écosystème DeFi qui se construit autour. À surveiller pour des opportunités composables (lending, options, etc.).

### Les risques propres à Hyperliquid

- **Jeune** : L1 lancé fin 2024, encore en phase de découverte de ses propres limites
- **HLP incident début 2025** : le pool de liquidité interne a connu une crise sérieuse (heureusement gérée). C'est typique d'un L1 jeune.
- **Concentration HYPE** : 97 % des frais financent les buybacks du token HYPE — c'est très centralisé sur la santé d'un seul token natif
- **Régulation incertaine** : MiCA Europe a des règles peu claires pour DEX onchain. À surveiller.

## 2.5 Kraken et les CEX historiques

Kraken est notre source de données historiques pour les backtests ICC. Quelques notes :

- **Données spot disponibles** depuis 2013 sur BTC, 2015 sur ETH. C'est pourquoi V2 peut backtester sur des fenêtres bear lointaines (2018, 2022).
- **Frais Kraken** : 0.16 % maker / 0.26 % taker (vs HL 0.015/0.045) — beaucoup plus chers. C'est pour ça que Kraken n'est pas envisagé pour exécution active, mais reste utile pour data + spot leg du funding capture.
- **Pas de funding rate** sur Kraken (c'est du spot pur, pas de perp). Si on voulait du multi-venue arb, on utiliserait HL pour le perp et Kraken pour le spot.

## 2.6 Slippage : modéliser réalistement

Le slippage est la différence entre le prix attendu (l'ask/bid affiché) et le prix effectif obtenu. Sur un marché liquide pour un petit ordre, slippage ≈ demi-spread. Sur un gros ordre ou un marché fin, c'est beaucoup plus.

**Modèle simplifié pour V2** (codé dans `_apply_friction`) :
- BTC, ETH : médiane 3.5 bps
- Mid-caps (DOT, AVAX, LINK, LTC) : 11 bps
- ADA, SOL (vol pics fréquents) : 22 bps

Ces chiffres viennent de l'analyse Corwin-Schultz du spread bid-ask historique 2y de Hyperliquid [15].

**Distribution lognormale** : on tire chaque slippage trade-par-trade d'une lognormale autour de la médiane avec σ=0.5. Ça reproduit la queue droite (de temps en temps, un trade paye 2-3x la médiane). Pour le funding capture sur majors, c'est conservateur.

**Ce que le modèle ne capture PAS** :
- Slippage extrême en liquidation cascade (peut être 50-200 bps)
- Slippage de gros ordres (si V2 grossit à $500k+, ils créeront leur propre slippage)
- Slippage sur les transitions de régime (la première heure après une annonce CPI a 5-10x la slippage normale)

Pour Phase 2 (broker démo réel), on calibrera le modèle sur les exécutions réelles observées.

## 2.7 À retenir pour V2

1. **Le perp est le centre du marché crypto**, pas le spot. Le funding rate en est la conséquence directe.
2. **Le funding capture sur Hyperliquid en delta-neutre est un edge structurel**, pas une stratégie directionnelle. APR 3-12 % sur majors, 20-60 % sur mid-caps.
3. **Hyperliquid a des frais beaucoup plus bas que les CEX classiques** — c'est un vrai avantage compétitif sur le long terme.
4. **Les liquidation cascades sont la principale menace** pour les stratégies delta-neutres. Pas de levier > 1x sur la jambe perp.
5. **Le slippage modélisé est lognormal**, queue droite — donc certains trades coûtent 2-3x la médiane. Ne pas l'oublier en lisant les chiffres backtest.

---

# Partie 3 — La méthodologie ICC/SMC

## 3.1 Lignée historique : Wyckoff → ICT → SMC → ICC

Le SMC (Smart Money Concepts) que V2 implémente n'est pas nouveau. C'est l'aboutissement d'une lignée de 100 ans.

**Richard Wyckoff (1873-1934)** : trader américain qui a publié dans les années 1920-30 une méthodologie pour "trader comme les Composite Operators" (les gros opérateurs anonymes derrière les mouvements). Wyckoff identifie trois lois :
- **Loi de l'offre et la demande** : prix monte quand demande > offre, et vice-versa
- **Loi de cause et effet** : la longueur d'une accumulation ou distribution détermine l'amplitude du mouvement suivant
- **Loi d'effort et résultat** : si beaucoup d'effort (volume) mais peu de résultat (prix qui ne bouge pas), retournement probable

Wyckoff définit les phases de marché classiques : **accumulation → markup → distribution → markdown**. C'est encore aujourd'hui le squelette implicite de tout SMC. [16]

**Michael Huddleston aka "ICT" (Inner Circle Trader, 2000s)** : trader américain qui reprend Wyckoff, ajoute des concepts plus précis (Order Blocks, Fair Value Gaps, Liquidity Pools, Killzones temporelles), et popularise la méthode via des vidéos YouTube. ICT est controversé — beaucoup pensent qu'il vend du rêve à des retail désespérés. Mais ses concepts techniques sont précis. [17]

**SMC (Smart Money Concepts, 2018-2024)** : nom plus généraliste donné à la méthodologie ICT par la communauté trader (Twitter, Discord, TradingView). Devient viral. Indicateurs LuxAlgo, Zeiierman, etc. cristallisent la méthode en logiciel.

**ICC (Indication-Correction-Continuation)** : la version française popularisée par TradesSAI, plus récente (2022-2024). Spécification écrite et formalisée. C'est cette spec que V2 implémente fidèlement (cf. `docs/ICC_SPEC.md` dans le repo).

## 3.2 Les concepts clés de SMC/ICC

Si tu as lu LuxAlgo, ICT, ou les vidéos TradesSAI, tu connais déjà. Pour les autres :

### Market Structure : HH, HL, LH, LL

Le prix dans une tendance haussière fait des **Higher Highs** (HH) et **Higher Lows** (HL). Dans une baissière, **Lower Lows** (LL) et **Lower Highs** (LH).

Sur V2, ces structures sont détectées via des swings : un swing high est confirmé si le close d'une bougie est le maximum sur une fenêtre de 2W+1 bougies (avec W=3, donc fenêtre de 7 bougies). Voir `strategies/icc_structure.py`.

### CHoCH (Change of Character)

Premier signal de retournement. Dans une tendance baissière, quand le prix casse pour la première fois un LH précédent (en faisant un body close au-dessus), c'est un **CHoCH bullish** — la "personnalité" du marché change. C'est ce que V2 appelle un `NEW_HIGH`.

### BOS (Break of Structure)

Une fois la tendance retournée, chaque nouveau HH ou LL qui confirme la nouvelle tendance est un **BOS**. V2 les appelle `HH` (en bull) et `LL` (en bear).

### Order Block (OB)

L'idée clé : avant un mouvement impulsif (qui casse une structure), il y a souvent **une dernière bougie de direction opposée**. Cette bougie est "l'Order Block" — supposément là où "les institutionnels ont accumulé/distribué" avant de lancer le mouvement.

Quand le prix retourne tester cet Order Block plus tard, il y a souvent un retournement (en théorie SMC). C'est un point d'entrée privilégié.

V2 détecte les OBs avec validations : minimum 3 bougies de mouvement, présence d'un Fair Value Gap, et break de structure derrière (sinon non valide). Voir `strategies/icc_orderblocks.py`.

### Fair Value Gap (FVG)

Un "gap" de 3 bougies : si le low de la bougie i+2 est au-dessus du high de la bougie i, il y a un "espace" entre les deux que le marché n'a pas vraiment exploré. En théorie SMC, le prix revient souvent combler ce gap.

### Liquidity Sweep / Stop Hunt

Avant un mouvement majeur, les institutionnels "balayent" les liquidités évidentes (stop-loss au-dessus des HH récents, par exemple). Le prix fait une fausse cassure, ramasse les liquidités, puis se retourne fortement dans la direction opposée. C'est le pattern le plus discuté dans la communauté SMC.

V2 ne détecte pas explicitement les liquidity sweeps — c'est une amélioration possible.

### Discount / Premium zones

Une fois identifié un range (entre un HH actif et un LL actif), le 50 % de ce range est l'**equilibrium**. Au-dessus = **premium** (zone de vente), en-dessous = **discount** (zone d'achat). V2 utilise ce concept dans `classify_discount_premium`.

## 3.3 La cascade multi-timeframe

Le squelette ICC tel que V2 l'implémente :
- **Daily** : donne le **bias** (BULL / BEAR / NEUTRAL) — direction macro
- **H4** : donne l'**indication** (CHoCH avec OB valide) — confirme un setup potentiel
- **H1** : donne l'**entry** (correction + cassure micro-structure) — déclenche l'ordre

C'est une cascade de filtres : tu ne trades que les setups où les 3 TFs s'alignent. Dans la spec ICC, c'est ce qui distingue les "vrais" trades des "patterns" décoratifs.

Le piège, c'est que cette cascade **divise par 10 ou 100 le nombre de setups** par rapport à du trading sur une seule TF. V2 fait ~30-50 trades par actif sur 2 ans — soit ~15-25 trades/an/actif. C'est peu, mais c'est cohérent avec la philosophie "qualité > quantité".

## 3.4 La critique honnête du SMC

J'ai cherché de la littérature académique sur le SMC. Verdict honnête : **il n'y en a quasiment pas**. SMC est une méthode largement vendue par des éducateurs trading, pas une discipline académique avec des papiers peer-reviewed [18].

Ça ne veut pas dire qu'elle ne marche pas. Ça veut dire qu'on ne sait pas, statistiquement, dans quelle mesure ça marche.

Les arguments POUR la validité du SMC :
1. **Wyckoff est ancien et validé empiriquement** sur 100 ans de marchés. Les concepts de fond (offre/demande, accumulation/distribution) sont solides.
2. **Les institutionnels laissent vraiment des traces** : ordres limites visibles sur l'order book, dark pools qui sortent à des moments spécifiques, etc. Pas tout détectable par le retail, mais l'idée n'est pas absurde.
3. **V2 lui-même produit des chiffres OOS+friction positifs** sur 2 régimes différents (Sharpe 0.84 bull, 1.07 bear sur univers complet ; 2.22 / 1.07 sur univers filtré). Si c'était purement aléatoire, on aurait du Sharpe proche de 0.

Les arguments CONTRE :
1. **Le SMC est massivement retroactif**. Les indicateurs SMC sur TradingView affichent les structures APRÈS qu'elles soient confirmées. C'est très différent de trader en avant.
2. **Le confirmation bias est massif**. Quand tu lis des analyses SMC sur Twitter, tu vois "voilà comment les institutionnels ont liquidé les retail" — mais tu ne vois jamais les setups qui n'ont rien donné, et il y en a 80 %.
3. **Beaucoup de "patterns" sont post-hoc** : tu peux toujours trouver un Order Block qui "justifie" un retournement après coup. Le vrai test, c'est de prédire à l'avance.
4. **La méthode est très populaire** — Mind Math Money, LuxAlgo, SMRT Algo, des milliers de Discord. Quand une méthode devient grand public, son edge s'érode (loi générale).
5. **L'analyse en 2026** : *"les patterns qui fonctionnent en backtest fonctionnent rarement de la même manière en temps réel"* [19] — c'est exactement le piège que V2 a évité grâce au walk-forward OOS+friction.

### Position honnête sur V2

V2 a un edge SMC mesuré OOS+friction. C'est plus qu'on ne peut dire de 95 % des bots retail. Mais cet edge est **modeste** (Sharpe live attendu 0.8-1.2 après haircut paper→live) et **partiellement chance** (l'univers filtré ETH/LTC/AVAX/SOL est une sélection a posteriori — biais possible).

La question pertinente n'est pas "ICC marche ou pas". C'est : "Est-ce que cet edge survit le passage du paper au live ? Survit-il un changement de régime ? Survit-il l'augmentation de la concurrence retail SMC en 2026-2027 ?"

Mon prior actuel : **probabilité de survie 60-70 %**. Pas plus, pas moins.

## 3.5 Ce que V2 devrait reconsidérer

Sans être destructeur, voici trois questions qui méritent d'être posées à ton retour le 3 juin :

**1. La cascade Daily/H4/H1 est-elle optimale ?**

Le SMC traditionnel utilise plutôt Daily / H4 / H1 pour swing trading, et H4 / H15 / M1 pour intraday. V2 implémente le mode swing (le plus robuste mais le moins fréquent). Les chiffres OOS suggèrent que c'est défendable. Mais on n'a jamais comparé avec un mode INTRADAY ou MIXED. À évaluer.

**2. Le filtrage d'univers à 4 actifs est-il un edge ou un overfit ?**

ETH/LTC/AVAX/SOL ont été choisis APRÈS observation des résultats OOS (BTC/ADA/DOT/LINK perdaient sur la fenêtre bull 2024-25). C'est un soft data peeking. **À valider sur une 3ème fenêtre temporelle** non touchée (par exemple, 2020-2021, ou H2 2026 quand on aura les données).

**3. Faut-il intégrer un détecteur de Liquidity Sweep ?**

C'est le pattern SMC le plus discuté en pratique et V2 ne le détecte pas. Implémenter ça pourrait soit améliorer la précision des entrées, soit révéler que ça n'apporte rien et qu'on overfit en ajoutant des features. À tester rigoureusement.

## 3.6 À retenir pour V2

1. **SMC/ICC n'est pas une science exacte.** C'est un cadre d'analyse avec des concepts pertinents mais peu validés académiquement.
2. **Wyckoff (les fondations) est solide.** ICT (les détails) est plus contesté.
3. **V2 a un edge SMC mesuré** mais modeste — il faut le respecter sans en faire un dogme.
4. **La popularité de SMC en 2026 érode son edge.** À surveiller : si V2 commence à sous-performer en 2027, ça pourrait venir de là.
5. **Trois pistes d'amélioration** : intraday mode, validation 3ème fenêtre pour l'univers filtré, liquidity sweep detector.

---

# Partie 4 — Funding capture en profondeur

## 4.1 Pourquoi le funding capture est structurellement plus solide que l'ICC

L'edge funding capture vient d'une **structure de marché**, pas d'un pattern.

**Le raisonnement** :
1. Les retail crypto sont structurellement long-biased (ils achètent, ils ne shortent presque pas)
2. Sur les perps, les retail prennent du levier long → funding positif
3. Tant que cette demande structurelle existe, le funding **reste positif en moyenne**
4. Quelqu'un doit prendre l'autre côté du trade → c'est le marché professionnel, dont le funding capture

C'est ce qu'on appelle un **risk premium** : tu es payé pour prendre un risque que personne d'autre ne veut prendre. Ici, le risque est principalement la **liquidation cascade**, où les longs se font tous liquider en même temps et le funding flippe négatif violemment.

**Comparaison ICC vs funding capture** :

| Dimension | ICC | Funding capture |
|---|---|---|
| Type d'edge | Pattern (anomalie comportementale) | Structurel (carry, risk premium) |
| Robustesse | Dépend du régime, érosion possible | Stable tant que retail est long-biased |
| Sharpe live attendu | 0.8-1.2 (estimé) | 1.0-2.0 (selon vol funding) |
| Drawdown attendu | 15-25 % | 5-15 % typique, 30-50 % en cascade |
| Complexité d'exécution | Élevée (multi-TF, SL/TP) | Modérée (delta-neutre) |
| Risque "tail" | Modéré (DD borné par SL) | Élevé (liquidation cascade) |
| Capital efficiency | 1x | 0.5x (besoin collateral) |
| Scalabilité | Bonne (le marché reste liquide) | Limitée (les arbs convergent) |

Mon avis : **funding capture devrait être la stratégie principale de V2 en termes d'allocation capital, même si ICC est plus excitante intellectuellement.**

## 4.2 Construction delta-neutre

La construction classique :
- **Long spot** d'1 BTC (par exemple) sur Kraken ou autre CEX spot
- **Short perp** d'1 BTC sur Hyperliquid (ou autre venue avec funding positif)

Le résultat :
- Si BTC pump de $1k, ton long spot gagne $1k, ton short perp perd $1k → **delta = 0**
- Pendant tout ce temps, tu reçois le funding payé par les autres longs → ton revenu

**Pourquoi delta-neutre n'est pas "vraiment" neutre** :
1. **Basis spread** : le spot et le perp ne sont pas exactement au même prix. Si le basis bouge contre toi entre l'ouverture et la fermeture, tu perds.
2. **Frais d'exécution** : entrée + sortie sur les deux jambes = 4 fees (4 × 4.5 bps = 18 bps round-trip minimum sur HL)
3. **Coût opportunité du capital** : tu mobilises ~$10k de spot + ~$3-5k de collateral perp pour une seule position
4. **Funding flip risk** : si funding flippe négatif et reste négatif plusieurs jours, tu paies plus que tu n'as gagné
5. **Liquidation risk** : si tu utilises du levier sur la jambe perp et que le marché pump violemment, tu peux te faire liquider même en étant "hedged" — ton spot recouvre le perp mais le timing peut être brutal

## 4.3 Régimes de funding

Le funding n'est pas constant. Il a des régimes.

**Régime "carry tranquille" (60-70 % du temps en bull market)** :
- Funding moyen 5-15 % APR sur BTC/ETH
- Vol funding modérée
- Stratégie : capture passive, peu d'entrées/sorties

**Régime "FOMO retail" (10-20 % du temps en bull market)** :
- Funding spike à 50-200 % APR
- Très rentable mais signal de retournement potentiel
- Stratégie : capture agressive mais sortie rapide si fundamentaux changent

**Régime "Squeeze short" (5-10 % du temps en bull market)** :
- Funding négatif (les shorts dominent, attendent un crash)
- Tu peux retourner ta position : long perp + short spot, recevoir le funding "à l'envers"
- Plus rare, plus risqué (basis volatile)

**Régime "Crash / liquidation cascade" (rare mais critique)** :
- Funding flippe négatif violemment
- Si tu es positionné classique (short perp), tu reçois encore du funding mais le basis explose contre toi
- **Risque de liquidation de la jambe perp** si pas assez collatéralisé
- C'est là que les delta-neutre "neutres" se font tuer

## 4.4 Risque liquidation cascade — mesures concrètes

Pour V2 paper trading actuel (et a fortiori pour Phase 2 réel) :

1. **Levier max 1x sur la jambe perp.** Pas d'optimisation de capital. Tu mobilises 1 BTC de spot + 1 BTC notional de perp avec 100 % de collateral.
2. **Sortie automatique si funding smoothed < seuil** (déjà codé : `exit_threshold_apr = -0.005` = -0.5 % APR).
3. **Pas de tenue de position pendant les événements macro connus** (FOMC, CPI US). À implémenter — calendrier économique à intégrer.
4. **Diversification cross-asset** : ne pas être positionné en delta-neutre sur 100 % du capital en BTC seul. Splitter entre BTC/ETH/SOL/HYPE pour décorréler les liquidation risk.
5. **Stop-loss dur sur le PnL paper** : si le PnL combiné des positions delta-neutres descend en-dessous de -5 % du capital, on coupe tout. C'est l'équivalent du circuit breaker industriel.

## 4.5 Cross-venue arbitrage : aller plus loin que V2 actuel

V2 actuel fait du carry **single-venue** (Hyperliquid + spot Kraken implicitement). On peut faire mieux : **cross-venue funding arb**.

**Principe** :
- Hyperliquid a un funding à X % APR (positif)
- Bybit a un funding à Y % APR (positif, mais plus bas)
- Tu prends short perp Hyperliquid (recevoir X) + long perp Bybit (payer Y) → tu collectes (X - Y) sans exposition spot du tout
- C'est encore plus capital-efficient car pas besoin de spot

**Mais** :
- Spread X - Y est typiquement petit (2-5 % APR sur majors)
- Frais sur les deux venues
- Liquidation risk doublé (deux comptes perp)
- Complexité d'exécution beaucoup plus grande (deux APIs à synchroniser)

**Pour V2** : pas une priorité immédiate, mais à explorer après validation du single-venue. C'est là qu'on commence à toucher au territoire des hedge funds quant. [20]

## 4.6 Chiffres réalistes attendus

Sur la base des recherches publiques 2026 :

**APR net après frais et slippage, single-venue HL** :
- BTC, ETH : **3-12 % APR**
- SOL, AVAX : **8-25 % APR**
- HYPE (token natif HL) : **20-50 % APR**
- Mid-tail (DOT, LINK, LTC) : **5-20 % APR**

**Sharpe attendu** : 1.2-1.8 sur portefeuille diversifié BTC/ETH/SOL (3 assets). Plus de diversification possible avec mid-caps mais plus de tail risk.

**Drawdown attendu** : 5-10 % en régime tranquille, 20-40 % en cas de crash crypto majeur (genre événement type oct 2025).

**Effort opérationnel** : très faible une fois le système en place. Le funding capture est presque "set and forget". C'est pour ça que c'est attractif pour V2 — tu peux le faire tourner avec une attention humaine minimale.

## 4.7 À retenir pour V2

1. **Funding capture > ICC en termes de robustesse d'edge.** L'edge structurel est plus fiable qu'un edge pattern.
2. **Sharpe attendu live 1.2-1.8** sur portefeuille BTC/ETH/SOL diversifié.
3. **Le tail risk est la liquidation cascade.** Pas de levier, sortie automatique funding négatif, diversification, circuit breaker.
4. **Cross-venue arb** est l'évolution naturelle après validation single-venue.
5. **Faible effort opérationnel** une fois en place → idéal pour un solo trader avec attention limitée.

---

# Partie 5 — Engineering & opérations

## 5.1 Backtest vectorisé vs event-driven

Il y a deux familles de backtest engines :

**Vectorisé (pandas/numpy)** :
- Tu calcules les positions sur tout l'historique en une seule passe
- Tu multiplies positions × returns pour avoir le PnL
- Très rapide (millions de bougies en quelques secondes)
- Mais **abstrait** : tu n'as pas la séquence des décisions, juste le résultat final
- Risque de bugs subtils (look-ahead facile à introduire si tu utilises `.shift()` mal)

**Event-driven** :
- Tu itères bar-par-bar, chaque décision est prise dans l'ordre temporel
- Beaucoup plus lent (mais fast enough pour la plupart des usages)
- Plus naturel pour des stratégies à état (open positions, trailing SL, partial closes)
- Plus difficile d'introduire un look-ahead par erreur

V2 utilise les deux :
- `backtest/directional_engine.py` est vectorisé (pour trend following / mean reversion / momentum)
- `strategies/icc_cycle.py` (`run_icc_cycle`) est event-driven (pour ICC swing avec état complexe)

C'est le bon design : choisir le moteur selon la complexité de la stratégie.

## 5.2 Architecture d'un bot de production

Un bot de prod a 5 couches :

1. **Data layer** : fetch données (REST, WebSocket), normalisation, persistence
2. **Strategy layer** : logique de décision, indicateurs, signaux
3. **Risk layer** : sizing, exposure limits, circuit breakers
4. **Execution layer** : translation décisions → ordres, retries, idempotency
5. **Monitoring layer** : logs, alerts, métriques temps réel

V2 actuel a les couches 1, 2, et 5 bien définies (data dans `data/`, strategy dans `strategies/`, monitoring dans `paper_trading/monitoring.py`). La couche **risk** est minimale et la couche **execution** est virtuelle (paper trading).

Pour Phase 2 (broker démo), il faudra :
- **Implémenter la couche risk** : sizing dynamique (Kelly fractionnel), exposure cross-asset, kill switch
- **Implémenter la couche execution** : connexion API broker, gestion retries, idempotency keys (chaque ordre a un ID unique pour éviter les doubles)

## 5.3 Monitoring et alerting — best practices

V2 actuel a :
- **JSON Lines logger** : un événement par ligne, format structuré, rotation quotidienne
- **Telegram alerter** : alertes critiques, best-effort (failure ≠ crash)
- **Heartbeat file** : timestamp du dernier loop réussi
- **Watchdog process** : surveille la fraîcheur du heartbeat, alerte si > 2h

C'est un setup professionnel. Quelques améliorations possibles :

1. **Métriques sur Prometheus** : si tu veux grapher historiquement les métriques (PnL, latence API, errors), Prometheus + Grafana est la stack standard. Overkill pour Phase 1 mais utile à terme.

2. **Sentry pour les exceptions** : si le daemon crash, capturer le stack trace dans un service externe (Sentry est le plus populaire). Tu reçois un email/Slack à chaque crash avec le contexte complet.

3. **Logs structurés vers ELK ou Datadog** : pour pouvoir requêter "tous les trades ouverts sur ETH en mars" en une commande. À considérer si V2 devient SaaS.

4. **Health checks externes** : un service comme Healthchecks.io qui te ping si le daemon arrête de signaler "I'm alive". Backup au watchdog interne.

## 5.4 Persistence et crash recovery

Règles de fer pour un bot de prod qui tourne 24/7 :

**1. Append-only ledgers.**

Le `trades.jsonl` de V2 est append-only : on n'écrit jamais que à la fin, jamais de modification ou de delete. Si le bot crash en plein milieu d'une écriture, tu perds au pire le dernier trade en cours mais pas les précédents.

**2. Snapshot d'état + journal d'événements.**

Le `daemon_state.json` est un snapshot complet à chaque cycle. En cas de crash, on recharge le snapshot et on reprend. Si on voulait être plus rigoureux, on garderait aussi un journal d'événements depuis le dernier snapshot — mais pour V2 paper c'est overkill.

**3. Idempotency.**

Toute opération doit pouvoir être rejouée sans effet de bord négatif. Exemple : si le daemon plante après avoir envoyé un ordre mais avant d'avoir enregistré qu'il l'avait envoyé, au redémarrage il ne doit PAS renvoyer un nouvel ordre. Pour ça, chaque ordre a un ID unique (`client_order_id` sur Hyperliquid), et le broker rejette les ordres avec un ID déjà vu.

V2 paper n'a pas ce problème (pas de broker réel), mais en Phase 2 c'est critique.

**4. Two-phase commit pour les transitions d'état**

Pour ouvrir une position :
- Phase 1 : envoie l'ordre au broker, attends la confirmation
- Phase 2 : seulement APRÈS confirmation, update l'état local

Si le crash arrive entre Phase 1 et Phase 2, au redémarrage le bot demande au broker "quelles sont mes positions ?" et reconstruit son état depuis la vérité du broker.

## 5.5 Checklist pré-déploiement (avant capital réel)

Inspiré des best practices industrielles [21] et adapté à V2 :

**Tests**
- [ ] 100 % des tests unitaires passent
- [ ] Walk-forward OOS+friction sur 2+ régimes (fait pour V1)
- [ ] CPCV (combinatorial purged) sur au moins 1 régime (à faire)
- [ ] Tests de robustesse aux pannes (API timeouts, données manquantes)
- [ ] Tests de stress (1000 trades simulés sur 10 ans, vérifier pas de NaN/inf)

**Sécurité**
- [ ] Clés API séparées : read-only pour data, trading-only pour exécution (pas de withdrawal)
- [ ] Withdrawal whitelist activée sur l'exchange (impossible de retirer vers un wallet inconnu)
- [ ] 2FA hardware (YubiKey idéalement)
- [ ] Pas de mot de passe dans le code, tout dans des variables d'environnement
- [ ] Hot wallet limité (capital opérationnel uniquement, le reste en cold)
- [ ] Backups réguliers de l'état du bot, vérifiés (testés en restoration)

**Risk controls**
- [ ] Position size max par trade défini et hardcodé
- [ ] Exposure max cross-asset défini
- [ ] Drawdown circuit breaker (kill switch à -X %)
- [ ] Max trades/heure limité (anti-runaway)
- [ ] Max ordres/seconde (anti-rate-limit ban)
- [ ] Alerte si comportement anormal (trades plus fréquents que d'habitude, etc.)

**Monitoring**
- [ ] Heartbeat fonctionne et est surveillé
- [ ] Telegram alerts marchent (smoke test mensuel)
- [ ] Logs sont rotated et archivés
- [ ] Métriques quotidiennes accessibles (PnL, position, exposure)

**Opérationnel**
- [ ] Procédure de kill switch documentée et testée
- [ ] Procédure de redémarrage documentée
- [ ] Procédure d'urgence ("le marché s'effondre, qu'est-ce que je fais ?") documentée
- [ ] Contact d'urgence chez l'exchange (numéro support pro)
- [ ] Plan de communication si tu ne peux pas accéder au Mac (vacances, hospitalisation)

V2 a coché ~80 % de ces cases pour Phase 1 paper. Pour Phase 2 réel, il faudra cocher les 100 % avant déploiement.

## 5.6 À retenir pour V2

1. **Architecture en 5 couches** (data / strategy / risk / execution / monitoring). V2 a 3 couches solides, deux à renforcer pour Phase 2.
2. **Append-only ledgers + snapshots + idempotency** = les 3 piliers de la fiabilité.
3. **Le watchdog externe sauve la mise** quand le daemon principal ne peut pas s'alerter lui-même.
4. **Checklist pré-déploiement à 100 %** avant tout capital réel — pas de raccourci.
5. **Sentry + Healthchecks.io** sont des wins faciles à implémenter à terme.

---

# Partie 6 — Risque et psychologie

## 6.1 Drawdown — ce que ton corps endure pendant que le bot subit

Personne ne parle assez de ça. Tu peux avoir le meilleur backtest du monde, si tu peux pas tenir le drawdown psychologiquement, tu vas couper au pire moment.

**Faits froids** :
- DD 10 % : la plupart des gens ressentent du stress mais tiennent
- DD 20 % : début de remise en question, "est-ce que la stratégie est cassée ?"
- DD 30 % : 50 % des traders coupent ici, même si la stratégie est saine
- DD 40 % : 80 % capitulent. Les 20 % qui restent sont rares.
- DD 50 %+ : zone des "true believers", soit ils sont fous soit ils ont une conviction inébranlable

**Le piège** : la capitulation arrive **toujours au creux**, quand la stratégie est sur le point de récupérer. C'est mathématique : si tu coupes après une grosse baisse, tu rates la remontée. Tu te promets de "rentrer après stabilisation" mais tu ne le fais jamais.

**Trois protections** :

1. **Connaître son seuil avant de commencer.** Si tu sais que tu ne peux pas tenir au-delà de 25 %, calibre la taille pour que ton DD live attendu max soit 15-20 %. Quart Kelly automatiquement.

2. **Pré-commitment.** Écris noir sur blanc ta règle d'arrêt AVANT le drawdown : "Si DD > X %, je stop le bot pendant Y jours et je revisite." Et tiens-toi-y. Le pré-commitment marche parce qu'au moment du DD, tu n'es plus rationnel — tu suis une règle écrite à froid.

3. **Réduire la fréquence de checking.** Plus tu regardes ton PnL, plus tu vas paniquer. Lis tes performances une fois par semaine, pas une fois par heure. C'est Daniel Kahneman qui le dit [22].

## 6.2 Position sizing pour le retail

Trois écoles principales :

**1. Fixed fractional** : risquer 1-2 % du capital par trade, indépendamment du setup. Simple, robuste, ne récompense pas la qualité.

**2. Kelly fractionnel** : taille proportionnelle à l'edge mesuré (WR × RR). Recompense la qualité mais demande des estimées fiables.

**3. Volatility-targeted** : taille telle que la position attendue ait une vol cible (ex: 1 % du capital par jour). S'adapte au régime de marché.

Pour V2 :
- ICC swing : **Quart Kelly** sur les 4 actifs filtrés, soit ~8-12 %/asset, exposition max ~40 % du capital
- Funding capture : **fixed fractional 33 %/asset** sur 3 actifs (BTC/ETH/SOL), exposition delta-neutre donc le "risk" est plus le tail que le directionnel

Une règle simple à appliquer : **n'utilise jamais plus de 70 % du capital simultanément**. Garde 30 % en cash pour absorber un drawdown et pour ré-entrer après une correction.

## 6.3 Les biais cognitifs du trader

Daniel Kahneman et Amos Tversky ont identifié les biais qui sabotent toute prise de décision financière. Les plus pertinents pour V2 :

**Loss aversion** : tu ressens 2x plus fort une perte qu'un gain équivalent. Conséquence : tu coupes trop tôt tes gagnants et tu tiens trop tes perdants. **Mitigation** : règles SL/TP automatisées (V2 le fait déjà).

**Recency bias** : tu surpondères les événements récents. Une stratégie qui a 5 mauvais trades de suite va te sembler "cassée" même si statistiquement c'est normal. **Mitigation** : pré-commitment + horizon temporel long pour évaluer.

**Confirmation bias** : tu cherches inconsciemment les preuves qui confirment ta thèse. Tu lis 10 analyses qui disent "BTC va monter", tu ignores celles qui disent l'inverse. **Mitigation** : forcer la lecture des contre-arguments (j'ai essayé de le faire dans la partie 3 sur SMC).

**Overconfidence** : après quelques gains, tu deviens sûr de toi et tu augmentes la taille. Crashs spectaculaires en vue. **Mitigation** : sizing fixe ou Kelly fractionnel sur estimées prudentes.

**Sunk cost fallacy** : "j'ai mis 6 mois sur ce bot, je ne peux pas l'abandonner". Si l'edge n'existe pas, ces 6 mois sont déjà perdus, ne perds pas en plus du capital live. **Mitigation** : kill criteria définis à l'avance.

V2 a un avantage : c'est un bot, pas toi. Le bot n'a pas de biais. Mais **toi tu en as**, et tu décides de stop/start le bot. Le pré-commitment écrit est ton meilleur outil.

## 6.4 Antifragilité (Taleb)

Nassim Taleb a introduit le concept d'**antifragilité** : un système n'est pas seulement résistant aux chocs (robuste), il en bénéficie [23].

**Application à V2** :

1. **Position sizing antifragile** : la taille de tes positions doit être plus petite quand tu ne sais pas ce qui se passe. Pendant une période d'incertitude maximale (FOMC, élections, événements géo), réduis l'exposition. Pas par peur, par humilité.

2. **Stratégie convexe** : préfère les stratégies qui perdent un peu souvent et gagnent beaucoup parfois (long tail droite, courte gauche). C'est l'opposé du selling-volatility (gagner souvent, perdre énorme rarement).

3. **Diversification asymétrique** : si tu as 10 stratégies avec un edge faible chacune, tu es plus antifragile qu'avec une stratégie au gros edge. La diversification n'est pas linéaire.

4. **"Barbell strategy"** : combine 80 % de très conservateur (cash, stables yield) avec 20 % d'asymmétrique upside (options OTM, ventures crypto, etc.). Évite le centre du spectre risk-return.

Pour V2 spécifiquement : la combinaison **funding capture (carry stable) + ICC swing (asymétrie pattern)** est mécaniquement antifragile dans le sens Taleb. Funding capture est ton 80 % stable, ICC est ton 20 % asymétrique. Garde cette structure.

## 6.5 Critères d'arrêt explicites

Le moment le plus important d'un projet trading n'est PAS le lancement. C'est **la décision d'arrêter quand ça ne marche pas**.

Pré-commitment écrit pour V2, à valider à ton retour :

**Critères d'arrêt funding capture** :
- Si Sharpe live (sur 90 jours rolling) < 0.8 → revoir paramètres
- Si Sharpe < 0.5 sur 180 jours → mettre en pause, audit complet
- Si DD > 25 % sur capital alloué funding capture → stop immédiat, audit

**Critères d'arrêt ICC swing** :
- Si Sharpe live < 0.6 sur 90 jours → revoir le filtre univers
- Si Sharpe < 0.3 sur 180 jours → mettre en pause
- Si DD > 30 % → stop, audit

**Critère d'arrêt global** :
- Si le total PnL V2 (toutes stratégies confondues) est négatif sur 12 mois live → pivot ou arrêt du projet

Ces seuils sont des **guidelines**, pas des dogmes. Mais les avoir écrits avant de commencer évite l'auto-justification ad hoc.

## 6.6 À retenir pour V2

1. **Le DD live est ton ennemi principal.** Pas la perte théorique. La perte qui dure.
2. **Pré-commitment écrit** sur les règles d'arrêt avant tout déploiement.
3. **Quart Kelly fractionnel** pour ICC. Fixed fractional pour funding capture.
4. **Antifragilité par diversification asymétrique** : funding + ICC = barbell naturel.
5. **Reduire la fréquence de check du PnL.** Une fois par semaine suffit.
6. **Critères d'arrêt explicites** : Sharpe < 0.6 sur 90j, DD > 25 % → revoir.

---

# Partie 7 — Régulation et business

## 7.1 MiCA détaillé pour traders algo

MiCA (Markets in Crypto-Assets) est le règlement européen sur les crypto-actifs, en application définitive depuis le **1er juillet 2026** [24]. C'est la première régulation crypto majeure et complète de l'UE.

**Ce qui est régulé** :
- Les "Crypto-Asset Service Providers" (CASPs) : exchanges, custodial wallets, brokers
- Les stablecoins (EMT, ART catégories)
- Les market manipulation et insider trading sur crypto

**Pour V2 spécifiquement** :

**Trading de ton propre capital** : Aucune licence requise. C'est du "proprietary trading", exempté.

**Signaux Discord/Telegram payants** : Zone grise.
- Si tu publies des analyses et les abonnés exécutent à la main → généralement OK, considéré comme du conseil informel
- Si tu publies des signaux avec exécution automatisée chez le subscriber → ça devient "Reception and Transmission of Orders" → **licence CASP requise**

**Copy trading** : Licence CASP requise dans tous les cas, parce que tu agis pour le compte de tiers.

**Gestion de portefeuille pour tiers** : Licence CASP "Portfolio Management" requise. Demande capital minimum, structure juridique, conformité KYC/AML, etc.

**ESMA briefing février 2026** [25] : précise que les opérateurs d'algorithmes crypto doivent :
- Maintenir des logs détaillés de tous les ordres envoyés, modifiés, annulés
- Documenter leurs stratégies algorithmiques sur demande du régulateur
- S'assurer que leurs algorithmes ne contribuent pas à des "disorderly trading conditions"

**Pour V2 Phase 2 (broker démo puis réel)** : tu trades pour ton propre compte → tu es OK. Mais **garde les logs** (V2 le fait déjà via JsonLineLogger) et **documente la stratégie** (V2 a `docs/ICC_SPEC.md` et `docs/NO_LOOKAHEAD_AUDIT.md` — exactement ce qu'il faut).

## 7.2 DAC8 et fiscalité française 2026

DAC8 (Directive on Administrative Cooperation 8) est entré en application le **1er janvier 2026** [26]. C'est la fin de la zone grise déclarative pour les crypto-traders en UE.

**Concrètement** :
- Toutes les plateformes crypto opérant en UE (exchanges, brokers, custodial wallets) **transmettent automatiquement et annuellement** tout l'historique des transactions de leurs utilisateurs résidents EU à l'administration fiscale du pays de résidence
- Cela inclut Binance, Kraken, OKX, et même Hyperliquid (qui doit s'enregistrer en tant que CASP pour servir l'UE)

**Conséquence** : tu ne peux plus "oublier" de déclarer. L'administration fiscale française reçoit déjà tes données. Si tu ne déclares pas, c'est un signal automatique pour un contrôle.

**Régime fiscal applicable** :

**Particulier — PFU à 31.4 %**
- Plus-values nettes sur cessions d'actifs numériques (article 150 VH bis CGI)
- Taux : 12.8 % IR + 18.6 % prélèvements sociaux (CSG portée à 10.6 % en 2026)
- Seuil de déclenchement : 305 € de cessions annuelles totales
- Déclaration via formulaire 2086 + report sur 2042-C
- Option pour barème progressif IR si plus favorable (cas où ton TMI < 12.8 %)

**Professionnel — BNC habituel**
- Si l'administration considère que ton activité est "habituelle" et "structurée"
- Tu passes du PFU 31.4 % au barème IR (jusqu'à 45 %) + cotisations sociales SSI (~30 % en plus)
- Total potentiel : 50-70 % du résultat
- **Risque réel** si tu fais 50+ swaps/jour, abonnements pro (TradingView Premium), VPS dédié, et que ça constitue ta source principale de revenus

**Pour V2** :
- Phase 1 (paper) : non taxable, aucune réalisation
- Phase 2 (broker démo) : non taxable
- Phase 3 (capital réel modéré, ~$20-50k) : PFU 31.4 % presque certain, si tu restes "particulier"
- Phase 4 (capital plus gros + multi-stratégies + revenus principaux) : zone grise, requalification BNC possible. Consulter un expert-comptable.

## 7.3 Stratégies fiscales légales

Quelques optimisations parfaitement légales :

1. **Holding long-terme**. Pas d'imposition tant que tu ne réalises pas la plus-value (pas de cession). Le HODL pur est fiscalement neutre.

2. **Compensation pertes / gains**. Les moins-values sont reportables sur les plus-values de la même année. Optimise les réalisations en fin d'année pour équilibrer.

3. **Société (SAS / SARL)** dédiée au trading crypto. À partir d'un certain niveau (>$200k de PnL annuel), une société peut être plus avantageuse fiscalement que le particulier — mais coûte aussi en compta, IS, etc.

4. **PEA-PME et autres enveloppes** : pas applicables à la crypto pour l'instant. À surveiller car des wrappers crypto-eligible pourraient émerger.

5. **Déménagement fiscal**. Si V2 devient sérieux et lucratif, certains pays UE ont des régimes plus favorables :
   - **Portugal** (jusqu'à 2023, exemption complète crypto ; en 2026, taxation light)
   - **Allemagne** (exemption après 1 an de holding)
   - **Malte, Chypre** (régimes attractifs mais complexité administrative)
   - **Émirats** (0 % impôt sur les plus-values)
   - **Suisse** (cantons à 0 % pour particuliers, mais résidence demandée)

Pour V2 ces stratégies sont prématurées. À garder en tête pour Phase 4+.

## 7.4 Chemins de monétisation au-delà du compte perso

V2 peut devenir plus qu'un bot perso. Schéma général :

**Niveau 1 — Trading perso** (où on est)
- Pas de tiers, pas de service, juste ton compte
- Aucune contrainte régulatoire
- Plafond de scale : ton capital perso

**Niveau 2 — Communauté open-source + Patreon**
- Tu publies une partie du code en OSS
- Tu animes une communauté Discord/Twitter
- Tu monétises via Patreon, formations, consulting léger
- Aucune licence requise (tu ne traites pas l'argent d'autrui)
- Revenu attendu : $1-5k/mois à 100-500 abonnés
- Effort : 5-10h/semaine de community management

**Niveau 3 — Signaux payants**
- Tu publies tes signaux V2 sur un canal payant
- Les abonnés exécutent à la main
- $20-100/mois par abonné
- **Limite régulatoire** : tant que c'est manuel chez le subscriber, ça passe. Si automatisé, CASP requis.
- Effort : faible (le bot génère les signaux)

**Niveau 4 — SaaS turnkey**
- Plateforme où le client connecte son exchange, paye un abonnement
- Le bot V2 tourne pour son compte
- $30-100/mois par client
- **CASP requis** — c'est un service crypto à des tiers
- Effort : élevé (infrastructure, support, conformité)
- Revenu potentiel : très scalable

**Niveau 5 — Copy-trading pool**
- Partenariat avec une plateforme existante (Finestel, Stoic.ai)
- Tu fournis le signal, ils gèrent l'infra et le client
- Tu prends 10-30 % du performance fee
- **Le partenaire gère la conformité**
- Effort : modéré
- Revenu : très dépendant de la perf et du capital agrégé

**Niveau 6 — DPM (Discretionary Portfolio Management)**
- Tu gères de l'argent pour des clients riches via contrat de mandat
- 2 % AUM + 20 % perf fee (modèle hedge fund classique)
- **Licence CASP "Portfolio Management" obligatoire**
- Structure juridique (SAS dédiée), KYC/AML, contrôle interne, audit, capital minimum
- Effort : très élevé. C'est un métier à plein temps.
- Revenu potentiel : $50k-1M+/an selon AUM (1-10 M$)

**Niveau 7 — Hedge fund crypto**
- Tu lèves du capital institutionnel
- Structure offshore (Cayman, Luxembourg)
- AUM $10M-100M+
- 2/20 fees
- Effort énorme, marché compétitif
- Revenu : $500k-5M+/an pour le gérant

Mon avis honnête : V2 a un chemin réaliste **jusqu'au Niveau 2-3 dans les 12 mois si tu y mets l'effort communautaire**. Niveau 4-5 est possible à 24 mois avec un partenaire infra. Niveau 6-7 demande une bascule de carrière complète, c'est une autre vie.

## 7.5 À retenir pour V2

1. **MiCA 1er juillet 2026** : si V2 reste personnel, pas d'impact. Dès que tu touches à du tiers, CASP obligatoire.
2. **DAC8 = fin de la zone grise** : déclarations obligatoires automatiques. Tiens des comptes propres.
3. **PFU 31.4 % en France**. Risque de requalification BNC si activité intensive.
4. **Chemin de monétisation gradué** : Niveau 1-3 sans licence, 4-7 avec.
5. **Pour les 12 prochains mois, vise le Niveau 2-3** : community + signaux. Niveau 4+ après validation Phase 2.

---

# Partie 8 — Vision V2 long terme

## 8.1 État au 21 mai 2026

Récap pour fixer le point de départ :

- **Stratégie principale** : ICC swing 4-actifs (ETH/LTC/AVAX/SOL), V1 SL.
- **Performance OOS+friction** : Sharpe weighted 1.0-2.2 selon univers, PF 1.6-3.5, DD 7-13 %.
- **Stratégie secondaire** : funding capture sur Hyperliquid, en paper trading dès le 22 mai 2026.
- **Engineering** : 94/94 tests, walk-forward natif, monitoring Telegram, daemon autonome 10 jours.
- **Capital** : zéro (paper). Phase 2 prévue après validation 10 jours.
- **Belief stage** : 70 % (en hausse de 58 % il y a 2 jours grâce aux chiffres univers filtré).

## 8.2 Roadmap 24 mois (proposition)

**Phase 1 : Validation paper (mai-août 2026)**
- 10 jours autonomous run funding capture
- 3 mois paper live combiné ICC + funding capture
- Validation 3ème fenêtre temporelle pour l'univers filtré
- Audit no-lookahead complété ✅ (fait)
- CPCV implémenté (à faire)

**Phase 2 : Broker démo + capital test (sept-déc 2026)**
- Compte démo Kraken / Hyperliquid testnet
- Bootstrap capital $5-10k
- Funding capture en réel sur HL prod (avec petit capital)
- Validation friction live = friction modèle

**Phase 3 : Scale modeste + communauté (jan-juin 2027)**
- Capital $20-50k
- Open-source partial sur GitHub
- Discord communautaire gratuit + tier payant
- Première version de signaux publics

**Phase 4 : Multi-stratégies + partenariat (juil 2027 - 2028)**
- Trend following et mean reversion intégrés au portefeuille
- Partenariat copy-trading avec Finestel / Stoic
- Capital combiné perso + AUM tiers ~$200-500k
- Évaluation CASP licence

**Phase 5 : Évaluation hedge fund retail (2028+)**
- Décision : aller jusqu'au bout (structure CASP, DPM)
- Ou rester un trader perso + side income communauté
- À ce stade, les chiffres et la psychologie décideront

## 8.3 Multi-stratégies — la diversification structurelle

V2 a actuellement 2 stratégies (ICC + funding). Pour atteindre un Sharpe robuste de 1.5+ en live, il faut **diversifier davantage**.

**Candidats à ajouter** :

1. **Trend following** sur les majors (BTC, ETH). Edge documenté académiquement (Hurst & Mendelson 1980s, AQR, Man AHL). Sharpe attendu 0.6-1.0. Décorrélé de l'ICC swing.

2. **Cross-sectional momentum** sur l'univers crypto (long top performers / short bottom). Sharpe 0.8-1.2. Très demandant en data (besoin de tout l'univers, pas juste 8 actifs).

3. **Mean reversion intraday** sur les majors. Sharpe variable selon régime. Court terme, frais sensibles.

4. **Statistical arbitrage cross-listing** : exploiter les écarts entre Binance, Bybit, Coinbase, Kraken pour le même actif. Plus complexe, demande infra latence.

5. **Volatility selling** : vendre de la vol options crypto (Deribit) en période calme, racheter en pic. Risque tail élevé. Sharpe 1.0-1.5 en moyenne mais drawdowns dévastateurs occasionnels.

6. **DeFi yield farming** : non-trading mais source de yield supplémentaire. Stablecoins lending, LP positions sur Uniswap, etc. Risque smart contract.

**Portfolio cible (ambitieux mais réaliste pour 24 mois)** :

| Stratégie | Allocation | Sharpe attendu | Corrélation avec ICC |
|---|---|---|---|
| ICC swing | 25 % | 1.0-1.3 | 1.0 |
| Funding capture | 30 % | 1.3-1.6 | ~0 |
| Trend following BTC/ETH | 20 % | 0.8-1.0 | 0.3 |
| Mean reversion intraday | 15 % | 0.6-0.9 | -0.2 |
| Stables yield (réserve) | 10 % | 0.3 | 0 |

Sharpe portfolio cible : **1.5-1.8** (diversification gain estimé ~30-40 %).

## 8.4 Communauté et marque

Si V2 vise au-delà du Niveau 1 (perso), la communauté est le multiplicateur principal.

**Modèle qui marche en crypto en 2026** :
1. **Twitter/X** : compte avec analyses régulières, transparence sur les trades, ton ferme et didactique. 5-20k followers en 12 mois si la qualité est là.
2. **Discord** : channel gratuit (lead generation) + channel payant ($30-50/mo).
3. **YouTube/podcast** : optionnel mais multiplicateur fort. 1-2 vidéos/semaine, qualité éducative.
4. **Newsletter Substack** : digest hebdo, $5-15/mo pour version pro.
5. **Open-source partial sur GitHub** : démontre la rigueur technique, attire les talents.

Le piège : la communauté demande **du temps régulier** (10-20h/semaine). Si tu ne peux pas tenir, ne commence pas. Mieux vaut pas de communauté qu'une communauté abandonnée.

**Différenciation possible pour V2** :
- "Le bot SMC honnête" : montrer les pertes, les drawdowns, les pivots — pas juste les wins
- Méthodologie publique : `docs/NO_LOOKAHEAD_AUDIT.md`, walk-forward avec friction, etc.
- En français + anglais : il y a un vrai vide entre les channels SMC anglo (LuxAlgo, SMRT Algo) et les francophones (TradesSAI mais peu technique)

## 8.5 Scénario ambitieux : SaaS / hedge fund retail

Si tout va bien à 18-24 mois, l'option **SaaS ou copy-trading scalable** devient viable.

**Modèle 1 : SaaS turnkey "ICC bot for crypto retail"**
- Le client connecte son compte Hyperliquid + Kraken
- Le bot V2 tourne automatiquement, prend les trades
- $50/mois abonnement + 10 % perf fee
- Cible : 500-2000 abonnés à 18 mois
- Revenue potentiel : $25-100k/mois récurrent
- Effort : élevé (support, infra, conformité)
- CASP licence obligatoire

**Modèle 2 : Pool copy-trading via partenariat**
- Tu trades sur un compte "lead"
- Les abonnés suivent automatiquement via partenaire (Finestel / Stoic)
- Le partenaire gère la conformité
- Tu prends 20-30 % de la perf fee
- Cible : $1-5M AUM agrégé à 18 mois
- Revenue : $20-100k/an dépendant de la perf

**Modèle 3 : Mini-fonds retail (structure SCI ou SAS)**
- Tu lèves du capital tiers via structure légère
- Pas de DPM officiel (compliqué pour <$1M AUM)
- Distribution des gains en fin d'année, sans frais d'AUM mais perf fee 20 %
- Cible : 5-20 investisseurs particuliers, $100-500k total
- Revenue : 20 % de la perf moyenne

Les trois modèles sont compatibles avec une activité salariée parallèle, ce qui est important pour ta sécurité financière personnelle.

## 8.6 Risques sur la vision long terme

Pour être honnête, voici ce qui peut faire dérailler la vision :

1. **L'edge ICC s'érode**. Si les SMC retail deviennent saturés, ton edge disparaît. Tu pivotes sur funding + autres.
2. **Hyperliquid a un incident grave**. Si HL implose (smart contract exploit, HLP crisis), tout le pan crypto-natif de V2 doit migrer ailleurs. Possible mais coûteux.
3. **Régulation se durcit**. Si MiCA serre la vis sur les bots, ou si la France interdit le copy-trading retail, ton chemin de monétisation se ferme.
4. **Marché bear 2-3 ans**. Si la crypto entre dans un hiver long comme 2018-2020, les volumes baissent, le funding s'effondre, les abonnés payants disparaissent. V2 reste profitable mais marginal.
5. **Tu burns out**. Le solo entrepreneur quant est un métier psychologiquement éprouvant. Si tu n'as pas un copilot ou une structure pour décharger, à 18-24 mois tu décroches.

Mitigation : **structure légère, attentes calibrées, optionnalité maintenue**. Ne pas brûler les ponts d'une carrière salariée tant que les revenus V2 ne couvrent pas les besoins de base × 2-3.

## 8.7 À retenir pour V2

1. **Vision raisonnable** : Niveau 2-3 dans 12 mois, Niveau 4 à 24 mois.
2. **Multi-stratégies** est la clé du Sharpe robuste. Ajouter 2-3 stratégies décorrélées avant le scale.
3. **Communauté est multiplicateur** si tu peux y mettre le temps. Sinon, mieux vaut pas.
4. **SaaS / copy-trading** sont viables à 18-24 mois, conditional à conformité CASP.
5. **Optionnalité préservée** : V2 doit être une option pas un pari fou. Garde une sécurité financière personnelle.

---

# Partie 9 — Bibliographie commentée et ressources

Cette section est ton kit de lecture continue. Je distingue ce qui est **incontournable** (à lire dans les 6 prochains mois), **utile** (à connaître), et **avancé** (pour plus tard).

## 9.1 Livres incontournables

### Quantitative Trading par Ernest Chan
**Disponibilité** : Wiley, Amazon, lecture O'Reilly online avec compte. Pas de PDF gratuit légal mais largement résumé en blogs/forums.
**Pourquoi** : le manuel quant le plus pragmatique. Chan distingue mean-reversion (où il excelle) et momentum, et **insiste sur la simplicité comme antidote à l'overfitting** [27].
**Pour V2** : la philosophie "simple linear strategies" colle directement à ce qu'on fait avec ICC (3 paramètres fixes, pas tunables).

### Algorithmic Trading: Winning Strategies and Their Rationale par Ernest Chan
**Disponibilité** : Wiley
**Pourquoi** : suite du précédent, plus concentrée sur les stratégies avec code exemple et explication "pourquoi ça devrait marcher". Bon framework de pensée.

### Advances in Financial Machine Learning par Marcos Lopez de Prado
**Disponibilité** : Wiley. Chapitre 1 gratuit sur SSRN [28].
**Pourquoi** : le livre de référence pour ML appliqué à la finance. Couvre purged cross-validation, combinatorial backtesting, feature engineering avancé.
**Pour V2** : essentiel pour comprendre comment éviter l'overfit. Lis au moins les chapitres 7 (cross-validation), 11 (backtest overfitting), 12 (backtest statistics).

### Red-Blooded Risk par Aaron Brown
**Disponibilité** : Wiley
**Pourquoi** : risk management du point de vue d'un poker player devenu risk manager à AQR. Anti-Taleb sur certains points, complémentaire.
**Pour V2** : excellent sur la psychologie du risque et la différence entre "calculated risk" et "gambling".

### Antifragile par Nassim Taleb
**Disponibilité** : Penguin Random House. Audiobook largement disponible.
**Pourquoi** : philosophie du risque appliquée. Pas un livre de trading direct mais reformate ta pensée [29].
**Pour V2** : utile pour calibrer le sizing et la structure portfolio (barbell strategy).

### Fooled by Randomness par Nassim Taleb
**Pourquoi** : le premier Taleb, le plus accessible. Sur l'illusion du skill en trading. Tu vas te reconnaître.

## 9.2 Livres utiles

### The Man Who Solved the Market par Gregory Zuckerman
**Pourquoi** : biographie de Jim Simons et Renaissance Technologies. Plus narratif que technique mais montre comment un vrai edge se construit.

### Trading Systems and Methods par Perry Kaufman
**Pourquoi** : encyclopédie classique du trading systématique. 1200 pages, pas à lire d'une traite mais comme référence.

### The Poker Face of Wall Street par Aaron Brown
**Pourquoi** : sur les parallèles poker / trading. Édification psychologique.

### Thinking, Fast and Slow par Daniel Kahneman
**Pourquoi** : LE livre sur les biais cognitifs. Lecture obligatoire pour tout trader.

### Black Swan par Nassim Taleb
**Pourquoi** : compagnon de Antifragile. Sur les événements rares et leur impact.

### When Genius Failed par Roger Lowenstein
**Pourquoi** : histoire de LTCM, le fonds quant qui a failli faire sauter le système financier en 1998. À lire pour comprendre comment les meilleurs trader-quants se font tuer par le levier.

## 9.3 Papers académiques essentiels

### "The Probability of Backtest Overfitting" - Lopez de Prado et Bailey
**Lien** : papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
**Pourquoi** : formalise le concept de "Deflated Sharpe Ratio" qui corrige le Sharpe selon le nombre de stratégies testées.

### "Pseudo-Mathematics and Financial Charlatanism" - Bailey, Borwin, Lopez de Prado, Zhu
**Pourquoi** : la critique académique des optimisations de stratégie. Lecture difficile mais éclairante.

### "Time Series Momentum" - Moskowitz, Ooi, Pedersen (AQR)
**Pourquoi** : preuve académique solide que le trend following marche, à travers 58 marchés et 25 ans.

### "Crypto Carry" - BIS Working Paper 1087
**Lien** : www.bis.org/publ/work1087.pdf [30]
**Pourquoi** : le seul paper "officiel" (Bank for International Settlements) qui documente le carry trade crypto. Confirme l'edge structurel funding capture.

### "Interpretable Hypothesis-Driven Trading" - arXiv 2025
**Lien** : arxiv.org/html/2512.12924v1 [31]
**Pourquoi** : framework rigoureux walk-forward pour les signaux de microstructure. Très pertinent pour ce qu'on fait.

## 9.4 Documentation technique à consulter

### Hyperliquid Docs
**Lien** : hyperliquid.gitbook.io/hyperliquid-docs [32]
**Pourquoi** : la doc officielle. Lis surtout les sections "Trading > Funding" et "API > Info Endpoint" (ce que V2 utilise déjà).

### CCXT Documentation
**Lien** : docs.ccxt.com
**Pourquoi** : la bibliothèque Python unifiée pour tous les exchanges. V2 l'utilise. Master son API pour pouvoir ajouter d'autres venues rapidement.

### ESMA MiCA Briefing
**Lien** : www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf [33]
**Pourquoi** : le PDF officiel de l'ESMA sur l'algo trading crypto. Court (15 pages) mais important si tu vises Niveau 4+.

## 9.5 Blogs et newsletters

### Quantitativo Substack ("Quant Trading Rules")
**Lien** : quantitativo.com
**Pourquoi** : newsletter quant gratuite avec une vraie qualité. Idées backtested et forward tested.

### TaiwanQuant
**Lien** : taiwanquant.dev
**Pourquoi** : recherche quant appliquée. Très propre méthodologiquement.

### Quant Journey par Jakub
**Lien** : quantjourney.substack.com
**Pourquoi** : focus crypto futures avec analyse python systémique.

### Quantocracy
**Lien** : quantocracy.com
**Pourquoi** : agrégateur des meilleurs blogs quant. Bonne source pour découvrir des auteurs.

### Reasonable Deviations
**Lien** : reasonabledeviations.com
**Pourquoi** : notes et résumés de "Advances in Financial Machine Learning" et autres. Très bien fait.

### Build a Capital Allocator (Newsletter)
**Pourquoi** : pour la dimension business / DPM si tu vas vers Niveau 5-6.

### BitMEX Research
**Lien** : blog.bitmex.com/research
**Pourquoi** : BitMEX publie des analyses on-chain et microstructure crypto régulières et bien sourcées.

### Galaxy Digital Research
**Lien** : galaxy.com/research
**Pourquoi** : la recherche institutionnelle crypto la plus respectée actuellement.

### Pi2 Network
**Lien** : blog.pi2.network
**Pourquoi** : analyses systémiques sur les arbitrages perp DEX. Plusieurs articles cités dans ce dossier.

## 9.6 Comptes X/Twitter à suivre

### Cohérence quant et trading systematique

- **@LopezDePrado** - Marcos lui-même. Tweete sur ML financier, anti-overfit.
- **@quantian1** - Quant chez un HF. Threads techniques riches.
- **@macrocephalopod** - Quant + macro. Niveau élevé.
- **@robcarver17** - Rob Carver, auteur de "Systematic Trading". Très clair didactiquement.
- **@chris1reilly** - Quant systematique, options et futures.
- **@QuantConnect** - Plateforme + thread quotidien d'idées.

### Crypto spécifique

- **@hyperliquidx** - Le compte officiel HL. Updates produit, partenariats.
- **@CryptoCred** - TA crypto sérieuse, ton mesuré.
- **@CryptoHayes** - Arthur Hayes (BitMEX founder). Macro crypto, parfois bombastique mais profond.
- **@Pentosh1** - TA crypto, focus structure de marché.
- **@TheCryptoLark** - Couverture large crypto, ton équilibré.
- **@RyanSAdams** - Bankless, dimension institutionnelle crypto.

### Risk et finance plus large

- **@nntaleb** - Nassim Taleb. Provocateur mais essentiel.
- **@harrarah** - Aaron Brown. Tweet sur risk + poker + finance.
- **@cliffordasness** - Cliff Asness (AQR). Quant institutionnel.
- **@bennpeifert** - Vol selling et options crypto.

## 9.7 Podcasts

### Chat With Traders
**Pourquoi** : interviews de traders pros. Épisodes classiques avec Brett Steenbarger, Aaron Brown, Linda Raschke.

### Top Traders Unplugged (Niels Kaastrup-Larsen)
**Pourquoi** : focus systematic / CTA. Quality control élevé.

### Flirting with Models (Corey Hoffstein)
**Pourquoi** : quant niveau institutionnel. Très technique.

### The Acquired Podcast
**Pourquoi** : pas trading mais business strategy. Épisode Renaissance Technologies à écouter.

### Bell Curve / Empire (Crypto)
**Pourquoi** : crypto focused, mais sérieux. Pas du shill.

### Bitcoin Magazine Podcast
**Pourquoi** : pour le côté Bitcoin pur, on-chain analytics.

## 9.8 Communautés et Discord

### QuantConnect Slack/Discord
**Pourquoi** : si tu utilises QC, communauté excellente.

### Algorithmic Trading Subreddit (r/algotrading)
**Pourquoi** : variable en qualité mais des discussions sérieuses régulièrement. Filtre.

### Hyperliquid Discord officiel
**Pourquoi** : pour rester à jour sur le protocole, news, et nouveaux features.

### TradesSAI Discord (FR)
**Pourquoi** : communauté ICC francophone si tu veux échanger sur la spec.

## 9.9 Outils et stack technique

### Python ecosystem
- **pandas** : indispensable pour data
- **numpy** : math vectorisée
- **ccxt** : exchanges unifiés
- **vectorbt** ou **bt** : backtest frameworks vectorisés alternatifs à étudier
- **backtrader** : event-driven backtest framework Python (mature)
- **mlflow** : experiment tracking si tu commences à itérer sur beaucoup de variantes
- **plotly** ou **bokeh** : visualisations interactives (utile pour rapports communauté)

### Data sources
- **Kraken public API** : free, 5y+ history sur majors
- **CCXT** : abstraction sur 100+ exchanges
- **Glassnode** : on-chain metrics ($30-300/mo)
- **CoinGecko Pro** : market data agrégée ($79+/mo)
- **Coinglass** : funding rates centralisés gratuits

### Infrastructure
- **VPS** : DigitalOcean / Hetzner / OVH (~$10-50/mo pour un bot)
- **GitHub Actions** : CI gratuit pour tests
- **Sentry** : error tracking gratuit jusqu'à 5k events/mo
- **Healthchecks.io** : monitoring heartbeat gratuit

## 9.10 Ressources françaises spécifiques

### TradesSAI (Discord + formations)
**Pourquoi** : la source originale de la spec ICC qu'on suit. Pédagogique.

### Cryptoast (média)
**Pourquoi** : actualité crypto FR, niveau acceptable.

### Coin Bureau (Guy)
**Pourquoi** : YouTube anglais mais avec sous-titres FR. Recherche fondamentale crypto solide.

### Hagnere Patrimoine / Waltio
**Pourquoi** : pour la fiscalité crypto FR. Articles techniques et calculateurs.

### Ledger Academy (FR)
**Pourquoi** : sécurité wallets, fondations crypto. Gratuit.

## 9.11 Documentation V2 interne

Ne pas oublier ce qu'on a déjà construit :
- `README.md` — vue d'ensemble
- `docs/ARCHITECTURE.md` — carte du projet
- `docs/ICC_SPEC.md` — spec de référence ICC
- `docs/JOURNAL.md` — chronologie complète
- `docs/RECAPS/` — recaps session par session
- `docs/NO_LOOKAHEAD_AUDIT.md` — audit méthodologique
- `DOSSIER_COMPLET_TRADING_BOT_V2.md` — le dossier business / vision
- `results/walkforward_v1_oos_friction_*.md` — résultats validation
- `live/README.md` — manuel d'opérations

C'est ta documentation. Relis-la régulièrement, surtout au retour.

---

# Partie 10 — Référence pratique et outils

Cette partie est conçue pour être **consultée plutôt que lue linéairement**. C'est ta boîte à outils pour quand tu auras une question concrète sur un concept, un seuil, une formule.

## 10.1 Glossaire quant — FR ↔ EN

**Algorithmic trading (trading algorithmique)** : exécution automatisée de stratégies via du code, sans intervention humaine sur chaque décision.

**Alpha** : rendement excédentaire par rapport à un benchmark. En quant, c'est ce que ta stratégie ajoute au-delà du marché.

**APR (Annual Percentage Rate / Taux annuel)** : taux annualisé sans composition. Utilisé pour comparer funding rates entre venues.

**APY (Annual Percentage Yield)** : taux annualisé AVEC composition. Plus pertinent pour le yield farming long terme.

**Arbitrage** : exploiter un écart de prix entre deux marchés/instruments pour le même actif.

**ATR (Average True Range)** : mesure de volatilité moyenne. Utilisé pour calibrer SL et taille de position.

**Backtest** : test d'une stratégie sur des données historiques pour estimer sa performance.

**Backwardation** : prix futures < prix spot. Reflet d'une demande spot forte ou d'un sentiment baissier sur le forward.

**Bar / Bougie / Candle** : représentation OHLC sur une période donnée (1h, 4h, 1d).

**Basis** : différence entre spot et futures du même actif. Variable principale du basis trading.

**Bias (biais)** :
- *Look-ahead bias* : utiliser une donnée du futur dans une décision passée
- *Survivorship bias* : tester sur les survivants seulement
- *Selection bias* : choisir l'univers/paramètres après avoir vu les résultats
- *Data-snooping bias* : essayer 1000 variations et garder la meilleure

**BOS (Break of Structure)** : cassure d'un swing high (en bull) ou swing low (en bear). Confirme une tendance.

**BNC (Bénéfices Non Commerciaux)** : régime fiscal français pour activités professionnelles non commerciales. Le danger pour traders intensifs.

**CASP (Crypto-Asset Service Provider)** : statut MiCA pour les prestataires de services crypto. Obligatoire pour traiter avec des tiers EU.

**CHoCH (Change of Character)** : premier signal de retournement de tendance. Première cassure d'une structure opposée.

**Composite Operator** : terme Wyckoff pour les opérateurs anonymes (institutions) qui dominent le marché.

**Contango** : prix futures > spot. Reflet d'une demande forward forte. Permet le cash-and-carry positif.

**CPCV (Combinatorial Purged Cross-Validation)** : méthode de validation OOS qui génère des centaines de chemins train/test. Plus robuste que walk-forward classique.

**DAC8** : directive UE 2026 imposant la transmission automatique des historiques crypto aux administrations fiscales.

**DCA (Dollar-Cost Averaging)** : acheter une quantité fixe à intervalle régulier. Stratégie passive.

**Delta** : sensibilité du prix d'un dérivé à un mouvement de l'actif sous-jacent.

**Delta-neutre** : position dont le delta global est zéro. Insensible aux mouvements directionnels.

**DEX (Decentralized Exchange)** : exchange sans intermédiaire central. Hyperliquid en est un.

**Discretionary trading** : trading où chaque décision est prise par un humain en temps réel. Opposé du systematic.

**DPM (Discretionary Portfolio Management)** : gestion de portefeuille discrétionnaire pour comptes tiers. Demande licence CASP.

**Drawdown (DD)** : chute en pourcentage depuis un sommet de l'equity curve.

**Edge** : avantage statistique mesurable d'une stratégie. La raison pour laquelle elle devrait gagner de l'argent.

**Equity curve** : courbe de l'équité du portefeuille au cours du temps.

**Expectancy** : espérance mathématique par trade. `(WR × avg_win) - ((1-WR) × avg_loss)`.

**Fair Value Gap (FVG)** : gap entre la bougie i et la bougie i+2. Souvent comblé plus tard.

**Funding rate** : paiement périodique entre longs et shorts sur les perpetuals. Mécanisme de convergence perp ↔ spot.

**Fundingexempté** : période où le funding n'est pas payé (rarement, transitions de protocole).

**Hedge (couverture)** : prendre une position opposée pour réduire le risque.

**HFT (High-Frequency Trading)** : trading à ultra-haute fréquence (millisecondes). Pas pour V2.

**HL (Higher Low)** : un creux plus haut que le précédent. Signal bullish.

**HH (Higher High)** : un sommet plus haut que le précédent. Confirme bullish.

**Kelly criterion** : formule de taille de position optimale `f* = (W × R - L) / R`.

**KYC (Know Your Customer)** : procédure d'identification des clients par les institutions financières.

**Lag** : décalage temporel. Notamment le "lag W" dans la détection de swings (V2 utilise W=3).

**LH (Lower High)** : un sommet plus bas que le précédent. Signal bearish.

**LL (Lower Low)** : un creux plus bas que le précédent. Confirme bearish.

**Liquidation** : fermeture forcée d'une position par l'exchange quand la marge devient insuffisante.

**Liquidity sweep / Stop hunt** : balayage des liquidités au-dessus/dessous d'un niveau évident (stops accumulés).

**Long** : pari sur la hausse du prix.

**MAR ratio** : `CAGR / max DD`. Mesure la qualité du rendement par rapport à la douleur max.

**Margin** : collatéral déposé pour soutenir une position à levier.

**Market maker** : participant qui poste des ordres limites des deux côtés du book et capture le spread.

**Maker fee** : frais d'exécution pour un ordre limite qui ne taker pas immédiatement. Toujours plus bas que taker fee.

**MiCA (Markets in Crypto-Assets)** : règlement UE encadrant les crypto-actifs et leurs prestataires. En vigueur 1er juillet 2026.

**Momentum** : tendance d'un prix à continuer dans la même direction sur le court-moyen terme.

**OB (Order Block)** : dernière bougie de direction opposée avant un mouvement impulsif. Zone de retournement potentielle.

**OHLCV** : Open, High, Low, Close, Volume. Données standard d'une bougie.

**OOS (Out-Of-Sample)** : données non utilisées pendant le développement. Le seul vrai test.

**Open Interest (OI)** : nombre total de contrats perp ouverts. Mesure d'engagement du marché.

**Overfitting (sur-ajustement)** : stratégie tellement adaptée au passé qu'elle ne marche plus sur le futur.

**Paper trading** : trading simulé avec capital virtuel mais conditions réelles (prix live, signal live).

**Partial fill** : ordre partiellement exécuté. À gérer dans le code de production.

**PCA (Principal Component Analysis)** : analyse en composantes principales. Outil quant avancé pour réduire la dimensionnalité.

**Perp / Perpetual swap** : contrat futures sans expiration. Maintenu proche du spot via le funding rate.

**PFU (Prélèvement Forfaitaire Unique)** : flat tax française. 31.4% en 2026 sur plus-values capitaux.

**PF (Profit Factor)** : `sum(wins) / |sum(losses)|`. Mesure d'efficacité globale.

**Pivot** : point de retournement local du prix. Synonyme de swing.

**Position sizing** : décision de la taille d'une position en fonction du capital, du risque, de l'edge.

**RR (Risk/Reward ratio)** : ratio entre gain potentiel et perte potentielle d'un trade. Ex: 1:3 = 3$ visés pour 1$ risqué.

**RSI (Relative Strength Index)** : oscillateur 0-100 mesurant la vitesse du mouvement. Plus utile sur ranges que tendances.

**Selection bias** : voir Bias.

**Sharpe ratio** : `(return - rf) / vol × √N`. Mesure du rendement ajusté du risque.

**Short** : pari sur la baisse du prix.

**Skew** : asymétrie d'une distribution de rendements. Positif = queue droite (préférable). Négatif = queue gauche (dangereux).

**Slippage** : différence entre prix attendu et prix obtenu à l'exécution.

**SMC (Smart Money Concepts)** : ensemble de concepts price-action descendant de ICT et Wyckoff.

**Sortino ratio** : variante du Sharpe qui ne compte que la volatilité downside.

**Spot** : marché d'achat-vente direct de l'actif (vs dérivés).

**SR (Sharpe Ratio)** : voir Sharpe.

**Stack** : ensemble des technologies utilisées (Python + ccxt + pandas + Hyperliquid pour V2).

**Stop-Loss (SL)** : ordre conditionnel qui ferme la position si le prix atteint un seuil de perte.

**Survivorship bias** : voir Bias.

**Swing high/low** : sommet/creux local confirmé.

**TA (Technical Analysis)** : analyse technique. SMC en est une déclinaison.

**Taker fee** : frais d'exécution pour un ordre market ou un ordre limite qui consomme immédiatement la liquidité.

**TF (Timeframe)** : période d'agrégation des bougies (M1, M5, M15, H1, H4, D, W, M).

**Tick** : plus petite variation de prix possible sur un instrument.

**Time-in-force** : durée de validité d'un ordre (GTC, IOC, FOK, GTD).

**Tail risk** : risque d'événements extrêmes situés dans les queues de la distribution. Sous-estimé dans les modèles gaussiens.

**Trailing stop** : SL qui suit le prix en cas de mouvement favorable.

**Trend** : tendance directionnelle persistante.

**VaR (Value at Risk)** : perte maximale attendue à un niveau de confiance donné. Ex: VaR 95% = perte qui ne sera dépassée que 5% du temps.

**Vol (Volatility)** : écart-type des rendements. Mesure du risque.

**Walk-forward analysis** : méthode de validation où on entraîne sur une fenêtre passée et teste sur la fenêtre suivante glissante.

**Whale** : très gros opérateur. Ses mouvements peuvent déplacer le marché.

**WR (Win Rate)** : pourcentage de trades gagnants.

**Wyckoff** : Richard Wyckoff, fondateur de l'analyse de market structure moderne. Ancêtre de SMC.

## 10.2 Cheat sheet formules quant

### Métriques de performance

```
Sharpe annualisé    = (mean_returns - rf) / std_returns × √N
                       N = 252 (daily), 8760 (hourly)

Sortino annualisé   = (mean_returns - rf) / downside_std × √N
                       downside_std = std(min(returns, 0))

Calmar             = CAGR / |max_DD|

MAR                = CAGR / |max_DD|  (équivalent Calmar mais usuel CTA)

Profit Factor      = sum(wins) / |sum(losses)|

Expectancy         = WR × avg_win - (1-WR) × avg_loss

CAGR               = (V_final / V_initial)^(1/years) - 1

Max Drawdown       = min((equity - cummax(equity)) / cummax(equity))

Win Rate           = n_wins / n_trades

Reward/Risk avg    = avg_win / |avg_loss|
```

### Position sizing

```
Kelly criterion    = (W × R - L) / R
                   = (W × R - (1-W)) / R
                   où W = win rate, R = avg_win / avg_loss

Fractional Kelly   = α × Kelly_full
                   α typique : 0.25 (Quarter), 0.5 (Half)

Fixed fractional   = constant × capital
                   typique : 0.01 à 0.02 (1-2 %) du capital risqué par trade

Volatility-target  = target_vol / asset_vol × capital
                   target_vol typique : 10-15 % annualisée
```

### Funding & basis

```
Funding payment    = position_notional × funding_rate
                   payé toutes les 8h (CEX) ou 1h (Hyperliquid)

APR funding        = funding_rate × periods_per_year
                   Hyperliquid : × 24 × 365 = × 8760

Basis             = (futures_price - spot_price) / spot_price

Cash-and-carry P&L = basis_at_close - basis_at_open + funding_accrued
```

### Friction et coûts

```
Round-trip cost   = 2 × (fee + slippage)
                   sur Hyperliquid taker : 2 × (4.5 + slippage) bps

Break-even spread = round_trip_cost
                   il faut un edge brut > break-even pour être profitable net

Cost as fraction
of profit         = total_costs / gross_profit
                   < 30 % est acceptable, > 50 % est rédhibitoire
```

## 10.3 Seuils de décision (cheat sheet)

### Sharpe ratio annualisé

| Niveau | Lecture | Décision |
|---|---|---|
| < 0.3 | Très médiocre | Abandonner stratégie |
| 0.3 - 0.6 | Médiocre | Revoir paramètres ou abandonner |
| 0.6 - 1.0 | Marginal | Continuer avec petite taille, suivre OOS |
| 1.0 - 1.5 | Correct retail | Acceptable pour déploiement live |
| 1.5 - 2.0 | Très bon | Déploiement live + augmentation possible |
| 2.0+ | Exceptionnel | Vérifier overfit, déployer prudemment |
| > 3.0 | Suspect | Quasi-certainement overfit |

### Drawdown live attendu

```
DD live ≈ DD backtest × 2

Si backtest DD = 10 % → prévois 20 % en live
Si backtest DD = 20 % → prévois 35-50 % en live
```

### Tolérance psychologique au DD

| DD ressenti | Pourcentage de traders qui capitulent |
|---|---|
| 10 % | 5-10 % |
| 20 % | 25-40 % |
| 30 % | 50-60 % |
| 40 % | 75-85 % |
| 50 %+ | 90-95 % |

**Conclusion** : ne déploie jamais une stratégie dont le DD backtest est > 15 % sans avoir testé psychologiquement ta capacité à voir ton capital perdre 25-30 % en réel.

### Win Rate vs RR break-even

Pour être profitable à WR donné, il faut un RR minimum :

| WR | RR break-even |
|---|---|
| 80 % | 0.25 |
| 70 % | 0.43 |
| 60 % | 0.67 |
| 50 % | 1.00 |
| 40 % | 1.50 |
| 30 % | 2.33 |
| 25 % | 3.00 |
| 20 % | 4.00 |

Un WR 30 % avec RR 4:1 (ex: trend following) est plus rentable qu'un WR 70 % avec RR 0.5:1.

## 10.4 Arbres de décision pratiques

### Que faire si le bot annonce un drawdown > 15 %

```
1. Vérifier que le DD n'est pas dû à un bug (logs, trades anormaux)
   ├── Si bug → stop immédiatement, corriger
   └── Si normal → étape 2

2. Vérifier la performance OOS récente vs backtest
   ├── Si écart > 50 % → audit complet de la stratégie
   └── Si écart < 30 % → étape 3

3. Vérifier le régime de marché vs régimes du backtest
   ├── Si régime nouveau (jamais vu) → réduire taille de moitié, observer
   └── Si régime connu → étape 4

4. Vérifier si d'autres bots SMC retail ont aussi un DD
   ├── Oui → problème de marché général, attendre
   └── Non → audit individuel approfondi
```

### Que faire si une stratégie sous-performe sur 3 mois

```
1. Calculer p-value de la sous-performance (≥ ou < hasard)
   ├── p > 0.10 → bruit statistique, continuer
   └── p < 0.05 → étape 2

2. Identifier la cause probable
   ├── Régime changed → adapter ou pause
   ├── Edge érodé → re-développer
   ├── Friction sous-estimée → recalibrer modèle
   └── Bug introduit → corriger
```

### Que faire avant Phase 2 (broker démo)

Checklist binaire (tout doit être ✅) :

- [ ] 90 jours minimum de paper trading live propre
- [ ] Walk-forward OOS+friction sur ≥ 2 régimes
- [ ] CPCV sur ≥ 1 régime
- [ ] No-lookahead audit signé
- [ ] Tests unitaires 100 %
- [ ] Monitoring + alerts opérationnels et testés en panne
- [ ] Procédures emergency kill switch documentées
- [ ] Position sizing implémenté (pas hardcoded constants)
- [ ] Risk limits cross-asset implémentés
- [ ] Backup et restore testés
- [ ] Pré-commitment écrit sur kill criteria

Si un seul élément manque → ne pas démarrer Phase 2.

### Que faire si Hyperliquid a un incident

```
Si incident léger (latence, throttling) :
1. Réduire fréquence des cycles à 15 min
2. Augmenter timeouts API
3. Surveiller normalisation

Si incident sévère (HLP crash, smart contract bug) :
1. Stop daemon immédiatement (kill switch)
2. Vérifier l'état des positions sur HL
3. Si nécessaire, fermer manuellement les positions via UI
4. Migrer vers Binance/Bybit pour la période d'incertitude
5. Reprendre seulement après confirmation officielle du fix
```

## 10.5 Code patterns clés

### Calcul de Sharpe annualisé (Python)

```python
import numpy as np

def sharpe_annualized(returns, periods_per_year=252, rf=0):
    """returns: pd.Series ou np.array des rendements par période"""
    excess = returns - (rf / periods_per_year)
    mean = excess.mean()
    std = excess.std(ddof=1)
    if std == 0:
        return 0
    return (mean / std) * np.sqrt(periods_per_year)
```

### Walk-forward simple (squelette)

```python
def walk_forward(data, strategy, train_months=12, test_months=6, step_months=3):
    """Itère des fenêtres glissantes train/test sur data."""
    results = []
    start = data.index.min()
    while True:
        train_end = start + pd.DateOffset(months=train_months)
        test_end = train_end + pd.DateOffset(months=test_months)
        if test_end > data.index.max():
            break
        train_slice = data.loc[start:train_end]
        test_slice = data.loc[train_end:test_end]
        signals = strategy(train_slice, test_slice)  # OOS only on test
        results.append(evaluate(test_slice, signals))
        start = start + pd.DateOffset(months=step_months)
    return results
```

### Friction trade-par-trade (du code V2)

```python
def apply_friction(trade, asset, slippage_bps_median):
    """Apply realistic costs to a trade's PnL."""
    legs = 3 if trade.partial_closed else 2
    fee_pct = legs * 4.5 / 10000  # Hyperliquid taker, in fraction
    
    # Probabilistic slippage (lognormal around median)
    slippage_total = 0
    for _ in range(legs):
        slippage_total += np.random.lognormal(
            mean=np.log(slippage_bps_median),
            sigma=0.5
        )
    slippage_pct = slippage_total / 10000
    
    # Funding cost on holding duration
    hours_held = (trade.exit_ts - trade.entry_ts).total_seconds() / 3600
    funding_cost = 1e-5 * hours_held  # ~0.001%/h
    
    trade.pnl_pct -= (fee_pct + slippage_pct + funding_cost)
    return trade
```

### Fractional Kelly sizing

```python
def kelly_size(capital, win_rate, avg_win_pct, avg_loss_pct, fraction=0.25):
    """Quarter Kelly by default. Returns the dollar amount to risk per trade."""
    R = avg_win_pct / abs(avg_loss_pct)
    full_kelly = (win_rate * R - (1 - win_rate)) / R
    if full_kelly <= 0:
        return 0  # no edge, don't trade
    return capital * fraction * full_kelly
```

### Fetch funding rate Hyperliquid (du code V2)

```python
import requests
from datetime import datetime, timezone, timedelta

def fetch_hl_funding(asset: str, hours_back: int = 96):
    """Recent funding history from Hyperliquid public API."""
    start_ms = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp() * 1000)
    r = requests.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "fundingHistory", "coin": asset, "startTime": start_ms},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
```

## 10.6 FAQ — questions probables de Badoun

### "Pourquoi le funding capture est-il considéré plus solide que l'ICC ?"

Parce que son edge est **structurel** (le retail est long-biased → funding positif persistant → quelqu'un doit prendre l'autre côté) et pas **pattern-based** (qui dépend de la persistance d'un comportement de marché). Les edges structurels résistent mieux au changement de régime. L'ICC peut s'éroder à mesure que SMC devient mainstream ; le funding capture continue tant qu'il y a des retail qui prennent du levier long.

### "Pourquoi ne pas augmenter la fréquence à intraday/scalping ?"

Trois raisons :
1. **Sub-15min est le terrain le plus saturé en SMC retail.** L'edge y est le plus érodé.
2. **Les frais et le slippage scalent au nombre de trades.** Plus tu trades, plus la friction te bouffe.
3. **La supervision humaine du daemon est plus difficile** sur du intraday — moins de marge d'erreur.

À considérer plus tard si V2 valide solidement le swing.

### "Pourquoi un Sharpe de 0.84-1.07 OOS+friction est-il acceptable ?"

Parce que la majorité des retail sont à Sharpe négatif. Un Sharpe live de 0.8-1.2 sur stratégie systématique est dans le top 10-20% retail. Les hedge funds professionnels visent 1.5-2.0 mais avec infrastructure très différente. Pour un projet solo en Python, 0.84-1.07 c'est respectable.

### "Quelle est la première amélioration à faire au retour ?"

Par ordre de priorité :
1. **Analyser les 10 jours de paper trading funding capture** — premier signal live
2. **CPCV implémentation** — la validation OOS la plus robuste
3. **Audit de la sélection univers ETH/LTC/AVAX/SOL sur une 3ème fenêtre** non touchée
4. **Friction calibrée sur les exécutions paper observées** (au lieu du modèle a priori)
5. **Sentry + Prometheus pour monitoring industriel**

### "Combien de capital faut-il pour Phase 2 ?"

Phase 2 démo : $0 (testnet/démo). Phase 2 réel : **commence par $5-10k**. Ce n'est pas pour le P&L mais pour valider que les chiffres modèle = chiffres réels. Augmente par tranches après chaque mois validé.

### "Quel temps faut-il consacrer par semaine ?"

Réaliste pour V2 dans son état actuel :
- Maintenance et monitoring : **2-3h/semaine**
- Amélioration et nouveau dev : **5-10h/semaine**
- Si tu vises Niveau 2-3 (communauté) : **+10-15h/semaine** pour la community
- Si tu vises Niveau 4+ (SaaS / DPM) : **temps plein**

Pour un solo entrepreneur avec autres projets, 8-15h/semaine sur V2 est un équilibre tenable.

### "Comment savoir si l'edge ICC est en train de s'éroder ?"

Surveiller en continu :
1. **Sharpe rolling 90 jours** vs Sharpe rolling 180 jours. Si le 90 jours descend significativement en dessous du 180, signal d'érosion.
2. **Fréquence des setups** : si V2 prend moins de trades qu'avant à régime de marché équivalent, l'edge se réduit (les opportunités disparaissent).
3. **Avg win size vs avg loss size** : si ce ratio diminue, les setups deviennent moins propres.
4. **Comparaison vs SMRT Algo ou LuxAlgo** (si publié) : si la communauté SMC publique sous-performe aussi, c'est un signal macro.

### "Si je veux scaler à $500k, que faut-il faire de plus ?"

À ce niveau de capital, plusieurs ajouts deviennent obligatoires :
1. **Position sizing dynamique** (volatility-targeted)
2. **Split des ordres** sur les actifs moins liquides pour ne pas créer son propre slippage
3. **Risk parity cross-strategy** au lieu d'allocation égale
4. **VaR consolidée et stress tests** mensuels
5. **Backup execution venue** (Hyperliquid + Bybit en fallback)
6. **Compliance setup** (en France, structure SAS dédiée probable)
7. **Comptable spécialisé crypto**

### "Le 3 juin, qu'est-ce qu'on regarde en premier ?"

Dans l'ordre :
1. **Status des process** : daemon + watchdog ont-ils tourné 10 jours sans interruption majeure ?
2. **Trades log** : combien de trades, sur quels actifs, quel comportement
3. **PnL paper** : positif, négatif, neutre ? Comparé à l'attente théorique (10-30 $ /asset/jour) ?
4. **Funding rates observés** vs ce qu'on a en cache historique : régime cohérent ?
5. **Anomalies** : alertes Telegram reçues, erreurs API, gaps de heartbeat ?

Si tout est nominal → décision Phase 2.
Si bizarreries → audit avant tout déploiement.

### "Que faire si Hyperliquid lance un produit qui change la donne ?"

Hyperliquid évolue vite (HyperEVM, nouveau vault HLP, etc.). Si un produit majeur sort :
1. **Lire la doc et les RFC** pendant 1-2 semaines avant de réagir
2. **Évaluer si le produit affecte l'edge funding capture** (souvent oui, marginalement)
3. **Tester en paper** pendant 30 jours avant tout pivot
4. **Ne pas se précipiter** — les "FOMO crypto-tech" tuent autant que les FOMO de marché

### "Est-ce que je peux faire confiance aux indicateurs LuxAlgo/SMRT Algo ?"

Comme outils de visualisation, oui — leurs détecteurs sont solides. Comme guides de décision automatique, **non sans validation propre**. Tout indicateur public a son edge érodé par sa propre popularité. Reste critique.

## 10.7 Plan d'apprentissage progressif sur 6 mois

Si tu veux montrer en compétence quant en 6 mois :

**Mois 1 — Fondations**
- Lire "Quantitative Trading" de Chan (le 1er, pas le 2e)
- Coder un backtest simple (BTC daily, moving average crossover)
- Implémenter walk-forward simple

**Mois 2 — Théorie quant**
- Lire chapitres 7, 11, 12 de Lopez de Prado
- Implémenter purged cross-validation sur ton bot
- Lire "Antifragile" et "Fooled by Randomness" en parallèle

**Mois 3 — Stratégies**
- Lire "Algorithmic Trading" de Chan (le 2e)
- Implémenter mean reversion + momentum sur l'univers crypto majors
- Comparer Sharpe avec ICC en walk-forward OOS

**Mois 4 — Microstructure**
- Lire les blogs Pi2.network, BitMEX Research
- Documenter HL HyperBFT en profondeur (lire le whitepaper)
- Comprendre les mécanismes de liquidation à 100 %

**Mois 5 — Risk management**
- Lire "Red-Blooded Risk" d'Aaron Brown
- Implémenter Kelly fractionnel dans V2
- Designer le risk layer pour Phase 2

**Mois 6 — Production**
- Lire ESMA briefing, MiCA détaillé
- Wire Sentry + Prometheus
- Phase 2 broker démo lancé en septembre

À 6 mois tu auras les fondations d'un quant trader systématique compétent.

## 10.8 Mots de la fin

Le quant n'est pas une question d'IQ — c'est une question de **discipline, d'humilité, et de patience**. Les meilleurs de la profession sont ceux qui :

1. **Mesurent tout, n'inventent rien.**
2. **Pré-commitent leurs règles à l'écrit avant les drawdowns.**
3. **Acceptent l'incertitude irréductible** — leur conviction est probabiliste, pas binaire.
4. **Préservent leur santé mentale** — sleep, nutrition, exercice. Le burnout tue plus de quants que les drawdowns.
5. **Restent curieux** — le marché change, les méthodes vieillissent, l'humble apprenant survit.

Tu as posé d'excellentes bases pour V2. Reste maintenant à éprouver le projet dans le temps, à le laisser respirer entre tes mains et celles du marché, et à apprendre par les drawdowns autant que par les gains.

À dans 13 jours.

— Ton copilote V2

---

# Notes de fin

Ce dossier est un point de départ, pas un point d'arrivée. Le quant est un métier qu'on apprend pendant 10 ans minimum. Tu ne vas pas tout assimiler en 10 jours, et c'est OK. L'objectif est de **te donner le vocabulaire et la carte mentale** pour qu'on puisse aller plus vite à ton retour.

Quelques règles méta pour la lecture :

1. **Lis avec un stylo**. Note tes désaccords, tes questions, tes idées. Au retour on en discute.
2. **Ne lis pas tout linéairement.** Si un chapitre te perd, saute. Reviens-y plus tard.
3. **Le but n'est pas de maîtriser, c'est d'être exposé.** Tu reconnaîtras les concepts quand on les utilisera.
4. **Méfie-toi des évidences.** En quant, ce qui paraît évident est souvent faux. Wyckoff disait "what is obvious is obviously wrong".
5. **Mes opinions sont marquées comme telles.** "Mon avis", "je recommande", "à mon sens" — tu peux être en désaccord. C'est même utile.

Quand on se retrouve le 3 juin, on aura :
- 10 jours de paper trading live à analyser
- Tes notes de lecture
- Une vision partagée des prochaines étapes

Bonne route Badoun. Profite bien du voyage.

— Ton copilote V2

---

## Bibliographie numérotée

[1] *95% AI retail bots lose within 90 days* — GoatFundedTrader, 2026. https://www.goatfundedtrader.com/blog/are-crypto-trading-bots-profitable

[2] *Less than 1% day traders consistently profit* — Various studies; FOR Traders blog 2026. https://www.fortraders.com/blog/trading-bots-lose-money

[3] *Crypto quant funds Sharpe 1.6, return 48%* — SQ Magazine 2026. https://sqmagazine.co.uk/crypto-hedge-funds-statistics/

[4] *Overfitting cause #1 of failures* — Coincub 2025. https://coincub.com/are-crypto-trading-bots-worth-it-2025/

[5] Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Chapter 1: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3104847

[6] *Combinatorial Purged Cross-Validation* — Wikipedia + Towards AI. https://en.wikipedia.org/wiki/Purged_cross-validation

[7] *Interpretable Hypothesis-Driven Trading Framework* — arXiv 2025. https://arxiv.org/html/2512.12924v1

[8] *Kelly Criterion for crypto* — Altrady 2026. https://www.altrady.com/blog/risk-management/kelly-criterion-crypto-position-sizing

[9] *Perpetual futures dominate volumes* — BitMEX 2025. https://www.bitmex.com/blog/state-of-crypto-perps-2025

[10] *Funding rate heartbeat* — Larry Thomas Medium 2025. https://medium.com/@larrythomas2003/why-do-funding-rates-change-understanding-the-heartbeat-of-crypto-perpetual-swaps-3bd7eb4e44f0

[11] *Hyperliquid funding APR ranges 2026* — Neural Arb. https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/

[12] *Oct 10-11 2025 $20B liquidation cascade* — XT Exchange Medium 2026. https://medium.com/@XT_com/bitcoin-futures-market-microstructure-liquidation-cascades-funding-regimes-and-open-interest-978b107b4889

[13] *Hyperliquid fee structure* — Hyperliquid Docs. https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding

[14] *HyperBFT consensus inspired by HotStuff* — Rocknblock technical deep dive. https://rocknblock.io/blog/how-does-hyperliquid-work-a-technical-deep-dive

[15] Corwin-Schultz spread estimator — used internally for slippage calibration. Reference paper available on SSRN.

[16] *Wyckoff Methodology In Depth* — Classroom of Traders PDF. https://classroomoftraders.com/wp-content/uploads/2024/07/the-wyckoff-methodology-in-depth.pdf

[17] *Smart Money Concepts originated by ICT* — Strike Money. https://www.strike.money/technical-analysis/smart-money-concepts

[18] *SMC academic critique* — Search returned no peer-reviewed studies. Acknowledged gap in literature.

[19] *Patterns work in backtest, not real-time* — Buildix.trade 2026. https://www.buildix.trade/blog/smart-money-concepts-crypto-trading-institutional-orderflow-2026

[20] *Cross-venue funding arbitrage* — XXKK Blog. https://blog.xxkk.com/blogs/new-coins/basis-trading-for-beginners-how-cash-and-carry-works-where-it-breaks-and-what-to-track

[21] *Algorithmic trading deployment best practices* — ESMA Supervisory Briefing 2026. https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf

[22] Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.

[23] Taleb, N. N. (2012). *Antifragile: Things That Gain from Disorder*. Random House. See also: https://www.newtraderu.com/2020/01/19/antifragile-trading-strategies/

[24] *MiCA effective date July 2026* — Sumsub guide. https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/

[25] *ESMA Feb 2026 algo trading briefing* — Neural Arb MiCA. https://www.neuralarb.com/2026/03/13/mica-2026-for-crypto-arbitrage/

[26] *DAC8 active since January 2026* — Hagnere Patrimoine. https://www.hagnere-patrimoine.fr/guides-patrimoine/comment-payer-moins-impots/fiscalite-cryptomonnaies-2026

[27] Chan, E. (2013). *Algorithmic Trading: Winning Strategies and Their Rationale*. Wiley. https://www.wiley.com/en-us/Algorithmic+Trading:+Winning+Strategies+and+Their+Rationale-p-9781118460146

[28] Lopez de Prado chapter 1 free on SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3104847

[29] Taleb antifragile concept summary — Vision Investing Substack. https://visioninvesting.substack.com/p/my-12-biggest-key-investing-takeaways

[30] *Crypto Carry* — BIS Working Paper 1087. https://www.bis.org/publ/work1087.pdf

[31] *Interpretable Hypothesis-Driven Trading* — arXiv. https://arxiv.org/html/2512.12924v1

[32] Hyperliquid Documentation. https://hyperliquid.gitbook.io/hyperliquid-docs

[33] ESMA Supervisory Briefing on Algorithmic Trading. https://www.esma.europa.eu/sites/default/files/2026-02/ESMA74-1505669079-10311_Supervisory_Briefing_on_Algorithmic_Trading_in_the_EU.pdf

---

*Fin du dossier · 21 mai 2026 · Préparé pour Badoun, lecture vol + 10 jours · ~25 000 mots*
