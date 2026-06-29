# SL Buffer Observation Hypothesis (Phase 1)

> **Statut** : hypothèse de surveillance proposée par V2 pour data-driven
> validation des buffers SL Phase 1 (Gold +$5, BTC **+$300**, ETH **+$10**)
> finalisés par Sebastien 29 mai 2026 PM-3.
>
> **Honnêteté** : le daemon actuel `paper_funding_capture` est
> **delta-neutre** (funding arb hedgé sur HL), il **NE produit PAS de
> données de stop-out** parce que les positions n'ont pas de SL
> directionnel. Pour générer les données empiriques nécessaires à
> l'arbitrage Phase 1 → Phase 2, deux chemins.

## Approche A — Backtest simulation (recommandée pour 3 juin)

**Principe** : simuler l'exécution de la stratégie ICC directional avec
les buffers Phase 1 sur l'historique récent disponible, et mesurer le
stop-out rate par actif.

**Avantages** :
- Données disponibles immédiatement (pas besoin d'attendre)
- Volume de trades simulés suffisant pour signal statistique (estimé
  20-60 trades par actif sur la fenêtre 6 mois)
- Permet comparaison Phase 1 (buffers fixes) vs Phase 1-alt (buffers
  ATR-normalized) en un seul run
- Aucun nouveau code daemon à déployer pendant la fenêtre absence

**Inconvénients** :
- Backtest ≠ paper trading (slippage modélisé, pas vécu)
- Re-introduit P14 risque look-ahead si pas codé proprement (le
  swing_cluster_top doit être calculé strictement à entry_bar)

**Implémentation suggérée** :
- Script `scripts/sl_buffer_stopout_sim.py` (à coder le **2 juin** en
  préparation meeting 3 juin)
- Input : historique Gold/BTC/ETH H4 sur fenêtre 6 mois OOS
- Pour chaque OB détecté par V2-dyn : simuler entrée avec SL =
  `swing_cluster_top + buffer[asset]`, suivre 20 bougies après pour
  voir si SL hit avant TP/timeout
- Output : `data/sl_buffer_sim/<asset>_stopout_rate.csv` avec colonnes
  `[ob_id, asset, entry_price, sl_price, time_to_stop_or_tp, hit_sl,
  hit_tp, max_adverse_excursion, max_favorable_excursion]`
- Metric clé : **stop-out rate (% des trades qui touchent SL avant TP)**
- Cible psychologique : 30-40% acceptable, > 50% = buffer trop tight,
  < 20% = buffer trop large

## Approche B — ICC directional paper daemon (longer term, post-3 juin)

**Principe** : scaffolder un 2e daemon paper trading distinct du
`paper_funding_capture`, qui exécute la stratégie ICC directionnelle
avec les buffers Phase 1 sur des prix HL temps réel.

**Avantages** :
- Données live, slippage réel, latence réelle
- Génère également des données pour V3 calibration plus large

**Inconvénients** :
- Nouveau daemon = nouveau code = risque opérationnel pendant la
  fenêtre absence — viole probablement Principle 18 (no mid-trip
  parameter changes)
- Seulement ~1 semaine de données entre déploiement et 3 juin —
  insuffisant pour signal statistique
- Plus de surface à monitorer pour Sebastien

**Recommandation** : **REPORTER cette approche à Phase 2** post-3 juin,
si l'Approche A indique que les buffers Phase 1 sont marginalement
acceptables et qu'on veut confirmation en live.

## Décision proposée

1. **Avant 3 juin** : exécuter Approche A (backtest simulation) →
   produire `SL_BUFFER_REPORT_3JUIN.md` avec stop-out rate observé par
   actif + recommandation Phase 2 buffer values.
2. **Au meeting 3 juin** : Sebastien + Badoun arbitrent — soit on garde
   Phase 1 buffers, soit on les ajuste avant de déployer ICC paper en
   Phase 2.
3. **Post-3 juin (Phase 2)** : si les Phase 1 buffers sont validés,
   scaffolder l'Approche B pour live paper validation continue.

## Métrique de succès (binary acceptance criteria, per Pattern 7)

- **Phase 1 buffers OK** ssi : stop-out rate observé sur 50+ trades
  simulés par actif **entre 25% et 50%** sur les 3 actifs.
- **Phase 1 buffers à élargir** ssi : stop-out rate > 50% sur ≥ 2 actifs.
- **Phase 1 buffers à resserrer** ssi : stop-out rate < 20% sur ≥ 2
  actifs (capital efficiency suboptimale).

## Risque opérationnel immédiat à relayer

Avant que Sebastien continue ses captures de pattern dataset, voici mon
**assessment honnête** sur les valeurs Phase 1 (basé sur l'observation
des wicks H4 dans l'alignment exercise 11-22 mai), **mis à jour avec la
révision PM-2 BTC $50 → $300** :

- **Gold +$5** : ✅ raisonnable. Wick excess moyen au-dessus body close
  ~$3-8 sur H4 → buffer $5 absorbe le bruit standard, pas les
  manipulation extremes. **Stop-out rate prédit : 25-35%**.
- **ETH +$10** ✅ **(finalisé 29 mai PM-3)** : Sebastien a choisi $10
  vs ma suggestion $15-25 — choix conservateur, Phase 2 ajustable
  vers le haut si stop-out observé reste tight. Couvre les wicks H4
  typiques ($4-10) avec marge limitée pour manipulations. **Stop-out
  rate prédit : 22-32%** (delta -10 à -15 pp vs $5 buffer ancien).
  ETH +$10 = 0.484% spot, ratio plus conservateur que BTC +$300
  (0.397% spot) en pourcentage, mais en absolu plus tight relatif
  au wick excess H4. À surveiller particulièrement.
- **BTC +$300** ✅ **(révisé 29 mai PM-2)** : couvre le wick excess H4
  typique ($80-200) + marge pour manipulations modérées. **Stop-out
  rate prédit : 18-30%** (delta -15 à -20 pp vs $50 buffer ancien).
  Trade-off : SL distance plus large = perte par trade stoppé plus
  grande. R:R impact à mesurer dans simulation Approche A.

**Logique de la révision BTC $50 → $300** : le swing_cluster_top inclut
déjà les wicks observés du cluster. Un buffer de seulement $50 au-dessus
serait percé par n'importe quelle nouvelle mèche dépassant la mèche max
historique du cluster par > $50 — typique en BTC où les "stop hunts"
de $200-500 au-dessus du cluster sont courantes. Le buffer $300 met le
SL hors de portée de la majorité des stop hunts non-directionnels, tout
en restant en-dessous d'un vrai breakout structurel (qui irait
généralement >$500 au-dessus).

**Conclusion à relayer à Sebastien (mise à jour 29 mai PM-3 — table FINALE)** :
Tous les 3 buffers Phase 1 sont maintenant arbitrés. Gold et BTC
confortables ; ETH +$10 est conservateur — à surveiller particulièrement
sur les premières semaines de simulation/paper trading car peut basculer
en zone "tight" sur sessions de manipulation intense (UK open, NY open
news). **Pas de blocker immédiat** — captures pattern dataset peuvent
continuer normalement.

**IMPORTANT — Trade-off R:R / Expectancy** (à intégrer dans le script
simulation `sl_buffer_stopout_sim.py` du 2 juin) :

Le buffer plus large ne se mesure pas uniquement par le stop-out rate.
Le critère pertinent est l'**expectancy nette** :

```
expectancy = WR × avgWin − (1 - WR) × avgLoss
```

Où :
- WR = (1 − stop-out rate) si on assume que les trades non stoppés
  atteignent le TP
- avgWin = distance moyenne du TP au prix d'entrée
- avgLoss = `buffer[asset]` (par construction, le SL est à
  `swing_cluster_top + buffer[asset]` au-dessus de l'entrée)

Pour BTC, élargir le buffer de $50 → $300 multiplie avgLoss par 6.
Si le stop-out rate ne baisse que de 35-50% → 18-30%, le gain WR est
~+17 pp mais la perte de R:R est ~-83% par trade stoppé. Net effect
sur expectancy à mesurer empiriquement.

**Le script simulation DOIT modéliser les 3 dimensions** :

1. **Stop-out rate par actif** (% trades qui hit SL avant TP/timeout)
2. **R:R moyen sur trades non stoppés** (TP distance / SL distance)
3. **Expectancy nette par actif** (formule ci-dessus, en USD ou en R)

**Trois critères de succès Phase 1 (binary, per Pattern 7 méthodologie)** :

- ✅ OK si : stop-out 25-50% **ET** expectancy nette > 0 (en R) **ET**
  ratio R:R moyen ≥ 1.5 sur trades winners
- ⚠ À élargir buffer ssi : stop-out > 50% sur ≥ 2 actifs (le SL est
  trop tight, on se fait sortir trop souvent)
- ⚠ À resserrer buffer ssi : stop-out < 20% mais expectancy nette
  négative ou marginale (capital efficiency mauvaise, le SL trop large
  consomme tout l'edge)

Le 2 juin je code `scripts/sl_buffer_stopout_sim.py` avec ces 3
dimensions. Output : `data/sl_buffer_sim/<asset>_metrics.csv` +
rapport synthétique `SL_BUFFER_REPORT_3JUIN.md` listant les valeurs
observées par actif et la recommandation Phase 2 data-driven.

---

*Rédigé 29 mai 2026 par V2 — observation hypothesis pour data-driven
Phase 1 → Phase 2 transition. Sources : `STRATEGIC_LOGIC_DOC v2.2`
concept #14, `PRINCIPLES.md` v1.4 P14, alignment exercise data
22-23 mai 2026.*
