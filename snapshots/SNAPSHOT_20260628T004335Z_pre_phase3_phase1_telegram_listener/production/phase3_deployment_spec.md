# Trading Bot V2 — Phase 3 Deployment Spec (v2 — operator-validated)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-27 01:30 UTC
**Version** : v2 (revised after Sebastien validation of operator decisions Phase 3 marathon plan)
**Previous version** : v1 preserved in `snapshots/SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`

**Purpose** : spec finale du déploiement Phase 3 (BTC+ETH always-in delta-neutre, $1k×2 sizing, marathon 365 jours, 7 safeguards A-G mandatory). **Aucun code production modifié dans cette session — ce document est une spec à valider par Sebastien avant tout merge.**

**Discipline** :
- Branch dédiée : `production/phase3-always-in-btc-eth-deployment` ✓
- Pre-snapshot : `SNAPSHOT_20260627T004802Z_pre_phase3_implementation_baseline/` ✓
- Production main HEAD : `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT** ✓
- Append-only sur ce fichier (v1 préservée snapshot)
- Aucun merge sur main jusqu'à validation Sebastien explicite

---

## 1. Évidence empirique Phase 2 (rappel)

Phase 2 closure : 8 hypothèses testées. Filter family empirically dominated. Pure always-in delta-neutre = winner. Voir `analysis/PHASE2_SESSION_DIGEST_2026-06-26.md` pour le récap complet.

| Strategy | OOS 13.5 mois | Max DD | Robustness |
|---|---:|---:|---|
| Filter (production actuel) BTC+ETH+SOL | $832 | -4.43 % | family closed, fragile |
| **Target — Always-in pure BTC+ETH** | **$1 686** | **-0.33 %** | **🟢 design trivial** |
| Always-in BTC+ETH+SOL+CB -0.75 % | $2 080 | -0.77 % | 1/4 axes pass, fragile |

Sebastien choice : **fallback robuste BTC+ETH pure always-in**. Coût opportunité ~$28/mois vs H6 best, en échange de simplicité maximale et robustness solide.

---

## 2. Changements code requis

### 2.1 Universe : drop SOL

**Fichier** : `live/paper_funding_capture.py`, ligne 79

```python
# AVANT (production actuel)
ASSETS = ["BTC", "ETH", "SOL"]

# APRÈS (Phase 3 design v2)
ASSETS = ["BTC", "ETH"]   # P33-empirical: SOL drop validated H4 ($90 fees > $24 gross)
```

### 2.2 Position sizing — $1 000 par asset hardcoded

**Fichier** : `live/paper_funding_capture.py`, ligne 80

```python
# AVANT
CAPITAL_PER_ASSET_USD = 10_000.0

# APRÈS (Sebastien decision: $1k×2 = $2k total, equal weight, hardcoded)
CAPITAL_PER_ASSET_USD = 1_000.0   # Phase 3: $1k BTC + $1k ETH = $2k total notional
```

**Justification** : Sebastien validates equal weight $1 000 per asset = $2 000 total notional. Reasons:
- N=2 actifs equal weight = robust, zero parameter over-fittable
- $2 000 total = capital comparable au backtest ratio (backtest $10k notional × $1 686 OOS = 16.86 % return; live $2k notional should produce ~$337 OOS pro-rata = ~$28/month expected)
- Conservative paper observation (no over-leverage during marathon learning)

### 2.3 Entry logic : remove filter → always-in

**Fichier** : `live/paper_funding_capture.py`, fonction `desired_signal_for_asset()` (~ligne 213)

```python
# AVANT — filter design
def desired_signal_for_asset(history: pd.Series) -> int:
    """Returns 1 (in position) or 0 (flat) based on smoothed funding signal."""
    if len(history) < SMOOTH_HOURS + 1:
        return 0
    position = generate_position(
        funding=history,
        smooth_hours=SMOOTH_HOURS,
        entry_threshold_apr=ENTRY_THRESHOLD_APR,
        exit_threshold_apr=EXIT_THRESHOLD_APR,
        min_hold_hours=MIN_HOLD_HOURS,
        min_flat_hours=MIN_FLAT_HOURS,
    )
    return int(position.iloc[-1])

# APRÈS — always-in delta-neutre (Phase 3)
def desired_signal_for_asset(history: pd.Series) -> int:
    """Phase 3 always-in design: always returns 1 (delta-neutral position).
    
    Empirical evidence Phase 2 closure: 8 hypotheses tested, filter design
    dominated by always-in across all configurations. Verdict P33-validated:
    BTC+ETH always-in delta-neutre = $1 686 OOS vs best filter $1 095 (35%
    beat-benchmark fail).
    
    The delta-neutral mechanics (short perp + long spot) cancel mark drift,
    leaving funding rate as pure PnL source. Cf. open_virtual_short() L230.
    """
    return 1
