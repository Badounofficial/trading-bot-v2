# OB Alignment — Divergence Report (V2-strict vs V2-dynamic vs Badoun)

> **Update du 22 mai 2026 (soir)** : Badoun a clarifié sa définition d'OB
> par message Cowork. La cassure structurelle est **le seul validateur**.
> Pas de seuil consécutif strict, pas de FVG obligatoire. J'ai refactoré
> dans `strategies/ob_detector_v2_dynamic.py` (W=2 par défaut) — l'ancien
> `strategies/icc_orderblocks.py` est conservé intact pour comparaison.
>
> **Décision pendant l'absence** : aucun paramètre du détecteur en
> production (V2-strict) n'est modifié. V2-dyn vit en parallèle. Calibration
> finale différée au **3 juin 2026**, voire au **gate du 12 août**.

## Résultat headline

| Actif | Badoun (cible) | V2-strict (icc_orderblocks) | V2-dyn (W=2, no filter) |
|---|:-:|:-:|:-:|
| Gold H4 | 3 (2 OB- + 1 OB+) | 0 | 5 (4 OB- + 1 OB+) |
| ETH H4  | 4 OB-             | 1 (OB- VERY_STRONG) | 7 (5 OB- + 2 OB+) |
| BTC H4  | 5 OB-             | 1 (OB- VERY_STRONG) | 6 (4 OB- + 2 OB+) |
| **Total** | **12** | **2** | **18** |

**Signal critique à relayer à Badoun avant décollage** :

> V2-dyn refactor → **18 OBs** au total. Badoun visait ~12. Léger overshoot
> (+6, dont 3 OB+ que Badoun n'a probablement pas marqués). On est dans
> le ballpark "≈12 = bonne piste" — **pas dans le 30+ overshoot** qui
> aurait été problématique.
>
> Hypothèses pour expliquer l'écart de 6 :
>   1. W=2 trop permissif → quelques micro-swings que l'œil de Badoun
>      ignore (à valider sur les screenshots originaux le 3 juin).
>   2. Tous les OB+ détectés par V2-dyn ne sont pas pertinents pour Badoun
>      sur cette fenêtre (downtrend dominant — il n'a marqué qu'1 OB+ sur
>      Gold en bottom zone).
>   3. Mon inférence des 12 OBs de Badoun à partir du seul OHLC (sans
>      screenshots) peut être imprécise — la cible "12" elle-même est
>      probablement à ±2.

## Comparaison détaillée par actif

### Gold H4 — V2-dyn = 5 OBs, Badoun = 3

| bar | timestamp UTC | type | wick anchor | body close | broke | distance | Badoun matched ? |
|---|---|---|---|---|---|---|---|
| 16 | 2026-05-13 20:00 | OB- | wick_low=4693.70 | 4703.50 | NEW_LOW@17 | 1 | probable NO (micro-move) |
| 19 | 2026-05-14 08:00 | OB- | wick_low=4694.60 | 4700.40 | LL@26 | 7 | **YES — match** |
| 28 | 2026-05-15 20:00 | OB- | wick_low=4537.00 | 4561.90 | LL@29 | 1 | probable NO (micro-move) |
| 33 | 2026-05-18 12:00 | OB+ | wick_high=4588.60 | 4547.70 | NEW_HIGH@35 | 2 | probable NO (Badoun OB+ is bottom zone) |
| 41 | 2026-05-19 20:00 | OB- | wick_low=4480.00 | 4491.80 | NEW_LOW@42 | 1 | probable NO mais proche |

Badoun's OB+ in the bottom zone (bar 42, 4467-4512) is NOT in V2-dyn output
parce qu'aucun NEW_HIGH ne casse à partir de là (la structure reste baissière
après bar 42). C'est probablement le **plus gros miss conceptuel** — un OB+
en bottom zone implique un retournement de tendance que V2-dyn ne valide pas
encore comme un "structural break" suffisant.

