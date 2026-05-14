# BUGS FOUND — Session 6b Bloc 8 (Test A — Dry Run E2E)

> **Date** : 14 mai 2026, ~5h du matin
> **Découvert lors de** : `python -m scripts.dry_run_48h` (premier test E2E avec vraie data Kraken)
> **Statut commit projet** : `abd9097` (dry_run_48h.py script) — `git status` clean
> **Tests verts** : 314/314 sur unitaires (Bloc 7 commité), mais E2E révèle des bugs d'intégration
> **Principe à appliquer** : "Si on voit un bug, on prend le temps de le résoudre. Deux fois la même erreur = négligence."

---

## 📋 SOMMAIRE EXÉCUTIF

Le dry run de 48 cycles a tourné sans crash (0 erreurs, 0 HALT), MAIS le résumé final montre :

```
Opens          : 12       ← positions ouvertes
Closes         : 12       ← mais...
Open positions : 12       ← TOUJOURS 12 ouvertes
Closed trades  : 0        ← aucun trade fermé !
Final equity   : $2446.99
PnL            : +$1446.99 (+144.70%)  ← IMPOSSIBLE en 48h avec ICC
```

**3 bugs identifiés**, dont 2 critiques et liés entre eux.

---

## 🐛 BUG #3 — Setup_id instable entre cycles (CRITIQUE — PRIORITÉ 1)

### Description

Le `setup_id` utilisé pour identifier un trade dans le strategy_adapter est :
```python
SetupId = tuple[str, int, str]  # (asset, h4_indication.bar_index, direction)
```

Mais `h4_indication.bar_index` est un **index de POSITION** dans le DataFrame H4, pas un identifiant stable basé sur le temps.

### Preuve

Dans `strategies/icc_cycle.py`, on accède aux barres par position :
```python
ligne 628:    bar = h4_prices.iloc[candidate.bar_index]
ligne 796:    bar = h4_prices.iloc[s.bar_index]
ligne 922:    obs_by_struct_bar = {ob.structure_broken.bar_index: ob ...}
```

### Conséquence

- **Cycle T** : DataFrame H4 a 168 bars (672 H1 ÷ 4). Une structure est à `bar_index = 152`.
- **Cycle T+1** : 1 nouvelle bougie H1 entre dans la fenêtre, 1 ancienne sort. Le DataFrame H4 a toujours ~168 bars MAIS potentiellement décalées d'1 position vers la gauche.
- Une même structure réelle (par exemple, le high du 12 mai 14h UTC) a maintenant `bar_index = 151`.
- → `setup_id = ("BTC", 152, "BUY")` au cycle T devient `setup_id = ("BTC", 151, "BUY")` au cycle T+1.
- → Pour l'adapter, c'est un **nouveau setup** → emet un Open. Mais la position était déjà ouverte sous l'ancien id.

### Logs warning observés

```
Close action for unknown position BTC_152_BUY — skipping
Close action for unknown position BTC_159_BUY — skipping
Close action for unknown position AVAX_158_BUY — skipping
[...]
```

→ Le code essaie de fermer des positions qui n'existent pas (parce qu'elles ont été créées sous des bar_indexes différents au cycle précédent).

### Solution proposée

Remplacer `h4_indication.bar_index` par un identifiant **stable basé sur le temps** :

```python
# AVANT
def setup_id(setup: TradeSetup) -> SetupId:
    return (setup.asset, setup.h4_indication.bar_index, setup.direction.value)

# APRÈS
def setup_id(setup: TradeSetup) -> SetupId:
    # Use the confirmed_at_ts of the H4 indication — stable across cycles
    ts = setup.h4_indication.confirmed_at_ts
    ts_str = pd.Timestamp(ts).isoformat() if ts else "unknown"
    return (setup.asset, ts_str, setup.direction.value)
```

**À vérifier avant de coder** :
- Que `StructurePoint.confirmed_at_ts` existe et est rempli (lu dans `sed -n '871,930p' strategies/icc_cycle.py` : `h4_confirmed_ts = h4_indic.confirmed_at_ts`).
- Que c'est bien le timestamp final/confirmé (pas un timestamp provisoire qui change).

### Tests à mettre à jour

Tous les tests de `test_strategy_adapter.py` qui utilisent `_fake_h4_indication(bar_index=...)` :
- Modifier `FakeStructurePoint` pour avoir un `confirmed_at_ts` réaliste
- Adapter `test_setup_id_is_tuple` pour vérifier le nouveau format

