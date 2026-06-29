# Gold H4 — V2-dyn raisonnement par OB (avec filtres Range + Structure + SL split)

> Pour chaque OB que V2-dyn a détecté sur Gold (60 H4 finissant 22 mai
> 23:59 UTC), raisonnement algorithmique + application **post-hoc** des
> 4 concepts structurels de Badoun.
>
> Annotations sources : 3 itérations Badoun :
>   - `badoun_screenshots/02_gold_annotated_v1.jpeg` (X sur OBs + FVG ajouté)
>   - `badoun_screenshots/03_gold_structure_ranges.jpeg` (structure traits + 3 boxes range)
>   - `badoun_screenshots/04_gold_sl_vs_ob_placement.jpeg` (annotation manuscrite SL ≠ OB)
>
> Détecteur : `strategies/ob_detector_v2_dynamic.py` (W=2). Pas de modif.

## Vue d'ensemble

V2-dyn a détecté **5 OBs** (4 OB- + 1 OB+).
Après application des filtres : **2 valides**. Badoun ajoute **1 OB-
manuel** (avec FVG marqué) → cible 3 OBs.

| # | OB | bar | ts UTC | V2-dyn | Filtre Range | Filtre Structure | Verdict | Annotation |
|---|---|---:|---|---|---|---|---|---|
| 1 | OB- | 16 | 05-13 20:00 | détecté | hors range | jambe valide | ✅ valide | implicite OK (top) |
| 2 | OB- | 19 | 05-14 08:00 | détecté | hors range | jambe valide | ✅ valide | implicite OK (top) |
| 3 | OB- | 28 | 05-15 20:00 | détecté | **dans range orange #2** | range entre swings | ❌ drop | X (range) |
| 4 | OB+ | 33 | 05-18 12:00 | détecté | **dans range orange #2** | range entre swings | ❌ drop | X (range) |
| 5 | OB- | 41 | 05-19 20:00 | détecté | **dans range orange #3** | range bottom | ❌ drop | X (range) |
| +A | OB- | ~38? | ~05-19 12:00 | **manqué** | hors range (post-break) | sortie de range haut | ✅ à ajouter | OB- + flèche FVG manuelle |

**Match cible : 2 V2-dyn + 1 ajouté = 3** vs cible Badoun 3 (2 OB- + 1 OB+).
**Compte exact**, mais le type diffère : Badoun voit 2 OB- (V2 valide) +
**1 OB- manuel** (au lieu d'un OB+). Pas d'OB+ validé sur Gold.

> Note importante : ce qui était au départ noté "1 OB+ en bas (zone
> verte)" dans le premier brief Badoun a été **reclassé OB-** par lui
> sur les screenshots. Le détecteur V2-dyn avait flaggé un OB+ à bar 33
> (au milieu du range) qu'il a X-out, et il ajoute un OB- proche.

---

## OB #1 — OB- @ bar 16 (2026-05-13 20:00 UTC) ✅

- Wick anchor : **4693.70**, body close : 4703.50
- Break : NEW_LOW @ bar 17 (1 bougie après seulement)
- Distance : 1 · FVG : non · consec : 1

**Mon raisonnement** : bougie verte bar 16 (close 4703.5), immédiatement
suivie d'un push baissier au bar 17 qui fait NEW_LOW à 4673.10. Walk-back
trouve cette bougie verte juste avant.

**Filtre Range** : c'est juste APRÈS le top initial (Gold a fait son top
à 4783 vers bar 4-5). Le marché est en début de jambe baissière macro,
hors de toute zone range. **Validé**.

**Filtre Structure** : début de la jambe haussière → baissière, transition
claire. Pas de range entre swings. **Validé**.

**SL placement (Concept 4)** : la bougie OB est tighter qu'un swing
structurel — le swing high réel est plus haut (bar 4 à 4783). Mais
pour CE setup local, le wick top de bar 16 (4709.00) sert de SL
immédiat. **Différence OB entry vs SL = minime**.

**Confidence Badoun** : implicite OK. Pas X-out.

## OB #2 — OB- @ bar 19 (2026-05-14 08:00 UTC) ✅

- Wick anchor : **4694.60**, body close : 4700.40
- Break : LL @ bar 26 (7 bougies après — la plus longue distance)
- Distance : 7 · FVG : oui · consec : 7

**Mon raisonnement** : LE OB clean de la fenêtre. Bougie verte bar 19,
suivie de 7 bougies baissières consécutives avec FVG, jusqu'au LL @ 26
(4540.90). C'est la jambe baissière principale 4700 → 4540.

**Filtre Range** : hors range, en pleine jambe directionnelle. **Validé**.

**Filtre Structure** : la transition du top initial vers la première
grosse jambe baissière. Jambe valide. **Validé**.