```

**Constantes filter deprecated (conservées pour rollback compatibility)** :
```python
# DEPRECATED Phase 3 — Phase 2 filter design constants, kept for rollback compatibility
# DO NOT USE — strategy is now always-in delta-neutre
# SMOOTH_HOURS = 24
# ENTRY_THRESHOLD_APR = 0.005
# EXIT_THRESHOLD_APR = -0.005
# MIN_HOLD_HOURS = 24
# MIN_FLAT_HOURS = 24
```

### 2.4 Exit logic : conserver mechanics actuelles

**Aucun changement requis** sur `close_virtual_short()` (ligne 246). Mechanics delta-neutre actuelle correcte :
- `realized_pnl_usd = funding_accrued_usd` (price PnL cancels par design delta-neutre)
- Le close ne sera plus jamais déclenché par signal change (always-in)
- Le close peut encore être déclenché par : kill switch (safeguard A), manual override (safeguard D), restart (safeguard F)

---

## 3. Safeguards A → G — détail implementation

### Safeguard A — Kill switch DD hardcoded

**Trigger** : portfolio DD < -1 % sur 24h rolling OU intra-position single asset DD < -1 %.
**Action** : auto-flat toutes positions + Telegram urgent + log incident + transition vers PENDING_USER_VALIDATION (safeguard F).
**Hardcoded** : threshold dans le code, pas en config externe (anti-tampering).

**Spec code** : ajouter dans `run_one_cycle()` (~ligne 380) :

```python
# Safeguard A — Kill switch hardcoded
KILL_SWITCH_DD_THRESHOLD_PCT = -1.0  # HARDCODED, do not externalize
KILL_SWITCH_LOOKBACK_HOURS = 24

def check_kill_switch(state: DaemonState) -> bool:
    """Returns True if kill switch should trigger (auto-flat + alert)."""
    # Compute portfolio DD over last 24h
    portfolio_equity_now = state.realized_pnl_usd + sum(
        p.get('funding_accrued_usd', 0) for p in state.positions.values()
    )
    # Track peak in state (persisted in daemon_state.json)
    peak = max(state.equity_peak_24h, portfolio_equity_now)
    state.equity_peak_24h = peak
    dd_pct = (portfolio_equity_now - peak) / sum(
        p['notional_usd'] for p in state.positions.values()
    ) * 100 if state.positions else 0
    return dd_pct < KILL_SWITCH_DD_THRESHOLD_PCT

# In main cycle, check BEFORE any position open/close action:
if check_kill_switch(state):
    log.log("KILL_SWITCH_TRIGGERED", dd_pct=dd_pct)
    flat_all_positions(state, log, alerter)
    state.mode = "PENDING_USER_VALIDATION"   # safeguard F coupling
    alerter.send("🚨 V2 KILL SWITCH TRIGGERED — DD < -1% / 24h. All positions flat. State: PENDING_USER_VALIDATION. Investigate immediately.")
    return
```

**Test sandbox required** : déclencher artificiellement (manipuler `equity_peak_24h` dans state), vérifier exit + Telegram + state transition.

### Safeguard B — 2nd watchdog indépendant

**Concept** : 2 surveillances orthogonales du daemon + du watchdog principal. Évite silent compound failure (cas 25 juin : daemon mort + watchdog mort = aucune alerte).

**Choix infra à valider Sebastien** :
- **Option B.1** : 2nd watchdog sur VPS Hetzner (process différent, même infra) — simple mais pas vraiment orthogonal
- **Option B.2** : 2nd watchdog sur Storage Box via cron (infra séparée Hetzner) — meilleur isolation
- **Option B.3** : 2nd watchdog cloud externe (cron-job.org, healthchecks.io free tier) — isolation totale mais dépendance externe

V2 recommande **B.2 (Storage Box cron)** : isolation infra, pas de dépendance externe, contrôle total.

**Spec implementation B.2** :
```bash
# Storage Box cron (à configurer sur Storage Box account)
# Cron: */15 * * * *
# Script: check_v2_heartbeat_secondary.sh

#!/bin/bash
# Pull V2 heartbeat from VPS, check freshness
HB=$(ssh -i ~/.ssh/storagebox_key badoun@5.161.246.190 'cat ~/trading-bot-v2/live/state/heartbeat.txt')
NOW=$(date -u +%s)
HB_EPOCH=$(date -u -d "$HB" +%s)
AGE_MIN=$(( (NOW - HB_EPOCH) / 60 ))

