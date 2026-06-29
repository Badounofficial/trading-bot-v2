# Trading Bot V2 — Phase 3 Rollback Protocol (v2 — operator-validated)

**Author** : V2 agent (autonomous)
**Date** : 2026-06-27 01:40 UTC
**Version** : v2 (revised after Sebastien validation Phase 3 marathon decisions)
**Previous version** : v1 preserved in `snapshots/SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`

**Purpose** : documenter et tester le rollback complet du déploiement Phase 3 (BTC+ETH always-in $1k×2) vers le baseline `232b883` (filter design BTC+ETH+SOL $10k×3) avant toute action de merge ou deployment.

**P31 dit** : *Pas de rollback testé = pas d'action.*

---

## 1. État baseline avant Phase 3

| Item | Valeur |
|---|---|
| Production main HEAD | `232b8835f1f336fa3507848a2a388a06e3c3d1cf` |
| Tag de référence | `audit/lookahead-fix-phase-b` (= 232b883) |
| Snapshot baseline | `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup/` |
| Universe production (baseline) | `["BTC", "ETH", "SOL"]` (filter design) |
| Strategy params (baseline) | `min_hold=24, entry=0.005, smooth=24, min_flat=24` |
| Position sizing (baseline) | `$10 000 per asset = $30 000 total notional` |

---

## 2. Conditions trigger rollback

Le rollback DOIT être déclenché si **une** des conditions suivantes survient pendant Phase 3 marathon :

| Trigger | Threshold | Cohérence avec safeguards |
|---|---|---|
| **Kill switch fired (safeguard A)** | DD < -1 % rolling 24h | Auto-flat exécuté → rollback à valider sous 24h |
| **Net P&L < -$100 cumul** | depuis deploy | Bigger than threshold safeguards |
| **Max DD réalisé > -2 %** | observed | 2× threshold kill switch — significant divergence |
| **Daemon crash loop > 3 restarts / 24h** | watchdog detection | Operational integrity gate failure |
| **API errors > 100/24h pendant 3j** | Hyperliquid major outage | May indicate filter design (more resilient ?) better short-term |
| **Position observed sur asset hors {BTC, ETH}** | from trades.jsonl audit | Config corruption — immediate rollback |
| **Funding rate inversion > 21j consec** | net funding < 0 sur 3 semaines | Strategy thesis violated — needs design re-eval |
| **Operational integrity projection at Day 180** | < 95 % uptime mid-marathon | Will fail Gate 5 at Day 365 |
| **Sebastien explicit decision** | Telegram `/v2_rollback YES` ou Cowork | Manual trigger |

**N'IMPORTE QUELLE de ces conditions = rollback immédiat, pas de débat.**

---

## 3. Procédure de rollback complète (5 min target)

### 3.1 Sur VPS (production daemon)

