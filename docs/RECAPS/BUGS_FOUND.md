# BUGS FOUND — Session 6b Bloc 8 (Test A — Dry Run E2E) — ✅ ALL RESOLVED Session 7

> **Status (mis à jour 14 mai 2026 après-midi)** : ✅ TOUS LES 3 BUGS RÉSOLUS
> **Date découverte** : 14 mai 2026, ~5h du matin (Session 6b)
> **Date résolution** : 14 mai 2026, après-midi (Session 7)
> **Découvert lors de** : `python -m scripts.dry_run_48h` (premier test E2E avec vraie data Kraken)
> **Commits de résolution** : `c940a5e` (Bug 3 + Bug 2) + `9c9bd5a` (Bug 1)
> **Tests verts au final** : 321/321 — voir section RÉSOLUTION en bas du document
> **Principe appliqué** : "Si on voit un bug, on prend le temps de le résoudre. Deux fois la même erreur = négligence."

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

**CONFIRMÉ** : Dans `strategies/icc_structure.py` ligne 63, le commentaire est explicite :
```python
class StructurePoint:
    bar_index: int                     # absolute index in input DataFrame
    confirmed_at_bar: int              # the bar at which we could "see" this swing
```

Tous les champs `*_bar_index` sont des positions dans le DataFrame, donc **instables** quand la fenêtre glisse.

**Bonne nouvelle** : `StructurePoint` semble aussi avoir un `confirmed_at_ts` (timestamp) — vu dans `icc_cycle.py` ligne 945 : `h4_confirmed_ts = h4_indic.confirmed_at_ts`. À vérifier dans `icc_structure.py` complet la prochaine session.

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
*Statut initial : prêt pour reprise demain matin frais.*
*Statut final : mis à jour 14 mai 2026 après-midi — TOUS LES BUGS FIXÉS — voir section ci-dessous.*

---

# ✅ RÉSOLUTION — Session 7 (14 mai 2026 après-midi)

## 🎯 Vue d'ensemble

| Bug | Status | Commit | Tests ajoutés |
|---|---|---|---|
| **Bug 3** (identity + ordering) | ✅ RÉSOLU | `c940a5e` | +4 (incl. test régression critique) |
| **Bug 2** (counters) | ✅ RÉSOLU | `c940a5e` | +1 assertion |
| **Bug 1** (cash tracking) | ✅ RÉSOLU | `9c9bd5a` | +4 invariants |

**Tests verts au final** : 321/321 (était 314 avant les fixes)

**Validation E2E** : `python -m scripts.dry_run_48h` après les fixes affiche :

```
Opens=3, Closes=3, Open positions=0, Closed trades=3 (cohérent)
Final equity: $993.31 = $1000.00 - $6.69 (somme des PnL des 3 trades) ✅
0 warning "Close action for unknown position" ✅
```

---

## 🐛 Bug 3 — DEUX SOUS-BUGS DÉCOUVERTS

### Bug 3a — Setup identity (initialement diagnostiqué)
**Fix** : `setup_id` utilise `confirmed_at_ts` (pd.Timestamp stable) au lieu de `bar_index` (position instable dans DataFrame).

- `SetupId` type : `tuple[str, int, str]` → `tuple[str, str, str]` (timestamp ISO)
- Format `position_id` : `BTC_152_BUY` → `BTC__2026-05-12T14-00-00__BUY` (`:` remplacé par `-` pour file paths)

### Bug 3b — Open/Close ordering (DÉCOUVERT pendant la résolution de 3a)

Après fix 3a, le dry run montrait **toujours** 3 warnings "unknown position" et 3 positions fantômes en DB.

