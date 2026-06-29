# Trading Bot V2 — Loss Forensic Phase 2 / H1 (min_hold_hours extension)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 17:15 UTC
**Hypothesis tested** : **H1 — Extending `min_hold_hours` (24 → 36 → 48 → 60) improves expectancy on BTC+ETH post-drop-SOL universe under realistic friction.**

**Discipline P31 + P33** :
- Branch dédiée : `analysis/loss-forensic-H1-min-hold-extended` ✓
- Pre-snapshot : `snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Post-snapshot : sera créé en fin de session
- Append-only sur ce fichier
- **P33 No-Skip enforced** : H1 testé même après que H4 ait suggéré un pivot direct vers H3. *On ne met rien de côté on n'a pas assez d'expertise pour savoir ce qui est négligeable d'essentiel.* Le résultat empirique tranche. Et il tranche — voir Verdict.

---

## 1. Méthodologie

### 1.1 Sample

- **Data** : `cache/funding_hyperliquid_{BTC,ETH}_USDC_USDC.parquet` — historique HL funding 2024-01-01 → 2026-05-04 = 854 jours = 28.5 mois
- **Period periodicity** : hourly (Hyperliquid)
- **n_periods** : 20 500 par asset
- **Capital** : $10 000 notional par asset (in line with V2 paper)
- **Friction** : `entry_cost_bps = exit_cost_bps = 10` (= 20 bps round-trip per trade, conservative incl. perp taker 7 bps + spot leg + slippage)

### 1.2 Walk-forward split (P3 discipline)

- **In-sample (IS)** : 2024-01-01 → 2025-03-15 (~14.5 mois)
- **Out-of-sample (OOS)** : 2025-03-15 → 2026-05-04 (~13.5 mois, 9 970 periods)
- **Verdict basé sur OOS uniquement** pour intégrité

### 1.3 Variants testées

| min_hold_hours | Comment |
|---|---|
| 24 | Baseline production current |
| 36 | +50 % de min_hold |
| 48 | +100 % |
| 60 | +150 % |

### 1.4 Alpha_lab discipline appliquée

| Gate | Application H1 |
|---|---|
| OOS récent | Split 2025-03-15+ ✓ |
| Ensemble debiasing | Moyenne sur 4 valeurs, no cherry-pick ✓ |
| Plateau detection | Test ±10 % autour optimal (54, 60, 66) ✓ |
| DSR (multi-test penalty) | Computed for N=4 tests ✓ |
| **Beat trivial benchmark** | Comparé à "always-in-position" (filter off) ✓ |
| Statistical confidence (n_trades) | 81 OOS combined BTC+ETH (suffisant pour ordre de grandeur, marginal pour confidence intervals serrés) |

---

## 2. Résultats principaux

### 2.1 BTC+ETH combined portfolio — FULL period (28.5 mo)

| min_hold | N trades | Gross funding | Total cost | **Net PnL** | Expectancy/trade | CAGR % |
|---|---:|---:|---:|---:|---:|---:|
| **24 (baseline)** | 124 | $6 826.75 | $2 480 | **$4 346.75** | $35.05 | ~9 % |
| 36 | 118 | $6 808.35 | $2 360 | **$4 448.35** | $37.70 | ~9 % |
| 48 | 109 | $6 803.33 | $2 180 | **$4 623.33** | $42.42 | ~9.5 % |
| 60 | 97 | $6 794.34 | $1 940 | **$4 854.34** | $50.04 | ~10 % |

**Monotonic improvement** : net PnL et expectancy croissent linéairement avec min_hold de 24 → 60.

### 2.2 BTC+ETH combined — OOS (13.5 mo)

| min_hold | N trades | Gross funding | Total cost | **Net PnL** | Expectancy/trade |
|---|---:|---:|---:|---:|---:|
| **24 (baseline)** | 81 | $1 842.34 | $1 620 | **$222.34** | $2.74 |
| 36 | 76 | $1 832.27 | $1 520 | **$312.27** | $4.11 |
| 48 | 71 | $1 826.25 | $1 420 | **$406.25** | $5.72 |
| 60 | 64 | $1 818.77 | $1 280 | **$538.77** | $8.42 |

**Monotonic improvement OOS également.** OOS expectancy à `min_hold=60` est ~3x baseline (24).

### 2.3 Per-asset breakdown OOS (médian Hyperliquid friction)

| Asset | min_hold | N | Net | Expectancy | Sharpe | Max DD % | WR % |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 24 | 40 | $141.79 | $3.54 | 1.47 | -3.59 | 17.5 |
| BTC | 36 | 38 | $170.29 | $4.48 | 1.81 | -3.30 | 18.4 |
| BTC | 48 | 34 | $246.78 | $7.26 | 2.77 | -2.93 | 20.6 |
| **BTC** | **60** | **29** | **$349.27** | **$12.04** | **4.23** | **-2.15** | **24.1** |
| ETH | 24 | 41 | $80.55 | $1.96 | 0.83 | -2.68 | 22.0 |
| ETH | 36 | 38 | $141.97 | $3.73 | 1.51 | -2.28 | 23.7 |
| ETH | 48 | 37 | $159.47 | $4.31 | 1.72 | -2.06 | 24.3 |
| **ETH** | **60** | **35** | **$189.51** | **$5.41** | **2.10** | **-1.91** | **25.7** |

### 2.4 Plateau detection autour de min_hold=60 (robustness ±10 %)

| Asset | mh=54 | mh=60 | mh=66 | Variation max |
|---|---:|---:|---:|---|
| BTC OOS net | $307.46 | $349.27 | $346.26 | ±12 % — pas un plateau strict, mais 60 et 66 quasi-identiques |
| BTC OOS Sharpe | 3.61 | 4.23 | 4.20 | Pic à 60, 66 dans 1 % |
| ETH OOS net | $155.90 | $189.51 | $185.08 | ±18 % — pic à 60, 66 dans 2 % |
| ETH OOS Sharpe | 1.68 | 2.10 | 2.05 | Pic à 60, 66 dans 2 % |

**Plateau detection** : les valeurs `[60, 66]` sont robustes ±5 %. La valeur `54` montre une dégradation de 12 % (BTC) et 18 % (ETH), suggérant que le pic est asymétrique : robuste à la hausse, fragile à la baisse de min_hold.

### 2.5 Ensemble debiasing (no cherry-pick)

Moyenne arithmétique des 4 valeurs testées, pour estimer la performance robuste si on choisit aléatoirement :

| Asset | Window | Ensemble net | Ensemble expectancy |
|---|---|---:|---:|
| BTC | Full | $2 610.15 | $55.40 |
| ETH | Full | $1 958.05 | $30.86 |
| BTC | OOS | $227.03 | $6.83 |
| ETH | OOS | $142.87 | $3.85 |

Ensemble OOS BTC+ETH combined ≈ $370 net sur 13.5 mois.

### 2.6 DSR correction

`sqrt(ln(4) / 9970)` = 0.0118 → Sharpe haircut ~0.59 sur les valeurs OOS. Les Sharpes annualisés OOS restent positifs après correction (BTC 60 : 4.23 → ~3.64 ; ETH 60 : 2.10 → ~1.51). Pas de gate failure sur ce critère.

---

## 3. 🚨 Beat trivial benchmark — le gate critique qui FAIL

### 3.1 Always-in-position benchmark (filter off)

Stratégie triviale : position = 1 du début à la fin, 1 seul entry + 1 exit, payés en friction. Aucun filtrage funding.

| Asset | Window | N trades | Net PnL | Sharpe | CAGR % | Max DD % |
|---|---|---:|---:|---:|---:|---:|
| BTC | Full | 1 | **$3 541.30** | 56.66 | 13.84 | n/a |
| ETH | Full | 1 | **$3 149.47** | 55.26 | 12.42 | n/a |
| BTC | OOS | 1 | **$875.05** | 42.07 | 7.66 | -0.18 |
| ETH | OOS | 1 | **$790.66** | 36.53 | 6.93 | -0.34 |

### 3.2 Filtered strategy vs always-in — comparaison OOS

| Asset | Best filter (min_hold=60) net OOS | Always-in net OOS | **Diff** | Filter underperformance |
|---|---:|---:|---:|---|
| BTC | $349.27 | $875.05 | **−$525.78** | Filter perd **60 %** vs benchmark |
| ETH | $189.51 | $790.66 | **−$601.15** | Filter perd **76 %** vs benchmark |
| **Combined** | **$538.77** | **$1 665.71** | **−$1 126.94** | **Filter perd 68 %** vs always-in |

**Le filter détruit de la valeur de manière systémique sur l'OOS.** Pour chaque trade que le filter ferme pour "éviter une période défavorable", il paie 20 bps de friction round-trip et rejette parfois des périodes où le funding redevient positif rapidement.

### 3.3 Lecture critique

L'analyse révèle un fait beaucoup plus important que l'optimisation de min_hold :

- **La stratégie funding capture telle que designée (entry/exit filter sur signal smoothed) est dominée par la stratégie triviale "always-in" sur cet historique HL 2024-2026.**
- Le filter détruit de la valeur via la friction d'entrée/sortie, sans capturer suffisamment de protection contre les périodes de funding négatif.
- Améliorer `min_hold` réduit l'auto-destruction du filter (moins de trades = moins de friction), mais ne fait que rapprocher le filter du benchmark trivial — sans le dépasser.

**Conclusion économique** : à friction 20 bps RT sur historique 2024-2026, **la meilleure variante filtrée (min_hold=60) capture seulement 32 % de la valeur que le benchmark trivial capture**.

---

## 4. Verdict H1

### 4.1 Synthèse alpha_lab

| Gate | Pass / Fail | Détail |
|---|---|---|
| Effect detectable (mh extension change PnL) | **PASS** | Monotonic improvement 24 → 60 |
| OOS positive (mh=60 > 0) | **PASS** | $538.77 net BTC+ETH combined |
| Robustness ±10 % around optimum | **PARTIAL** | Robuste à la hausse (60 = 66), fragile à la baisse (60 → 54 perd 12-18 %) |
| DSR-corrected Sharpe (4 tests) | **PASS** | Sharpe BTC 60 reste ~3.64 post-DSR |
| **Beat trivial benchmark** | **🔴 FAIL** | Always-in OOS = $1 665.71 vs best filter $538.77 (filter perd 68 %) |
| Ensemble debiasing (no cherry-pick) | **MARGINAL** | $370 net OOS — au-dessus de 0 mais loin du benchmark $1 665.71 |

### 4.2 Decision per Sebastien's criteria

> **GO** : min_hold optimal trouvé, robuste, beat benchmark → mérite intégration
> **MARGINAL** : effet detectable mais fragile → archive avec notes
> **NO-GO** : pas d'effet measurable au-dessus baseline → archive

**Verdict H1 = MARGINAL**, with **a stronger caveat that overrides the parameter decision** :

L'effet de `min_hold_hours` extension est **réel et bénéfique en isolation** (60 > 24 sur 5 métriques sur 5), mais le **gate "beat trivial benchmark" du critère alpha_lab échoue** : la stratégie filtered, quel que soit le min_hold testé, est dominée par la stratégie "always-in-position" (filter off) sur l'OOS 13.5 mois 2025-2026.

**Recommandation V2** :
- ❌ **NE PAS merger H1 sur main** (même avec min_hold=60 optimal) — l'amélioration locale ne sauve pas un design strategique qui sous-performe le benchmark trivial
- ✅ **Archiver H1 results** comme baseline empirique pour les hypothèses suivantes
- 📌 **Faire remonter à Sebastien la question stratégique critique** : faut-il garder un filter funding du tout, ou pivoter vers une stratégie "always-in delta-neutre avec gestion de risque sur extrême funding" ?

### 4.3 Mention P33

Conformément au principe operator no-skip (P33), H1 a été testé même après que H4 ait suggéré un pivot direct vers H3 (asset filter). **Le résultat empirique tranche : H1 fail le beat-benchmark gate, et révèle un problème structurel plus profond que H3 seul n'aurait pas identifié.** Si V2 avait bypassé H1, le finding "filter destroys value vs always-in" serait resté caché jusqu'à H3 ou plus tard, perdant du temps sur des optimisations marginales d'un design fondamentalement sous-optimal.

P33 a fait son travail.

---

## 5. Implications pour les hypothèses Phase 2 suivantes

### 5.1 H3 (Asset filter) — révision préalable

H4 avait identifié SOL comme killer économique (gross $23.65 < fees $90). H1 révèle que **même sur BTC+ETH post-drop-SOL, le filter est sous-optimal vs always-in**.

H3 doit maintenant tester deux dimensions :
- (a) Asset universe restrict (BTC-only, BTC+ETH) — comme initialement prévu
- (b) **+ Compare to always-in benchmark sur l'univers restreint** — nouveau critère obligatoire

Si BTC always-in beat encore BTC filtered → H3 confirme le pivot vers une stratégie différente.

### 5.2 H2 (entry_threshold raising) — pertinence reduced

Si le filter en soi détruit de la valeur, raising le seuil d'entrée (0.005 → 0.01) ne fera que :
- Réduire encore le nombre de trades (moins de friction payée)
- Réduire la couverture funding capture
- Plus se rapprocher de "always-in" sans jamais l'atteindre

H2 reste à tester per P33, mais l'attente est qu'il converge vers une fraction de la performance always-in.

### 5.3 H5 (Delta-neutre hedge) — déjà dans le backtest

L'engine V2 (`backtest/engine.py`) modélise déjà une position delta-neutre (short perp + long spot). Les résultats de H1 sont donc **déjà en mode hedgé**, et le verdict "filter < always-in" tient sous cette hypothèse. H5 n'est pas un game-changer attendu — c'est plus une clarification design.

### 5.4 Nouvelle hypothèse émergente — H6 ?

À envisager : **always-in avec drawdown circuit-breaker** — pas de filter funding mais kill switch si funding rate cumulatif sur N heures sous seuil critique. Hybride entre la simplicité de always-in et la protection contre une dérive macro extrême.

À soumettre à Sebastien si validation Phase 2 reste ouverte après H1/H2/H3 archivés.

---

## 6. Memorable phrase / quote

> *min_hold=60 collecte $538 OOS. always-in collecte $1665 sur les mêmes 13.5 mois. Le filter coûte $1127, soit 68 % de la valeur qu'il prétend protéger.*

Et plus succinct :

> *P33 a fait son travail : H1 a passé tous les gates sauf le seul qui compte (beat trivial benchmark). Si j'avais bypassé H1 per ma proposition post-H4, ce finding serait resté caché.*

---

## 7. Prochain pas

**H1 — LIVRÉ. Verdict MARGINAL avec override "beat-benchmark fail". Branche `analysis/loss-forensic-H1-min-hold-extended` archivée, pas de merge sur main.**

**Validation Sebastien requise sur** :
1. Le verdict beat-benchmark fail (filter < always-in) — confirmer ou demander vérification additionnelle
2. La question stratégique critique : faut-il garder un filter funding dans le design V2 ?
3. La priorité Phase 2 suivante :
   - **Option A** : continuer H3 puis H2 strictly per P33 ordre original
   - **Option B** : Sebastien accepte que H3/H2 testent maintenant aussi le beat-benchmark gate explicitement (révision méthodo, pas skip)
   - **Option C** : ouvrir H6 (always-in + circuit breaker) dès maintenant comme hypothèse compétitive

**Snapshot post-H1** à créer après validation. Production code main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` reste **INTACT**.

---

*Phase 2 H1 generated by V2 agent on 2026-06-26 by read-only analysis of historical funding data via existing `strategies/funding_capture.py` + `backtest/engine.py` (no code modification). Snapshot pre-H1 `snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended`. Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — INTACT.*