if [ $AGE_MIN -gt 15 ]; then
  curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d "chat_id=$SEBASTIEN_CHAT_ID" \
    -d "text=🚨 V2 2ND WATCHDOG ALERT — heartbeat stale ${AGE_MIN}min from Storage Box check. Primary watchdog may also be down."
fi
```

### Safeguard C — Daily reconciliation Telegram 12:05 UTC

**Concept** : daily message orthogonal au watchdog (ne dépend pas du daemon principal). Confirme P&L cohérent, position state, deviation vs expected.

**Spec implementation** :
- Cron sur VPS (séparé du daemon) : `5 12 * * *`
- Script `live/daily_reconciliation.py` (nouveau fichier)
- Lit `daemon_state.json` + compute net P&L 24h + max DD 24h + deviation vs running expectation

**Telegram message format** :
```
📊 V2 Daily Reconciliation — [YYYY-MM-DD]
Day {N}/365 of Phase 3 marathon

Net P&L 24h: $X.XX (cumul: $Y.YY / target $300-450/mois)
Max DD 24h: -X.XX% (kill switch at -1%)
Positions: BTC $1k entry $XX,XXX, funding accrued $X.XX
           ETH $1k entry $X,XXX, funding accrued $X.XX
Cycle count: XXXX, uptime: Xd, restarts last 24h: 0

Backtest expected pro-rata: $X.XX/day | Live: $X.XX/day | Deviation: +/-X%
```

**Si manqué 2 jours consec** → flag manuel humain (ne pas auto-déclencher autre action).

### Safeguard D — Manual override Telegram `/v2_flat YES`

**Concept** : permettre à Sebastien de fermer toutes positions en urgence depuis son iPhone Telegram.

**Spec implementation** :
- Nouveau process `live/telegram_command_listener.py` (polling Telegram getUpdates)
- Auth : whitelist `SEBASTIEN_CHAT_ID` hardcoded (anti-spoofing)
- 2-step confirmation : `/v2_flat` → V2 répond "confirm with /v2_flat YES" → Sebastien envoie `/v2_flat YES` → action exécutée
- Action : flat all positions + state → PENDING_USER_VALIDATION + Telegram confirmation + log

**Code skeleton** :
```python
# live/telegram_command_listener.py (new file)
SEBASTIEN_CHAT_ID = "<hardcoded>"  # whitelist
PENDING_FLAT_CONFIRMATION = False
PENDING_FLAT_TIMESTAMP = None

def process_command(msg):
    global PENDING_FLAT_CONFIRMATION, PENDING_FLAT_TIMESTAMP
    if msg['from']['id'] != SEBASTIEN_CHAT_ID:
        return  # ignore non-whitelisted
    text = msg['text'].strip()
    if text == "/v2_flat":
        PENDING_FLAT_CONFIRMATION = True
        PENDING_FLAT_TIMESTAMP = time.time()
        telegram_reply("/v2_flat received. Confirm with: /v2_flat YES (within 60s).")
    elif text == "/v2_flat YES":
        if PENDING_FLAT_CONFIRMATION and (time.time() - PENDING_FLAT_TIMESTAMP) < 60:
            execute_emergency_flat()
            PENDING_FLAT_CONFIRMATION = False
        else:
            telegram_reply("No pending /v2_flat or timeout. Ignored.")
```

### Safeguard E — Position size cap hardcoded

**Concept** : empêcher runaway si bug sizing ou config corruption.

**Spec** :
```python
# In open_virtual_short() (~ligne 229)
MAX_POSITION_NOTIONAL_USD = 1_000.0       # HARDCODED per asset
MAX_TOTAL_NOTIONAL_USD = 2_000.0           # HARDCODED total portfolio

def open_virtual_short(asset, mark_price, state, log):
    notional = CAPITAL_PER_ASSET_USD
    if notional > MAX_POSITION_NOTIONAL_USD:
        log.log("HARDCAP_PER_ASSET_VIOLATION", attempted=notional, cap=MAX_POSITION_NOTIONAL_USD)
        alerter.send(f"🚨 V2 hard cap per-asset violation: tried to open {asset} at ${notional}, cap ${MAX_POSITION_NOTIONAL_USD}. Refused.")
        return
    total_notional_after = sum(p['notional_usd'] for p in state.positions.values()) + notional
    if total_notional_after > MAX_TOTAL_NOTIONAL_USD:
        log.log("HARDCAP_TOTAL_VIOLATION", attempted=total_notional_after, cap=MAX_TOTAL_NOTIONAL_USD)
        alerter.send(f"🚨 V2 hard cap total violation: tried to total ${total_notional_after}, cap ${MAX_TOTAL_NOTIONAL_USD}. Refused.")
        return
    # proceed with open...