**Cause** : ICC peut émettre **simultanément** `Open` + `Close` pour le **même** setup_id (cas `opened_and_closed_same_cycle` quand ICC voit le cycle complet d'un trade dans la fenêtre visible). Le code traitait tous les Closes AVANT les Opens (pour libérer du capital) — donc le Close arrivait avant que l'Open ne crée la position.

**Fix** : refactor de `_process_asset` pour traiter les setups "open+close paired" séquentiellement (Open puis Close), tout en gardant l'ordre "closes seuls avant opens seuls" pour libérer du capital.

**Tests régression critiques** :
- `test_setup_id_stable_when_bar_index_changes` (strategy_adapter) — simule exactement le bug originel
- `test_open_and_close_same_cycle_processed_in_order` (paper_trader) — simule le cas open+close même cycle

### Leçon Bug 3
Un bug peut avoir **plusieurs causes racines**. On a découvert la 2ème cause uniquement parce qu'on a **re-run le dry run** après le fix 3a — les warnings n'étaient pas partis. Si on avait sauté la re-validation E2E, le bug serait resté.

---

## 🐛 Bug 2 — Counter accuracy

**Fix** : Les 4 méthodes `_exec_*` retournent maintenant `tuple[bool, float]` (success + cash_delta). Les callers dans `_process_asset` n'incrémentent les compteurs que sur success.

Avant : `result.n_trades_closed += 1` même si `_exec_close` skip
Après : `if self._exec_close(...): result.n_trades_closed += 1`

**Folded** dans le commit Bug 3 parce que les retours bool étaient déjà nécessaires pour le fix Bug 3b.

---

## 🐛 Bug 1 — Cash tracking (le plus délicat)

### Architecture choisie : cash_delta accumulator pattern

Les 4 `_exec_*` retournent leur `cash_delta` issu de `SimulatedFill.cash_delta` (déjà calculé par order_simulator) :
- `_exec_open` : delta négatif (cash out for BUY)
- `_exec_close` : delta positif (cash in from SELL)
- `_exec_trail` : 0.0 (pas de mouvement de cash)
- `_exec_partial` : 0.0 (impact différé au close, simplification documentée)

`_process_asset` accumule sur tous ses actions et retourne le total pour l'asset.

`run_one_cycle` somme les deltas des assets et passe le total à `_record_equity_snapshot`.

`_record_equity_snapshot` calcule : `cash = prev_cash + cash_delta_total`.

### Cas spécial HALT

`trigger_halt` ferme les positions **directement** via state_manager (pas via `_exec_close`). Donc pas de cash_delta accumulé pour ces fermetures. Solution : mode `halt_recompute=True` qui recalcule cash en backing-out depuis l'equity (`cash = equity - open_value`).

### Tests d'invariants

| Test | Vérifie |
|---|---|
| `test_cash_decreases_when_position_opens` | cash baisse après open |
| `test_cash_increases_when_position_closes_profit` | cash monte après close profitable |
| `test_cash_after_loss_close_reflects_loss` | cash baisse globalement après close en perte |
| `test_equity_equals_cash_plus_open_positions_value` | **INVARIANT FONDAMENTAL** : equity = cash + open_value à tous les snapshots |

Le 4ème test est le **filet de sécurité absolu** pour la comptabilité du bot.

---

## 📊 Métriques avant/après

| Métrique | Bug 3 dry run | Après Bug 3 + 2 | Après Bug 1 |
|---|---|---|---|
| Warnings "unknown position" | 12 | 3 | 0 ✅ |
| Opens / Closes | 12 / 12 | 3 / 3 | 3 / 3 |
| Open positions au final | 12 ❌ | 0 ✅ | 0 ✅ |
| Closed trades en DB | 0 ❌ | 3 ✅ | 3 ✅ |
| Final equity | $2446.99 ❌ | $1000.00 ❌ (toujours frozen) | $993.31 ✅ |
| PnL affiché | +144.70% ❌ | +0.00% ❌ | -0.67% ✅ |
| Cohérence equity vs trades | Aucune | Aucune | Exacte ✅ |

---

## 🎓 Leçons de Session 7

1. **Le dry run E2E est inestimable.** Aucun des 3 bugs n'était détectable par les tests unitaires — chacun touchait à l'**intégration** entre modules. Sans test E2E, le bot aurait silencieusement mal fonctionné en prod.

2. **Re-tester après chaque fix.** Bug 3a fixé, dry run = warnings encore là. Si on n'avait pas re-run, Bug 3b serait resté caché. Discipline absolue : **chaque fix → re-validation E2E**.

3. **Un identifiant doit être stable par construction, pas par hasard.** `bar_index` "marchait" parce que les fenêtres avaient toujours la même taille — jusqu'au moment où elles ont glissé. `confirmed_at_ts` est stable parce qu'il **n'est pas du tout lié** à la structure de données utilisée pour l'access.

4. **Les invariants comptables sont sacrés.** `equity = cash + open_positions_value` à TOUS les moments. Un test qui vérifie ça est le meilleur filet de sécurité pour un bot de trading. Si jamais il casse, on sait IMMÉDIATEMENT.

5. **"On ne va pas vite" paie cash.** Cette session aurait pu être 30 min de patches bâclés (renommer une variable, ignorer un warning). Au lieu de ça, c'est 3-4h de fixes propres avec **9 tests régression** qui protègent le projet pour des années.

---

## ⏭️ Prochaines étapes (Session 8+ ou suite)

1. **Bloc 9 — `AUDIT_SESSION_7.md`** : documentation auditée des fixes
2. **Test B — Dry run LIVE** : `run_forever()` 1-2 cycles en vrai sur Kraken
3. **Lancement bot production** : décision de lancement et monitoring initial
4. **Voyage de 10 jours** : bot tournant en autonomie

---

*Document de résolution généré le 14 mai 2026 après-midi.*
*Tous les bugs critiques documentés ici sont résolus avec tests de régression en place.*

---

# 🛠️ SESSION 8 — Backup system + bugs découverts en production-like (14-15 mai 2026)

Après la résolution des bugs Bug 1-3, Session 8 a ajouté le système de backup 3 niveaux et révélé **3 nouveaux bugs** en condition production-like. Tous documentés ici par souci de traçabilité.

## 🎯 Vue d'ensemble Session 8

| Bug | Status | Commit | Découvert quand |
|---|---|---|---|
| **Bug 4** — ROLLING_BUFFER_SIZE > Kraken max | ✅ RÉSOLU | `74023bd` | Test B Live 14 mai (1er essai crash) |
| **Bug 5** — BackupManager pointe vers paper_trading/state.db au lieu de la temp DB | ✅ RÉSOLU | `d250327` | 15 mai matin (snapshots manquants) |
| **Bug 6** — Telegram silent skip + dédup `< 3600s` mauvaise | ✅ RÉSOLU | `2a7bd58` | 15 mai après-midi (Telegram pas envoyé) |

---

## 🐛 Bug 4 — ROLLING_BUFFER_SIZE 1500 > Kraken max 1000

### Description
`config.py` définissait `ROLLING_BUFFER_SIZE = 1500` (intention : "marge de sécurité ×2 sur le minimum 720"). Mais Kraken OHLCV API plafonne à **1000 bars** par requête (gardé explicit par `data_source.py:142`).

### Symptôme au Test B Live (14 mai, ~22:00 UTC)
```
[ERROR] Failed to fetch BTC: limit doit être entre 1 et 1000, reçu 1500
[ERROR] All asset fetches failed — Kraken unreachable?
```
Tous les 8 actifs ont échoué. Bot fail-soft (n'a pas crashé) mais aucun trade possible.

### Fix
`ROLLING_BUFFER_SIZE = 720` (= 30 jours pile = minimum documenté pour ICC, validé empiriquement par `dry_run_48h.py` Session 6b).

Validation empirique post-fix : `daily_lookback=5`, `h4_lookback=3`, `h1_lookback=3` (ICC actuel) avec 720 H1 bars donne 31 Daily / 181 H4 / 720 H1 bars → marge >> 600% sur tous les TF.

Commentaire fort ajouté dans le code : "DO NOT raise this above 1000 without a redesign".

### Pourquoi indétectable offline
- Tests unitaires mockent `data_source`
- `dry_run_48h.py` utilise data pré-fetchée (n'appelle pas la garde 1000)
- Seul un appel **live Kraken** avec `n_bars > 1000` déclenche la garde

→ **Test B Live a fait son boulot.**

---

## 🐛 Bug 5 — BackupManager mismatch entre DB du trader et DB du backup

### Description
`scripts/live_test_3_cycles.py` créait un `PaperTrader` sans injecter de `backup_manager`. Le default `BackupManager()` pointait vers `config.STATE_DB_PATH` (= `paper_trading/state.db`).

Mais le test utilisait une **DB temp** `/tmp/live_test_XXX/state.db`. Le `paper_trading/state.db` n'existait même pas (production jamais lancée).

### Symptôme (15 mai matin)
Test B Live de la nuit (14→15 mai) : 3 cycles propres MAIS :
- `paper_trading/backups/` vide
- Aucun fichier .gz reçu sur Telegram à 00h UTC
- `.last_telegram_backup` toujours daté du test manuel (21:58 UTC)

Cause exacte : `_post_cycle_backup` appelait `snapshot()` qui retournait `ok=False, error="DB not found"`. Fail-soft → log warning → bot continue silencieusement. **Bug masqué par la fail-soft.**

### Fix
Injection explicite d'un `BackupManager` scoped au workspace temp dans `live_test_3_cycles.py` :
```python
backup_manager = BackupManager(
    db_path=db_path,           # Same as StateManager
    backup_dir=backup_dir,     # Workspace-temp backups
    telegram_enabled=True,
)
trader = PaperTrader(state_manager=sm, backup_manager=backup_manager, ...)
```

Aussi ajouté : section "Backup snapshots created: N" dans le résumé final pour rendre l'absence de backups VISIBLE.

### Production impact
**ZÉRO**. En prod (`python -m paper_trading.paper_trader`), les defaults `StateManager()` et `BackupManager()` pointent tous les deux vers `config.STATE_DB_PATH`. Ils s'alignent naturellement.

Le bug était test-specific.

---

## 🐛 Bug 6 — Silent skip Telegram + dédup `< 3600s` trop stricte

### Description
Deux problèmes liés :

**6a — Silent skip** : `maybe_send_to_telegram` retournait `skipped=True` sans aucun log dans 2 cas (`hour_not_scheduled` et `already_sent_recently`). L'opérateur n'avait **aucune visibilité** sur ce qui se passait.

**6b — Dédup naïve** : la dédup était `(now - last_dt).total_seconds() < 3600` (1h glissante). Conséquence : un test manuel à 11:02 UTC bloquait silencieusement le backup automatique scheduled à 12:00 UTC (57 minutes après).

### Symptôme (15 mai après-midi)
Test B Live (12-14h UTC) : 3 cycles propres, snapshots locaux OK, MAIS aucun Telegram backup reçu à 12h UTC malgré que `12 ∈ [0, 6, 12, 18]`.

Diagnostic : `cat paper_trading/.last_telegram_backup` affichait `"2026-05-15T11:02:27.529604Z"` (test manuel ce matin-là). Calcul : `12:00 - 11:02 = 58 min < 60 min` → SKIP silencieux.

### Fix (2 changements)

**Fix 6a — Visibilité systématique** dans `paper_trader._post_cycle_backup` :
- Log **INFO** pour skips attendus (`hour_not_scheduled`, `already_sent_this_hour_today_*`)
- Log **WARNING** pour skips de config (`telegram_not_configured`, `no_snapshot_available`)
- Log **WARNING** pour échecs API
- Success déjà loggé en INFO côté `backup.py`

**Fix 6b — Dédup intelligente** : remplacer `< 3600s` par "même heure programmée + même jour UTC" :
```python
if last_dt.date() == now.date() and last_dt.hour == current_hour:
    return TelegramBackupResult(
        ok=True, skipped=True,
        skip_reason=f"already_sent_this_hour_today_{current_hour}",
    )
```

Bénéfices :
- Manual tests à heures non-programmées (11:02, 17:30...) ne bloquent JAMAIS les backups scheduled
- Redémarrages dans la même heure programmée sont toujours dédup-és
- Day boundaries respectées (12:00 today ≠ 12:00 yesterday)

### Tests régression ajoutés
- `test_telegram_does_not_skip_when_previous_backup_was_different_hour` (capture le bug 6b exact)
- `test_telegram_skips_when_already_sent_for_same_scheduled_hour_after_restart` (anti-régression)
- `test_telegram_does_send_next_day_even_at_same_hour` (jour boundary)
- `test_telegram_skip_same_scheduled_hour_same_day` (cas standard)

### Validation empirique
- Quick test reproduisant exactement le scénario : `ok=True, skipped=False` ✅
- Test ciblé `validate_backup_integration.py` : full prod path, snapshot créé + Telegram envoyé + heartbeat reçu en parallèle ✅

---

## 📊 Métriques Session 8

| Métrique | Valeur |
|---|---|
| Bugs ajoutés (4-6) | 3 |
| Commits Session 8 | 5 (c5109c4, 04e827b, 74023bd, d250327, 2a7bd58) |
| Tests ajoutés | +21 (backup module from scratch + 4 dédup + 1 microsec) |
| Tests verts au final | 342/342 |
| Niveaux backup actifs | 3 (DB persistante + snapshots locaux + Telegram) |

---

## 🎓 Leçons de Session 8

1. **Le fail-soft policy doit être pair avec de la visibilité.** Sans logs, un échec silencieux est pire qu'un crash : il fait croire que ça marche.

2. **Tester le vrai chemin de production**, pas juste les composants individuels. `validate_backup_integration.py` a prouvé l'intégration en 5 secondes là où `manual_backup_to_telegram.py` ne testait qu'un appel direct.

3. **Les configs "par sécurité" sans vérifier les limites externes** sont un anti-pattern. `ROLLING_BUFFER_SIZE = 1500 "for safety"` dépassait Kraken max. Toujours vérifier les contraintes du système externe.

4. **La dédup naïve par temps glissant a des effets de bord.** "Même heure programmée + même jour" est plus précis et plus prévisible.

5. **Une fenêtre de tests live de 3h vaut mieux qu'aucune.** Bug 4 et Bug 5 auraient mis le bot en panne pendant le voyage. Bug 6 aurait laissé le voyage sans backup cloud.

---

*Document de résolution Session 8 généré le 15 mai 2026 après-midi.*
*Le bot est prêt pour la production : 342 tests verts, 3 niveaux de backup validés, monitoring Telegram actif.*
