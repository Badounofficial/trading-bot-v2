# ETH H4 — V2-dyn raisonnement par OB (avec filtres Range + Structure)

> Pour chaque OB que V2-dyn a détecté sur ETH (60 H4 finissant 22 mai
> 23:59 UTC), raisonnement algorithmique + application **post-hoc** des
> 4 concepts structurels de Badoun (Range, Breakout retro, Structure, SL).
>
> Source annotation : `badoun_screenshots/01_eth_annotated.jpeg`
> Détecteur : `strategies/ob_detector_v2_dynamic.py` (W=2). Pas de modif.

## Vue d'ensemble

V2-dyn a détecté **7 OBs** (5 OB- + 2 OB+).
Après application théorique des filtres Concept 1 + 3 : **3 valides**.
Badoun ajoute **1 OB- manuel** (à droite hors range) → cible 4 OBs.

| # | OB | bar | ts UTC | V2-dyn brut | Filtre Range | Verdict final | Annotation Badoun |
|---|---|---:|---|---|---|---|---|
| 1 | OB- | 9 | 05-14 12:00 | détecté | hors range | ✅ valide | implicite OK (top) |
| 2 | OB- | 18 | 05-16 00:00 | détecté | hors range | ✅ valide | implicite OK |
| 3 | OB- | 28 | 05-17 16:00 | détecté | hors range | ✅ valide | implicite OK |
| 4 | OB- | 32 | 05-18 08:00 | détecté | **dans range orange** | ❌ drop | X (range) |
| 5 | OB+ | 33 | 05-18 12:00 | détecté | **dans range orange** | ❌ drop | X (range) |
| 6 | OB+ | 47 | 05-20 20:00 | détecté | **dans range orange** | ❌ drop | X (range) |
| 7 | OB- | 48 | 05-21 00:00 | détecté | **dans range orange** | ❌ drop | X (range) |
| +A | OB- | ~57? | ~05-22 16:00 | **manqué** | hors range (post-break) | ✅ à ajouter | OB- manuscrit hors range |

**Match cible : 3 V2-dyn gardés + 1 ajout manuel = 4** vs cible Badoun 4 OB-.
**Exact en compte.**

---

## OB #1 — OB- @ bar 9 (2026-05-14 12:00 UTC) ✅

- Wick anchor : **2245.10**, body close : 2297.50
- Break utilisé : NEW_LOW @ bar 15 (cassure du swing initial à bar 3)
- Distance OB → break : 6 bougies (la plus longue)
- FVG : oui, consec : 6 bougies baissières

**Mon raisonnement** : bougie verte au top de la fenêtre (close 2297.5),
suivie d'un dump de 6 bougies avec FVG. Walk-back jusqu'à bar 3 swing low
initial. Aucune autre bougie verte significative entre.

**Filtre Range** : hors range. Avant cette bougie, le marché monte
nettement de 2235 à 2298 — pas de consolidation. Après, dump franc.
→ **Validé**.

**Filtre Structure** : c'est précisément le top de la jambe haussière
initiale + début de la jambe baissière → jambe valide LH-LL. **Validé**.

**SL placement (Concept 4)** : la bougie OB est elle-même le swing high
local (close 2297.5, wick high 2298.5). Le SL irait au-dessus de 2298.5
(wick top). Probablement pas de différence OB vs SL ici car la bougie
OB EST la bougie structurelle.

**Confidence Badoun** : HAUTE (implicite, "vraies cassures incontestables").

## OB #2 — OB- @ bar 18 (2026-05-16 00:00 UTC) ✅

- Wick anchor : **2222.10**, body close : 2226.90
- Break : LL @ bar 20
- Distance : 2 · FVG : non · consec : 2

**Mon raisonnement** : après le LH @ bar 18 (2226.90), price casse le LL
suivant à 2175.60. V2-dyn pointe bar 18 comme la dernière bougie verte
avant la cassure.

**Filtre Range** : hors range. Le marché continue sa descente directionnelle
(2230 → 2175 sur 2 bougies). **Validé**.

**Filtre Structure** : jambe LH-LL claire, dans la descente macro. **Validé**.

