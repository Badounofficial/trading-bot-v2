# Proposed V3 OB Output Format — Mock Schema

> **Statut** : mock pour discussion. **Pas de code écrit**. Décision et
> implémentation au gate du 3 juin / 12 août 2026 selon Principe 18.
>
> Schéma proposé pour intégrer les 4 concepts structurels de Badoun
> (Range, Breakout retro, Structure-OB linked, SL ≠ OB) dans la sortie
> du détecteur V3.
>
> Origine : retours Badoun 23 mai sur les 3 fenêtres alignment, screenshots
> dans `badoun_screenshots/`, divergence_report.md section "Concepts
> structurels manqués".

## V2-dyn actuel (rappel)

```python
@dataclass
class DynamicOB:
    type: OBType                       # 'OB+' | 'OB-'
    bar_index: int
    timestamp: pd.Timestamp
    wick_anchor_price: float           # 1 SEUL niveau (low pour OB-, high pour OB+)
    body_open: float
    body_close: float
    wick_high: float
    wick_low: float
    zone_low: float
    zone_high: float
    structure_broken: StructurePoint
    break_bar: int
    break_ts: pd.Timestamp
    n_bars_between_ob_and_break: int
    has_fvg_after: bool
    consec_same_color_count: int
    consumed: bool
    consumed_at_bar: Optional[int]
    consumed_at_ts: Optional[pd.Timestamp]
```

**Limitations** :
1. Pas de distinction OB entry zone vs SL reference price
2. Aucun classement Range vs Leg directionnel
3. Pas de tracking du leg structurel englobant (HH-HL ou LH-LL)
4. Pas de re-évaluation dynamique en cas de breakout du range
5. `wick_anchor_price` est utilisé à la fois comme entry et stop → trop
   serré

## V3 cible (mock)

```python
@dataclass
class StructuralOB_V3:
    # ─── Identité ───
    ob_id: str                         # "BTC_2026-05-15_OB-_bar22"
    type: OBType                       # 'OB+' | 'OB-'
    timestamp: pd.Timestamp
    bar_index: int

    # ─── ZONE D'ENTRÉE (signal d'entry, zone d'invalidation immédiate) ───
    ob_entry_zone: EntryZone           # voir ci-dessous

    # ─── SL REFERENCE (placement stop-loss, séparé) ───
    sl_reference_price: float          # wick top du swing structurel (LH)
                                       # ou wick bottom (HL) pour OB+
    sl_reference_bar: int              # bar de la bougie structurelle
                                       # PEUT être différent de bar_index

    # ─── CONTEXTE STRUCTUREL ───
    structural_context: StructuralContext

    # ─── VALIDATION (les 3 filtres) ───
    validation: ValidationFlags

    # ─── SCORE ───
    confidence_v3: float               # 0.0-1.0 score composite

    # ─── HISTORIQUE & TRACKING ───
    consumed: bool
    consumed_at_bar: Optional[int]
    re_evaluated_at: Optional[pd.Timestamp]  # NEW : si re-évalué (Concept 2)


@dataclass
class EntryZone:
    """The OB candle itself — signal d'entrée + invalidation immédiate."""
    low: float                         # = wick_low (OB-) ou body_open (OB+)
    high: float                        # = body_close (OB-) ou wick_high (OB+)
    anchor: float                      # = wick_low (OB-) ou wick_high (OB+)
    body_open: float
    body_close: float
    wick_full_low: float               # wick complet pour reference
    wick_full_high: float


@dataclass
class StructuralContext:
    """Inscription dans la structure de marché — Concepts 1 et 3."""

    # Jambe structurelle englobante (Concept 3)
    leg_type: Literal['HH-HL', 'LH-LL', 'in_range', 'transition']
    leg_origin_bar: Optional[int]      # début du leg (swing low pour LH-LL, etc.)
    leg_origin_price: Optional[float]
    leg_break_bar: Optional[int]       # fin du leg (cassure structurelle)
    leg_break_price: Optional[float]

    # Range englobant (Concept 1)
    is_in_range: bool                  # True si le OB est dans une zone consolidation
    range_top: Optional[float]         # si is_in_range
    range_bottom: Optional[float]      # si is_in_range
    range_start_bar: Optional[int]
    range_end_bar: Optional[int]       # None si encore active à anchor time

    # Cassure de range (Concept 2)
    range_broken: bool                 # True si le range englobant a été cassé
    range_break_direction: Optional[Literal['up', 'down']]
    range_break_bar: Optional[int]


@dataclass
class ValidationFlags:
    """3 filtres d'admissibilité — un OB n'est exploitable que si TOUS PASSED.

    Sauf si is_in_range=True ET range_broken=True (Concept 2 retro).
    """
    structural_break_confirmed: bool   # cassure CHoCH/BoS confirmée
    directional_momentum_ok: bool      # Concept 1 : body avg / wick avg > seuil
                                       #            ATR pre-OB > seuil
    not_in_unbroken_range: bool        # Concept 3 : leg_type != 'in_range'
                                       #            OU range_broken=True (Concept 2)

    # Composite — exploitable si TOUTES vraies, ou si retro_validated
    is_exploitable: bool
    retro_validated: bool              # True si l'OB était initialement
                                       # in_range mais le range a été cassé
                                       # → OB devient exploitable a posteriori
```