### Estimation

**1h30-2h** : modifier le setup_id, retester les 28 tests adapter, re-run dry run pour confirmer.

---

## 🐛 BUG #1 — Cash never updated in equity snapshots (CRITIQUE — PRIORITÉ 2)

### Description

Dans `paper_trading/paper_trader.py`, méthode `_record_equity_snapshot()` :

```python
# Get cash from previous snapshot, then adjust by transactions of THIS cycle
latest = self.sm.get_latest_equity_snapshot()
if latest is None:
    cash = config.INITIAL_CAPITAL
else:
    cash = latest.cash  # ← BUG : on prend juste l'ancien cash, jamais modifié
    # (TODO: precise cash tracking via order_simulator deltas)
```

Le `cash` est **figé** à `INITIAL_CAPITAL` après le premier cycle. Quand on ouvre une position et qu'on dépense $125, le cash en DB reste à $1000.

### Conséquence

- Bot ouvre 12 positions, chacune coûte ~$125 → devrait avoir dépensé $1500
- Mais cash reste à $1000 + valeur mark-to-market des positions ≈ $1500
- → Equity affichée = $1000 + $1500 = $2500 (au lieu de $0 + $1500 = $1500)
- → PnL fictif de +$1500 = +144% en 48h

### Solution proposée

**Option A — Tracker cash via les cash_deltas des fills (recommandé)** :
- Dans chaque `_exec_open` / `_exec_close` / `_exec_partial`, accumuler le delta cash de la transaction
- Passer ce delta au `_record_equity_snapshot()`
- Cash final = cash début cycle + somme des deltas

**Option B — Recalculer cash from scratch chaque cycle** :
- cash = INITIAL_CAPITAL - somme(open_positions.initial_capital_used) + somme(closed_trades.pnl_dollars + closed_trades.initial_capital_used)
- Plus simple à raisonner mais plus coûteux

**Recommandation** : Option A. C'est l'approche standard et c'est testable.

### Tests à ajouter

1. `test_cash_decreases_when_position_opens` — invariant
2. `test_cash_increases_when_position_closes_at_profit`
3. `test_equity_equals_cash_plus_open_value` — invariant fondamental
4. `test_cash_after_halt_correct` — cas limite

### Estimation

**1h30** : design + implémentation + 4 tests + re-test dry run.

---

## 🐛 BUG #2 — Compteur n_trades_closed incrémenté même si skip (MINEUR)

### Description

Dans `paper_trading/paper_trader.py`, méthode `_process_asset()` :

```python
for a in closes:
    self._exec_close(a, timestamp_iso)
    result.n_trades_closed += 1   # ← incrémenté même si _exec_close a skip
```

Quand `_exec_close` rencontre une position inconnue (cf Bug 3), elle log un warning ET return None, **mais le compteur s'incrémente quand même**.

### Conséquence

Le résumé affiche "12 closes" alors qu'**aucun** close réel n'a eu lieu (les 12 trades restent ouverts en DB).

### Solution

Modifier `_exec_close` pour retourner `bool` :
```python
def _exec_close(self, a, ts) -> bool:
    pos = self.sm.get_open_position(...)
    if pos is None:
        return False  # skipped
    # ... do the close ...
    return True
```

Et dans `_process_asset` :
```python
for a in closes:
    if self._exec_close(a, timestamp_iso):
        result.n_trades_closed += 1
    else:
        result.n_trades_skipped += 1  # ou n_closes_skipped si on veut différencier
```

Idem pour `_exec_trail` et `_exec_partial`.

### Tests à mettre à jour

- `test_close_action_unknown_position_skipped` doit aussi vérifier que `result.n_trades_closed == 0`.

### Estimation

**15 min** : modifier les 3 méthodes _exec_*, ajuster les tests, refaire.

---

## 🔄 SÉQUENCE DE FIX RECOMMANDÉE

Vu les dépendances entre les bugs :

### Étape 1 — Bug 3 (setup_id stable) — 1h30-2h
- Sans setup_id stable, impossible de tracker correctement les positions
- Doit être fait EN PREMIER

### Étape 2 — Bug 1 (cash tracking) — 1h30
- Dépend de Bug 3 (positions correctement trackées)
- Architecture : accumulateur de cash_delta par cycle

### Étape 3 — Bug 2 (compteur) — 15 min
- Indépendant, peut être fait avant ou après
- Préfère le faire en passant pendant Étape 2

