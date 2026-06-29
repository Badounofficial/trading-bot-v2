# BTC H4 — V2-dyn raisonnement par OB

> Pour chaque OB que V2-dyn a détecté sur la fenêtre alignment BTC (60 H4
> finissant 22 mai 23:59 UTC), voici **mon raisonnement algorithmique**.
> Plus les 3 OBs que Badoun a ajoutés en annotation et que j'ai manqués.
> Honnête : si je n'ai pas d'explication propre, je le dis.
>
> Détecteur utilisé : `strategies/ob_detector_v2_dynamic.py` avec W=2.

## Vue d'ensemble

| # | OB | bar | ts UTC | Validation Badoun |
|---|---|---:|---|---|
| 1 | OB- | 10 | 05-14 16:00 | non commenté (probable OK) |
| 2 | OB- | 22 | 05-16 16:00 | non commenté (probable OK) |
| 3 | OB+ | 27 | 05-17 12:00 | **❌ X — faux positif** |
| 4 | OB- | 28 | 05-17 16:00 | **✅ cerclé — correct** |
| 5 | OB- | 32 | 05-18 08:00 | non commenté |
| 6 | OB+ | 47 | 05-20 20:00 | **❌ X — faux positif** |

Plus 3 OBs ajoutés par Badoun et que j'ai manqués (analyse plus bas).

---

## OB #1 — OB- @ bar 10 (2026-05-14 16:00 UTC)

- Wick anchor : **81026.00** (wick_low)
- Body close : 81368.00
- Break utilisé : **NEW_LOW** à bar 20 (cassure du swing low initial à bar 6)
- Bougie opposite-color : bullish candle bar 10 (body 81264 → 81368), c'est la dernière bougie verte avant l'impulsion vers bar 20
- Distance OB → break : 10 bougies (la plus longue de la fenêtre)
- FVG dans l'impulsion : oui · 10 bougies consécutives baissières

**Pourquoi ce candidat** : ICC textbook. La bougie verte au top du swing,
suivie d'un dump de 10 bougies, avec FVG. Aucune autre bougie verte
n'apparaît dans l'impulsion. Cas le plus propre.

**Confidence Badoun probable** : HAUTE. Big swing top, impulse propre,
break confirmé large.

---

## OB #2 — OB- @ bar 22 (2026-05-16 16:00 UTC)

- Wick anchor : **78093.00** (wick_low)
- Body close : 78226.00
- Break utilisé : **LL** à bar 24 (cassure du low précédent à bar 20 NEW_LOW)
- Bougie opposite-color : bullish candle bar 22 (body 78198 → 78226 — small body)
- Distance OB → break : 2 bougies
- FVG : non · 2 bougies consécutives baissières seulement

**Pourquoi ce candidat** : algorithmiquement, après le NEW_LOW@20 qui a
créé un nouveau plus bas, le marché rebondit jusqu'à bar 22 (la dernière
bougie verte avant le LL suivant à bar 24). C'est la "deuxième jambe" de
la cascade baissière.

**Honnêteté** : le body est minuscule (28 pts) — c'est un OB structurellement
valide mais "petit". Badoun ne l'a pas commenté — soit il est OK avec ce
flag, soit il l'aurait éliminé visuellement comme bruit.

**Confidence Badoun probable** : MOYENNE. Le LL est techniquement vérifié
mais le body de la bougie OB est très petit.

---

## OB #3 — OB+ @ bar 27 (2026-05-17 12:00 UTC) — **❌ REJETÉ PAR BADOUN**