```bash
# T-0 — STOP tous les V2 processes immédiatement
ssh badoun@5.161.246.190 << 'EOF'
cd ~/trading-bot-v2
# Stop systemd service first (production VPS uses systemd)
sudo systemctl stop v2-daemon.service 2>/dev/null
sudo systemctl stop v2-telegram-listener.service 2>/dev/null
sudo systemctl stop v2-watchdog-primary.service 2>/dev/null
sudo systemctl stop v2-ob-forward.service 2>/dev/null
# Fallback if not on systemd
pkill -f paper_funding_capture
pkill -f telegram_command_listener
pkill -f ob_forward_dispatcher
pkill -f watchdog
pkill -f daily_reconciliation
sleep 5
ps aux | grep -E "paper_funding|watchdog|ob_forward|telegram_command|daily_reconcil" | grep -v grep || echo "all V2 processes stopped"
EOF

# T+30s — Snapshot état post-incident pour forensique
ssh badoun@5.161.246.190 << 'EOF'
cd ~/trading-bot-v2
bash scripts/v2_snapshot.sh rollback_phase3_post_incident_$(date -u +%Y%m%d_%H%M)
EOF

# T+1min — Restore code from baseline 232b883 sur VPS
ssh badoun@5.161.246.190 << 'EOF'
cd ~/trading-bot-v2
git fetch origin
git checkout main
git reset --hard 232b8835f1f336fa3507848a2a388a06e3c3d1cf
git log --oneline -1   # confirm at 232b883
ls live/paper_funding_capture.py
grep -nE "ASSETS|CAPITAL_PER_ASSET_USD|MIN_HOLD_HOURS" live/paper_funding_capture.py | head -5
EOF

# T+1m30 — Restore daemon state from pre-Phase3 baseline
ssh badoun@5.161.246.190 << 'EOF'
cd ~/trading-bot-v2
# Identifier le snapshot pre-Phase3 le plus récent
SNAP=$(ls -dt snapshots/SNAPSHOT_*pre_phase2_to_phase3_transition_backup* | head -1)
[ -z "$SNAP" ] && SNAP=$(ls -dt snapshots/SNAPSHOT_*pre_phase3_implementation_baseline* | head -1)
echo "Restoring from: $SNAP"
cp $SNAP/daemon_state.json live/state/ 2>/dev/null
cp $SNAP/heartbeat.txt    live/state/ 2>/dev/null
cp $SNAP/trades.jsonl     live/state/ 2>/dev/null
python3 -c "
import json
d = json.load(open('live/state/daemon_state.json'))
print(f'BASELINE RESTORED cycle={d[\"cycle_count\"]} realized=\${d[\"realized_pnl_usd\"]:.4f}')
print(f'Positions: {list(d[\"positions\"].keys())}')
"
EOF

# T+2min — Restart services baseline (filter design)
ssh badoun@5.161.246.190 << 'EOF'
sudo systemctl start v2-daemon.service
sudo systemctl start v2-watchdog-primary.service
sudo systemctl start v2-ob-forward.service
sleep 5
systemctl status v2-daemon.service --no-pager | head -5
cat ~/trading-bot-v2/live/state/heartbeat.txt
EOF

# T+5min — Verify all 3 processes UP + send Telegram confirmation
ssh badoun@5.161.246.190 << 'EOF'
ps aux | grep -E "paper_funding|watchdog|ob_forward" | grep -v grep
cd ~/trading-bot-v2
source venv/bin/activate
python3 -c "
from paper_trading.monitoring import TelegramAlerter
t = TelegramAlerter()
res = t.send('🔄 V2 PHASE 3 ROLLBACK COMPLETE — reverted to main 232b883 baseline (filter BTC+ETH+SOL \$10k×3). Daemon UP, state restored from pre-Phase3 snapshot. Forensic snapshot rollback_phase3_post_incident preserved. Pattern 32 repair-before-run protocol active — investigate before any new deploy.')
print(f'telegram: ok={res.ok}')
"
EOF
```

### 3.2 Sur Mac (côté analyses, non-production)

Si une branche Phase 3 a été mergée sur main par accident :

```bash
cd ~/Desktop/trading-bot-v2
git fetch origin
git log --oneline -10

# Identify the bad merge commit SHA — likely a fast-forward from production/phase3-...
# Revert is safer than reset
git revert <bad_merge_sha> -m 1
git push origin main

# OR hard reset à 232b883 (last resort — preserves nothing)
# ⚠ DANGEROUS — pas de recovery facile
# git reset --hard 232b8835f1f336fa3507848a2a388a06e3c3d1cf
# git push --force-with-lease origin main
```

**Préférer `git revert`** qui préserve l'historique des erreurs (P30 evidence density).

---

## 4. Rollback test PRÉ-deployment (P31 obligatoire)

**Le rollback DOIT être testé en sandbox AVANT toute deployment Phase 3.**

### 4.1 Protocol de test sandbox (à exécuter Sebastien OR V2 sub-agent)

