# V2 Look-Ahead Audit — Phase B Report

- **Date** : 2026-06-22 (UTC)
- **Baseline commit (main HEAD)** : `c4daa192ba2756e250d6f409ac26d28564a647e4`
- **Branch** : `audit/lookahead-fix` (fast-forwarded to main HEAD then commit applied)
- **Tag** : `audit/lookahead-fix-phase-b`
- **Snapshots** : `pre-phase-b-baseline` (before any change), `post-phase-b-fix-applied` (after final commit)
- **Files patched** : `backtest/engine.py` (line 55 — vectorised PnL + the parallel computation inside `_build_trades`)

---

## 1. Méthodologie

Phase A confirmed mécaniquement la présence d'un biais de look-ahead simultané dans le moteur funding : `engine.py:55` calcule `funding_pnl = position * funding * capital`, mais `position[t]` est généré par `strategies/funding_capture.py:53` via un `rolling().mean()` *right-aligned*, donc `position[t]` dépend de `funding[t]`. Le produit au même index introduit un biais causal.

Phase B mesure l'impact économique de ce biais sur le P&L et le Sharpe, en comparant deux runs du moteur sur des données strictement identiques :

- **NOFIX** : `funding_pnl = position * funding * capital` (état actuel `engine.py:55`, version reproduite in-script pour ne pas dépendre du commit git).
- **WITHFIX** : `funding_pnl = position * funding.shift(1).fillna(0) * capital` (correction mandatée par la mission, alignée sur l'idiome `position.shift(1) * return` déjà utilisé par `backtest/directional_engine.py:47`).

Une correction symétrique est appliquée dans `_build_trades` (ligne 167) pour que le `gross_funding` par trade additionne exactement la même série `funding.shift(1)` que la courbe d'equity vectorisée. Sans cela, métriques agrégées et métriques par trade divergeraient.

Le harness vit dans `outputs/phase_b_harness.py` ; les exécutions plus longues vivent dans le bloc python inline qui a généré `outputs/phase_b_robustness.json`.

### Données

- Source : cache parquet Hyperliquid pré-existant (`cache/funding_hyperliquid_<asset>_USDC_USDC.parquet`)
- Fréquence : funding horaire
- Actifs : **BTC, ETH, SOL** (les 3 actifs avec funding Hyperliquid cachés)
- Fenêtres testées :
  - `last_6m` : 2025-11-04 → 2026-05-04 (~4 379 barres × 3 actifs)
  - `last_12m` : 2025-05-04 → 2026-05-04 (~8 760 barres × 3 actifs)
  - `full_2024_2026` : 2024-01-01 → 2026-05-04 (~20 500 barres × 3 actifs)

### Paramètres

- Capital : $10 000 par actif (i.e. $10k spot long + $10k perp short par actif)
- Friction par jambe : 4.5 bps taker + 0.87 bps slippage (config.yaml) → 10.74 bps entry, 10.74 bps exit
- Stratégie : `funding_capture` avec smooth=24h, entry>0.5% APR, exit<-0.5% APR, min_hold=24h, min_flat=24h (config par défaut)

---

## 2. Résultats par actif

### Fenêtre `last_6m` (2025-11-04 → 2026-05-04)

| Asset | Sharpe NOFIX | Sharpe WITHFIX | ΔSharpe | PnL NOFIX | PnL WITHFIX | ΔPnL | ΔPnL % | ΔMaxDD (pp) |
|-------|--------------|----------------|---------|-----------|-------------|------|--------|-------------|
| BTC   | -6.50        | -6.42          | +0.08   | -$367.30  | -$362.64    | +$4.66  | +1.27% | +0.04 |
| ETH   | -3.41        | -3.33          | +0.08   | -$166.99  | -$162.95    | +$4.04  | +2.42% | +0.04 |
| SOL   | -10.21       | -10.10         | +0.11   | -$613.52  | -$607.24    | +$6.28  | +1.02% | +0.06 |
| **Aggregate** | — | — | — | **-$1 147.81** | **-$1 132.83** | **+$14.98** | **+1.31%** | — |

### Fenêtre `last_12m` (2025-05-04 → 2026-05-04)

| Asset | Sharpe NOFIX | Sharpe WITHFIX | ΔSharpe | PnL NOFIX | PnL WITHFIX | ΔPnL | ΔPnL % |
|-------|--------------|----------------|---------|-----------|-------------|------|--------|
| BTC   | +2.09        | +2.16          | +0.07   | +$181.91  | +$187.52    | +$5.61  | +3.08% |
| ETH   | +2.35        | +2.43          | +0.08   | +$201.35  | +$207.44    | +$6.09  | +3.02% |
| SOL   | -4.20        | -4.10          | +0.10   | -$452.87  | -$442.50    | +$10.38 | +2.29% |
| **Aggregate** | — | — | — | **-$69.61** | **-$47.54** | **+$22.07** | **+31.7%** ⚠ |

⚠ Le pourcentage relatif explose ici parce que la base agrégée frôle zéro. Le bon repère pour cette fenêtre est le pourcentage par actif (2-3%), pas le rapport global.

### Fenêtre `full_2024_2026` (2024-01-01 → 2026-05-04, ~28 mois)

| Asset | Sharpe NOFIX | Sharpe WITHFIX | ΔSharpe | PnL NOFIX | PnL WITHFIX | ΔPnL | ΔPnL % |
|-------|--------------|----------------|---------|-----------|-------------|------|--------|
| BTC   | +13.49       | +13.56         | +0.07   | +$2 427.57 | +$2 439.84 | +$12.26 | +0.51% |
| ETH   | +8.40        | +8.48          | +0.08   | +$1 706.24 | +$1 722.80 | +$16.56 | +0.97% |
| SOL   | +7.42        | +7.53          | +0.11   | +$1 701.70 | +$1 727.24 | +$25.54 | +1.50% |
| **Aggregate** | — | — | — | **+$5 835.51** | **+$5 889.88** | **+$54.36** | **+0.93%** |

Détails complets (n_trades, win_rate, durée moyenne, etc.) dans `outputs/phase_b_baseline_NOFIX.json` (6-month, harness) et `outputs/phase_b_robustness.json` (3 fenêtres).

---

## 3. Verdict empirique

Trois constats, dans l'ordre d'importance :

**A. Le biais est réel mais beaucoup plus petit que ce que Phase A craignait.** L'écart absolu se situe entre $4 et $26 par actif et par fenêtre, soit **0.5–3% du P&L NOFIX par actif** suivant la fenêtre. Phase A avait estimé $200–3 000 par actif et par an, on est ~1–2 ordres de magnitude en dessous. La raison probable : la stratégie smoothe sur 24h en horaire, donc l'autocorrélation `funding[t]` vs `funding[t-1]` est très élevée (~0.95+), et le décalage d'un cran ne change presque rien à l'effet capté.

**B. La direction du biais est OPPOSÉE à la prédiction Phase A.** Sur toutes les fenêtres et tous les actifs, **le fix AUGMENTE le P&L** (NOFIX est biaisé vers le bas, pas vers le haut). Phase A ne raisonnait que sur l'effet "entrée" (smoothed monte → on entre → on encaisse le funding[t] simultané positif) en oubliant la symétrie côté "sortie" (smoothed descend → on sort → le funding[t] simultané au seuil de sortie est *bas/négatif* et plombe la métrique). Empiriquement, l'effet sortie domine légèrement, d'où le signe inverse.

**C. L'edge net survit complètement au fix.** Sur la période complète 2024-2026 avec friction réaliste (10.74 bps entry + 10.74 bps exit), l'agrégat passe de **+$5 835.51 (NOFIX) à +$5 889.88 (WITHFIX)** sur $30k déployés sur 28 mois — l'edge n'est ni détruit ni significativement érodé. Le Sharpe per-asset reste élevé (BTC 13.5+, ETH 8.5+, SOL 7.5+), et bouge à peine après fix. La sous-fenêtre 6 mois reste perdante avec ou sans fix : ce n'est pas un artefact du biais, c'est un régime de funding défavorable.

---

## 4. Recommandation

**Merge to main : OUI**, mais pour des raisons hygiéniques, pas économiques.

Détail :
- Le fix supprime un biais causal réel et minuscule. C'est principlement correct : `funding.shift(1)` aligne le moteur funding sur l'idiome déjà utilisé par `directional_engine.py:47` (`position.shift(1) * return`) et sur la sémantique strict-causal de la production (`live/paper_funding_capture.py:273` filtre `ts <= last_booked`).
- L'impact économique du biais est négligeable (~1% relatif au pire) et de signe *contraire* à ce qu'on craignait, donc personne n'avait surestimé l'edge en prod sur la base des backtests.
- En attendant le merge, aucune urgence opérationnelle : pas de stop kill-switch nécessaire, le système live n'est pas affecté (la production utilise déjà le filtrage causal correct ; seul le moteur de backtest était impacté).
- Le fix améliore légèrement les chiffres reportés (Sharpe +0.07 à +0.11), donc les rapports backtest futurs seront un poil plus généreux qu'avant (et plus justes).

Caveats :
- Ce résultat tient pour la stratégie `funding_capture` actuelle (smoothing 24h, hourly funding). Pour une variante avec smoothing très court (ex. 1h) ou un funding moins autocorrélé, le biais pourrait redevenir matériel — il faudra remesurer avant d'utiliser le moteur sur de telles variantes.
- Mesure faite sur 3 actifs majeurs (BTC/ETH/SOL). Pour les altcoins exotiques avec funding plus erratique, le biais peut varier ; l'audit Phase B couvre les actifs effectivement déployés en paper.

---

## 5. Procédure de rollback

Si le fix se révèle problématique en live (ce qui serait surprenant — il n'affecte que le backtest), voici les options classées par friction :

### Rollback total (annule tout Phase B)
```bash
cd /Users/mindcompletionbody/Desktop/trading-bot-v2
git checkout main                # quitte audit/lookahead-fix
git update-ref -d refs/tags/audit/lookahead-fix-phase-b
git update-ref refs/heads/audit/lookahead-fix c4daa192ba2756e250d6f409ac26d28564a647e4
```
Le snapshot `pre-phase-b-baseline` (sous `snapshots/SNAPSHOT_20260622T002253Z_pre-phase-b-baseline/`) contient le `git_head.txt` et la diff non-commitée — voir `ROLLBACK.md` à côté.

### Rollback du seul fix moteur (si Phase B est mergée puis problématique)
Le commit Phase B touche uniquement `backtest/engine.py` (et ajoute des fichiers `outputs/`). Pour annuler le shift :
```bash
git revert <commit-sha-phase-b>   # crée un revert propre
```
ou patch manuel : restaurer `funding_pnl = position * funding * capital` dans `engine.py:55` et retirer le `shifted_funding = funding.shift(1).fillna(0)` dans `_build_trades`.

### Aucune action côté live
La production (`live/paper_funding_capture.py`) n'utilise pas `backtest/engine.py`. Aucun processus live à arrêter, pas de state à restaurer, pas de positions ouvertes à toucher.

---

## 6. Open questions pour l'operator (Sebastien)

1. **Mesurer aussi sur les autres actifs paper-tradés ?** L'audit B couvre 3 actifs (BTC, ETH, SOL). Si d'autres actifs sont en production paper (cf. liste effective dans `live/state/daemon_state.json`), faut-il étendre la mesure avant merge ? Recommendation : non, l'autocorrélation funding est structurelle, peu de chance que le résultat soit qualitativement différent ailleurs.

2. **Reporter le fix dans la documentation backtest ?** Le fichier `STRATEGIC_LOGIC_DOC.md` ou les rapports historiques font-ils des claims numériques basés sur le moteur biaisé ? Si oui, ils sont *sous-estimés* d'environ 1% — pas alarmant mais utile à corriger pour la traçabilité.

3. **Faut-il ajouter un test de régression `test_engine_no_lookahead`** qui vérifie qu'à `position[t]` constant on a bien `funding_pnl[t] = position[t] * funding[t-1] * capital` ? Recommendation : oui, c'est trivial, cf. `tests/test_engine.py`. À faire en Phase C séparée pour ne pas polluer le commit atomique Phase B.

4. **Le smoothing 24h sur funding horaire crée une autocorrélation très forte qui masque le biais.** Si une future variante de la stratégie raccourcit la fenêtre (e.g. 1h ou 4h), le biais doit être remesuré : la conclusion "edge survit" n'est pas garantie pour ces variantes.

---

## 7. Annexes — Métadonnées commit

- **Commit Phase B** : voir `git log audit/lookahead-fix --oneline` après application
- **Tag** : `audit/lookahead-fix-phase-b`
- **Fichiers modifiés** : `backtest/engine.py` (2 sites : ligne 55 et `_build_trades`)
- **Fichiers ajoutés** :
  - `outputs/phase_b_harness.py` (harness exécutable, 6-month run)
  - `outputs/phase_b_baseline_NOFIX.json` (résultats fenêtre 6m, run NOFIX *avant* application du fix)
  - `outputs/phase_b_WITHFIX.json` (résultats fenêtre 6m, run WITHFIX *après* application du fix)
  - `outputs/phase_b_robustness.json` (3 fenêtres × 3 actifs, NOFIX et WITHFIX par exécution unique avec version buggy reproduite in-script)
  - `outputs/V2_LOOKAHEAD_AUDIT_PHASE_B.md` (ce rapport)

P31 discipline : tout le travail tient en **1 seul commit** sur `audit/lookahead-fix`, branche distincte de main, snapshots pré et post pour rollback mécanique.