- Wick anchor : **78519.00** (wick_high)
- Body close : 78015.00 — bougie ROUGE (close < open)
- Break utilisé : **NEW_HIGH** à bar 28 (création d'un nouveau plus haut local à 78381)
- Bougie opposite-color : bearish candle bar 27 (body 78370 → 78015)
- Distance OB → break : 1 bougie

**Mon raisonnement** : juste après la cascade baissière, le marché a fait
un rebond de bar 26 à bar 28 qui a créé un nouveau swing high local (à
78381, plus haut que les highs récents de la séquence baissière). V2-dyn
y a vu une cassure haussière, et walk-back → dernière bougie rouge = bar 27.
L'algo a fait son job mécaniquement.

**Pourquoi probablement faux positif (mon hypothèse)** :
1. **OB+ contre-trend dominant.** Sur cette fenêtre, BTC est en downtrend
   clair (81368 → 75350 = -7.5%). Un OB+ ponctuel au milieu d'un dump
   n'est pas tradeable dans le contexte. C'est un retracement, pas un
   retournement.
2. **Le "NEW_HIGH" à bar 28 n'est qu'un higher-high LOCAL.** Il est plus
   bas que tous les highs antérieurs au crash (81992 wick à bar 10). Donc
   structurellement faible.

**Ajustement candidat (à valider 3 juin, pas maintenant)** :
- Filtre macro : OB+ valide **uniquement si le bias H4 ou D1 est haussier**
  (close > MA50 par exemple, ou la séquence de structures montre HH/HL
  cohérent sur les 30 dernières bougies).

**Confidence Badoun probable** : NULLE — confirmé X.

---

## OB #4 — OB- @ bar 28 (2026-05-17 16:00 UTC) — **✅ CERCLÉ PAR BADOUN**

- Wick anchor : **77812.00** (wick_low)
- Body close : 78381.00 (close > open = bullish — la même bougie que le
  high local du #3, vue de l'autre côté)
- Break utilisé : **NEW_LOW** à bar 30 (le swing high local de bar 28
  est immédiatement invalidé par la chute à bar 30)
- Bougie opposite-color : bullish candle bar 28
- Distance OB → break : 2 bougies
- FVG : non · 2 bougies consécutives baissières

**Pourquoi ce candidat** : après le bref rebond bar 26-28 (qui a triggé
le faux OB+ #3), le marché reprend immédiatement le downtrend et fait un
nouveau low à bar 30 (76897, sous le LL@24 à 77989). V2-dyn walk-back
depuis bar 30 → dernière bougie verte = bar 28. C'est la "troisième jambe"
de la cascade baissière.

**Validation Badoun ✅** : ce flag est correct. C'est le pattern *"rebond
faux-positif puis continuation de la jambe principale"* — exactement ce
qu'un trader SMC veut détecter pour shorter.

**Note algorithmique intéressante** : la bougie bar 28 sert à la fois de
"swing high local" qui valide le faux OB+ #3 ET de "OB- correct" qui
valide le break NEW_LOW@30. C'est la même bougie, deux interprétations.
Le filtre "bias macro" qui éliminerait le #3 garderait correctement le #4.

**Confidence Badoun** : HAUTE (cerclé).

---

## OB #5 — OB- @ bar 32 (2026-05-18 08:00 UTC)

- Wick anchor : **76631.00** (wick_low)
- Body close : 77253.00
- Break utilisé : **LL** à bar 33 (cassure du NEW_LOW@30 à 76897)
- Bougie opposite-color : bullish candle bar 32 (body 77039 → 77253)
- Distance OB → break : 1 bougie (la plus courte)
- FVG : non · 1 bougie consécutive baissière

**Pourquoi ce candidat** : continuation immédiate du downtrend. La bougie
verte bar 32 est suivie directement par la bougie rouge bar 33 qui fait
le nouveau low. Algorithmiquement valide.

**Honnêteté** : distance=1 est très courte. Visuellement c'est juste une
respiration de 1 H4 dans la jambe baissière, pas un vrai swing high. C'est
le kind d'OB que Badoun a probablement appelé "pas commenté" — ni rejet
ni validation explicite. Peut-être un kind d'OB "valide structurellement
mais marginal" qu'il garde en bruit de fond.

**Confidence Badoun probable** : FAIBLE-MOYENNE. Sera intéressant de
clarifier au 3 juin.

---

## OB #6 — OB+ @ bar 47 (2026-05-20 20:00 UTC) — **❌ REJETÉ PAR BADOUN**

- Wick anchor : **77768.00** (wick_high)
- Body close : 77533.00 — bearish candle
- Break utilisé : **NEW_HIGH** à bar 48 (création d'un nouveau plus haut
  local à 78075, plus haut que les 15 derniers H4)
- Bougie opposite-color : bearish candle bar 47
- Distance OB → break : 1 bougie

**Mon raisonnement** : entre bar 33 (LL à 76394) et bar 48 (NEW_HIGH à
78075), le marché a fait un rally de $1681 sur 15 bougies. V2-dyn classe
bar 48 comme un NEW_HIGH parce que le high (78075) dépasse tous les highs
locaux récents. Walk-back depuis bar 48 → origin (bar 42 HL), dernière
bougie rouge dans [42, 47] = bar 47.

**Pourquoi probablement faux positif** :
1. **OB+ contre-trend** (même raison que #3). BTC est toujours en
   downtrend macro — le rally bar 33→48 est juste un retracement avant la
   chute finale vers 75350.
2. **Distance trop courte (1 bougie).** Une dernière bougie rouge juste
   avant la bougie verte qui fait le NEW_HIGH n'est pas un setup
   exploitable — c'est juste la dernière respiration avant le breakout.

**Ajustement candidat (à valider 3 juin)** :
- Même filtre "bias macro" que pour #3
- ET/OU exiger `distance >= 3` pour réduire le bruit ultra-court

**Confidence Badoun** : NULLE — confirmé X.

---

# Les 3 OBs que Badoun a ajoutés et que V2 a manqués

## MANQUÉ #A — OB- vers 05-21, zone ~78000

Probablement la bougie verte au top du rally bar 33→48 (bars 45-48 zone,
prix proches de 77800-78174).

**Mon hypothèse d'omission** : V2-dyn a effectivement détecté la bougie
verte bar 48 (78075) mais comme **OB+** (parce que c'est un NEW_HIGH),
pas comme OB-. L'algo dit : "ce high a cassé une structure haussière",
donc l'OB en question est un OB+ (#6 ci-dessus), pas un OB-.

**Pourquoi Badoun le voit comme OB-** : il a probablement raison que
**ce n'était pas un vrai retournement**. Le marché a fait un fake
breakout au-dessus de 78000, puis a immédiatement re-cassé à la baisse.
Dans cette lecture, bar 48 (la bougie verte) **devient** un OB- parce
qu'elle est la dernière bougie haussière avant la jambe baissière
finale (78075 → 75350).

**Le problème algorithmique** : V2-dyn n'a pas de structure break baissière
clair après bar 48. La séquence est HL@50 (77147), LH@54 (77740), puis
chute. Mais **aucun NEW_LOW ou LL n'est confirmé** par W=2 dans la
fenêtre, parce que les derniers bars (56-59) où le low se forme n'ont
pas assez de barres APRÈS pour confirmer un nouveau swing low.

**C'est exactement le problème "queue de fenêtre"** que Badoun a noté.
Le break qui validerait cet OB- existe dans la réalité mais arrive après
la fin de notre fenêtre alignment.

**Solution candidate** :
- Soit étendre la fenêtre de detection de 5-10 bougies après l'ancre
  (mais ce n'est plus une vraie "fenêtre fixe pour l'exercice")
- Soit accepter une catégorie "OB pending" pour les bougies opposite-color
  proches du dernier high/low, en attente de confirmation par les
  bougies futures
- Soit relaxer le W=2 vers W=1 sur les derniers bars (mais ça introduit
  d'autres faux positifs)

## MANQUÉ #B — OB- vers 05-21/22, zone ~77500-77800

Probablement la bougie verte bar 50 (HL à 77147, body 77013→77147) ou
bar 53 (LH à 77740, body ~77530→77640).

**Mon hypothèse d'omission** : même cause que #A — pas de break NEW_LOW
ou LL confirmé après ces bougies dans la fenêtre. Le LH@54 n'est pas un
break, c'est juste une structure intermédiaire qui se forme.

**Honnêteté** : je ne suis pas 100% sûr de quelle bougie spécifique
Badoun pointe ici. Sans son screenshot exact, c'est de l'inférence sur
le price action. À confirmer le 3 juin.

## MANQUÉ #C — OB+ dans la zone basse vers 05-20, ~76500

Bougie rouge probablement à bar 37 (body 76757→76125 wick low),
bar 39 (HL à 76489), ou bar 42 (HL à 76692). Toutes ces bougies sont
dans la zone $76125-$76700.

**Mon hypothèse d'omission** : V2-dyn **a détecté un OB+ pour le rally
qui suit** (le #6 OB+ rejeté à bar 47), mais a fait son walk-back
seulement jusqu'à l'**origin = bar 42** (le HL le plus récent), pas
jusqu'à la vraie base de la rally (bar 37 ou 33).

**Le problème algorithmique** : la fonction `_find_last_opposite_candle`
walks back depuis le break (bar 48) jusqu'à `origin_bar_index` = 42.
Elle ne va pas plus loin parce que bar 42 est marqué comme l'origin
structurel du NEW_HIGH@48 par `detect_structures`. Mais Badoun, lui,
remonte visuellement jusqu'au vrai bottom (bar 33 LL à 76394 ou bar 37
LH à 77199) parce qu'il voit le swing complet.

**Hypothèse de cause profonde** : quand il y a plusieurs HLs en escalier
qui précèdent un NEW_HIGH (39 HL → 42 HL → 48 NEW_HIGH), V2-dyn s'arrête
au HL le plus récent. Badoun remonte jusqu'au swing low qui a initié le
mouvement (bar 33 ou bar 37). Cette différence est **structurelle, pas
de paramètre** — c'est une différence dans la définition du "swing
origin" entre l'algo et l'œil.

**Solution candidate** :
- Modifier `detect_structures` pour que l'origin d'un NEW_HIGH soit le
  swing low le plus PROFOND (en valeur de prix) dans la séquence de HLs
  précédents, pas le HL le plus récent
- Ou ajouter un nouveau type d'OB+ "deep-origin" qui walks back plus
  loin quand il y a une chaîne de HLs

---

# Patterns de divergence sur BTC

**Récap honnête des 6 V2-dyn vs 5+ Badoun** :

| Catégorie | Compte | Status |
|---|:-:|---|
| V2 correct (Badoun valide) | 2 (OB# 4) + probable 1-2 non commentés | Cas idéal |
| V2 faux positif (Badoun X) | 2 (OB# 3 et #6, les deux OB+) | À filtrer |
| V2 manqué (Badoun ajoute) | 3 (2 OB- queue de fenêtre + 1 OB+ deep origin) | À élargir |
| Net | 2 corrects, 2 à filtrer, 3 à ajouter | Recall ~40%, precision ~50% |

**Lecture stratégique** : les 2 axes d'amélioration sont clairs et
**indépendants** :
1. **Filtre macro pour les OB+** : éliminerait #3 et #6 — gain precision
2. **Détection queue-de-fenêtre + deep-origin** : ajouterait #A, #B, #C
   — gain recall

Si on appliquait les deux ajustements idéalement, on serait probablement
à precision ~80%, recall ~70%, F1 ~0.74.

**Aucune modif appliquée maintenant.** Décision au 3 juin selon Principe 18.

---

# Mes questions ouvertes à Badoun

1. **OB #2 (bar 22) et OB #5 (bar 32) — non commentés** : tu les valides
   silencieusement, ou tu les considères comme bruit ignoré ? Le body
   très petit (28 pts pour #2, distance=1 pour #5) est-il un problème ?
2. **Le MANQUÉ #A** : quand un fake breakout NEW_HIGH se transforme
   immédiatement en cassure baissière, est-ce que la bougie qui a fait
   le faux high doit être tagguée OB- (lecture rétrospective) plutôt
   qu'OB+ (lecture initiale) ?
3. **Le MANQUÉ #C** : quand tu places ton OB+ au bottom, tu remontes
   jusqu'à quel niveau de swing low ? Le plus profond du leg, ou le HL
   intermédiaire le plus récent ?

Tes réponses changeront les "solutions candidates" qu'on retient pour
le calibrage 3 juin.

---

*Diagnostic rédigé 23 mai 2026, V2-dyn W=2. Aucun paramètre modifié.
Sources : `alignment_ob_2026_05_22/btc/{data.csv, ob_detection_dynamic.csv,
structure_summary.csv}`.*
