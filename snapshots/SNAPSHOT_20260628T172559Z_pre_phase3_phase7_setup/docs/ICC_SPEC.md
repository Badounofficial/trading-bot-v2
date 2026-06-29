# ICC SPECIFICATION — Référence condensée

> Résumé de la spec ICC complète (issue de `Strategie_ICC_Complete.docx`
> + 5 PDFs Tests Unitaires).
>
> **C'est LE document de référence** quand on code. Tout code ICC doit être
> aligné ligne par ligne avec ce qui suit. Pas de rafistolage.

---

## Origine et statistiques

- **Créateur** : TradesSAI (YouTube)
- **Stats vérifiées** : $20.8M PnL, PF 3.36, WR 88% (Jan-Mar 2026, Gold only)
- **Régle d'or** : Ne jamais trader le breakout. Toujours attendre correction + HL/LH.
- **Markets recommandés par TradesSAI** : XAUUSD (Gold), NAS100, US30, EURUSD

---

## Les 5 Tests Unitaires (foundation)

### TU#1 — La Bougie

**Règle absolue** : Body close only.

- Bougie haussière = Close > Open (acheteurs gagnent)
- Bougie baissière = Close < Open (vendeurs gagnent)
- Méche = liquidité (faux mouvements, stop hunts), **PAS** une cassure structurelle
- Une cassure de zone n'est valide QUE si Body close au-delà du niveau
- Jamais entrer sur une bougie en cours — attendre la clôture

### TU#2 — La Structure de Marché

**Pivot = origine de l'impulsion** (PAS un pivot mathématique).

C'est la première bougie (son close le plus extrême) qui a lancé le mouvement ayant cassé une zone.

**Les 4 types** :
- **HH** (Higher High) : prix monte ET casse high précédent (body close)
- **HL** (Higher Low) : prix descend SANS casser low précédent, puis remonte au-dessus du high précédent
- **LH** (Lower High) : prix monte SANS casser high précédent, puis redescend en dessous du low précédent
- **LL** (Lower Low) : prix descend ET casse low précédent (body close)

**Règles d'or séquence** (LOIS) :
- Si HL → DOIT faire HH (sinon = signal reversal)
- Si HH → DOIT faire HL (sinon = signal reversal)
- Si LH → DOIT faire LL (sinon = signal reversal)
- Si LL → DOIT faire LH (sinon = signal reversal)

**New High / New Low ≠ HH/LL** :
- Marché bearish (LH+LL) casse un LH par body close → **NEW HIGH** (pas HH)
- Marché bullish (HH+HL) casse un HL par body close → **NEW LOW** (pas LL)
- Devient HH/LL UNIQUEMENT quand le marché reproduit dans la nouvelle direction
- **New High/Low = CHoCH (Change of Character) = INDICATION**

**Structures cassées vs actives** :
- Une structure cassée (body close au-delà) ne compte plus
- Maintenir actives vs cassées en mémoire
- Seules les actives proches du prix actuel sont pertinentes

### TU#3 — Order Blocks

**OB- (bearish)** = dernière bougie HAUSSIERE avant grand mouvement BAISSIER
**OB+ (bullish)** = dernière bougie BAISSIERE avant grand mouvement HAUSSIER

Zone OB = du OPEN au CLOSE de la bougie OB (**body only**, pas les meches).

**Validation OB (seuils)** :
- 3 bougies consécutives même sens + FVG = VALIDE
- 5 bougies consécutives même sens SANS FVG = VALIDE
- < 3 bougies = INVALIDE (même avec FVG)
- 1 grosse bougie englobe 5+ précédentes = VALIDE

**Hiérarchie de force** :
- **VERY_STRONG** : FVG + casse ancienne structure + min 3 bougies
- **STRONG** : (FVG + 3 bougies) OU (cassure structure + 5+ bougies)
- **MODERATE** : 5+ bougies sans FVG ni cassure
- **WEAK** : <3 bougies ou 3-4 sans FVG = INVALIDE

