# Trading Bot V2 — Loss Forensic Phase 2 / H6 Robustness Test

**Author** : V2 agent (autonomous)
**Date** : 2026-06-26 23:35 UTC
**Hypothesis tested** : **H6 Robustness — Avant deployment paper du design "BTC+ETH+SOL + CB DD -0.75 %", confirmer que le finding H6 n'est pas un edge-case basé sur N=1 event historique. 4 axes de robustness à passer.**

**Discipline P31 + P33** :
- Branch dédiée : `analysis/loss-forensic-H6-robustness` ✓
- Pre-snapshot : `snapshots/SNAPSHOT_20260626T232553Z_pre_H6_robustness/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Post-snapshot : sera créé en fin de session
- Append-only sur ce fichier

---

## 1. AXE 1 — Plateau sensitivity DD threshold

### 1.1 Sweep autour de -0.75 % (optimum H6)

| Threshold | Net OOS | Delta vs best |
|---|---:|---|
| -0.50 % | $1 629.92 | **-22 %** 🔴 |
| -0.65 % | $1 614.56 | **-22 %** 🔴 |
| **-0.75 % (best)** | **$2 079.81** | baseline |
| -0.85 % | $2 069.52 | -0.5 % 🟢 |
| -1.00 % | $2 056.94 | -1.1 % 🟢 |
| -1.25 % | $2 031.91 | -2.3 % 🟢 |

### 1.2 Lecture critique — plateau asymétrique

**Asymétrie majeure détectée** :
- **Right side (less aggressive, |t| > 0.75)** : SMOOTH PLATEAU. Variation ±3 % entre -0.75 % et -1.25 %.
- **Left side (more aggressive, |t| < 0.75)** : **CLIFF**. -0.65 % perd 22 %, -0.50 % perd 22 %.

Le saut de $1 615 à $2 080 entre -0.65 % et -0.75 % révèle une **discontinuité comportementale** : ces deux thresholds capturent ou ratent l'event SOL critique selon le timing exact.

### 1.3 Verdict AXE 1

**🔴 FRAGILE** (asymétrique) — robuste sur 50 % du range ±25 % (côté supérieur), fragile sur 50 % (côté inférieur). En production, une mis-calibration de 0.10 % vers une CB plus agressive coûte $465 sur 13.5 mois.

---

## 2. AXE 2 — Walk-forward additional folds

### 2.1 Optimum CB threshold par fold

| Fold | OOS start | Best threshold | Best net |
|---|---|---:|---:|
| Fold 1 (default) | 2025-03-15 | -0.75 % | $2 079.81 |
| Fold 2 | 2025-06-01 | **-0.50 %** | $1 788.65 |
| Fold 3 | 2025-09-01 | **-0.50 %** | $789.39 |
| Fold 4 | 2025-12-01 | **-0.50 %** | $323.73 |

### 2.2 Lecture critique — instabilité optimum

**Optimum CB threshold varie sauvagement entre folds** : [-0.75 %, -0.50 %, -0.50 %, -0.50 %]. Range = 0.25 %. Center = -0.5625 %. ±25 % bound = 0.14 %. **Range > bound → fragile**.

L'optimum à -0.75 % est **spécifique au fold 1** (long OOS window incluant l'event Feb 2026). Sur les folds plus courts (fold 4 = 5 mois), l'optimum se déplace vers -0.50 % où la CB protège différemment les périodes courtes.

### 2.3 Décroissance du net par fold (sample size)

Le net décroît rapidement avec la longueur de l'OOS : $2 080 → $1 789 → $789 → $324. Ce n'est pas surprenant (moins de données = moins de funding accumulé), mais suggère que **le résultat H6 dépend fortement de la fenêtre incluant l'event Feb 2026**.

### 2.4 Verdict AXE 2

**🔴 FRAGILE** — l'optimum CB threshold n'est pas stable across folds. La calibration -0.75 % serait incorrecte pour 75 % des fenêtres OOS testées.

---

## 3. AXE 3 — Cross-period stress test (28.5 mois full)

### 3.1 CB events sur l'historique complet 2024-01 → 2026-05

À threshold -0.75 % (optimum AXE 1), événements CB observés sur les 3 assets sur les 28.5 mois :

| Asset | N events | Timing |
|---|---:|---|
| BTC | 0 | — (jamais déclenché, DD max -0.15 %) |
| ETH | 0 | — (jamais déclenché, DD max -0.34 %) |
| SOL | **1** | 2025-04-22 07:00 UTC, DD = -0.750 % |

**Total : 1 event sur 72 asset-months (24 mois × 3 assets)**.

### 3.2 Lecture critique — edge-case-protector confirmé

Per le brief Sebastien : *"Si N events = 1 (le seul Feb 2026) → fragile, conclure que CB est un edge-case-protector pas un mechanism general"*.

**Verdict statistique** : N=1 sur 28.5 mois ne suffit pas pour démontrer empiriquement qu'un CB design est une stratégie générale. C'est une protection contre **un événement spécifique** (le SOL down-funding regime de 2025-04 / 2026-02 selon le windowing).

### 3.3 Note sur le double-event temporal

L'event sur full period (2025-04-22) diffère du timing initialement reporté dans H6 OOS (2026-02-10). Pourquoi : le peak equity est computé relatif à la fenêtre. Sur full period, SOL atteint son peak plus tôt et le DD breach -0.75 % arrive plus tôt aussi. **Cette dépendance au peak reset rend le CB difficile à interpréter sur des fenêtres glissantes — un bug de design à investiguer**.

### 3.4 Verdict AXE 3

**🔴 FRAGILE** — 1 event sur 28.5 mois est trop peu pour conclusion statistique. CB est un edge-case-protector, pas un mechanism general.

---

## 4. AXE 4 — Sensitivity to perturbation conditions

### 4.1 Funding rate perturbed by ±0.5 %

| Perturbation | First CB fire timestamp | Delta vs no-perturb |
|---|---|---:|
| -0.5 % | 2025-10-12 00:00 | 0 h |
| -0.25 % | 2025-10-12 00:00 | 0 h |
| **0 %** | **2025-10-12 00:00** | baseline |
| +0.25 % | 2025-10-12 00:00 | 0 h |
| +0.5 % | 2025-10-12 00:00 | 0 h |

### 4.2 Lecture critique

CB fire timing est **complètement stable** sous perturbation ±0.5 % de funding rate. La trajectoire cumulative absorbe le bruit léger, et le DD -0.75 % est atteint au même instant.

**Mais attention** : ceci ne teste que la stabilité de TIMING d'un event qui aura LIEU. Si le sample size effectif est N=1, la stabilité du timing de cet unique event ne change pas le verdict statistique global.

### 4.3 Verdict AXE 4

**🟢 ROBUST** sur le critère timing perturbation. Caveat : ne valide pas la fréquence des events, juste leur stabilité quand ils se produisent.

---

## 5. Verdict global H6 Robustness

### 5.1 Scorecard

| Axe | Pass / Fail | Note |
|---|---|---|
| AXE 1 Plateau sensitivity | **🔴 FRAGILE** | Asymétrique — robust côté supérieur, cliff côté inférieur |
| AXE 2 Walk-forward folds | **🔴 FRAGILE** | Optimum varie [-0.75 %, -0.50 %] across folds |
| AXE 3 Cross-period (24 months) | **🔴 FRAGILE** | N=1 event sur 72 asset-months — edge-case-protector |
| AXE 4 Sensitivity perturbation | 🟢 ROBUST | Stable mais ne valide qu'1 event |

**Axes passés : 1/4. Verdict global : 🟡 MARGINAL leaning 🔴 FRAGILE.**

### 5.2 Interprétation honnête

L'amélioration +8.5 % vs always-in benchmark observée en H6 dépend de **1 unique event SOL** (timing variant selon la fenêtre, mais toujours 1 seul). Sur d'autres fenêtres ou avec d'autres marchés/régimes, ce CB pourrait :
- Ne jamais déclencher (overhead inutile mais zéro coût)
- Déclencher au mauvais moment (faux signal protégeant une mèche temporaire)
- Manquer un vrai event (le -0.75 % calibré sur historique 2025 pourrait être inadapté à régime 2027)

### 5.3 Recommendation V2

Per critères Sebastien :
- 🟢 **ROBUST** : 3+ axes pass → GO BTC+ETH+SOL+CB → **NON ATTEINT**
- 🟡 **MARGINAL** : 1-2 axes pass → **fallback BTC+ETH** ← actuel
- 🔴 **FRAGILE** : 0 axe pass → fallback BTC+ETH

**Verdict V2 = 🟡 MARGINAL → fallback BTC+ETH pure always-in recommandé pour déploiement paper**.

| Design | Net OOS 13.5 mois | Max DD | Note |
|---|---:|---:|---|
| H6 BTC+ETH+SOL + CB -0.75 % | $2 079.81 | -0.77 % | **Fragile sur 3/4 axes robustness** |
| **Always-in pure BTC+ETH** | **$1 685.71** | **-0.33 %** | **🟢 Robuste, simple, déployable** |

Le coût d'opportunité du fallback BTC+ETH = -$394 vs H6 best ($1 686 vs $2 080). **Mais on évite la fragilité** et on garde un design 100 % simple (no CB logic à implémenter, debug, monitor).

---

## 6. Phrase that closes

> *H6 robustness : 1/4 axes pass. L'optimum -0.75 % CB est asymétrique (cliff à -0.65 %), instable across folds (varie de -0.50 % à -0.75 %), et basé sur N=1 event sur 28.5 mois. Le robustness AXE 4 (perturbation) est ROBUST mais ne valide que la stabilité d'un unique event. Verdict MARGINAL → fallback BTC+ETH pure always-in recommandé.*

---

## 7. Prochain pas

**H6 Robustness — LIVRÉ. Verdict MARGINAL leaning FRAGILE. Branche `analysis/loss-forensic-H6-robustness` archivée, pas de merge.**

**Recommandation déploiement paper (à valider opérateur)** :
- **PRIMARY** : BTC+ETH pure always-in (no CB) → $1 686 OOS, max DD -0.33 %, simple
- **FALLBACK secondaire** : BTC-only pure always-in → $885 OOS, max DD -0.14 %, ultra-conservatif
- **NOT recommanded** : BTC+ETH+SOL+CB → fragile sur 3/4 axes

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*H6 Robustness generated by V2 agent on 2026-06-26 by read-only analysis. Snapshot pre-H6-robustness `SNAPSHOT_20260626T232553Z_pre_H6_robustness`. Production code untouched.*