**SL placement** : la bougie LH structurelle est bar 18 elle-même. SL au
wick top = 2230.50. OB entry = body close 2226.90. Différence ~3.6 pts =
buffer raisonnable.

**Confidence Badoun** : HAUTE-MOYENNE (implicite OK, body petit).

## OB #3 — OB- @ bar 28 (2026-05-17 16:00 UTC) ✅

- Wick anchor : **2175.30**, body close : 2191.40
- Break : LL @ bar 30
- Distance : 2 · FVG : non · consec : 2

**Mon raisonnement** : après le rebond bar 24-28 dans le downtrend, V2-dyn
identifie bar 28 comme la dernière bougie verte avant le nouveau LL @ 30
(à 2089.40).

**Filtre Range** : hors range. C'est la **fin** d'un mini-rebond, suivi
d'un dump franc vers 2089. La bougie 28 (2192) + dump à 2089 = drop de
103 pts en 2 bougies. Mouvement directionnel net. **Validé**.

**Filtre Structure** : jambe LH-LL valide, swing high local à bar 28 puis
break baissier. **Validé**.

**SL placement** : LH structurel à bar 28 (wick high 2192.70). OB entry
zone body close 2191.40. Différence minime — bougie OB ≈ bougie
structurelle.

**Confidence Badoun** : HAUTE (implicite, c'est dans la jambe baissière
principale).

## OB #4 — OB- @ bar 32 (2026-05-18 08:00 UTC) ❌

- Wick anchor : **2109.30**, body close : 2132.50
- Break : LL @ bar 33

**Mon raisonnement initial** : bougie verte juste avant le LL @ 33
(à 2106.40, soit -26 pts en 1 bougie).

**Filtre Range — RAISON DROP** : bar 32 marque le **début de la zone
range orange** que Badoun a tracée (18-22 mai, zone 2100-2150). Le marché
oscille dans cette box pendant 4 jours **sans cassure directionnelle**.
Le LL @ 33 à 2106.40 n'est qu'une oscillation interne au range — il ne
casse pas le bottom global du range (2089 atteint à bar 30 = vraie limite
basse).

**Verdict** : ❌ **drop**. Marqué X par Badoun dans son screenshot.

**Hypothèse implémentation détecteur range** : ATR contraction sur ce
segment vs la phase 13-15 mai. La volatilité chute clairement après le
dump initial — un capteur ATR ou un detector "range-bound" l'aurait
flaggé.

## OB #5 — OB+ @ bar 33 (2026-05-18 12:00 UTC) ❌

- Wick anchor : **2156.10** (wick_high), body close : 2106.40
- Break : NEW_HIGH @ bar 37 (à 2140.00)

**Mon raisonnement initial** : après le LL @ 33, rebond jusqu'à bar 37
qui crée un nouveau plus haut local. V2-dyn classe ça comme NEW_HIGH et
walk-back identifie bar 33 (dernière bougie rouge) comme OB+.

**Filtre Range — RAISON DROP** : exact même range orange que #4. Le
"NEW_HIGH" @ bar 37 à 2140 n'est pas une cassure haussière macro — il
reste largement sous le top de range (2156 vu à bar 33 lui-même). C'est
juste une oscillation interne.

**Filtre Structure** : faux signal de cassure. Si on regardait la
structure macro, l'OB+ ici n'a pas de signification — le marché reste
dans son range.

**Verdict** : ❌ **drop**. Marqué X par Badoun.

## OB #6 — OB+ @ bar 47 (2026-05-20 20:00 UTC) ❌

- Wick anchor : **2140.10** (wick_high), body close : 2129.10
- Break : HH @ bar 48 (à 2145.40)

**Mon raisonnement initial** : HH local à bar 48 valide un OB+ rétro à
bar 47 (la dernière bougie rouge).

**Filtre Range — RAISON DROP** : dans le même range orange (le HH @ 48 à
2145 reste sous le top de range 2156 atteint à bar 33). Aucune cassure
haussière macro.

**Verdict** : ❌ **drop**. Marqué X par Badoun.

**Pattern récurrent** : V2-dyn génère systématiquement des faux positifs
dans les zones range parce que les NEW_HIGH/HH/NEW_LOW/LL **locaux**
sont interprétés comme des cassures structurelles, alors qu'ils ne
brisent pas la box englobante.