```

### Safeguard F — Sanity check on restart (PENDING_USER_VALIDATION)

**Concept** : après crash + restart, daemon attend signal explicite Sebastien avant de re-ouvrir positions.

**Spec** :
```python
# In main() boot sequence
if state.mode == "PENDING_USER_VALIDATION":
    log.log("BOOT_PENDING_USER_VALIDATION_DETECTED", restart_count=state.restart_count)
    alerter.send(
        f"⚠️ V2 booting in PENDING_USER_VALIDATION mode (set by previous incident). "
        f"Restart count: {state.restart_count}. "
        f"To resume: send /v2_resume YES (within 60s after /v2_resume). "
        f"To rollback: see phase3_rollback_protocol.md."
    )
    # Daemon stays alive but takes NO position actions until /v2_resume YES received via Telegram
    while state.mode == "PENDING_USER_VALIDATION":
        # heartbeat continues, but no open/close/decision
        sleep(LOOP_INTERVAL_SEC)
        check_pending_resume_command()
```

### Safeguard G — OB forward dispatcher verified weekly

**Concept** : vérification automatique hebdo que OB forward dispatcher fonctionne. Source orthogonale au watchdog principal.

**Spec** : extension du Saturday Recap script (`scripts/generate_saturday_recap.py`) :
```python
# Add to Saturday Recap generation
def check_ob_forward_health():
    """Verify OB forward dispatcher emitted at least 5 Telegram messages in past 7 days."""
    # Read live/state/forward_charts/ for files dated past 7 days
    # Count expected daily emissions
    forward_dir = ROOT / "live" / "state" / "forward_charts"
    today = datetime.now(timezone.utc).date()
    expected_emissions = 0
    actual_emissions = 0
    for day_offset in range(7):
        check_date = today - timedelta(days=day_offset)
        # Check if dispatcher fired that day (look for files dated that day)
        day_str = check_date.strftime("%Y%m%d")
        matching_dirs = list(forward_dir.glob(f"{day_str}_*"))
        expected_emissions += 1  # 1 per day expected
        if matching_dirs:
            actual_emissions += 1
    if actual_emissions < expected_emissions - 1:  # tolerate 1 miss
        send_telegram(f"⚠️ V2 OB forward dispatcher health: only {actual_emissions}/{expected_emissions} emissions last 7 days. Investigate.")
