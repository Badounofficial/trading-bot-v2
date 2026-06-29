# Dossier complet — Trading Bot v2

**Date** : 12 mai 2026  
**Auteur** : audit assisté + analyse marché  
**Périmètre** : projet `~/Desktop/trading-bot-v2/`, branche `main` au commit `fbf497a`.  
**Cible lecteur** : porteur du projet, en phase de décision stratégique post-Session 6.

---

## 1. Résumé complet du projet

### 1.1 Objectif et vision

Trading Bot v2 est un bot de **trading crypto algorithmique** construit autour d'une implémentation rigoureuse de la méthodologie **ICC (Indication-Correction-Continuation)** — la déclinaison TradesSAI des Smart Money Concepts (SMC) / ICT. Le projet vise un dispositif **production-ready** pour exécuter automatiquement des trades long/short sur un panier de cryptos majeures, avec une logique de structure de marché reproductible, traçable et testable.

La vision affichée dans `README.md` : *"Implémentation rigoureuse, testée, validée sur 12 ans de données"*. Le ton est clairement quant — chaque concept ICC est encodé via des **Tests Unitaires (TU#1 à TU#5)** et chaque déviation par rapport à la spec ICC est interdite (`docs/ICC_SPEC.md` est cité comme référence non négociable).

### 1.2 Stratégies implémentées

Le repo contient **cinq stratégies** distinctes, à des niveaux de maturité différents :

| Stratégie | Fichier | État | Description |
|---|---|---|---|
| **ICC swing** (cœur du projet) | `strategies/icc_cycle.py` + `icc_structure.py` + `icc_orderblocks.py` | **Production-ready**, 63/63 tests | Pipeline 3-TF Daily/H4/H1, détecte indications CHoCH sur H4 + OB, attend correction, entre sur cassure micro-structure H1. SL/TP/trailing structurels. |
| **Walk-forward ICC** | `strategies/walkforward_icc.py` | Production-ready | Validation OOS glissante (12m train / 6m test / 3m step) avec verdict Hard/Soft. |
| **Trend Following** | `strategies/trend_following.py` (+ `_FIXED.py`) | Refactor en cours | Stratégie de suivi de tendance vectorielle simple. |
| **Funding Capture** | `strategies/funding_capture.py` | Implémentée, peu exploitée | Capture du funding rate sur Hyperliquid (long spot / short perp delta-neutral). |
| **Mean Reversion + Cross-Sectional Momentum** | `strategies/mean_reversion.py`, `strategies/momentum_xsec.py` | Implémentées via `run_strategies.py` | Pendants quant classiques, runner multi-actifs avec walk-forward. |

### 1.3 Architecture technique

- **Multi-TF strict** : Daily / H4 / H1, alimenté par `data/fetch_multi_tf.py`. Les données Kraken vont jusqu'à 12 ans sur 1d et ~5 ans sur 1h ; Hyperliquid est limité (5 000 barres 1h, ~7 mois).
- **Pas de mode intraday/scalping implémenté.** L'enum `TradeMode` annonce `SWING / INTRADAY / SCALPING` mais les commentaires précisent `(future)` et seul SWING est câblé. Aucune donnée sub-horaire (M1/M5/M15) n'est dans le cache.
- **Backtest** : moteur directionnel `backtest/directional_engine.py` (vectorisé) + moteur funding `backtest/engine.py`.
- **Paper trading** : `paper_trading/` contient un simulateur d'ordres + une couche data source (utilisée Session 6a pour valider la logique avant tout broker réel).
- **Tests** : 94 tests pytest passent à la dernière vérification (`tests/test_icc_*.py`, `test_engine.py`, `test_paper_trader.py`, etc.).
- **Pas de broker connecté.** La Session 6 cadre explicitement la **Phase 1 = paper trading local sans broker**, *"zéro capital immobilisé, zéro engagement"*. Phase 2 prévue : broker démo (Kraken envisagé). Phase 3 : capital réel petit.

### 1.4 Actifs et données

Les 8 actifs **utilisables avec couverture complète Daily/H4/H1** sont : **BTC, ETH, SOL, ADA, AVAX, DOT, LINK, LTC**. DOGE est listé dans le cache mais sa couverture 1h et 4h est trop courte (un mois et quatre mois respectivement) pour être inclus.

Côté Hyperliquid, le cache contient les **funding rates** (BTC/ETH/SOL USDC, 20 500 lignes) et les prix 1h (5 000 lignes chacun, depuis octobre 2025). Couverture suffisante pour la stratégie funding mais insuffisante pour un backtest ICC long.

### 1.5 Décisions clés (mai 2026)

- **Session 5 Walk-Forward ICC** : verdict consigné dans `docs/RECAPS/SESSION_5_RESULTS.md` (à valider avec l'historique réel).
- **Session 6 cadrage** : pivot vers paper trading local pur, abandon des plans broker précoces. Décision prudentielle : valider 3-6 mois en paper avant Phase 2.
- **Fix SL V2 (12 mai 2026)** : un fix validé sur un projet sibling (ICC Trading Bot, 5.3 ans, 4 actifs) consistant à déplacer le SL de H1 vers H4 a été **testé puis rejeté** sur trading-bot-v2. Trois variantes mesurées sur 332 trades, 8 actifs, 2024-2025 :

  | Variante | Win Rate | Profit Factor | Σ PnL | Max DD |
  |---|---:|---:|---:|---:|
  | **V1 (actuel)** SL H1-close + 0.1% | **60.5 %** | **3.84** | **+501 pp** | ~7 % |
  | V2b SL H4-close + 0.1% | 39.2 % | 1.19 | +121 pp | ~28 % |
  | V2 SL H4-wick + 0.1% | 42.5 % | 1.44 | +292 pp | ~27 % |

  V1 domine sur 7/8 actifs ; seul DOT s'améliore en V2 (+58 pp). Cause : le V1 de ce codebase ancre déjà sur le **close H1** (très serré), pas sur la mèche — la marge offerte par V2 n'a pas le même effet que sur le projet sibling où V1 était sur la mèche H1. Les détails sont dans `results/SL_V1_VS_V2_ANALYSIS.md`. **Décision : on garde V1 par défaut**, V2/V2b restent disponibles via le flag `sl_mode` pour expérimentations futures.

### 1.6 Chiffres backtest validés

Période **2024-01-01 → 2025-12-31** (2 ans, fenêtre où tous les TFs des 8 actifs se chevauchent), variante V1 (la seule recommandée à ce stade) :

- **332 trades** au total, **WR 60.5 %**, **PF 3.84**, **ΣPnL +501.2 pp** (somme des returns par trade, equally-weighted across assets)
- **Max DD ~7 %** en moyenne (entre 2.8 % sur ETH et 11.7 % sur ADA)
- Sharpe annualisé moyen estimé fourchette **1.5 – 2.0** d'après la dispersion des trades (donnée à recalculer rigoureusement avec un walk-forward dédié sur ce horizon).
- Top contributeurs : AVAX (+101.9 pp), LINK (+89.1 pp), ETH (+89.3 pp), SOL (+72.2 pp), LTC (+53.9 pp).
- Asset le plus faible : BTC (+25.7 pp) — pas catastrophique mais le moins productif, ce qui colle au fait que BTC est plus "macro-driven" et moins réactif aux micro-structures H1.

⚠️ Important : ces chiffres sont **in-sample sur la fenêtre 2024-2025**. Le walk-forward Session 5 (`strategies/walkforward_icc.py`) doit être relancé pour produire des chiffres OOS robustes — c'est sur ces chiffres OOS que reposeront les décisions Phase 2.

### 1.7 Stack et code

- Python 3.x, dépendances minimales : `pandas`, `numpy`, `pyarrow`, `ccxt` pour les données.
- Git actif, ~10 sessions documentées dans `docs/RECAPS/`.
- ~340 lignes pour `compare_sl_v1_v2.py` (le script qui sert maintenant de référence pour comparer des variantes SL).
- Pas de CI/CD ni de monitoring — c'est ok pour la Phase 1.

---

## 2. Vision d'expert — ce qui est solide, ce qui peut s'optimiser

### 2.1 Ce qui est solide

**Discipline méthodologique** : les Tests Unitaires par concept ICC (TU#1 La Bougie → TU#5 Walk-Forward) et l'interdiction de dévier de `ICC_SPEC.md` produisent un code que je trouve **rare dans le retail algo**. La majorité des bots SMC publics ([SMC Sniper Pro](https://www.tradingview.com/script/UVjjiTx1-SMC-Sniper-Pro/), [LuxAlgo SMC](https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/), [SMRT Algo](https://smrtalgo.com/)) sont des indicateurs visuels TradingView — pas des bots end-to-end avec backtest reproductible, walk-forward et tests unitaires. C'est un vrai différenciateur.

**Architecture multi-TF synchronisée sans lookahead** : la confirmation à `bar_index + W` et la non-utilisation de futur dans `detect_structures()` sont rigoureusement traitées. Sur le marché des bots SMC commerciaux, le lookahead bias est la cause N°1 d'écart backtest/live ; ne pas l'avoir ici est un atout.

**Honnêteté intellectuelle** : tester le fix V2, mesurer, rapporter qu'il dégrade les résultats et le retirer du défaut est exactement ce qu'il faut faire. C'est rare. La règle informelle du métier est *"95 % des bots AI perdent de l'argent dans les 90 jours"* en partie parce que leurs auteurs ne mesurent jamais avec rigueur après deploiement ([source goatfundedtrader](https://www.goatfundedtrader.com/blog/are-crypto-trading-bots-profitable)).

**Choix d'Hyperliquid pour le funding capture** : timing stratégique excellent — Hyperliquid détient désormais **44 % du volume perp DEX** ([Yellow.com avril 2026](https://yellow.com/news/hyperliquid-perpetual-dex-volume-share)) et **~50 % des frais perp-DEX** ([Pi2.network](https://blog.pi2.network/arbitrage-opportunities-in-perpetual-dexs-a-systematic-analysis/)). Les fees sont parmi les plus bas du marché (0.015 % maker / 0.045 % taker), bien sous Binance et Bybit.

### 2.2 Ce qui peut s'optimiser techniquement

**Backtest manque de friction réaliste sur ICC.** Le moteur ICC actuel (`icc_cycle.py`) calcule les PnL trade-par-trade en pourcentage *brut* — il n'applique pas explicitement les fees (~4.5 bps taker × 2 legs sur Hyperliquid) ni le slippage médian (~0.87 bps mentionné dans `config.yaml`). Sur 332 trades en 2 ans, ça représente facilement **~8-10 pp de drag** annuel sur le total qu'on n'a pas dans les +501 pp. À intégrer impérativement avant tout passage en Phase 2.

**Risk-of-ruin et sizing absent.** Les chiffres "WR 60.5 %, PF 3.84, ΣPnL +501 pp" supposent un sizing identique sur chaque trade. Il n'y a pas (encore) :
- gestion de l'exposition simultanée (deux trades buy ETH + buy AVAX au même moment → 200 % d'exposition)
- contrôle volatility-targeted (ajuster la taille selon la vol réalisée du moment)
- corrélation matrix entre actifs (ETH/SOL/AVAX sont fortement corrélés → un *risk-off* coordonné peut t'aligner sur un drawdown bien pire que le 11.7 % d'ADA isolé)

**Pas de Sharpe / Sortino / Calmar consolidés à l'échelle portefeuille.** Les métriques par asset sont là, l'agrégation est partielle. C'est gênant pour vendre/présenter ; et c'est trivial à ajouter.

**Pas de monitoring temps-réel ni de circuit-breaker.** Anticipable mais critique. À minima : flag "stop everything if drawdown > X" et alerte Telegram (déjà câblé dans `config.yaml`, à brancher).

### 2.3 Ce qui peut s'optimiser stratégiquement

**Faut-il implémenter le mode INTRADAY/SCALPING (les stubs M15/M5/M1) ?**

**Mon avis : non, pas maintenant.** Trois raisons :

1. **ROI temps probablement négatif.** Implémenter INTRADAY = télécharger M15/M5/M1 sur les 8 actifs (Kraken supporte mais avec profondeur limitée — typiquement quelques mois à 1 an de M15), refactor le pipeline 3-TF pour 5 TFs, refaire toute la batterie de tests, refaire walk-forward. C'est ~3-6 sessions. Le bénéfice attendu n'est pas évident : tu vas chercher des opportunités plus fréquentes, mais avec un edge structurel plus faible (le SMC institutionnel se voit mieux sur H1/H4 que sur M5).

2. **Le SMC retail sub-15min est l'endroit où "tout le monde joue"** ([buildix.trade analyse 2026](https://www.buildix.trade/blog/smart-money-concepts-crypto-trading-institutional-orderflow-2026)). Plus la TF est basse, plus la concurrence est dense (HFT, market makers, copy-traders) et plus l'edge SMC s'érode. Le swing H4 reste un terrain où le retail peut encore battre le marché-neutre car les institutionnels y traînent leur slow-money.

3. **Le bot actuel n'a pas encore livré son potentiel.** +501 pp sur 2 ans in-sample, OOS pas encore validé. Avant d'ajouter de la surface d'attaque, **consolide le swing en live**.

**Funding Capture vs ICC swing — que prioriser ?**

**Funding capture mérite d'être priorisé en parallèle, pas à la place.** Argumentaire :

- C'est **delta-neutre** : ça ne consomme pas le même budget de risque que l'ICC. Tu peux faire tourner les deux en même temps sur le même capital sans double exposition directionnelle.
- L'APR net réaliste sur Hyperliquid en 2026 : **3–12 % sur BTC/ETH, 20–60 %+ sur mid-caps** ([neuralarb](https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/)). Sur un compte modeste, c'est 1 000-6 000 $ par 10 000 $ — pas mince.
- Le **break-even funding spread** sur Hyperliquid est de seulement ~1.3 bps par fenêtre 8h en mode maker. Très exploitable.
- La techno est plus simple à mettre en live : pas de SL/TP/structure à monitorer, juste des règles d'entrée/sortie sur le funding smoothed (déjà codé dans `funding_capture.py`).
- **Risques connus** : funding flips négatifs lors de selloffs sharp ; liquidation risk si tu pousses au-dessus de 5x leverage (interdit pour cette stratégie) ; risque smart contract / chain Hyperliquid lui-même.

**Recommandation chiffrée** : 60 % du temps sur ICC swing (consolidation OOS + Phase 2 broker démo), 30 % sur funding_capture (le pousser jusqu'à un live paper Hyperliquid avec les vrais funding rates), 10 % sur tooling (friction réaliste + monitoring + sizing). Pas de scalping avant 2027.

### 2.4 Pièges à éviter (best practices 2026 manquantes)

1. **Overfitting silencieux.** Les +501 pp sur 2 ans in-sample sont brillants ; le test du jugement, c'est le walk-forward OOS Session 5. Sur les bots crypto retail, **95 % perdent dans les 90 jours** ([fortraders](https://www.fortraders.com/blog/trading-bots-lose-money)) — l'overfitting est la cause N°1 citée. Relancer le walk-forward avec les params V1 actuels est non-négociable.

2. **Pas de "death by paper cuts".** Les bots tournent 24/7. Une petite latence (200 ms) + un slippage de 5 bps sur un mauvais moment + un fee mal calibré = 1-2 pp d'érosion annuelle. **Tracer les exécutions réelles dès le paper trading** est crucial — c'est ce que fait `paper_trading/order_simulator.py`, mais il doit être enrichi avec une distribution de slippage réaliste tirée de l'order book.

3. **Pas de séparation hot/cold wallet** documentée. Quand Phase 2 arrive (Kraken démo puis réel), tu auras besoin d'une discipline stricte : API keys read-only par défaut, signature write isolée, withdrawal whitelist activée, 2FA hardware. Ce n'est pas optionnel.

4. **Réglementaire MiCA.** Le règlement européen est entré en application définitive **le 1er juillet 2026** ([sumsub](https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/)). Pour un trader perso qui tourne son propre bot, **pas de licence CASP requise** ([neuralarb](https://www.neuralarb.com/2026/03/13/mica-2026-for-crypto-arbitrage/)). Mais dès que tu introduis un service (copy-trading, signaux, gestion pour compte de tiers), tu tombes sur "Portfolio Management" ou "Reception and Transmission of Orders" et tu dois être licencié. À garder en tête pour les questions de monétisation (section 5).

5. **DAC8 et déclaratif fiscal.** Depuis le **1er janvier 2026**, les plateformes crypto transmettent automatiquement ton historique à l'administration fiscale française ([Hagnere Patrimoine](https://www.hagnere-patrimoine.fr/guides-patrimoine/comment-payer-moins-impots/fiscalite-cryptomonnaies-2026)). Plus de zone grise sur la déclaration.

6. **Backtest sur le mauvais cycle.** 2024-2025 est dominé par un bull market BTC (~120 % en 2025). Si le bot était entrainé/optimisé sur ce régime, attendez-vous à une dégradation en cas de bear/rangy markets. C'est partiellement adressé par le walk-forward mais reste à monitorer en live.

---

## 3. SWOT objectif

### 3.1 Strengths

- **Rigueur d'implémentation rare** dans le retail : Tests Unitaires par concept, walk-forward natif, anti-lookahead.
- **Backtest in-sample fort** : 332 trades, WR 60.5 %, PF 3.84, +501 pp sur 2 ans, 8 actifs liquides.
- **Honnêteté analytique** : fix V2 testé, mesuré, rejeté et documenté.
- **Stack moderne et liquide** : Hyperliquid + Kraken, deux des venues les plus liquides du marché crypto en 2026 ; Hyperliquid à lui seul = ~70 % du volume perp on-chain ([yellow.com](https://yellow.com/research/hyperliquid-perp-volume-dominance-how-2026)).
- **Frais bas** : 4.5 bps taker / 1.5 bps maker sur Hyperliquid, sous Binance et Bybit ([Hyperliquid docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)).
- **Diversification stratégique** : 5 stratégies en parallèle (ICC, trend, funding, mean-rev, momentum xsec) — chacune avec un edge théorique différent.

### 3.2 Weaknesses

- **Pas encore de live ni de paper temps-réel** : tout est in-sample / backtest historique. La distance entre backtest brillant et P&L live est où meurent 95 % des bots.
- **Friction de marché sous-modélisée** dans le pipeline ICC (fees + slippage non appliqués trade par trade).
- **Pas de sizing portefeuille** ni de risk-management cross-asset.
- **Mode INTRADAY/SCALPING vendu par l'enum, jamais codé** — dette de design à effacer ou implémenter.
- **Couverture data limitée** : 2 ans seulement où Daily/H4/H1 se croisent pour les 8 actifs. Pour un walk-forward rigoureux, il en faudrait 4-5.
- **Pas de CI/CD, pas de monitoring temps-réel, pas de circuit-breaker.**
- **Mono-développeur, mono-machine.** Pas de redondance, pas de fail-over.
- **Documentation interne dense mais en français** — friction si tu cherches à attirer collaborateurs externes.

### 3.3 Opportunities

- **Hyperliquid en pleine ascension** : market share perp DEX 36 % → 44 % en 4 mois début 2026 ([yellow.com](https://yellow.com/news/hyperliquid-perpetual-dex-volume-share)). Bot premier-arrivé sur perp DEX = avantage de fees, de profondeur, et de funding edges plus juteux que sur CEX.
- **Vide commercial sur les bots SMC end-to-end** : la majorité du marché est constitué d'indicateurs TradingView (LuxAlgo, Zeiierman, SMC Sniper Pro) — pas de bots complets backtest + exécution. Une offre verticale "ICC bot turnkey crypto" trouverait un segment.
- **Funding arb** : marché actif, APR net 8-25 % sur majors, 30-80 % sur long-tail ([neuralarb](https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/)). Espace pour un bot dédié si tu pousses la stratégie funding_capture.
- **DPM / RIA crypto / family offices** : les fonds quant crypto délivrent **48 % de rendement moyen, Sharpe 1.6** ([sqmagazine](https://sqmagazine.co.uk/crypto-hedge-funds-statistics/)). Si ton bot OOS s'approche de Sharpe 1.5 avec DD <15 %, tu es packageable.
- **Marché copy-trading SaaS** : plateformes type Finestel, Stoic, Bitget Copy Trading. Le coût d'entrée pour un trader sur ces plateformes est ~$10 ([Bitget academy](https://www.bitget.com/academy/crypto-copy-trading-2)).
- **Communauté SMC active** : LuxAlgo, SMRT Algo (15 000+ membres), SMC Community algoat. Si tu builds une couche communautaire (signaux, copy, Discord), la base d'audience existe.

### 3.4 Threats

- **Régulation MiCA active depuis le 1er juillet 2026** ([sumsub](https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/)). Tout service crypto en Europe doit être licencié CASP. Bot pour ton propre capital = ok. Bot pour tiers / signaux automatisés = licence requise.
- **ESMA briefing février 2026** sur les HFT/algo crypto : logs obligatoires des ordres envoyés/modifiés/annulés, documentation des stratégies sur demande ([neuralarb MiCA](https://www.neuralarb.com/2026/03/13/mica-2026-for-crypto-arbitrage/)). Pas bloquant pour un solo, mais à anticiper.
- **Exchange risk Hyperliquid** : c'est un L1 jeune (lancé 2023, scaling rapide). Risque smart contract et risque opérationnel (déjà eu un incident majeur début 2025 sur le HLP). Mitigation : split du capital entre venues, position sizing modeste sur Hyperliquid.
- **Régime de marché** : si 2026-2027 inverse en bear/rangy après le bull 2024-2025, les performances vont se réduire. Le SMC en marché illiquide ou très volatil sous-performe ([forextradelab](https://forextradelab.com/blog/smart-money-concepts-ict-trading-guide/)).
- **Crypto tail risk** : flash crashes, ruptures de stablecoins, exploits cross-chain. La VaR 1 % d'un portefeuille crypto reste 10-20× celle d'un portefeuille TradFi.
- **Concurrence des LLM/agentic trading** : les plateformes type 3Commas, Cryptohopper, WunderTrading proposent maintenant des bots à IA générative et tirent leurs utilisateurs vers le grand public. L'edge "ICC pur" se défend, mais nécessite communication.
- **Fiscalité FR** : PFU passé à **31.4 % en 2026** (CSG augmentée de 1.4 pp) ([Hagnere](https://www.hagnere-patrimoine.fr/guides-patrimoine/comment-payer-moins-impots/fiscalite-cryptomonnaies-2026)). Si tu fais 50 swaps/jour sur Hyperliquid avec leverage, **requalification BNC habituel quasi-certaine** — barème IR + cotisations sociales, beaucoup plus dur que PFU.

---

## 4. État de l'art — recherche web avec sources

### 4.1 Bots ICC / SMC en crypto, 2026

L'état de l'art SMC/ICT en crypto 2026 est dominé par les **indicateurs TradingView** plus que par des **bots end-to-end**. Les acteurs publics majeurs :

- **LuxAlgo SMC** — indicateur gratuit, le plus populaire, gère BOS/CHoCH internes et swing, OBs, premium/discount, equal highs/lows ([TradingView LuxAlgo](https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/)).
- **Zeiierman SMC Premium** — modèle subscription ([TradingView Zeiierman](https://www.tradingview.com/script/eJdZpiDr-Smart-Money-Concepts-Premium-Expo/)).
- **SMC Sniper Pro (quantflowlabs)** — invite-only, subscription ([TradingView SMC Sniper Pro](https://www.tradingview.com/script/UVjjiTx1-SMC-Sniper-Pro/)).
- **SMRT Algo** — système trading complet avec composante SMC, ~15 000 membres actifs crypto/stocks/forex/futures ([smrtalgo.com](https://smrtalgo.com/)).
- **smart-money-concepts (joshyattridge)** — package Python open-source pour algo trading SMC, en *libre* ([GitHub joshyattridge](https://github.com/joshyattridge/smart-money-concepts)).

Le **takeaway clé** : les patterns SMC marchent en backtest si tu y appliques des règles de risque strictes, **mais l'efficacité réelle en live varie fortement avec le régime** — meilleur en trending market, dégradé en illiquide/extrême volatil ([forextradelab guide 2026](https://forextradelab.com/blog/smart-money-concepts-ict-trading-guide/)). L'article buildix.trade 2026 note explicitement que *"les patterns qui fonctionnent en backtest fonctionnent rarement de la même manière en temps réel"* ([buildix.trade](https://www.buildix.trade/blog/smart-money-concepts-crypto-trading-institutional-orderflow-2026)).

**Différenciation potentielle pour trading-bot-v2** : le projet n'est ni un indicateur, ni un bot greybox cloud — c'est une stack Python end-to-end open-friendly avec tests unitaires. Position rare.

### 4.2 Performance moyenne des bots crypto retail

- **Cryptohopper / 3Commas / WunderTrading** : top utilisateurs reportent **12-25 % annualisés** en marché favorable ([browse-ai.tools 2026](https://www.browse-ai.tools/blog/top-ai-tools-crypto-traders-3commas-vs-cryptohopper-2026)).
- **Hedge funds quant crypto** : moyenne **48 % de rendement annuel, Sharpe 1.6, vol 46 %**, 28 % des hedge funds crypto sont quant ([sqmagazine 2026](https://sqmagazine.co.uk/crypto-hedge-funds-statistics/)). Market-neutral à ~13 % return mais Sharpe ~2x supérieur aux long-only.
- **Bitcoin 2025** : +120 %. Crypto hedge fund moyen : +36 %. Seuls quelques fonds quant ont battu BTC.
- **Échec retail** : 95 % des bots AI retail perdent dans les 90 jours ([goatfundedtrader](https://www.goatfundedtrader.com/blog/are-crypto-trading-bots-profitable)). Causes principales : leverage excessif, overfitting, mismatch stratégie/marché.

### 4.3 Marché funding-arbitrage sur Hyperliquid et perp DEX

- **Hyperliquid market share** : 44 % du volume perp-DEX en avril 2026 (vs 36.4 % en janvier), ~70 % du volume perp on-chain, $21.8 B de volume 24h, $7.3 B d'open interest ([yellow.com](https://yellow.com/news/hyperliquid-perpetual-dex-volume-share), [DeFiLlama](https://defillama.com/protocol/hyperliquid)).
- **HYPE token** : market cap ~$10.2 B, rang #13 CoinGecko mai 2026 ([CoinGecko HYPE](https://www.coingecko.com/en/coins/hyperliquid)).
- **Profitabilité du funding arb** : APR net 3-12 % sur BTC/ETH, 20-60 %+ sur mid-caps (SOL, HYPE, listings récents), 30-80 % sur long-tail ([neuralarb 2026](https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/)).
- **Frais Hyperliquid** : 0.015 % maker / 0.045 % taker, inférieurs à Binance (0.020 / 0.050) et Bybit (0.020 / 0.055).
- **Funding payé toutes les heures** sur Hyperliquid (vs 8h sur la plupart des CEX). Break-even spread = ~1.3 bps par fenêtre 8h en mode maker.
- **Règle prudentielle** : leverage ≤ 5x pour funding arb. Le yield ne justifie pas la liquidation risk au-delà ([Hyperliquid funding docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)).

### 4.4 Régulation crypto Europe et fiscalité France 2026

- **MiCA en vigueur définitive** depuis le **1er juillet 2026**. Toute entreprise offrant des services crypto à des clients UE sans licence CASP est en infraction ([sumsub](https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/), [ESMA MiCA](https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/markets-crypto-assets-regulation-mica)).
- **Bot perso (proprietary trading)** : pas de licence requise.
- **Bot pour tiers / signaux exécutant automatiquement chez subscribers** : "Portfolio Management" ou "Reception and Transmission of Orders" → licence CASP requise ([neuralarb MiCA](https://www.neuralarb.com/2026/03/13/mica-2026-for-crypto-arbitrage/)).
- **ESMA supervisory briefing février 2026** : algo trading crypto soumis à logs détaillés et documentation des stratégies sur demande.

**Fiscalité France 2026** :
- **PFU = 31.4 %** depuis le 1er janvier 2026 (CSG portée de 9.2 % à 10.6 %) ([Hagnere Patrimoine](https://www.hagnere-patrimoine.fr/guides-patrimoine/comment-payer-moins-impots/fiscalite-cryptomonnaies-2026), [Waltio](https://www.waltio.com/fr/tout-savoir-sur-la-fiscalite-crypto/)).
- Plus-values déclarées via **formulaire 2086**, seuil > 305 € de cessions annuelles.
- Option barème progressif IR possible si plus favorable.
- **DAC8 actif depuis 1er janvier 2026** : transmission automatique des historiques par les plateformes au fisc.
- **Risque de requalification BNC habituel** si activité de bot intensive + outils pros + revenu majeur (typiquement : 50 swaps/jour, leverage, VPS dédié, abonnements). BNC = barème IR + cotisations sociales, beaucoup plus lourd que PFU.

### 4.5 Concurrents directs

| Type | Acteur | Modèle |
|---|---|---|
| Indicateur TV gratuit | LuxAlgo SMC | Freemium, viral, base d'audience massive |
| Indicateur TV payant | Zeiierman SMC, SMC Sniper Pro | Subscription mensuelle |
| Bot tout-en-un | 3Commas, Cryptohopper, WunderTrading, Bitsgap | SaaS $30-100/mois, AI marketed, grid/DCA dominants |
| Bot tout-en-un avec SMC | SMRT Algo | $30-100/mois, 15 000+ membres |
| Copy-trading | Binance Copy, Bybit Copy, eToro, Bitget | Exchange-natif, 0 abonnement, marge sur spread |
| Copy-trading SaaS | Finestel, Stoic | Subscription + perf fees |
| Open-source package | smart-money-concepts (joshyattridge) | Gratuit, framework Python |

**Lecture stratégique** : il n'y a quasi-personne sur le segment *"bot SMC/ICC end-to-end Python, transparent, backtest reproductible, open-friendly"*. Le marché bot commercial est dominé par des SaaS opaques. Le marché open-source est dominé par les indicateurs ou les frameworks bruts. trading-bot-v2 est dans un créneau étroit mais réel.

---

## 5. Marché ciblé

### 5.1 Segmentation des clients potentiels

| Segment | Description | Volume | Willingness to pay |
|---|---|---|---|
| **A — Toi-même, capital perso** | Tu fais tourner le bot sur ton propre compte, pas de service externe. | N=1 | 100 % de l'edge te revient. Pas de licence. |
| **B — Communauté open-source / dev quant** | Tu publies en open-source, audience GitHub/Discord, monétisation via Patreon ou consulting | Communauté SMC active 15-50 k personnes ([SMRT Algo a 15k+ membres](https://smrtalgo.com/)) | $5-20/mois Patreon, ~5-10 % conversion → 50-200 € MRR au début |
| **C — Signaux Discord/Telegram payants** | Tu publies les signaux du bot, abonnés exécutent à la main ou via copy | Marché crypto signal services large mais saturé | $20-100/mois par abonné. Mais demande à licence CASP en EU si exec automatique. |
| **D — SaaS bot turnkey** | Plateforme où l'utilisateur connecte son exchange, paye un abonnement, le bot tourne | TAM : utilisateurs 3Commas/Cryptohopper, ~M+ traders crypto retail | $30-100/mois ; benchmark TradingView Pro = $14.95/mo, SMRT Algo Essential = $14.95+/mo |
| **E — Copy-trading SaaS** | Plateforme type Finestel : tu copies les trades du bot, paye une perf fee | Croissant rapidement | 0 fixe + 10-30 % perf fee ; min deposit clients ~$10-250 |
| **F — DPM / RIA / family office** | Gestion de capital tiers avec contrat de mandat | Petit volume mais haut ticket | 2 % AUM + 20 % perf fee classique ; nécessite licence CASP + structures juridiques |
| **G — Hedge fund crypto** | Stratégie packagée vendue à un fonds existant | Très spécifique | $100k-1M licence ou employment quant |

### 5.2 Taille de marché

- **Trading bots crypto retail** : marché global plusieurs millions d'utilisateurs cumulés sur 3Commas + Cryptohopper + Bitsgap + WunderTrading ; TAM mondial estimé en milliards $ ([altrady](https://www.altrady.com/blog/crypto-bots/cryptohopper-review)).
- **Copy-trading crypto** : Binance, Bybit, OKX dominent, des dizaines de milliers de "lead traders" actifs ; Binance affiche 2 300+ traders vérifiés ([browse-ai.tools](https://www.browse-ai.tools/blog/best-generative-ai-platforms-crypto-trading-2026-3commas-vs-cryptohopper)).
- **Hedge funds crypto quant** : ~28 % des hedge funds crypto, soit environ 200-300 fonds actifs mondialement (estimation issue de Crypto Fund Research, [cryptofundresearch](https://cryptofundresearch.com/best-performing-crypto-funds/)).
- **Communauté SMC active** : 15-50k pour les principaux indicateurs commerciaux ; potentiellement 100k+ traders pratiquant SMC à divers degrés.

### 5.3 Willingness to pay

Données publiées :
- TradingView Plus : **$29.95/mo** ([TradingView pricing](https://www.tradingview.com/pricing/))
- TradingView Essential : **$14.95/mo**
- SMRT Algo : **~$15-30/mo** suivant le tier
- Cryptohopper Pioneer/Adventurer/Hero : **$19-99/mo** ([Cryptohopper review altrady](https://www.altrady.com/blog/crypto-bots/cryptohopper-review))
- 3Commas Pro : **~$50-100/mo**
- Copy-trading sur exchange : 0 fixe + 10 % de perf fee sur les meilleurs traders Binance
- Finestel / Stoic : pricing variable, dépose minimum $250-1000 typique sur copy-trading sérieux

**Pour trading-bot-v2** : Segment B + C (open-source + Discord payant) est le chemin réaliste à court terme. Segment D ou E (SaaS / copy) demande infrastructure et compliance MiCA. Segment F demande structure juridique + licence — pas avant 2027 si jamais.

### 5.4 Mon recommandation client cible

**Phase 1 (aujourd'hui → 6 mois)** : segment A. Tu fais tourner pour toi seul. Valide la rentabilité OOS et live paper.

**Phase 2 (6-18 mois)** : segment B. Open-source partial (le moteur ICC, les TUs), monétise via consulting / formation / Patreon. Communauté Discord gratuite + tier payant avec accès aux signaux du bot. Pas de licence requise tant que tu ne fais pas d'exécution automatique pour autrui.

**Phase 3 (18+ mois, optionnel)** : segment D ou E si tu veux scaler. Structure CASP, partenariat avec une plateforme copy-trading existante (Finestel a déjà l'infra et la conformité), ou intégration TradingView via Lightspeed/AutoView pour des signaux automatisés sur compte client.

---

## 6. Projection financière réaliste — 3 scénarios

### 6.1 Hypothèses transversales

- **Année type** = comportement marché crypto modéré, ni full bull 2024-2025 ni full bear 2018/2022. Hypothèse de retour à la moyenne.
- **Sharpe brut** issu du backtest in-sample V1 = estimation 1.5-2.0 ; **Sharpe net** réaliste après friction réelle + slippage live = **0.8-1.3** (haircut classique 30-40 %).
- **Drawdown anticipé** = backtest 7 % → live anticipé **15-25 %** (haircut classique 2-3x).
- **Rendement annuel brut V1** sur backtest = +501 pp / 2 ans = ~250 pp annuel = **+250 %** brut equally-weighted across 8 assets. **À pondérer par le sizing réel** : tu ne peux pas tenir 8 positions full-size simultanées si les corrélations sont là.
- **Sizing réaliste** : 1/8e du capital par position pleine, soit ~12.5 % d'exposition par trade, donc rendement portefeuille ≈ ΣPnL/N_assets = 501 / 8 = ~63 pp sur 2 ans = **~31 %/an portefeuille brut**.
- **Friction** : -3 à -5 pp/an de drag réaliste (fees + slippage + market impact).
- **Net annuel V1 hors fiscalité estimé** : **20-28 %**.
- **Crypto hedge fund quant 2025** : 48 % moyenne, Sharpe 1.6 ([sqmagazine](https://sqmagazine.co.uk/crypto-hedge-funds-statistics/)). On vise réaliste à un niveau retail.

### 6.2 Scénario A — État actuel (mai 2026, bot V1, 8 actifs)

| Capital | Bas (Sharpe 0.8, DD 25%) | Médian (Sharpe 1.0, DD 18%) | Haut (Sharpe 1.3, DD 15%) |
|---|---|---|---|
| **$10 000** | +$1 200 / -25 % (perte max -$2 500) | **+$2 200** / DD -18 % | +$3 200 / DD -15 % |
| **$50 000** | +$6 000 | **+$11 000** | +$16 000 |
| **$100 000** | +$12 000 | **+$22 000** | +$32 000 |

Hypothèses : capital en USD equivalent, bot tournant 24/7, fiscalité non déduite (à -31.4 % en PFU sur PV nettes), pas de levier au-delà de la position 1x spot équivalent.

Au capital $10k, **médian = +$2 200/an net de friction**. Couvrir un loyer ou un coût VPS — pas un revenu de remplacement.

### 6.3 Scénario B — Fin de la conception (12-18 mois)

Hypothèses : friction réaliste intégrée au backtest, walk-forward OOS validé, funding_capture poussée jusqu'à live (+ICC swing), mode INTRADAY/SCALPING **non implémenté** (recommandation section 2), monitoring + sizing portefeuille en place.

Adjustments :
- ICC swing : Sharpe net espéré 1.0-1.4, ~22-32 % rendement annuel (consolidé).
- Funding capture sur Hyperliquid (delta-neutral, indépendant) : APR net **+5-15 %** sur BTC/ETH, jusqu'à **+25-50 %** sur SOL/AVAX/DOT si on accepte le risque liquidation < 5x.
- Sizing : ICC sur ~50 % du capital, funding sur ~50 % (delta-neutre donc ne consomme pas le même "risk budget" mais consomme du collateral). Combined effective return = ICC * 0.5 + Funding * 0.5.

| Capital | Bas | Médian | Haut |
|---|---|---|---|
| **$10 000** | +$1 800 (Sharpe combo ~0.9) | **+$3 000** (Sharpe combo ~1.2) | +$4 500 (Sharpe combo ~1.5) |
| **$50 000** | +$9 000 | **+$15 000** | +$22 500 |
| **$100 000** | +$18 000 | **+$30 000** | +$45 000 |

Médian sur $50k = +$15 000/an. À ce niveau, le bot couvre largement les coûts d'infrastructure (VPS, abos data, monitoring) et commence à générer un revenu complémentaire.

### 6.4 Scénario C — Optimisé (24+ mois)

Hypothèses : multi-stratégies en portefeuille (ICC swing + funding capture + trend following léger en complément), multi-comptes (Kraken + Hyperliquid + une 3e venue type Bybit), SaaS ou pool copy-trading lancé via partenariat (segment E), structure CASP en cours ou contractualisée auprès d'un partenaire licencié.

Revenus :
- **Propres trades** : capital $100k-500k → +20-30 %/an = $25k-150k
- **Copy-trading / Patreon / signaux payants** : 100-500 abonnés à $20-50/mo = **+$24-300k/an** (très dépendant de l'effort communautaire et de la performance affichée)
- **Perf fees éventuel partenariat plateforme** : 10-20 % sur capital géré client externe, ~$10-50k/an si on attire $500k-1M de capital tiers

| Setup | Bas | Médian | Haut |
|---|---|---|---|
| Propre $100k + 100 subs $20/mo | +$45k/an | **+$70k/an** | +$100k/an |
| Propre $500k + 500 subs $30/mo | +$200k/an | **+$320k/an** | +$500k/an |

⚠️ Le scénario C suppose **un succès marketing/communauté**. C'est l'inconnue dominante. Sur le pur trading propre, le médian top est ~30 %/an net — pas de magie possible sans levier supplémentaire.

### 6.5 Recommandation chiffrée

**Capital de démarrage recommandé : $20-50k** une fois le walk-forward OOS validé et 3 mois de paper live propres. Sous $10k, le drag fees/slippage devient pénalisant et le drawdown $-2k psychologiquement difficile à tenir.

**Cible 12 mois** : Scénario B médian sur $30k = +$9 000/an net de friction, hors fiscalité. Validation de la viabilité économique. À ce stade, décision Phase 3 / extension.

**Cible 24-36 mois** : Scénario C médian si la dimension communautaire est embarquée. Sans communauté, plafond Scénario B sur $100-500k → +$30-100k/an pur trading propre.

---

## 7. Question IBKR — réponse claire

**Question** : *Est-ce que trading-bot-v2 nécessite IBKR (Interactive Brokers) avec capital réel ?*

**Réponse : NON.**

J'ai cherché toutes les variations (`IBKR`, `Interactive Brokers`, `ib_insync`, `ib_api`, `ibapi`, `TWS`, `IB Gateway`) dans tout le repo (`*.py`, `*.md`, `*.yaml`, `*.txt`) : **zéro mention**.

Ce que le projet mentionne en termes de broker :
- `docs/RECAPS/SESSION_6_CADRAGE.md` : *"⚠️ Cette version remplace le v1 qui prévoyait un broker (Kraken/OANDA). Phase 1 = paper trading local sans broker, zéro capital immobilisé, zéro engagement."*
- Le broker envisagé pour Phase 2 est **Kraken** (crypto), pas IBKR.
- `paper_trading/order_simulator.py` : simulateur local, pas de connexion broker.
- `config.yaml` : exchange = `hyperliquid` (DEX, pas IBKR).

**Aucun fichier ne suggère d'ouvrir un compte IBKR pour ce projet.** Si l'utilisateur a un souvenir d'avoir dû ouvrir IBKR, il s'agit certainement d'un **autre projet** — par exemple le sibling project *ICC Trading Bot* qui couvrait potentiellement du forex/futures (IBKR est l'API standard pour ces marchés). Mais sur trading-bot-v2, c'est crypto pur, exchanges crypto (Hyperliquid, Kraken), zéro IBKR.

**À transmettre à l'user** : *"Non, pas ce projet. Tu peux laisser IBKR de côté pour trading-bot-v2. Si tu as eu cette demande pour un autre projet (probablement le sibling ICC Trading Bot ou un projet TradFi/forex/futures), on regardera celui-là séparément."*

---

## Sources

### Section 2 — Vision d'expert
- [Smart Money Concepts in Crypto: How Institutions Actually Trade — buildix.trade, 2026](https://www.buildix.trade/blog/smart-money-concepts-crypto-trading-institutional-orderflow-2026)
- [SMC & ICT Trading Guide 2026 — ForexTradeLab](https://forextradelab.com/blog/smart-money-concepts-ict-trading-guide/)
- [Hyperliquid funding rate strategy 2026 — MEXC Learn](https://www.mexc.com/learn/article/hyperliquid-funding-rate-strategy-earning-passive-income-in-2026/1)
- [Hyperliquid vs CEXs perp arbitrage 2026 — Neural Arb](https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/)
- [Hyperliquid funding docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)

### Section 3 — SWOT
- [Hyperliquid TVL fees revenue — DeFiLlama](https://defillama.com/protocol/hyperliquid)
- [Hyperliquid Owns 13% Of All Perp Volume — Yellow.com](https://yellow.com/research/hyperliquid-perp-volume-dominance-how-2026)
- [Hyperliquid Hits 44% Of All Perp DEX Volume — Yellow.com](https://yellow.com/news/hyperliquid-perpetual-dex-volume-share)
- [Why Most Trading Bots Lose Money — For Traders](https://www.fortraders.com/blog/trading-bots-lose-money)
- [Are Crypto Trading Bots Profitable — GoatFundedTrader](https://www.goatfundedtrader.com/blog/are-crypto-trading-bots-profitable)
- [Arbitrage Opportunities in Perpetual DEXs — Pi2 Network](https://blog.pi2.network/arbitrage-opportunities-in-perpetual-dexs-a-systematic-analysis/)

### Section 4 — Recherche web (sources principales)

ICC / SMC :
- [smart-money-concepts Python package — joshyattridge GitHub](https://github.com/joshyattridge/smart-money-concepts)
- [LuxAlgo SMC Indicator — TradingView](https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/)
- [Zeiierman SMC Premium — TradingView](https://www.tradingview.com/script/eJdZpiDr-Smart-Money-Concepts-Premium-Expo/)
- [SMC Sniper Pro — TradingView](https://www.tradingview.com/script/UVjjiTx1-SMC-Sniper-Pro/)
- [SMRT Algo](https://smrtalgo.com/)
- [Smart money concepts in crypto trading — Cointelegraph](https://cointelegraph.com/news/smart-money-concepts-smc-in-crypto-trading-how-to-track-profit)

Performance bots crypto :
- [Most Profitable Trading Bots 2026 — WunderTrading](https://wundertrading.com/journal/en/reviews/article/top-profitable-trading-bots)
- [3Commas vs Cryptohopper 2026 — browse-ai.tools](https://www.browse-ai.tools/blog/top-ai-tools-crypto-traders-3commas-vs-cryptohopper-2026)
- [Cryptohopper Review 2026 — Altrady](https://www.altrady.com/blog/crypto-bots/cryptohopper-review)
- [Are Crypto Trading Bots Worth It 2025 — Coincub](https://coincub.com/are-crypto-trading-bots-worth-it-2025/)

Hedge funds quant :
- [Crypto Hedge Funds Statistics 2026 — SQ Magazine](https://sqmagazine.co.uk/crypto-hedge-funds-statistics/)
- [Best Performing Crypto Funds 2025 — Crypto Fund Research](https://cryptofundresearch.com/best-performing-crypto-funds/)
- [Industry Guide to Crypto Hedge Funds 2025 — Crypto Insights Group](https://www.cryptoinsightsgroup.com/resources/industry-guide-to-crypto-hedge-funds-2025-edition)

Régulation :
- [MiCA 2026 for Crypto Arbitrage — Neural Arb](https://www.neuralarb.com/2026/03/13/mica-2026-for-crypto-arbitrage/)
- [Markets in Crypto-Assets Regulation (MiCA) — ESMA](https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/markets-crypto-assets-regulation-mica)
- [MiCA Regulation 2026 — Sumsub](https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/)
- [MiCA Regulation Tracker — Latham & Watkins](https://www.lw.com/en/markets-in-crypto-assets-regulation-tracker)

Fiscalité France :
- [Fiscalité Crypto 2026 — Hagnere Patrimoine](https://www.hagnere-patrimoine.fr/guides-patrimoine/comment-payer-moins-impots/fiscalite-cryptomonnaies-2026)
- [Fiscalité crypto France 2026 — Waltio](https://www.waltio.com/fr/tout-savoir-sur-la-fiscalite-crypto/)
- [Déclaration plus-values actifs numériques — impots.gouv.fr](https://www.impots.gouv.fr/particulier/questions/comment-declarer-les-plus-ou-moins-values-sur-cessions-dactifs-numeriques)
- [Fiscalité crypto Ramify](https://www.ramify.fr/crypto/fiscalite)

### Section 5 — Marché
- [TradingView Subscriptions pricing](https://www.tradingview.com/pricing/)
- [Best Crypto Copy Trading Platforms 2026 — Koinly](https://koinly.io/blog/best-crypto-copy-trading-platforms/)
- [Best Crypto Copy Trading 2026 — Bitget Academy](https://www.bitget.com/academy/crypto-copy-trading-2)
- [Best Crypto Copy Trading Platforms 2026 — Finestel](https://finestel.com/blog/best-crypto-copy-trading-platforms/)
- [Best Crypto Copy Trading Platforms 2026 — Stoic.ai](https://stoic.ai/blog/best-crypto-copy-trading-platforms-in-2026-complete-review-from-a-professional-trader/)

### Section 6 — Projections (sources de calibration)
- [Crypto Hedge Funds Statistics 2026 — SQ Magazine](https://sqmagazine.co.uk/crypto-hedge-funds-statistics/) (Sharpe 1.6, vol 46 %, avg 48 % return quant 2025)
- [Hyperliquid funding strategy 2026 — Neural Arb](https://www.neuralarb.com/2026/04/24/hyperliquid-vs-cexs-perp-arbitrage-after-fees-funding-slippage/) (APR funding arb 3-12 % majors, 20-60 % mid-caps)
- Backtest interne `results/sl_v1_vs_v2_20260512_150242.json` (V1 reference numbers)

---

*Fin du dossier. Toute donnée non sourcée explicitement est issue d'analyses du code et résultats backtest interne au projet `trading-bot-v2`, commit `fbf497a` du 12 mai 2026.*