### Étape 4 — Re-run dry_run_48h.py — 5 min
- Validation finale : doit montrer Opens > 0, Closes > 0, Open positions au final < Opens (sauf si toutes encore en cours), equity raisonnable

### Total estimé : 3h-3h30

---

## ✅ CRITÈRES D'ACCEPTATION POUR CONSIDÉRER LES 3 BUGS RÉSOLUS

Après les fixes, le dry_run_48h.py doit afficher :

1. **`Opens` cohérent** : nombre raisonnable (10-30 pour 48h sur 8 cryptos)
2. **`Closes` cohérent** : devrait être proche de `Opens` (la plupart des trades se ferment dans la fenêtre, peut-être quelques uns restent ouverts)
3. **`Open positions = Opens - Closes`** au final (invariant comptable)
4. **`Final equity` réaliste** : entre $700 et $1300 typiquement. Plus jamais de +144%.
5. **`Drawdown` cohérent** avec le PnL
6. **Aucun warning `Close action for unknown position`** dans les logs

---

## 📂 ÉTAT DU PROJET AU MOMENT DE LA DÉCOUVERTE

### Commits récents
```
abd9097 (HEAD -> main) Session 6 Bloc 8 - dry_run_48h.py script (E2E test on real Kraken data)
b97b276 Session 6 Bloc 7 Etape 3 - paper trader orchestrator
40089eb Session 6 Bloc 7 Etape 2 - multi-TF data prep for ICC
eb0ee4f Session 6 Bloc 7 Etape 1 - ICC strategy adapter with delta detection
d9fdad0 Session 6 Bloc 6 - monitoring (JSON Lines + Telegram, fail-soft)
3f41cf7 chore: pin dependencies + add SESSION_6a_RECAP
897fe37 Session 6 Bloc 5 - stop manager (DD + Daily loss safeguards)
```

### Tests
- 314 tests offline passent (Bloc 7 complet en tests unitaires)
- Bug d'intégration trouvé par dry run E2E (couverture qui manquait)

### Backup
- ZIP créé sur Lexar : `trading-bot-v2_session6b_bloc7_20260514_0519.zip` (1.7 Mo)
- ⚠️ Le ZIP contient `.env` (à exclure aux prochains backups)

### Working tree
- `git status` propre
- Aucune modification non commitée

---

## 🎯 CE QUE LE PROCHAIN CLAUDE DOIT FAIRE

Quand Badoun reviendra (probablement le 14 mai après-midi ou le 15 mai au matin), il copiera-collera ceci :

> *"Salut Claude, je reprends `/Users/mindcompletionbody/Desktop/trading-bot-v2/` après pause.
> J'ai fait Session 6b hier soir (Bloc 6 + Bloc 7, 314 tests verts).
> Le dry run E2E a révélé 3 bugs critiques documentés dans `BUGS_FOUND.md`.
> Je veux qu'on les fixe dans l'ordre proposé (Bug 3 → Bug 1 → Bug 2).
> Important : on ne va pas vite. Si tu vois quelque chose qui ne va pas, on creuse."*

### Le prochain Claude doit :

1. **LIRE** `BUGS_FOUND.md` en entier
2. **NE PAS** présumer la solution — vérifier dans le code que les hypothèses tiennent (en particulier que `confirmed_at_ts` existe sur `StructurePoint`)
3. **Pour chaque fix** : design → tests → implémentation → vérif → commit
4. **Re-run dry_run_48h.py** entre chaque fix pour confirmer

---

## 💭 LEÇONS À RETENIR

1. **Le dry run E2E a fait son boulot.** 314 tests unitaires passaient, mais l'intégration vraie a révélé 3 bugs invisibles autrement. Ne JAMAIS faire confiance aux tests unitaires seuls pour un système intégré.

2. **+144% en 48h = signal d'alarme**, pas de succès. Si jamais le bot affiche un résultat extraordinaire, c'est presque toujours un bug, pas une victoire.

3. **L'identifiant d'entité doit être stable.** Position dans un DataFrame ≠ identité. Le timestamp est plus fiable.

4. **Les compteurs doivent refléter la réalité.** Un counter qui s'incrémente même quand l'action skip = rapport menteur.

5. **On ne fixe pas dans la fatigue.** Cette session a duré ~4h, le découverte des bugs s'est faite après. Le bon choix : documenter et reprendre frais.

---

*Document généré le 14 mai 2026, ~5h15 du matin, après ~4h de session productive.*
*Statut : prêt pour reprise demain matin frais.*