**FVG (Fair Value Gap)** :
- Bullish : Low de la bougie 3 > High de la bougie 1 = gap vers le haut
- Bearish : High de la bougie 3 < Low de la bougie 1 = gap vers le bas

**Usage UNIQUE** : un OB consommé (testé ou cassé) ne revient jamais dans la liste.

**Tendance vs contre-tendance** :
- OB dans le sens de la tendance H4 = PUISSANT
- OB contre la tendance H4 = FRAGILE (à éviter en swing)

**Discount / Premium** :
- Range = entre HIGH actif et LOW actif
- 50% = équilibre
- Zone PREMIUM (au-dessus de 50%) = pour chercher OB- (vendre)
- Zone DISCOUNT (sous 50%) = pour chercher OB+ (acheter)

### TU#4 — L'Indication ICC (Impulse-Correction-Continuation)

**3 phases** :

1. **INDICATION** (phase I = CHoCH) — INFORMATION, **PAS** entrée
   - Cassure d'une zone de structure (body close au-delà)
   - Création d'un OB valide (cassure structure = displacement)
   - CHoCH : marché crée NEW HIGH ou NEW LOW (premier point opposé)

2. **CORRECTION** (phase C1) — ATTENTE, **PAS** entrée
   - Le prix retrace vers la zone d'impulsion (l'OB)
   - Pendant la correction, on observe la structure micro
   - Le low de l'impulse ne devient HL que QUAND le prix aura cassé le New High
   - Tant que la structure de l'indication n'est pas reproduite : **No Trade Zone**

3. **CONTINUATION** (phase C2) — **ENTRÉE**
   - Le marché REPREND dans le sens de l'indication
   - Body close H1 au-delà du LH (buy) ou HL (sell) = NEW HIGH/LOW = ENTRÉE
   - La structure entry_TF (M5/M15) doit être ALIGNÉE avec H4

**Flow multi-TF en cascade** :
- **DAILY** : le biais (HH+HL = BUY, LH+LL = SELL). Jamais trader contre.
- **H4** : l'indication (CHoCH = New High/Low + OB valide). Aligné avec Daily.
- **H1** : l'entrée (body close au-delà du LH/HL après correction).