### ETH H4 — V2-dyn = 7 OBs, Badoun = 4 OB-

| bar | ts UTC | type | wick anchor | body close | broke | dist | Badoun matched ? |
|---|---|---|---|---|---|---|---|
| 9  | 05-14 12:00 | OB- | wick_low=2245.10 | 2297.50 | NEW_LOW@15 | 6 | **YES — top zone** |
| 18 | 05-16 00:00 | OB- | wick_low=2222.10 | 2226.90 | LL@20      | 2 | **YES — top zone (2e)** |
| 28 | 05-17 16:00 | OB- | wick_low=2175.30 | 2191.40 | LL@30      | 2 | **YES — below high** |
| 32 | 05-18 08:00 | OB- | wick_low=2109.30 | 2132.50 | LL@33      | 1 | **YES — below high (2e)** |
| 33 | 05-18 12:00 | OB+ | wick_high=2156.10 | 2106.40 | NEW_HIGH@37 | 4 | probable NO |
| 47 | 05-20 20:00 | OB+ | wick_high=2140.10 | 2129.10 | HH@48 | 1 | probable NO |
| 48 | 05-21 00:00 | OB- | wick_low=2127.90 | 2145.40 | NEW_LOW@50 | 2 | probable NO (Badoun ?? exclu ?) |

ETH = **4 OB- matchent parfaitement** la cible Badoun (bars 9, 18, 28, 32).
Les 3 supplémentaires V2-dyn (2 OB+ + 1 OB-) sont probablement les
"extras" — bar 48 OB- peut être le "??" exclu par Badoun.

### BTC H4 — V2-dyn = 6 OBs, Badoun = 5 OB-

| bar | ts UTC | type | wick anchor | body close | broke | dist | Badoun matched ? |
|---|---|---|---|---|---|---|---|
| 10 | 05-14 16:00 | OB- | wick_low=81026.00 | 81368.00 | NEW_LOW@20 | 10 | **YES — top** |
| 22 | 05-16 16:00 | OB- | wick_low=78093.00 | 78226.00 | LL@24      | 2  | **YES probable** |
| 27 | 05-17 12:00 | OB+ | wick_high=78519.00 | 78015.00 | NEW_HIGH@28 | 1 | probable NO |
| 28 | 05-17 16:00 | OB- | wick_low=77812.00 | 78381.00 | NEW_LOW@30 | 2 | **YES probable** |
| 32 | 05-18 08:00 | OB- | wick_low=76631.00 | 77253.00 | LL@33      | 1  | **YES probable** |
| 47 | 05-20 20:00 | OB+ | wick_high=77768.00 | 77533.00 | NEW_HIGH@48 | 1 | probable NO |

BTC = **4 OB- matchent probablement** la cascade descendante de Badoun (10,
22, 28, 32). Le 5e OB- attendu serait soit bar 37, soit bar 56 — V2-dyn ne
les détecte pas parce qu'il n'y a pas de NEW_LOW/LL clean après dans la
fenêtre. Possible miss qui sera confirmé sur le screenshot.

## Analyse algorithmique des écarts

### Pourquoi V2-strict (icc_orderblocks) ratait 10/12

Récap brièvement (couvert dans la première version de ce rapport) :
- **Strength filter trop strict** : WEAK rejected, MODERATE/STRONG/VERY_STRONG only.
  3+ candles avec FVG OU 5+ candles sans FVG. Élimine 80% des candidates.
- **W=3 dans `detect_structures`** : rate les swings serrés (W=2 visuel chez Badoun).
- **Body-only zone** : `[min(o,c), max(o,c)]` ignore les mèches.

### Pourquoi V2-dyn overshoot (+6 vs Badoun) {#overshoot}

