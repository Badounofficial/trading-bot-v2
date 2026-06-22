# OB Alignment Exercise — 22 May 2026 anchor

> **Objectif** : aligner le langage OB entre Badoun (annotation manuelle visuelle)
> et V2 (détection algorithmique) sur un ensemble de 3 fenêtres fixées dans le
> temps, pour que les futurs backtests valident la **stratégie de Badoun**, pas
> juste *"l'interprétation que le bot a de la stratégie de Badoun"*.

## Protocole

**Ancre commune** : `2026-05-22 23:59 UTC` (close week-end marchés CFD/Forex).

**3 fenêtres fixes** :

| Actif | TF | Bougies | Source data | Fenêtre |
|---|---|---|---|---|
| **Gold (XAUUSD)** | H4 | 60 | yfinance `GC=F` resampled 1h→4h | 2026-05-11 04:00 → 2026-05-22 20:00 UTC |
| **ETH** | H4 | 60 | Hyperliquid perp ETH/USDC via ccxt | 2026-05-13 00:00 → 2026-05-22 20:00 UTC |
| **BTC** | H4 | 60 | Hyperliquid perp BTC/USDC via ccxt | 2026-05-13 00:00 → 2026-05-22 20:00 UTC |

La dernière bougie inclus dans chaque fenêtre est celle qui **clôture à
2026-05-23 00:00 UTC** (= 1 minute après l'ancre 23:59 UTC, c'est le H4 close
naturel le plus proche). Pour Gold, comme le marché a des gaps week-end, les
60 H4 couvrent ~14 jours calendaires au lieu de 10.

## Que contient ce dossier

```
alignment_ob_2026_05_22/
├── README.md                       (ce fichier — le protocole)
├── INSTRUCTIONS_BADOUN.md          (briefing labelling mobile pour Badoun)
├── gold/
│   ├── data.csv                    (60 H4 OHLC bruts)
│   ├── ob_detection.csv            (OBs détectés par V2)
│   ├── structure_summary.csv       (toutes les structures, dont les breaks
│   │                                qui n'ont PAS produit d'OB — diagnostic)
│   └── chart_annotated.png         (chart H4 avec OBs marqués par V2)
├── eth/  (même structure)
└── btc/  (même structure)
```

Le script qui génère tout : `scripts/build_ob_alignment.py` (re-runnable).

## Résultats V2 (snapshot 22 mai 2026)

| Actif | Structures totales | Breaks | OBs détectés | Breaks sans OB |
|---|---|---|---|---|
| **Gold** | 11 | 3 | **0** | 3 |
| **ETH** | 13 | 5 | **1** (OB- VERY_STRONG) | 4 |
| **BTC** | 11 | 4 | **1** (OB- VERY_STRONG) | 3 |

Le détecteur V2 est paramétré conformément au TU #3 :
- `swing_lookback = W = 3` (standard pour H4)
- Critère de validation : 3+ bougies dans le sens du move ET FVG présent,
  OU 5+ bougies dans le sens sans FVG nécessaire
- Strength : VERY_STRONG (FVG + break + 3+ candles), STRONG, MODERATE.
  WEAK = rejeté, non sauvegardé.

Le **faible nombre d'OB par fenêtre est attendu** sur 60 bougies H4 : c'est
~10 jours de marché et le détecteur est strict par design (TU#3 exige FVG
+ structure break + N candles minimum).

## Pourquoi cet exercice est critique

Sans alignement préalable du langage OB :

- Si V2 dit *"j'ai détecté 12 OBs"* et Badoun en voyait 8 différents, les
  backtests V2 valident un objet qui n'est pas la stratégie de Badoun.
- Tous les chiffres OOS+friction du dossier (Sharpe 2.22 bull / 1.07 bear)
  reposent sur la définition algorithmique actuelle. Si elle diverge de
  l'intuition Badoun, ces chiffres ne parlent pas de la stratégie de Badoun.

L'exercice consiste donc à mesurer la **convergence** et identifier les
**divergences**, pour qu'on calibre ensuite le détecteur OU qu'on accepte
explicitement la déviation.

## Workflow de Badoun (durant les 10 jours d'absence)

Badoun annote manuellement les **mêmes 3 fenêtres** sur TradingView mobile :
- Gold H4 : 60 bougies se finissant au close du 22 mai
- ETH H4 : idem
- BTC H4 : idem

Format détaillé dans `INSTRUCTIONS_BADOUN.md`.

Pour chaque OB qu'il identifie, il fournit :
- Screenshot avec annotation (cercle/flèche/texte)
- Type (OB+ ou OB-)
- Raison brève (*"FVG net + structure cassée"*, *"poussée de 5 bougies"*, etc.)

Il envoie au fil des jours via Telegram/Cowork, je collecte dans un dossier
`badoun_annotations/`.

## Consolidation au 3 juin

À son retour, je produis un **rapport de comparaison** :

### Métriques
- **Précision V2** = `(OBs V2 confirmés par Badoun) / (OBs total V2)`
- **Recall V2** = `(OBs Badoun retrouvés par V2) / (OBs total Badoun)`
- **F1** = harmonique précision + recall

### Diagnostic des divergences
Pour chaque OB qu'un seul côté a vu :
- Quel paramètre l'aurait fait apparaître/disparaître dans l'autre direction ?
- Hypothèses candidates : `OB_min_candles` trop strict, FVG mal détecté
  (body vs wick), zone definition (open-close vs full range), strength filter
  trop restrictif, ...

### Calibrage proposé
Si la divergence est explicable par un paramètre, on propose un set de
paramètres ajustés et on re-run les backtests OOS+friction sur le nouveau
detector. C'est un GO/NO-GO majeur du protocole méthodologique.

## Reproductibilité

Pour re-générer ce dossier à n'importe quel moment :

```bash
cd ~/Desktop/trading-bot-v2
python3 scripts/build_ob_alignment.py
```

Le script utilise :
- `ccxt.hyperliquid` (Hyperliquid public API — pas de credentials)
- `yfinance` (Yahoo Finance — pas de credentials)
- `strategies/icc_structure.detect_structures` (W=3)
- `strategies/icc_orderblocks.detect_order_blocks` (TU#3 conforme)

---

*Protocole gelé le 22 mai 2026 avant départ de Badoun. Consolidation prévue
3 juin 2026.*
