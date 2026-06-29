# Briefing OB Labelling — pour Badoun, mobile, durant le trip

> Tu as ton iPhone, TradingView, 10 jours, et envie de comparer ton œil au
> détecteur V2 sur **3 fenêtres figées** dans le temps. Voici le mode d'emploi.

## Quoi annoter

**Exactement 3 fenêtres, fixées au 22 mai 2026 23:59 UTC** :

1. **Gold (XAUUSD)** — H4 — 60 bougies finissant le 22 mai 20:00 UTC
2. **ETH** — H4 — 60 bougies finissant le 22 mai 20:00 UTC
3. **BTC** — H4 — 60 bougies finissant le 22 mai 20:00 UTC

Sur TradingView mobile, **zoome pour voir exactement les 60 dernières H4
avant ce vendredi 22 mai 23:59 UTC**. Si tu vois plus ou moins, ce n'est
pas grave — l'important c'est que la zone soit comparable.

## Pour chaque OB que tu identifies

### 1. Screenshot

Avant de tirer la capture, vérifie :
- **L'horodatage est visible** en haut/bas du chart (TradingView affiche
  date + heure de la bougie sous le curseur)
- L'OB est **clairement visible** (zoom suffisant)
- Le TF (H4) est visible dans le coin

### 2. Annote sur l'image

TradingView mobile a un outil de dessin (icône crayon en haut à droite) :
- **Rectangle** autour de la zone OB
- **Flèche** dans le sens du mouvement attendu
- **Texte court** : `OB+` ou `OB-`

Au besoin tu peux aussi annoter dans Photos après avoir tiré la capture,
peu importe le moyen tant que c'est lisible.

### 3. Nom du fichier

Format : `{asset}_ob{N}_{YYYY_MM_DD}_OB{plus|minus}.png`

Exemples :
- `gold_ob1_2026_05_18_OBplus.png`
- `eth_ob3_2026_05_15_OBminus.png`
- `btc_ob2_2026_05_20_OBplus.png`

Le **YYYY_MM_DD** = la date de la bougie OB elle-même (pas la date du
screenshot).

### 4. Commentaire bref pour chaque OB

Dans une note Apple Notes dédiée (titre : *"OB alignment 22 mai"*), ou
directement dans le message Telegram quand tu envoies, ajoute pour chaque
screenshot :

```
gold_ob1_2026_05_18_OBplus :
  - Raison : FVG net + structure cassée + 4 bougies de poussée
  - Confiance : 4/5
  - Active à l'ancre : oui (pas re-touchée)
```

Le format minimal acceptable :
```
gold_ob1 : OB+ propre, FVG, 4 bougies, confiance 4
```

## Champs utiles (pas tous obligatoires — sois pragmatique)

Pour chaque OB :
- **Type** : `OB+` (demand, à acheter) ou `OB-` (supply, à vendre)
- **Raison** : libre, court (FVG, structure break, n bougies, range, etc.)
- **Confiance** : 1-5 (1 = douteux, 5 = textbook propre)
- **Active à l'ancre** : oui/non (l'OB n'a pas été re-touché par le prix
  avant le 22 mai 23:59)
- **Session** (optionnel) : asia / london / ny — quand la bougie OB s'est
  formée

## Envoi

Trois options, par ordre de préférence :

1. **Telegram** au bot V2 — tu m'envoies les images groupées avec un
   commentaire sous chaque batch (3-5 OB par message c'est l'idéal)
2. **Cowork chat** quand tu as du wifi calme
3. **Apple Notes synchronisée iCloud** — au retour je collecte d'un coup

Si tu veux structurer dans une seule note, ce format est parfait :

```
=== OB Alignment 22 mai — GOLD H4 ===

OB1 — 2026-05-13 16:00 UTC — OB+
  Raison : double bottom + FVG après 5 bougies
  Confiance : 5/5 — textbook
  Active à l'ancre : non (consommée le 17 mai)

OB2 — 2026-05-18 08:00 UTC — OB-
  Raison : poussée bearish 6 candles + FVG
  Confiance : 4/5
  Active à l'ancre : oui
...

=== ETH H4 ===
...

=== BTC H4 ===
...
```

## Combien d'OB par actif ?

Tu y vas par ton œil — peu importe le compte exact. Quelques repères :
- **0-2 OBs** : très propre, peu de mouvement structurel sur la fenêtre
- **3-6 OBs** : volume normal pour 60 H4 sur des marchés directionnels
- **7+ OBs** : tu es probablement trop permissif — vérifie

Le but n'est PAS d'en trouver beaucoup, c'est d'en trouver les BONS — ceux
que tu prendrais effectivement en setup.

## Règle critique — pas de look-ahead

Quand tu labelliser un OB, regarde-le **comme si le marché s'arrêtait à
cette bougie**. Ne te dis pas *"je sais que c'est tombé après donc c'était
un OB- évident"* — c'est précisément le biais qu'on veut éviter.

Tag d'abord **par qualité du setup au moment de la formation**. Si l'OB a
finalement tenu et le marché est parti dans le sens prévu, tu peux noter
*"active à l'ancre : oui, prix parti vers TP"* — c'est une INFO séparée du
diagnostic de qualité.

## En cas de doute

Envoie quand même. *"Confiance 2, je sais pas trop si c'en est un mais je
pense que oui"* = info utile. C'est exactement les cas borderline qui
révèlent où le détecteur V2 diverge de ton œil.

## Au retour le 3 juin

On consolide ensemble en 30 min :
1. Je vide les screenshots et la note dans le dossier `badoun_annotations/`
2. On remplit ensemble un CSV qui matche les OBs V2 vs Badoun ligne à ligne
3. Je calcule précision / recall / F1
4. On identifie les divergences explicables par paramètre
5. **Décision** : on calibre le détecteur OU on accepte la déviation, par OB.

---

**TLDR** : 3 fenêtres figées, screenshot + texte court par OB, envoi à ta
guise, on consolide le 3 juin. **Bon trip.**
