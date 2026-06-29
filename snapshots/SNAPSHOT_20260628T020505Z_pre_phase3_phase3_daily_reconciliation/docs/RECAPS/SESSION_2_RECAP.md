# RECAP Session 2 — ICC Structure Detection (TU#1 + TU#2)

**Date** : 10 Mai 2026 (soir)
**Durée** : ~3 heures
**Statut** : ✅ Complète et validée
**Tests** : 22/22 passent
**Validé sur** : BTC daily/H4, ETH daily, SOL daily

---

## 1. OBJECTIF DE LA SESSION

Implémenter de manière **fidèle aux TU** la détection des structures de marché ICC :
- Lecture de bougie (TU#1)
- Structure HH/HL/LH/LL (TU#2)
- Sans rafistolage, sans paramètre arbitraire

**Pourquoi cette session est critique** : c'est la fondation de tout le reste. Si la détection des structures est fausse, tout l'algorithme ICC (Order Blocks, Indication, Correction, Continuation) est faux.

---

## 2. CE QU'ON A LIVRÉ

### Fichiers créés

| Fichier | Lignes | Rôle |
|---|---|---|
| `strategies/icc_structure.py` | 320 | Moteur de détection des structures ICC |
| `tests/test_icc_structure.py` | 380 | 22 tests unitaires |
| `scripts/validate_icc_on_real_data.py` | 100 | Script de validation visuelle |

### Concepts implémentés

1. **`StructurePoint` dataclass** — représente un point de structure avec :
   - type, price, timestamp, bar_index
   - confirmed_at_bar (lag W)
   - origin_bar_index + origin_price
   - broken status + broken_at metadata

2. **`is_swing_high` / `is_swing_low`** — primitives de détection
   - Utilisent close uniquement (TU#1)
   - Confirment avec lag W bars de chaque côté

3. **`detect_structures`** — pipeline principal
   - Itère chronologiquement
   - Confirme les swings avec lag W
   - Classifie chaque swing selon le contexte

4. **Helpers d'analyse** :
   - `summarize_structures` → stats
   - `get_active_structures` → filtre les non-cassées
   - `get_structures_by_type` → filtre par type

---

## 3. ALGORITHME ADOPTÉ — 2 étapes

### Étape A — Confirmation de swing (lag W)

À chaque bar `i`, on regarde la bar `i-W` :
- Est-elle un swing high local (close max de la fenêtre [i-2W, i]) ? → confirmé
- Est-elle un swing low local ? → confirmé

**Pas de lookahead** : la confirmation arrive toujours W bars APRÈS le swing lui-même.

### Étape B — Classification ICC

Pour chaque swing confirmé, on lui assigne un type selon :
- **active_high** = dernière référence high non cassée
- **active_low** = dernière référence low non cassée
- **trend** = BULL | BEAR | NEUTRAL (calculé depuis l'historique)

#### Pour un swing HIGH :
```
si active_high == None         → INITIAL_HIGH
si new_price > active_high.price :
    si trend == BULL           → HH (reproduction)
    sinon                       → NEW_HIGH (CHoCH)
sinon                           → LH (pullback)
```

#### Pour un swing LOW : (symétrique)
```
si active_low == None          → INITIAL_LOW
si new_price < active_low.price :
    si trend == BEAR           → LL (reproduction)
    sinon                       → NEW_LOW (CHoCH)
sinon                           → HL (pullback)
```

---

## 4. RÈGLES ICC RESPECTÉES (audit ligne par ligne contre les TU)

| Règle TU | Implémentation | Statut |
|---|---|---|
| TU#1 : Body close only | `is_swing_high` utilise `closes[i]` uniquement | ✅ |
| TU#1 : Wick = liquidité | Aucune référence à `high`/`low` dans la logique de cassure | ✅ |
| TU#2 : Pivot = origine d'impulse | Origin assigné via `_find_prior_opposite_swing` | ✅ |
| TU#2 : Pas de pivothigh math | Pas d'utilisation de `ta.pivothigh` ou équivalent | ✅ |
| TU#2 : Sequence-aware HH/HL/LH/LL | Trend tracking + classification contextuelle | ✅ |
| TU#2 : New High/Low vs HH/LL | Logique conditionnelle sur `trend` | ✅ |
| TU#2 : Structures actives vs cassées | Champ `broken` + tracking via `_refresh_state` | ✅ |
| Doc ICC : Origin = first bar of impulse | Origin = prior opposite swing bar | ✅ |

**Aucun rafistolage détecté.** Tout est aligné avec la spec.

---

## 5. PROBLÈMES RENCONTRÉS PENDANT LA SESSION

### Problème 1 — v1 (rejetée) : approche en 1 passe

**Symptôme** :
- INITIAL_HIGH non marqué cassé après NEW_HIGH
- HH générés à chaque bougie qui monte (sans pullback)
- Génération de LH avec prix de break_bar au lieu d'origin

**Cause** :
Logique linéaire qui traite chaque body close dépassant le active high comme une nouvelle structure, sans attendre un vrai pullback.

**Solution** :
Refonte complète en architecture 2-step :
1. D'abord détecter les vrais swings (avec confirmation lag W)
2. Ensuite classifier selon contexte

**Leçon** : un swing ICC = un point de retournement local confirmé, pas chaque bar qui dépasse un niveau.

### Problème 2 — Tests numpy bool

**Symptôme** : `assert is_swing_high(...) is True` échouait avec erreur vide.

**Cause** : `np.array.max() == val` retourne `numpy.bool_`, pas Python `bool`. Donc `result is True` est False même si `result == True`.

**Solution** : utiliser `assert result` au lieu de `assert result is True`.

**Leçon** : éviter `is True` / `is False` avec retours numpy. Utiliser `bool(result)` si on a besoin de Python bool explicite.

### Problème 3 — Tests synthétiques trop courts

**Symptôme** : tests qui s'attendaient à détecter des structures mais n'en détectaient aucune.

**Cause** : `is_swing_high(i, W)` requiert `i + W < len(data)`. Pour détecter un swing à idx X, il faut au moins X+W+1 bars de données. Les tests avec 9-20 bars n'avaient pas assez de "right context".

**Solution** : étendre toutes les séquences de test à 25+ bars minimum.

**Leçon** : règle de pouce — toujours avoir au moins `2W + 5` bars pour les tests synthétiques.

---

## 6. DÉCISIONS IMPORTANTES PRISES

### Décision 1 — swing_lookback différent par TF

- **Daily** : W=5 (réduit le bruit, capture les swings significatifs)
- **Intraday (H4/H1)** : W=3 (plus sensible aux mouvements rapides)

**Justification** : un swing local de 5 jours en daily est un vrai pivot. En H4, 3 bars = 12h, suffisant pour valider.

**Risque** : potentiel paramètre à optimiser. Mais pas pour l'instant — choix par défaut raisonnable, on évite l'optimisation prématurée.

### Décision 2 — Pas de paramètre arbitraire (anti-overfitting)

Pas de `min_correction_pct`, `max_correction_pct`, ou autre seuil arbitraire dans la structure detection.

**Justification** : la spec ICC dit "no indicators, no arbitrary thresholds". On reste fidèle. Les paramètres seront introduits si vraiment nécessaire en Session 4 (machine à états), mais avec walk-forward systématique.

### Décision 3 — Origin = prior opposite swing (pas une fenêtre)

L'origin d'un swing high = le swing low juste avant (chronologiquement).

**Justification** : c'est ce qui correspond au TU#2 ("HL = price descends... then rises above previous high"). Le HL EST l'origine du futur HH.

---

## 7. VALIDATION SUR DONNÉES RÉELLES

Lancé `scripts/validate_icc_on_real_data.py` sur :

| Actif | Bars | Période | Structures | H/L Ratio | Sanity Checks |
|---|---|---|---|---|---|
| BTC daily | 4457 | 2013-10 → 2025-12 | 542 | 1.01 | 5/5 ✓ |
| ETH daily | 3794 | 2015-08 → 2025-12 | 468 | 1.05 | 5/5 ✓ |
| BTC h4 | 4383 | 2024-01 → 2025-12 | 902 | 1.05 | 5/5 ✓ |
| SOL daily | 1659 | 2021-06 → 2025-12 | 193 | 1.03 | 5/5 ✓ |

**Observations qualitatives** :
- Ratio H/L proche de 1.0 → algorithme symétrique
- Sur BTC daily, structures actives au 31-12-2025 montrent un marché passé de bullish à bearish (NEW_HIGH $124k → LL $85k) — détection cohérente
- Sur BTC H4, ~1.2 structures/jour — cohérent avec ICC scalping

**Sanity checks passants** :
- Chronological order ✓
- Origins valid (origin_bar < structure_bar) ✓
- Broken metadata (broken_at_bar > bar_index) ✓
- Confirmation lag = W exact ✓
- High/Low balance ratio ≤ 2.0 ✓

---

## 8. CE QU'IL RESTE À FAIRE (Session 3+)

### Session 3 — Order Blocks (TU#3)

**Objectif** : détection des Order Blocks (zones où institutions ont opéré)

**Composants à coder** :
- OB- = dernière bougie haussière avant grand mouvement baissier
- OB+ = dernière bougie baissière avant grand mouvement haussier
- Détection FVG (Fair Value Gap) : gap entre meches de bougies adjacentes
- Validation : cassure structure obligatoire
- Scoring force : VERY_STRONG / STRONG / MODERATE / WEAK
- Discount/Premium : OB+ doit être en zone discount (sous 50% range), OB- en premium
- Usage unique : un OB consommé ne revient pas

**Estimation** : 3-4h, 6-8 tests unitaires

**Dépendance** : `icc_structure.py` (déjà prêt)

### Session 4 — Cycle ICC complet (TU#4)

- detect_icc_cycle multi-TF (Daily → H4 → H1)
- Machine à états SCANNING → INDICATION → CORRECTION → READY → IN_TRADE → COOLDOWN
- Money management : SL trailing structurel, partial close 85%, TP sur OB opposé

### Session 5 — Walk-forward + verdict

- Run sur 8 cryptos × 12 ans
- Comparaison vs trend following / mean reversion
- Document final

---

## 9. CHECKLIST D'AUDIT (validé pour cette session)

Voir `docs/AUDIT_TEMPLATE.md` pour la checklist complète.

- [x] Code aligné ligne par ligne avec TU#1 et TU#2
- [x] Tous les tests passent (22/22)
- [x] Validé sur ≥3 actifs réels
- [x] Sanity checks tous verts
- [x] Performance acceptable (<1s pour 5000 bars)
- [x] Pas de rafistolage détecté
- [x] Pas de lookahead
- [x] Pas de paramètre arbitraire critique
- [x] Documentation à jour (`JOURNAL.md` + ce recap)
- [x] Git commit fait

---

## 10. BILAN HONNÊTE

### Ce qui a bien marché
- L'approche 2-step a éliminé tous les bugs de la v1
- Tests unitaires détaillés ont catché plusieurs problèmes subtils
- Validation sur données réelles a confirmé que l'algorithme se comporte sensiblement

### Ce qui aurait pu être mieux
- J'ai perdu du temps sur la v1 avant de réaliser que l'approche fondamentale était mauvaise. **Leçon** : prendre 15 min de spec algorithmique AVANT de coder évite ce genre de détour.

### Risques identifiés pour la suite
- **Session 3 (OB)** plus complexe que Session 2 — multiples critères de validation
- **Session 4 (cycle complet)** nécessite synchronisation multi-TF — risque de bugs subtils
- **Données H4** limitées à 2 ans (vs 12 ans daily) — on devra peut-être resampler depuis H1

### Niveau de confiance dans la fondation
**Élevé.** Tests passent, validation réelle OK, code propre et documenté. On peut bâtir le reste dessus en confiance.

---

*Fin du recap Session 2 — 10 Mai 2026*