```

---

## 4. Calendrier deployment + checkpoints

| Jalon | Date (relative à T0) | Action / Verification |
|---|---|---|
| **T-7 jours** | Pre-deploy week | Sandbox test 7 safeguards exhaustif |
| **T-1 jour** | Day before deploy | Snapshot Storage Box manual `pre_phase3_deployment_T-1` |
| **T-0 (deploy)** | Phase 3 start | Cutover atomic, snapshot pre/post |
| **T+1 jour** | Day 1 | Daily reconciliation OK, all safeguards verified live |
| **T+7 jours** | Week 1 | First Saturday Recap Phase 3 format |
| **T+30 jours** | Day 30 | Sanity check live vs backtest expected (±50% tolerance) |
| **T+90 jours** | Day 90 | First checkpoint statistique exhaustif + ajustements config si needed |
| **T+180 jours** | Day 180 | Mid-marathon evaluation. 5-gate framework appliqué (preliminary) |
| **T+365 jours** | Day 365 | **Final evaluation pour real capital decision** |

---

## 5. Diff résumé code production

| File | Lines changed | Nature |
|---|---:|---|
| `live/paper_funding_capture.py` | +50 / -10 | Universe drop SOL + sizing $1k + always-in entry + 4 safeguards inline (A, E, F invocation) |
| `live/telegram_command_listener.py` | +60 new file | Safeguard D — manual override listener |
| `live/daily_reconciliation.py` | +80 new file | Safeguard C — daily reconciliation report |
| `scripts/generate_saturday_recap.py` | +30 | Safeguard G — OB forward health check inclusion |
| Storage Box cron script | +20 new file | Safeguard B — 2nd watchdog (à déployer Storage Box, pas dans repo VPS) |
| `backtest/engine.py` | 0 | Inchangé |
| `live/ob_forward_dispatcher.py` | 0 | Inchangé |
| `live/watchdog.py` | 0 | Inchangé |
| `paper_trading/monitoring.py` | 0 | Inchangé |

**Diff total estimé** : ~240 lignes effectives, 3 nouveaux fichiers. Plus complexe que v1 spec (~15 lignes) car les 7 safeguards exigent infrastructure additionnelle.

---

## 6. Validation pré-merge — alpha_lab gates adaptés

| Gate | Check |
|---|---|
| Backtest cohérence | `backtest/engine.py` re-run with config Phase 3 → expect $1 686/10 (proportionnel) = $168.6 sur sizing $1k×2 OOS BTC+ETH always-in ±5 % |
| Unit tests existants | `pytest tests/` — tous green (P4 discipline) |
| Lint + type | `flake8` + `mypy` clean sur fichiers modifiés/nouveaux |
| No look-ahead | Conservé per P14 + P1 |
| **Safeguard A test** | Manipulate `equity_peak_24h` artificially in state, verify kill switch fires |
| **Safeguard B test** | Stop daemon manually, verify 2nd watchdog Storage Box detects within 15 min |
| **Safeguard C test** | Manual run `daily_reconciliation.py`, verify Telegram message format correct |
| **Safeguard D test** | Send `/v2_flat` from Sebastien chat, verify confirmation flow + execution |
| **Safeguard E test** | Try to open position at $2k notional, verify hard cap refusal |
| **Safeguard F test** | Manually set `state.mode = "PENDING_USER_VALIDATION"`, restart daemon, verify no auto-open |
| **Safeguard G test** | Manual run Saturday Recap with OB forward absent, verify health flag |
| Manual smoke test | `python live/paper_funding_capture.py --once` opens BTC+ETH @ $1k each, no SOL |
| Compat Saturday Recap | `python scripts/generate_saturday_recap.py --no-telegram` génère sans erreur |

---

## 7. Snapshot policy P15 / P31 pour le merge

| Étape | Snapshot label | Quand |
|---|---|---|
| Pre-spec v1 | `pre_phase3_implementation_baseline` ✓ | Pre-Phase3 baseline |
| Post-spec v1 | `post_phase3_spec_docs_v1` ✓ | After v1 docs written |
| Pre-transition backup | `pre_phase2_to_phase3_transition_backup` ✓ | Avant cette session v2 |
| Post-spec v2 | `post_phase3_spec_docs_v2` | À créer après cette session (3 docs + digest) |
| Pre-code-change | `pre_phase3_code_change_application` | Avant édition de code |
| Post-code-change | `post_phase3_code_change_application` | Après édition, avant tests |
| Pre-tests | `pre_phase3_tests_alpha_lab_gates` | Avant pytest + safeguards tests |
| Post-tests | `post_phase3_tests_passed` | Après tous gates pass |
| Pre-merge | `pre_phase3_merge_to_main` | Avant merge |
| Post-merge | `post_phase3_merge_to_main` | Après merge |
| Pre-VPS-deploy | `pre_phase3_vps_deployment` | Avant cutover VPS systemd |
| T-0 cutover | `phase3_T0_deployment_marathon_start` | Cutover atomic moment |
| T+30, T+90, T+180, T+365 | `phase3_checkpoint_day_X` | Each checkpoint |

---

## 8. Phrase that closes

> *Phase 3 design v2 = BTC+ETH always-in pure delta-neutre, $1k×2 = $2k notional total hardcoded, marathon 365 jours, 7 safeguards mandatory A→G. ~240 lignes code change anticipées (vs v1 estimation ~15 lignes — la robustness ops coûte). Production main 232b883 INTACT et le restera jusqu'à validation Sebastien explicite de cette spec v2.*

---

## 9. Décisions opérateur requises sur cette spec v2

1. **Safeguard B infra choice** : Option B.2 (Storage Box cron, V2 recommandation), B.1 (VPS same), ou B.3 (cloud externe) ?
2. **Telegram chat_id pour whitelist Safeguard D** : à confirmer (probablement déjà connu via Sebastien telegram.env) ?
3. **Daily reconciliation format Sec 3.C** : ok ou changements ?
4. **Manual override syntax `/v2_flat YES`** : ok ou autre syntaxe ?
5. **Saturday Recap extension Safeguard G** : intégrer dans existing recap, ou nouveau report dédié ?
6. **Sandbox test rollback** : qui exécute — Sebastien ou V2 en sub-agent isolé ?
7. **Approval merge-flow** : tests sandbox 7 safeguards passés → Sebastien explicit GO merge, ou intermediate stage ?

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*Phase 3 Deployment Spec v2 generated by V2 agent on 2026-06-27 by integrating Sebastien-validated operator decisions: $1k×2 sizing, 365-day marathon, 7 safeguards A→G mandatory. Snapshot baseline `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup`. v1 preserved `SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`. Production code untouched.*