**Checklist avant entrée** :
- [ ] Daily aligné dans la bonne direction
- [ ] H4 indication validée (cassure structure + OB + New High/Low)
- [ ] H1 correction terminée (prix revenu vers l'OB)
- [ ] H1 body close au-delà du LH (buy) ou HL (sell)

**Ce qui annule un setup** :
- Prix casse l'OB de l'indication
- H4 cree un New High/Low OPPOSÉ
- Daily change de tendance
- Correction dépasse 100% de l'impulse
- Pas de cassure du LH/HL sur H1 après correction
- Marché reste en No Trade Zone

### TU#5 — Mise en pratique

(Exemples visuels — pas de nouvelle règle, application des TU#1-4)

---

## Money Management

### Stop Loss
- **Position initiale** : sous le PREVIOUS HL (BUY) ou au-dessus du PREVIOUS LH (SELL) — l'**avant-dernier**
- **Bouge à la CONTINUATION** (2ème cassure), jamais à l'indication
- **Trailing structurel** : suit les HL/LH suivants

### Take Profit
- **Scalping** : RR 1:2 fixe (ou OB opposé TF supérieure pour correction trades)
- **Intraday** : pivot structurel H4 ou measured move
- **Swing** : prochain OB H4 ou swing high/low de la grande TF

### Pas de Break-Even
TradesSAI : "I don't go break-even. If I went BE, I would have been stopped out TWICE."

### Partial Close 85%
- Au TP : fermer 85%, garder 15% risk-free
- Les 15% courent avec trailing SL structurel
- Tant que la structure tient = on reste

### Measured Move (TP par défaut)
Si pas d'OB : TP = prix d'entrée + distance(indication).

---

## Modes de trading (TFs)

| Mode | Ref | Confirm | Entry | Hold |
|---|---|---|---|---|
| **SWING** (Badoun, trading réel) | H4 | H1 | M15 | Jours/semaines |
| **INTRADAY** (post-cassure H4) | H4 | H1 | M5 | Heures |
| **SCALPING** (le plus adapté au bot) | H4 (infor) | M15 ou H1 | M1 | Minutes |

---

## Dynamique des sessions

### Kill Zones
- 8:00 AM ET : ouverture London
- 9:30 AM ET : ouverture NY (2ème vague institutionnelle)
- **Displacement pendant ces heures = présence institutionnelle**

### Pattern inter-sessions
- **Asie** : crée un range (high/low)
- **UK** : touche le high ou le low d'Asie
- **NY** : va chercher l'opposé de ce que UK a touché

### Tendance intra-session
- Une fois que NY lance sa tendance, toute la session suit
- **Privilégier setups NY 8am-11am ET**

---

## Erreurs FATALES à éviter (pour le bot)

1. Trader le breakout sans attendre le pullback
2. Utiliser les meches comme cassures (toujours body close)
3. Prédire le marché au lieu de s'adapter
4. Utiliser pivots mathématiques au lieu de l'origine réelle
5. Comparer deux pivots sans la séquence complète
6. Entrer sur bougie en cours ou bougie opposée
7. Break-Even pendant correction normale
8. Ignorer l'alignement multi-TF
9. Considérer HH/LL au premier break (c'est New High/Low)

---

## Ce que le code DOIT gérer

1. **Jamais anticiper** — seulement réagir aux body closes
2. **Maintenir l'état des structures** (actives vs cassées)
3. **Détecter les structures intermédiaires** H1 dans les pivots H4
4. **Vérifier alignement multi-TF** AVANT chaque entrée
5. **Différencier New High/Low vs HH/LL**
6. **OB usage unique** avec force scoring

---

## Citations clés de TradesSAI

- "Stop overcomplicating it. Swing break + volume = entry. That's it."
- "I don't predict the markets. I just follow what price is doing."
- "Focus on PRECISION, not money. Better entries = bigger lot sizes."
- "Consistency > Profitability."
- "Every price movement is NOT tradable — wait for setups."
- "Higher the timeframe, stronger the rules apply."
- "I don't go break-even. If I went BE, I would have been stopped out TWICE."

---

## Statut d'implémentation

| Composant | TU concerné | Status | Fichier |
|---|---|---|---|
| Bougie + Body close | TU#1 | ✅ Done | `icc_structure.py` |
| Swing detection | TU#2 (partie) | ✅ Done | `icc_structure.py` |
| HH/HL/LH/LL classif | TU#2 | ✅ Done | `icc_structure.py` |
| New High/Low (CHoCH) | TU#2 | ✅ Done | `icc_structure.py` |
| Active vs broken | TU#2 | ✅ Done | `icc_structure.py` |
| Order Blocks | TU#3 | 🔨 Session 3 | `icc_orderblocks.py` |
| FVG detection | TU#3 | 🔨 Session 3 | `icc_orderblocks.py` |
| Force scoring | TU#3 | 🔨 Session 3 | `icc_orderblocks.py` |
| Discount/Premium | TU#3 | 🔨 Session 3 | `icc_orderblocks.py` |
| Multi-TF cascade | TU#4 | 🔨 Session 4 | `icc_cycle.py` |
| Indication detection | TU#4 | 🔨 Session 4 | `icc_cycle.py` |
| Correction tracking | TU#4 | 🔨 Session 4 | `icc_cycle.py` |
| Continuation entry | TU#4 | 🔨 Session 4 | `icc_cycle.py` |
| Money management | doc complet | 🔨 Session 4 | `icc_cycle.py` |
| Walk-forward | n/a | 🔨 Session 5 | `walkforward_icc.py` |

---

*Référence cristallisée. Toute modif doit être validée contre ce document.*

*Dernière maj : 10 Mai 2026*