## OB #7 — OB- @ bar 48 (2026-05-21 00:00 UTC) ❌

- Wick anchor : **2127.90**, body close : 2145.40
- Break : NEW_LOW @ bar 50 (à 2114.00)

**Mon raisonnement initial** : bar 48 = HH local, immédiatement suivi
d'un dump qui crée un new local low @ 50. Pattern "fake breakout puis
continuation" — V2-dyn flag.

**Filtre Range — RAISON DROP** : encore le range orange. Le "NEW_LOW"
@ 50 à 2114 reste au-dessus du bottom de range (2089). Pas une vraie
cassure.

**Verdict** : ❌ **drop**. Marqué X par Badoun.

## OB MANQUÉ +A — OB- ajouté manuellement par Badoun (hors range, droite)

Badoun a annoté "OB-" en blanc à droite de son screenshot, en dehors
du rectangle orange — vraisemblablement vers bar 57 (22 mai 16:00 UTC,
prix ~2135) ou bar 58 (22 mai 20:00 UTC, prix ~2065).

Probable interprétation : c'est la bougie verte juste avant la cassure
finale de la box vers le bas (le dump 22 mai vers 16:00-20:00 UTC qui
amène le prix de ~2135 à 2057 — sortie du range par le bas).

**Pourquoi V2-dyn l'a manqué** : la cassure du range (NEW_LOW au-dessous
du bottom 2089) n'arrive qu'à bar 58 (22 mai 20:00 UTC, low 2056.20).
Pour V2-dyn, cette cassure structurelle nécessiterait :
1. Confirmation par W=2 — bar 58 est avant-dernière, pas assez de bars
   après pour confirmer un swing low.
2. Le NEW_LOW @ 58 cassant le bottom de range @ 2089 — V2-dyn ne tracking
   pas le "range bottom" comme structure trackable.

**Cas Concept 2 (breakout retroactive validation)** : si V2-dyn avait
re-évalué les OBs in_range après confirmation de breakout, l'OB que
Badoun pointe ici serait probablement la dernière bougie verte avant le
dump final. **C'est exactement le cas d'usage du Concept 2**.

**Solution candidate** :
1. Tracker explicitement le top et bottom de chaque range orange détecté
2. Quand un breakout du range est confirmé (close > top ou < bottom),
   re-scan les bougies à l'intérieur pour identifier l'OB rétroactif
3. C'est un nouveau type de structure : `RANGE_BREAK_DOWN` / `RANGE_BREAK_UP`,
   différent des NEW_LOW/LL/NEW_HIGH/HH classiques

---

# Patterns observés sur ETH

1. **Tous les OBs ETH dans le range orange sont des faux positifs.**
   100% de drop rate sur les 4 OBs (#4-7) après filtre Range. Le détecteur
   actuel **génère beaucoup de bruit en zone consolidation** — c'est le
   pattern le plus important à fixer.
2. **Les 3 OBs hors range (#1-3) sont tous validés implicitement.**
   V2-dyn est correct dans les jambes directionnelles claires.
3. **L'OB manqué est tout à droite, après cassure du range** — pattern
   "breakout retroactive validation" non implémenté.

**Estimation post-filtres** :
- Sans filtre : 7 détectés, 3 corrects, 4 faux positifs, 1 manqué.
  Precision 43%, Recall 75%, F1 0.55.
- Avec filtres Range + Structure : 3 détectés, 3 corrects, 0 faux positif,
  1 manqué (toujours). Precision 100%, Recall 75%, F1 0.86.
- Avec filtres + Concept 2 (breakout retro) : 4 détectés, 4 corrects.
  **Precision 100%, Recall 100%, F1 1.00**.

L'application théorique des 3 concepts (Range + Structure + Breakout
retro) donne un détecteur parfait sur ETH. Évidemment à vérifier sur
d'autres fenêtres pour éviter l'overfit visuel — mais le signal est
fort.

---

*Diagnostic ETH rédigé 23 mai 2026 — V2-dyn W=2. Aucun paramètre modifié.
Sources : `data.csv`, `ob_detection_dynamic.csv`, `structure_summary.csv`,
`badoun_screenshots/01_eth_annotated.jpeg`.*