```bash
# Sandbox setup
cd /tmp
git clone <Mac-local-path>/trading-bot-v2 v2_sandbox_rollback_test_phase3
cd v2_sandbox_rollback_test_phase3

# Apply Phase 3 changes (commit on sandbox branch, ne push pas)
git checkout production/phase3-always-in-btc-eth-deployment

# Verify Phase 3 config in code
grep ASSETS live/paper_funding_capture.py | head -1
# Expected: ASSETS = ["BTC", "ETH"]
grep CAPITAL_PER_ASSET_USD live/paper_funding_capture.py | head -1
# Expected: CAPITAL_PER_ASSET_USD = 1_000.0
grep "return 1" live/paper_funding_capture.py | grep -A 2 desired_signal | head -3
# Expected: function returns 1 (always-in)

# Simulate Phase 3 deployment state
mkdir -p live/state
cat > live/state/daemon_state.json << 'EOF'
{
  "cycle_count": 100,
  "last_loop_ts": "2026-06-27T01:00:00+00:00",
  "started_at": "2026-06-27T00:00:00+00:00",
  "positions": {
    "BTC": {"asset": "BTC", "direction": 1, "entry_ts": "2026-06-27T00:00:00+00:00", "entry_price": 75000, "notional_usd": 1000, "units": 0.01333, "funding_accrued_usd": 0.50, "last_funding_ts": "2026-06-27T01:00:00+00:00"},
    "ETH": {"asset": "ETH", "direction": 1, "entry_ts": "2026-06-27T00:00:00+00:00", "entry_price": 2000, "notional_usd": 1000, "units": 0.5, "funding_accrued_usd": 0.30, "last_funding_ts": "2026-06-27T01:00:00+00:00"}
  },
  "realized_pnl_usd": 0.0,
  "unrealized_pnl_usd": 0.0,
  "api_error_count_hourly": 0,
  "api_error_window_start": "",
  "sent_messages": [],
  "mode": "PHASE3_MARATHON",
  "equity_peak_24h": 0.80
}
EOF

# Step 1: simulate trigger condition (kill switch fired, DD < -1%)
# Manipulate state to trigger
python3 -c "
import json
d = json.load(open('live/state/daemon_state.json'))
d['equity_peak_24h'] = 50.0   # Force peak high
d['positions']['BTC']['funding_accrued_usd'] = -30.0  # Force DD
d['positions']['ETH']['funding_accrued_usd'] = -25.0
json.dump(d, open('live/state/daemon_state.json', 'w'), indent=2)
print('State manipulated to trigger kill switch on next cycle')
"

# Step 2: execute rollback protocol manually (simulating SSH commands)
git checkout main
git reset --hard 232b8835f1f336fa3507848a2a388a06e3c3d1cf
echo "Restored to main $(git rev-parse HEAD)"

# Step 3: verify config is back to baseline
grep -nE "ASSETS|CAPITAL_PER_ASSET_USD|MIN_HOLD" live/paper_funding_capture.py | head -5
# Expected:
# ASSETS = ["BTC", "ETH", "SOL"]   (drop SOL reverted)
# CAPITAL_PER_ASSET_USD = 10_000.0   (sizing reverted)
# MIN_HOLD_HOURS = 24   (filter actif)

# Step 4: validate state restoration logic from snapshot copy
# In real rollback, snapshot would be from pre-Phase3 baseline
ls /home/badoun/Desktop/trading-bot-v2/snapshots/SNAPSHOT_*pre_phase2_to_phase3_transition_backup* 2>/dev/null
# Verify daemon_state.json structure matches baseline expectations

# Step 5: dry-run daemon with restored config
python3 live/paper_funding_capture.py --once 2>&1 | tail -10
# Expected: daemon opens 3 positions BTC+ETH+SOL $10k each, cycle starts, telemetry intact

# Cleanup sandbox
cd /tmp && rm -rf v2_sandbox_rollback_test_phase3
```

### 4.2 Critères de succès du test rollback

| Item | Verification | Pass condition |
|---|---|---|
| Code restoration | `git rev-parse HEAD` | == `232b8835f1f336fa3507848a2a388a06e3c3d1cf` |
| Universe config | `grep ASSETS live/paper_funding_capture.py` | == `["BTC", "ETH", "SOL"]` |
| Sizing config | `grep CAPITAL_PER_ASSET_USD` | == `10_000.0` |
| Filter active | `grep MIN_HOLD_HOURS` | == `24` |
| Daemon state | Boot test | Reads pristine state without error |
| Heartbeat | First cycle emits | UTC timestamp fresh |
| Position decisions | Cycle 1 | Opens 3 positions BTC+ETH+SOL si funding signal positif |
| Safeguards reverted | Files exist (Phase 3) but unused by baseline | OK car baseline doesn't import them |

**Si une seule condition fail** → rollback procedure inadequate, revoir avant deployment Phase 3.

### 4.3 Décision opérateur — qui exécute le sandbox test

**V2 recommandation** : **Sebastien lui-même** sur son Mac, parce que :
- Test du flow SSH VPS nécessite credentials qui sont chez Sebastien
- Sandbox V2 isolation est cheaper que Mac (peut faire le test pure-Mac)
- Validation par opérateur = additional layer of vérification

**Alternative** : V2 peut spawn un sub-agent pour exécuter le test sur copy isolated du repo. Plus rapide mais moins de visibility opérateur.

---

## 5. Liste des snapshots de restoration disponibles (preserve forever)

Du plus récent au plus pertinent pour rollback Phase 3 → baseline :

| Snapshot | Date UTC | État représenté |
|---|---|---|
| `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup` | 2026-06-27 01:07 | **Baseline absolu pre-Phase 3, recommandé pour rollback** |
| `SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1` | 2026-06-27 00:52 | Post Phase 3 spec v1 (avant validation) |
| `SNAPSHOT_20260627T004802Z_pre_phase3_implementation_baseline` | 2026-06-27 00:48 | Pre-Phase 3 spec writing |
| `SNAPSHOT_20260626T232754Z_post_H6_robustness` | 2026-06-26 23:27 | Post Phase 2.5 closure |
| `SNAPSHOT_20260626T232553Z_pre_H6_robustness` | 2026-06-26 23:25 | Pre H6 robustness |
| `SNAPSHOT_20260626T163036Z_pre_loss_forensic_phase1` | 2026-06-26 16:30 | Baseline absolue pre-Phase 2 |

