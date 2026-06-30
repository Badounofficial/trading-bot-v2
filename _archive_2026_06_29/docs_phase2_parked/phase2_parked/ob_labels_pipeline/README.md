# OB Labeling Pipeline — Mode d'emploi

> **Objectif** : construire un dataset supervisé d'Order Blocks que Badoun valide manuellement (OB+ / OB- / OB neutre), pour qu'on en extraie ensuite la **distribution caractéristique** et qu'on entraîne le détecteur du bot dessus.

## Pourquoi

Tu vois des **formes** sur le chart. Moi je vois des **séries de nombres**. Cette pipeline est le pont entre les deux : tu m'envoies une photo + quelques métadonnées (timestamp, actif, TF, type OB), je récupère les chiffres OHLC correspondants et j'apprends *"quand Badoun dit OB+, voici quelle distribution de features se présente"*.

## Workflow

### Quand tu repères un OB sur ton chart (TradingView)

1. **Screenshot** la zone : 30-50 bougies autour de l'OB, TF visible, prix lisibles
2. **Note dans `labels.csv`** une ligne avec :
   - `label_id` : identifiant unique (incrément)
   - `timestamp_utc` : heure exacte de la bougie OB (UTC, format `YYYY-MM-DD HH:MM`)
   - `asset` : `BTC`, `ETH`, `SOL`, `GOLD`, `EURUSD`, etc.
   - `tf` : timeframe (`H4`, `H1`, `M30`, `M15`)
   - `ob_type` : `OB+` (bullish, à acheter), `OB-` (bearish, à vendre), `OB?` (douteux)
   - `direction` : `long` / `short`
   - `push_candles` : nombre de bougies dans le sens du move APRÈS l'OB
   - `reverse_candles_before` : nombre de bougies inverses JUSTE AVANT l'OB
   - `fvg_present` : `oui` / `non` — y a-t-il un Fair Value Gap dans les X bougies suivantes ?
   - `fvg_within_n_candles` : si `fvg_present=oui`, dans combien de bougies (1, 2, 3...)
   - `engulfing` : `oui`/`non` — la bougie OB englobe-t-elle la précédente ?
   - `created_swing` : `high` / `low` / `none` — l'OB a-t-il créé un swing significatif ?
   - `session` : `asia` / `london` / `ny_am` / `ny_pm`
   - `comment` : libre — *"très propre, juste après CHoCH H4"*, *"sweep liquidity puis OB"*, etc.
   - `screenshot_path` : chemin relatif vers la photo (ex : `screenshots/2026-05-22_BTC_H1_OB+.png`)
   - `validation` : `valid` (l'OB a tenu et le marché est parti dans le sens prévu) / `failed` (cassé) / `pending` (pas encore résolu)

3. **Sauvegarde le screenshot** dans `data/ob_labels/screenshots/` avec le nom indiqué dans la colonne `screenshot_path`.

### Sur ton iPhone pendant l'absence

Tu peux faire le repérage en mode dégradé :
- Notes Apple → une note par OB avec : `date heure asset TF type direction commentaire`
- Captures d'écran TradingView mobile dans un album dédié "OB labels"
- Au retour, on remplit le CSV en 30 min ensemble

### Au retour (3 juin)

Je passerai ton CSV dans `scripts/extract_ob_features.py` (à créer) qui :
1. Pour chaque ligne, va chercher les OHLC dans `data/` autour du timestamp
2. Extrait ~25 features quantitatifs (range, body ratio, ATR-relative size, volume si dispo, distance au swing, etc.)
3. Sortie : `data/ob_labels/features.parquet` — prêt pour clustering / classification

Ensuite on regarde **la distribution** des features pour les `OB+ valid` vs les `OB- valid` vs les `failed`. Si une frontière nette ressort (median + IQR sépare bien les classes), on a notre détecteur. Sinon, on essaie un petit modèle (decision tree / logistic regression) — pas de deep learning, on veut interpréter.

## Quantité visée pour qu'on ait du signal

- **Minimum exploitable** : 30 OB labellisés par actif × 3 actifs (BTC/ETH/Gold) = 90 labels
- **Confortable** : 100 par actif = 300 labels
- **Idéal** : 200 par actif = 600 labels

Tu n'es pas obligé de tout faire en mode actif pendant le trip — même 10-15 labels propres sur un actif sera suffisant pour démarrer.

## Règle critique — pas de look-ahead pendant le labeling

⚠️ Quand tu labellises un OB, regarde-le **comme si le marché s'arrêtait à cette bougie**. Ne te dis pas *"je sais que ça a marché donc je le tag OB+"* — c'est précisément le biais qu'on essaie d'éviter. Tag d'abord **par qualité du setup au moment de la formation**, et utilise la colonne `validation` séparée pour dire si ça a finalement tenu ou pas.

Sinon on entraîne un modèle qui mémorise des coïncidences plutôt qu'un modèle qui détecte des setups.

## Conseil pratique

Mets-toi une fenêtre TradingView avec ta watchlist + un onglet de ce dossier ouvert dans Finder. Quand tu vois un OB, **30 secondes pour screenshot + ligne CSV**. Plus c'est en flux tendu, moins tu surcalibres a posteriori.

---

*Pipeline créée le 22 mai 2026 par V2 avant le départ de Badoun.*