## Exemple de sortie attendue (cas BTC bar 10 — OB- top)

```json
{
  "ob_id": "BTC_2026-05-14_OB-_bar10",
  "type": "OB-",
  "timestamp": "2026-05-14T16:00:00+00:00",
  "bar_index": 10,

  "ob_entry_zone": {
    "low": 81026.0,
    "high": 81368.0,
    "anchor": 81026.0,
    "body_open": 81264.0,
    "body_close": 81368.0,
    "wick_full_low": 81026.0,
    "wick_full_high": 81992.0
  },

  "sl_reference_price": 81992.0,
  "sl_reference_bar": 10,

  "structural_context": {
    "leg_type": "transition",
    "leg_origin_bar": 3,
    "leg_origin_price": 78801.0,
    "leg_break_bar": 20,
    "leg_break_price": 78034.0,
    "is_in_range": false,
    "range_top": null,
    "range_bottom": null,
    "range_start_bar": null,
    "range_end_bar": null,
    "range_broken": false,
    "range_break_direction": null,
    "range_break_bar": null
  },

  "validation": {
    "structural_break_confirmed": true,
    "directional_momentum_ok": true,
    "not_in_unbroken_range": true,
    "is_exploitable": true,
    "retro_validated": false
  },

  "confidence_v3": 0.92,

  "consumed": false,
  "consumed_at_bar": null,
  "re_evaluated_at": null
}
```

## Exemple — cas ETH bar 32 (OB- in range, drop par V3)

```json
{
  "ob_id": "ETH_2026-05-18_OB-_bar32",
  "type": "OB-",
  "timestamp": "2026-05-18T08:00:00+00:00",
  "bar_index": 32,

  "ob_entry_zone": {
    "low": 2109.30, "high": 2132.50, "anchor": 2109.30,
    "body_open": 2119.50, "body_close": 2132.50,
    "wick_full_low": 2109.30, "wick_full_high": 2138.70
  },

  "sl_reference_price": 2138.70,
  "sl_reference_bar": 32,

  "structural_context": {
    "leg_type": "in_range",
    "leg_origin_bar": null,
    "leg_origin_price": null,
    "leg_break_bar": null,
    "leg_break_price": null,
    "is_in_range": true,
    "range_top": 2156.10,
    "range_bottom": 2089.00,
    "range_start_bar": 30,
    "range_end_bar": null,
    "range_broken": false,
    "range_break_direction": null,
    "range_break_bar": null
  },

  "validation": {
    "structural_break_confirmed": true,
    "directional_momentum_ok": false,
    "not_in_unbroken_range": false,
    "is_exploitable": false,
    "retro_validated": false
  },

  "confidence_v3": 0.15,

  "consumed": false,
  "consumed_at_bar": null,
  "re_evaluated_at": null
}
```

→ `is_exploitable = false` parce que dans range non-cassé. **Drop**.

## Exemple — cas ETH OB- manqué après cassure range (Concept 2 retro)

À la fin de la fenêtre 22 mai, le range orange 2089-2156 finit par
casser au-dessous de 2089 (le low 2056 atteint à bar 58). Tous les OBs
initialement marqués `is_in_range=true, range_broken=false` doivent être
**re-évalués** :

