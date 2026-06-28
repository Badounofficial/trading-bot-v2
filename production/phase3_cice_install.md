# ʼCɩcɛ Install — VPS deployment for Phase 7 monitoring

**Audience** : Sebastien, post-Phase-3 cutover, before Phase 7 baseline fit.
**Author** : V2 agent, 2026-06-28
**ʼCɩcɛ version target** : `1.0.0` (commit `150f5d1`)

---

## 1. Why install ʼCɩcɛ on the VPS

Phase 7 setup (`live/drift_monitor_baseline.py` + future checkpoint scripts at Day 30/90/180/365) imports the `cice` package at runtime:

```python
from cice import DriftMonitor                    # Phase 7 daily / checkpoints
from cice import IronGloveValidator, ArraySignal # Day 30/90/180/365 5-gate
from cice import preflight as PF                 # pre-cutover audit (already done Phase 6)
from cice import lookahead_probe                 # already done Phase 6
```

V2 daemon runtime itself (`paper_funding_capture.py` etc.) does NOT import ʼCɩcɛ — per §10 NATIVE decision. ʼCɩcɛ is the validation/monitoring sidekick, not part of the trading loop.

---

## 2. Prerequisites on VPS

- Python 3.9+ in V2's venv at `/home/badoun/trading-bot-v2/.venv`
- Git clone of ʼCɩcɛ already pushed to `/home/badoun/cice` (Sebastien did this in advance — confirmed in his Phase 6 brief: "VPS : `/home/badoun/cice` (déjà déployé, commit `150f5d1`)")

If not yet on VPS:

```bash
ssh badoun@5.161.246.190
git clone <cice-repo-url> /home/badoun/cice
cd /home/badoun/cice
git checkout 150f5d1   # pin to known-good commit
```

---

## 3. Install command

```bash
ssh badoun@5.161.246.190
cd /home/badoun/trading-bot-v2
.venv/bin/pip install -e /home/badoun/cice
```

The `-e` (editable) install means if Sebastien later updates the `/home/badoun/cice` checkout (e.g. `git pull` for a new ʼCɩcɛ release), the V2 venv picks up changes immediately without a reinstall.

---

## 4. Smoke verification

```bash
.venv/bin/python -c "
import cice
print('cice version:', cice.__version__)
from cice import DriftMonitor, IronGloveValidator, ArraySignal, preflight, lookahead_probe
print('all imports OK')
"
```

Expected output:
```
cice version: 1.0.0
all imports OK
```

If `ModuleNotFoundError: No module named 'scipy'` → install scipy first:
```bash
.venv/bin/pip install scipy
```

(Per ʼCɩcɛ deps list: numpy + pandas + scipy core; pyflakes optional for preflight static audit.)

---

## 5. Optional: pin scipy + pyflakes in V2 requirements

After ʼCɩcɛ install verified, capture the exact deps for reproducibility:

```bash
cd /home/badoun/trading-bot-v2
.venv/bin/pip freeze | grep -E "cice|scipy|pyflakes|numpy|pandas" >> requirements_phase7_cice.txt
```

This file is for future-Sebastien if he ever needs to rebuild the venv from scratch.

---

## 6. Trigger Phase 7 baseline fit

After ʼCɩcɛ install verified:

```bash
cd /home/badoun/trading-bot-v2
.venv/bin/python live/drift_monitor_baseline.py
```

Expected outcome:
- Reads `cache/funding_hyperliquid_BTC_USDC_USDC.parquet` and `..._ETH_...parquet`
- Slices to OOS window 2025-03-15 → 2026-05-04
- Fits `cice.DriftMonitor` on the 2-feature reference (funding_BTC + funding_ETH)
- Self-check: PSI on reference vs itself ≈ 0 (stable)
- Writes `live/state/drift_monitor_baseline.pkl`

If the cache parquet files are NOT present on the VPS (they may have been gitignored), Sebastien needs to push them from Mac via:

```bash
# On Mac:
scp ~/Desktop/trading-bot-v2/cache/funding_hyperliquid_BTC_USDC_USDC.parquet \
    ~/Desktop/trading-bot-v2/cache/funding_hyperliquid_ETH_USDC_USDC.parquet \
    badoun@5.161.246.190:/home/badoun/trading-bot-v2/cache/
```

---

## 7. Day 0 sequence (operator runbook)

After cutover atomic complete + ʼCɩcɛ installed + drift_monitor baseline fitted:

```bash
# 1. Mark Day 0 + send Telegram boot alert
.venv/bin/python live/phase3_day0_mark.py
# (or with explicit timestamp: --ts 2026-06-28T15:00:00+00:00)

# 2. Update the PHASE3_MARATHON_T0 constant in daily_reconciliation.py
#    Take the day0_ts printed by step 1, edit live/daily_reconciliation.py near line 67:
#    PHASE3_MARATHON_T0 = "2026-06-28T15:00:00+00:00"

# 3. Verify daemon is running healthy
sudo systemctl status v2-daemon v2-telegram-listener v2-daily-reconciliation.timer
tail -F live/logs/daemon_$(date -u +%Y-%m-%d).log

# 4. Confirm in Telegram chat that boot alert arrived. Reply to V2: "Day 0 ACK"
```

Day 0 anchored. Marathon clock starts ticking. Sebastien holds the rollback button at every step via `/v2_flat YES`.

---

## 8. Reference — ʼCɩcɛ scripts that V2 will produce during the marathon

(These are NOT in scope for Phase 7 setup itself, but listed here so Sebastien knows what's coming.)

| Script | Trigger | Purpose |
|---|---|---|
| `live/drift_monitor_daily.py` | cron daily 12:10 UTC (5min after reconciliation) | Compute current 7-day rolling funding distributions, run `dm.check()`, alert if PSI ≥ 0.25 |
| `analysis/phase3_checkpoint_day_30.md` | scripted at Day 30 | Run `IronGloveValidator(ppy=1095)` 5-gate, append verdict GO/NO-GO |
| `analysis/phase3_checkpoint_day_90.md` | scripted at Day 90 | Same, mid-marathon |
| `analysis/phase3_checkpoint_day_180.md` | scripted at Day 180 | Same, half-marathon, preliminary go/no-go for full marathon |
| `analysis/phase3_checkpoint_day_365.md` | scripted at Day 365 | FINAL 5-gate, real capital decision |

These scripts will be authored by V2 in dedicated phases (Phase 7.1, 7.2, etc.) once cutover is complete and daemon stability is confirmed (typically T+7 days).

---

*ʼCɩcɛ install doc generated by V2 agent on 2026-06-28 for Phase 7 deployment. ʼCɩcɛ sovereignty rule 7 respected (V2 imports, never patches/overrides). Production main `232b883` INTACT until Sebastien explicit cutover merge.*