**SL placement (Concept 4)** : ici la bougie OB (bar 19, wick high 4713.60)
est la bougie structurelle elle-même. La structure macro a son swing high
plus haut (bar 11 à ~4725). Pour le setup, SL au-dessus du wick top de
bar 19 = 4713.60. Probablement le placement attendu.

**Confidence Badoun** : implicite HAUTE. Cas textbook.

## OB #3 — OB- @ bar 28 (2026-05-15 20:00 UTC) ❌

- Wick anchor : **4537.00**, body close : 4561.90
- Break : LL @ bar 29 (1 bougie après)
- Distance : 1 · FVG : non · consec : 1

**Mon raisonnement initial** : bougie verte bar 28, LL @ 29 à 4540.90.
Walk-back trouve bar 28.

**Filtre Range — RAISON DROP** : c'est ICI que commence la 2e zone range
orange tracée par Badoun (image 02). Le marché stabilise entre ~4540-4585
sur plusieurs jours après le drop initial. Le LL @ 29 à 4540.90 reste DANS
le range, pas une cassure macro.

**Filtre Structure** : range entre deux swings, pas une jambe.

**Verdict** : ❌ **drop**. Marqué X dans le screenshot 02.

## OB #4 — OB+ @ bar 33 (2026-05-18 12:00 UTC) ❌

- Wick anchor : **4588.60** (wick_high), body close : 4547.70
- Break : NEW_HIGH @ bar 35 (à 4585.50)
- Distance : 2 · FVG : non · consec : 2

**Mon raisonnement initial** : NEW_HIGH @ 35 valide un OB+ à bar 33 (la
dernière bougie rouge avant la poussée).

**Filtre Range — RAISON DROP** : exact même range orange #2. Le NEW_HIGH
@ 35 à 4585.50 reste sous le top de range (~4588 wick à bar 33 lui-même).
Pas de cassure haussière macro — c'est juste une oscillation interne.

**Filtre Structure** : faux signal de cassure haussière. La séquence reste
range entre 4540-4590.

**Verdict** : ❌ **drop**. Marqué X.

**Particularité — Concept 4 application directe** : c'est EXACTEMENT le
cas illustré par Badoun dans le screenshot 04. Il a annoté manuscritement
*"Bougie qui est techniquement le LH mais l'OB valide est juste en
dessous"* — il pointe avec une flèche orange la bougie verte autour de
4585 (bar ~35) comme "swing structurel" et précise que **l'OB
exploitable est la bougie en-dessous**, et que **le SL doit aller au-dessus
de la bougie structurelle**.

→ Si on était dans une vraie configuration où ce break était valide
(pas range), l'output V3 attendu serait :
```
ob_entry_zone   = bougie ~bar 34 ou 35 (juste sous LH, body 4555-4565)
sl_reference    = wick top du LH structurel (~4588 à bar 35)
```

Mais comme le filtre Range invalide ce setup entièrement → drop.

## OB #5 — OB- @ bar 41 (2026-05-19 20:00 UTC) ❌

- Wick anchor : **4480.00**, body close : 4491.80
- Break : NEW_LOW @ bar 42 (1 bougie après, à 4467.10)
- Distance : 1 · FVG : non · consec : 1

**Mon raisonnement initial** : bougie verte bar 41 (close 4491.8), NEW_LOW
@ 42 à 4467.10. Walk-back trouve bar 41.

**Filtre Range — RAISON DROP** : c'est dans la 3e zone range orange tracée
par Badoun (image 03), au bottom autour de 4455-4520. Le NEW_LOW @ 42 ne
casse pas le range macro vers le bas — le marché bounce après et reste
dans la box.

**Verdict** : ❌ **drop**. Marqué X dans le screenshot 02.

## OB MANQUÉ +A — OB- ajouté avec FVG par Badoun (~05-19 ~4555)

Dans le screenshot 02, Badoun a annoté manuellement **"OB-"** + une flèche
**rouge** marquée **"FVG"** dans la zone autour du 19 mai à ~4540-4560.

Probable interprétation : c'est la bougie verte ~bar 38 ou bar 39 (HL
détecté par W=2 à 4536.20) qui a précédé la chute vers 4467. Le FVG est
le gap entre cette bougie et la suivante.

**Pourquoi V2-dyn l'a manqué** : la chaîne structurelle de V2-dyn (W=2)
après le NEW_HIGH @ 35 est : LH @ 33 (origin), break NEW_HIGH @ 35,
puis... aucun break NEW_LOW clair après. La structure devient HL @ 39
(non broken), HL @ 42 (non broken). V2-dyn ne déclenche pas d'OB- là.

**Mais visuellement et factuellement** : entre bar 35 (4585) et bar 42
(4467 NEW_LOW), il y a clairement une grosse chute. La bougie verte qui
a précédé cette chute (bar 38 ou similaire) DEVRAIT être un OB-.

**Pourquoi le détecteur ne le voit pas — diagnostic structurel** :
- V2-dyn déclenche les OB- sur `NEW_LOW` et `LL`. Le NEW_LOW @ 42 EST
  bien détecté.