**Pour rollback Phase 3 → baseline** : utiliser `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup` (plus récent, le plus proche de l'état production attendu post-merge baseline).

---

## 6. Communication rollback (Telegram automated)

Pendant un rollback, V2 envoie 3 messages :

```
🚨 V2 PHASE 3 ROLLBACK INITIATED — trigger: [trigger_name]
DD/error/Sebastien decision triggered rollback.
Stopping production daemon, capturing forensic snapshot.

[T+2min]
🔧 V2 PHASE 3 ROLLBACK IN PROGRESS — code reverted to 232b883, state restored from pre-Phase3 baseline.

[T+5min]
✅ V2 PHASE 3 ROLLBACK COMPLETE — baseline filter BTC+ETH+SOL design UP, daemon healthy, positions [BTC, ETH, SOL] open, realized $X.XX. Forensic snapshot preserved at [snapshot_path]. P32 Repair-Before-Run active — diagnose RCA before any redeploy.
```

---

## 7. Post-rollback forensic (mandatory)

Per P32 Repair-Before-Run + P30 Evidence Density :

1. **Préserver le snapshot post-incident forever** (`rollback_phase3_post_incident_<timestamp>`)
2. **Diff baseline state vs post-incident state** : identifier ce qui a divergé
3. **Root cause analysis** : pourquoi le trigger s'est déclenché ?
4. **Document RCA** dans `analysis/loss_forensic_phase3_rollback_<date>.md`
5. **P32 discipline** : avant tout nouveau deployment Phase 3, le root cause doit être adressé en spec
6. **Update success_criteria.md** si threshold trigger révèle un gap

---

## 8. Phase 3 vs baseline trade-off — pour mémoire opérateur

| Item | Baseline (filter) | Phase 3 (always-in) | Note |
|---|---|---|---|
| Code complexity | High (filter + min_hold + thresholds) | Low (always-in delta-neutre) | Phase 3 wins on simplicity |
| Backtest expected | $832 OOS (BTC+ETH+SOL) | $1 686 OOS (BTC+ETH, pro-rata $168 sur $1k×2) | Phase 3 wins |
| Universe count | 3 (BTC+ETH+SOL) | 2 (BTC+ETH) | Phase 3 wins on focus |
| Position sizing | $10k×3 = $30k | $1k×2 = $2k | Phase 3 conservative paper |
| Safeguards | Existing (heartbeat, watchdog) | Existing + 7 mandatory A→G | Phase 3 wins on robustness |
| API resilience | Existing | Existing | Tie |
| Rollback path | Phase 3 → baseline (this doc) | Baseline → Phase 3 (already deployed v1) | Phase 3 has known rollback |

Le rollback baseline est **dégradant en terme de net P&L** (filter design loses ~$650 sur 13.5 mois OOS BTC+ETH vs always-in), mais peut être **temporairement nécessaire** si Phase 3 révèle un problème opérationnel critique avant fix.

---

## 9. Phrase that closes

> *Rollback Phase 3 → baseline 232b883 documenté en 5 étapes (~5 min), conditionné par 9 triggers explicites alignés avec safeguards, testable en sandbox avant deployment. P31 enforced : pas de rollback testé = pas d'action. P32 enforced : post-rollback RCA mandatory.*

---

## 10. Validation Sebastien requise sur cette spec v2

1. **9 triggers liste** (Sec 2) : ces conditions couvrent les risques attendus du marathon 365j ?
2. **Procedure rollback 5min** (Sec 3) : acceptable, ou changements ?
3. **Sandbox test executor** (Sec 4.3) : Sebastien lui-même ou V2 sub-agent isolé ?
4. **Telegram messages format** (Sec 6) : ok ou changer ?

Production main HEAD `232b8835f1f336fa3507848a2a388a06e3c3d1cf` — **INTACT**.

---

*Phase 3 Rollback Protocol v2 generated by V2 agent on 2026-06-27. Snapshot baseline `SNAPSHOT_20260627T010744Z_pre_phase2_to_phase3_transition_backup`. v1 preserved `SNAPSHOT_20260627T005205Z_post_phase3_spec_docs_v1/`. Production code untouched.*