```json
{
  "ob_id": "ETH_2026-05-21_OB-_bar48",
  "type": "OB-",
  "timestamp": "2026-05-21T00:00:00+00:00",
  "bar_index": 48,
  // ... fields ...

  "structural_context": {
    "leg_type": "in_range",
    "is_in_range": true,
    "range_top": 2156.10,
    "range_bottom": 2089.00,
    "range_broken": true,                // ← updated at bar 58
    "range_break_direction": "down",
    "range_break_bar": 58
  },

  "validation": {
    "structural_break_confirmed": true,
    "directional_momentum_ok": true,     // retroactive: momentum confirmé
    "not_in_unbroken_range": true,       // ← range now broken
    "is_exploitable": true,              // ← passe à true après breakout
    "retro_validated": true              // ← flag explicite
  },

  "confidence_v3": 0.68,                  // moins que 0.92 (clean) car retro

  "re_evaluated_at": "2026-05-22T20:00:00+00:00"  // bar 58
}
```

## Algorithme V3 — pipeline conceptuel (NOT IMPLEMENTED)

```
detect_obs_v3(prices):
    structures      = detect_structures(prices, W=2)
    ranges          = detect_consolidation_zones(prices, structures)   # NEW
    legs            = classify_structural_legs(structures, ranges)     # NEW

    candidate_obs   = []
    for break_event in structures.filter(is_break=True):
        ob_candle   = find_ob_candle_v3(prices, break_event, ranges)  # walk-back ajusté
        sl_candle   = find_structural_swing_for_sl(prices, break_event, legs)  # NEW
        candidate_obs.append(build_v3_ob(ob_candle, sl_candle, break_event, ranges, legs))

    # Concept 2 — re-evaluate as new bars come in
    for ob in candidate_obs:
        if ob.is_in_range and range_broken_since(ob, prices):
            ob.range_broken = True
            ob.is_exploitable = re_check_exploitability(ob)
            ob.retro_validated = True

    return candidate_obs
```

Trois nouvelles fonctions à coder :
1. `detect_consolidation_zones(prices, structures)` — Concept 1 (la plus
   difficile, demande heuristique sur ATR contraction ou variance close)
2. `classify_structural_legs(structures, ranges)` — Concept 3
3. `find_structural_swing_for_sl(prices, break_event, legs)` — Concept 4

La fonction `find_ob_candle_v3` est un raffinement de l'actuelle
`_find_last_opposite_candle` :
- Skip dojis (déjà fait)
- Optionnel : préférer la bougie pré-FVG si FVG détecté (cf. Question 7
  Gold)

## Estimation budget Phase 2 (gate 12 août)

| Sous-tâche | Effort estimé | Risque |
|---|---|---|
| Coder `detect_consolidation_zones` | 2-3 jours | Élevé — l'heuristique range est subjective |
| Coder `classify_structural_legs` | 1 jour | Moyen |
| Coder `find_structural_swing_for_sl` | 1 jour | Faible — pattern walk-back simple |
| Refactor `detect_obs_dynamic` → `detect_obs_v3` | 1 jour | Faible |
| Tests unitaires V3 (fixtures sur les 3 fenêtres alignment) | 1 jour | Faible |
| Walk-forward OOS+friction avec V3 | 2-3 jours | Moyen — résultats vs V2-strict |
| **Total estimé** | **8-10 jours** | |

Si V3 surclasse V2-strict de >= 0.2 Sharpe sur le walk-forward OOS+friction
→ V3 devient le détecteur canonique.

## Métriques cibles V3

| Métrique | V2-strict actuel | V2-dyn (cet exercice) | V3 cible (post-filtres) |
|---|:-:|:-:|:-:|
| Recall  | 17% | 83% | 80% |
| Precision | 100% | 56% | 90% |
| F1 | 0.29 | 0.67 | 0.85 |
| Sharpe attendu (OOS+friction, filtered universe) | 1.07-2.22 | non testé | 1.5-2.8 cible |

---

*Mock schéma rédigé 23 mai 2026 par V2 — purement documentaire. Aucun
fichier `strategies/*.py` ou `live/*.py` modifié. À discuter au 3 juin
puis itérer vers une vraie spec PR.*