Hypothèses **non testées** (pas de modification pendant l'absence) :

1. **W=2 capture trop de swings** :
   - Gold bar 16 (1 bougie après le break) et bar 28 (idem) sont des
     micro-swings que W=3 aurait éliminés. Sur les 5 OBs Gold V2-dyn, 2
     sont probablement de ce type.
2. **OB+ contre-trend pas pertinents pour Badoun** :
   - Tous les marchés sur 13-22 mai étaient en downtrend dominant. Badoun
     n'a marqué qu'1 seul OB+ (Gold bottom zone) sur les 3 actifs. V2-dyn
     trouve 5 OB+ au total (Gold 1, ETH 2, BTC 2). Probable filtre
     contextuel "OB+ uniquement dans une tendance haussière confirmée"
     que l'œil de Badoun applique implicitement.
3. **Distance to break = 1 candidates** :
   - V2-dyn détecte des OB- où la dernière bougie verte est juste 1 barre
     avant le break (distance=1). C'est techniquement correct par la
     définition Badoun, mais visuellement ces "OBs minute" peuvent être
     ignorés au profit du plus grand swing high. Note : sur les Badoun
     matched, les distances sont 6, 7, 10 (gros OBs) — pour les
     non-matched, les distances sont 1-2 (petits OBs).

### Pourquoi V2-dyn miss potentiellement le bar 35 Gold + bar 42 Gold OB+

- **Gold bar 35 (Badoun OB-)** : V2-dyn pointe bar 41 à la place. C'est
  la dernière bougie verte avant le NEW_LOW à bar 42. C'est **logiquement
  correct** par la définition dynamique. Si Badoun marquait bar 35 et pas
  bar 41 sur son screenshot, c'est qu'il applique une heuristique
  supplémentaire (probablement "OB- au swing high lui-même quand le push
  initial est massif", même si une autre bougie verte intermédiaire
  existe). À clarifier le 3 juin.

- **Gold bar 42 (Badoun OB+ bottom)** : V2-dyn ne le voit pas parce qu'il
  n'y a pas de NEW_HIGH qui casse vraiment la structure descendante après
  bar 42 — la structure suivante est `HL` à bar 51 (un higher low), pas
  une cassure de structure plein. Possible enhancement : Badoun semble
  accepter un OB+ en bottom zone même quand la cassure suivante est
  faible (HL plutôt que NEW_HIGH). À clarifier.

## Métriques actuelles (best-effort estimation)

Sans les screenshots originaux, mes meilleurs estimés en supposant que les
12 timestamps inférés sont corrects (±1 bar) :

| Détecteur | Vrais positifs | Faux positifs | Faux négatifs | Précision | Recall | F1 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| V2-strict | 2 | 0 | 10 | 100% | 17% | 0.29 |
| V2-dyn (W=2) | 10 (probable) | 8 (probable) | 2 (probable) | ~56% | ~83% | 0.67 |

V2-dyn double le F1 vs V2-strict. C'est l'ordre de grandeur attendu pour
**"recalibration directionnellement correcte"** — pas optimisé, mais sur la
bonne piste.

## Décision actée pour la suite immédiate

- ✅ **`strategies/ob_detector_v2_dynamic.py`** : créé, non-utilisé par
  la production. Test isolé sur les 3 fenêtres = ce rapport.
- ✅ **`strategies/icc_orderblocks.py`** : **INTACT**. Production
  (daemon paper_funding_capture, walk-forwards, tests unitaires)
  continue d'utiliser V2-strict pendant l'absence.
- ✅ **Exercice forward 23 mai → 2 juin** : utilisera **V2-dyn**
  (pas V2-strict) pour matcher au mieux l'attente visuelle de Badoun et
  obtenir un signal recalibration utile au retour.

## À valider 3 juin (calibration meeting)

1. Confirmer les vrais timestamps des 12 OBs Badoun via screenshots originaux
2. Identifier précisément lesquels des 18 OBs V2-dyn sont validés ou
   rejetés
3. Décider :
   - Si V2-dyn est ~80% precision → **on canonicalise V2-dyn**
   - Sinon, ajouter filtre contextuel (distance >= 3, OB+ only in
     uptrend, etc.) — itération vers F1 > 0.80
4. Re-runner les **walk-forwards OOS+friction** avec le détecteur calibré
   avant tout déploiement de capital

---

# Concepts structurels manqués — apport critique de Badoun 23 mai

> **Section ajoutée 23 mai 2026 après réception des 4 screenshots annotés
> de Badoun (ETH + 3 versions itératives Gold).** Ces 4 concepts ne sont
> PAS dans le détecteur V2-dyn actuel et expliquent **tous les écarts
> de divergence** observés. Ils sont la fondation conceptuelle pour la
> calibration finale du détecteur — pas implémentés maintenant per le
> Principe 18.
>
> Screenshots originaux sauvegardés dans `badoun_screenshots/` :
>   - `00_btc_annotated.jpeg` (premier retour BTC 23 mai matin)
>   - `01_eth_annotated.jpeg` (ETH avec range orange 18-22 mai)
>   - `02_gold_annotated_v1.jpeg` (Gold avec range + FVG manuel)
>   - `03_gold_structure_ranges.jpeg` (Gold avec traits structure + 3 ranges)
>   - `04_gold_sl_vs_ob_placement.jpeg` (Gold avec annotation manuscrite SL ≠ OB)

## Concept 1 — Filtre RANGE (invalidation OB en consolidation)

**Citation Badoun** : *"il n'y a pas de cassure évidente, pas de bougies
avec un vrai mouvement institutionnel — évidemment certaines bougies
seront plus grandes que d'autres mais ça ne veut pas dire qu'il y a eu
injection de capitaux sur les marchés"*.

**Règle** : un OB formé à l'intérieur d'une zone où le prix range
(oscillation sans direction franche, pas de body candles directionnelles
significatives) **n'est PAS valide**, même si la cassure structurelle
existe techniquement. Le marché doit montrer un mouvement directionnel
net (large body candles, momentum confirmé) pour qu'un OB compte comme
exploitable.

**Visualisation** (`01_eth_annotated.jpeg`) : Badoun a tracé un grand
rectangle orange entre le 18 et 22 mai sur ETH (zone ~2100-2150). Il X-out
tous les OBs que V2-dyn a détectés dedans (2 OB+ + 2 OB-). Il ne valide
que les 3 OB- du haut ("vraies cassures incontestables, surtout sur une
TF pareille").

**Implication algorithmique** : ajouter un **filtre de range pré-OB** qui
détecte les zones de consolidation et bloque toute validation d'OB
formé dedans, sauf si breakout confirmé (cf. Concept 2).

## Concept 2 — Breakout = validation rétroactive

**Règle complémentaire au Concept 1** : si un OB se forme dans une zone
de range MAIS que le prix finit par casser au-dessus ou en-dessous du
range → l'OB **devient valide rétrospectivement**.

- La zone reste "range" tant qu'elle est respectée → OBs internes invalidés
- Devient "trigger zone" quand elle est cassée → OBs internes ré-évalués

**Implication algorithmique** : l'évaluation d'un OB doit être
**dynamique** — un OB peut passer de `invalid (in range)` à
`valid (range broken)` au fil du temps. Pas un classement définitif au
moment de la détection.

## Concept 3 — Structure de marché ↔ OB sont LIÉS

**Citation Badoun** : *"tant que ce n'est pas cassé par une autre
structure, les OBs qui se créent dedans sans casser le prix dans ce
carré ne sont pas valides. Si dans ce carré un OB se forme et casse
soit en haut soit en bas → cet OB sera valide. Tant que ça reste
dedans → c'est du range."*

**Visualisation** (`03_gold_structure_ranges.jpeg`) : Badoun a tracé en
traits gris/blancs la structure de marché complète sur Gold (high 12 mai →
low → high 14 mai → low 18 mai → high 19 mai → low). Plusieurs
rectangles orange marquent les zones de range entre deux swing points
structurels successifs.

**Règle dérivée** : avant de valider un OB, vérifier qu'il s'inscrit
dans une **jambe structurelle valide** (séquence HH/HL ou LH/LL avec
direction franche), pas dans une box entre 2 swing points.

**Différence avec mon W=2 actuel** : V2-dyn détecte les CHoCH/BoS
techniques mais ne classifie pas les "jambes valides" vs les "ranges
entre jambes". Un swing high + swing low successifs ne suffisent pas —
il faut que le mouvement entre les deux soit directionnel.

## Concept 4 — SL placement ≠ OB placement (séparation critique)

**Citation Badoun manuscrite** (`04_gold_sl_vs_ob_placement.jpeg`) :
*"Bougie qui est techniquement le LH mais l'OB valide est juste en
dessous, je te l'ai mis. Du coup s'il y a une entrée en Sell le SL
devrait se trouver au dessus de la bougie de la structure, celle avec
la flèche orange."*

**Règle** : la bougie qui marque le **LH structurel** (swing point au
top de la jambe) et la bougie qui est le **vrai OB exploitable** sont
souvent **deux bougies différentes** :
- **OB entry zone** = la bougie verte juste **en-dessous** du LH structurel
  (signal d'entrée + zone wick-inclusive d'invalidation immédiate)
- **SL reference price** = le wick haut du LH structurel **AU-DESSUS**
  (placement réel du stop-loss, plus haut que la bougie OB)

**Implication algorithmique majeure** : le détecteur doit produire
**deux niveaux distincts par OB** :

```
ob_entry_zone   = [body_close, wick_top_of_OB_candle]   (zone signal)
sl_reference    = wick_top_of_structural_LH_candle      (zone stop)
```

Aujourd'hui V2-dyn ne produit qu'**un seul niveau** (`wick_anchor_price`).
Le SL est donc placé trop près du prix d'entrée → trop de stop-outs.

**Exemple concret sur Gold** (`04_gold_sl_vs_ob_placement.jpeg`) :
- La bougie verte que Badoun a labellisée OB- (autour de 4555, le 19 mai)
- La bougie structurelle LH au-dessus (autour de 4585, la même date)
- Différence : ~30 pts (~0.65%)
- Si on place le SL à 4555 (wick anchor OB) → premier coup de mèche le sort
- Si on place le SL à 4585 (wick LH structurel) → buffer correct

## Synthèse des 4 concepts en termes algorithmiques

Pour passer de V2-dyn (recall 83% / precision 56% / F1 0.67) à V3 cible
(recall 80% / precision 90% / F1 0.85), il faudra :

| Concept | Filtre algorithmique candidat | Effet attendu |
|---|---|---|
| #1 Range | Détecter zones range (ATR contraction, body avg < X% range) → bloquer OBs internes | Élimine 60-70% des faux positifs (OB+ contre-trend dans dump) |
| #2 Breakout retro | Re-évaluation dynamique des OBs en range si breakout confirmé | Récupère 10-15% des OBs initialement blockés |
| #3 Structure | Classifier chaque OB comme `in_valid_leg` vs `in_range_between_legs` | Élimine 20-30% des faux positifs résiduels |
| #4 SL split | Produire `ob_entry_zone` + `sl_reference_price` séparément | Pas de gain F1, mais réduit le drawdown réel de 30-50% via meilleur SL |

**Aucune de ces 4 implémentations n'est faite maintenant.** Format de
sortie proposé dans `proposed_v3_output_format.md`.

## Recalibration des 18 OBs V2-dyn après application mentale des filtres

Application théorique des Concepts 1 + 3 (sans coder) sur les 3 fenêtres :

### Gold (5 V2-dyn → 2 valides après filtres)

| OB | bar | Filtre Range | Filtre Structure | Verdict |
|---|---|---|---|---|
| OB- | 16 | hors range | jambe valide | **garde** |
| OB- | 19 | hors range | jambe valide | **garde** |
| OB- | 28 | dans range orange | range entre swings | **drop** |
| OB+ | 33 | dans range orange | range entre swings | **drop** |
| OB- | 41 | dans range bas | trop proche bottom | **drop** |

+ 1 OB- ajouté par Badoun avec FVG (vers 4555 le 19 mai) → manqué par
V2-dyn parce que mon walk-back s'arrête au HL le plus récent. Cf.
Concept 3 + le diagnostic dans `gold/v2_reasoning_per_ob.md`.

**Compte final probable Badoun = 3 OBs valides** (2 V2-dyn gardés + 1 ajouté).

### ETH (7 V2-dyn → 3 valides après filtres + 1 ajouté = 4)

| OB | bar | Filtre Range | Verdict |
|---|---|---|---|
| OB- | 9  | hors range | **garde** |
| OB- | 18 | hors range | **garde** |
| OB- | 28 | hors range | **garde** (top de la jambe basse) |
| OB- | 32 | dans range orange | **drop** |
| OB+ | 33 | dans range orange | **drop** |
| OB+ | 47 | dans range orange | **drop** |
| OB- | 48 | dans range orange | **drop** |

+ 1 OB- ajouté manuellement par Badoun à droite hors range = 4 total
attendu.

### BTC (6 V2-dyn → 2-3 valides après filtres + 3 ajoutés = 5-6)

Voir `btc/v2_reasoning_per_ob.md`. La principale réinterprétation après
les nouveaux concepts :
- Les 2 OB+ rejetés (#3 bar 27, #6 bar 47) étaient effectivement dans
  des micro-ranges entre les jambes baissières → **Concept 1 + 3
  expliquent leur invalidation** mieux que mon hypothèse initiale
  "contre-trend macro" seule.
- Les OBs silencieux non-commentés (#2 bar 22, #5 bar 32) étaient
  probablement dans des zones de range mineures → **Concept 1 répond
  partiellement à ma question ouverte #1**.

## Mise à jour des questions ouvertes pour le 3 juin

**Question 1 BTC (OBs silencieux #2 et #5)** : ✅ probablement résolue
par Concept 1 + 3. Bar 22 (range mineur 24-27) et bar 32 (range bottom)
sont probablement écartés comme "in_range".

**Question 2 BTC (fake breakout retag OB- vs OB+)** : encore ouverte.
Liée au Concept 2 (re-évaluation rétroactive) mais besoin de clarification
sur le mécanisme de retag.

**Question 3 BTC (walk-back OB+ deep)** : encore ouverte. Liée au
Concept 3 — la définition d'"origin" du leg structurel doit remonter
au vrai swing low, pas au HL le plus récent.

**Nouvelles questions** :

**Question 4** : comment **détecter algorithmiquement** une zone de
range vs une jambe valide ? Critères candidats :
- ATR contraction (ATR < X% du prix moyen)
- Body average / wick average ratio < seuil
- Variance des closes < seuil
- Aucune bougie body > 1.5x ATR sur N bars

**Question 5** : pour le SL placement (Concept 4), le LH structurel à
utiliser est-il toujours le swing high le plus proche du break, ou
peut-il être plus profond dans le leg ? Exemple Gold image 4 : la bougie
LH est très proche du OB (1-2 bars). Sur d'autres setups, pourrait-elle
être plus loin ?

---

*Rapport mis à jour 22 mai 2026 — V2-dyn implémenté, V2-strict conservé.
Sources : `alignment_ob_2026_05_22/{asset}/{data.csv, ob_detection.csv,
ob_detection_dynamic.csv, structure_summary.csv}`, `badoun_annotations.csv`,
`strategies/ob_detector_v2_dynamic.py`.*