- Walk-back depuis bar 42 → origin = bar 37 (LH à 4548.10) — la dernière
  structure opposite avant. Donc le search range est [37, 41].
- Dans [37, 41], la dernière bougie verte est... **bar 41** ! C'est
  exactement l'OB #5 que V2-dyn a détecté !

**Donc V2-dyn ne manque PAS un OB- ici — il choisit le mauvais candidat**.
Badoun pointe une bougie verte plus profonde dans la séquence (bar 38
peut-être), alors que V2-dyn prend la plus récente (bar 41).

**Hypothèse cause** : Badoun, regardant le FVG marquant la cassure, a
remonté jusqu'à la bougie qui PRÉCÈDE le FVG, pas la plus proche du
NEW_LOW. C'est une définition différente : "OB- = bougie verte précédent
le FVG du leg" plutôt que "OB- = dernière bougie verte avant le break
confirmé".

**Solution candidate (V3)** :
- Quand un FVG est détecté dans le leg baissier, le candidate OB- est
  la bougie immédiatement avant le FVG, **pas** la plus récente bougie
  verte (qui peut être après le FVG).
- C'est un raffinement du walk-back actuel : on ne prend pas systématiquement
  la "most recent opposite", on prend "most recent opposite AVANT le FVG".

**Vérification de l'hypothèse** : si Badoun pointe la bougie pré-FVG, on
gagne :
- Un meilleur niveau de prix (plus proche du body close pré-impulse)
- Une distance OB → break plus réaliste (pas 1 bougie = bruit)
- Un FVG validé visiblement → confiance signal augmentée

---

# Patterns observés sur Gold

1. **2/5 OBs V2-dyn validés** (#1 et #2 = OB- top). Tous sont dans la
   jambe baissière initiale 13-15 mai.
2. **3/5 OBs V2-dyn invalidés par filtre Range** (#3, #4, #5). Tous dans
   les zones range orange ; pattern systémique.
3. **1 OB- manqué = wrong candidate, pas miss total** — V2-dyn a vu le
   break mais a pointé la mauvaise bougie verte (la plus récente au lieu
   de la pré-FVG).

**Estimation post-filtres** :
- Sans filtre : 5 détectés, 2 corrects, 3 faux positifs, 1 "wrong candidate".
  Precision 40%, Recall ~50% (2/3 si on compte le wrong candidate comme
  miss partial). F1 ≈ 0.44.
- Avec filtres Range + Structure : 2 détectés, 2 corrects, 0 faux positif,
  1 wrong candidate. Precision 100%, Recall 67% (2/3). F1 0.80.
- Avec filtres + "OB pre-FVG" candidate refinement : 3 détectés, 3
  corrects. **Precision 100%, Recall 100%, F1 1.00**.

---

# Concept 4 (SL ≠ OB) — application Gold

Le screenshot 04 est **la référence pédagogique** sur ce concept. Il
illustre directement avec la bougie ~bar 33-35 (autour de 4555-4588) :

| Élément | Valeur | Bougie source |
|---|---|---|
| Bougie structurelle (LH au sens swing point) | ~4588 wick high | bar ~35 |
| Bougie OB valide (entry) | ~4555 body close, ~4536 wick low | bar 33 |
| Différence OB entry vs SL ref | ~33 pts (0.7%) | |

**Cas pratique** : si on prenait un short à 4555 (OB entry) avec SL à
4555 wick top (4588 du même OB candle) = SL trop large parfois, ou
SL au wick top de la bougie OB = trop serré.

**Avec Concept 4 split** :
- OB entry zone = body close 4555 ± wick = 4536-4555
- SL reference = wick top de la **bougie structurelle distincte** = 4588
- Risk = ~33 pts entre entry et SL (au lieu de ~3 pts si on prenait le
  même OB sans split)
- Trade exploitable avec un R:R réaliste

L'enseignement est : V2-dyn ne supporte pas cette distinction
aujourd'hui. La sortie ne donne qu'un `wick_anchor_price`. Pour V3, il
faut deux niveaux.

---

# Questions ouvertes (en plus de celles de BTC)

**Question 6 Gold** : quand un OB+ se forme dans un downtrend macro
clair (comme bar 33), faut-il toujours le drop, ou peut-il être valide
si la zone range est cassée vers le haut ensuite (Concept 2 retroactive
validation pour OB+ in range) ?

**Question 7 Gold** : sur le manqué +A, est-ce que la règle "OB- = pré-FVG"
remplace ou s'ajoute à la règle "OB- = most recent opposite avant
break" ?

À discuter avec Badoun au 3 juin.

---

*Diagnostic Gold rédigé 23 mai 2026 — V2-dyn W=2. Aucun paramètre modifié.
Sources : `data.csv`, `ob_detection_dynamic.csv`, `structure_summary.csv`,
3 screenshots Badoun dans `badoun_screenshots/`.*
