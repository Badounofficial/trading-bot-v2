# Live Paper Trading — Operations Manual

> **Purpose** : run the `funding_capture` strategy as an autonomous virtual
> paper trader on Hyperliquid PUBLIC funding data, with no real capital,
> for the absence window **22 May → 2 June 2026**.

This folder is everything you (Badoun) need to operate, monitor, or
intervene on the daemon — including from your iPhone while away.

---

## 1. Files in this folder

| File | Purpose |
|---|---|
| `paper_funding_capture.py` | The daemon itself. Runs the 5-min decision loop, calls Hyperliquid public API, opens/closes virtual positions, persists state, fires Telegram alerts. |
| `watchdog.py` | Separate process. Monitors `state/heartbeat.txt` freshness. Alerts via Telegram if the daemon went silent > 2 h. |
| `run_daemon.sh` | Sleep-immune wrapper (`caffeinate -i`) with auto-restart loop. Use this to launch in production. |
| `telegram_smoke_test.py` | One-shot validator of the Telegram chain (already run earlier, OK). |
| `smoke_long.py` | Multi-cycle smoke test (used to debug — keep as reference). |
| `state/` | All daemon state: positions, trade ledger, funding history, heartbeat. |
| `logs/` | Daily logs from daemon + wrapper. |

---

## 2. Launch sequence — vendredi 22 May morning

**Total time : 10 minutes max.** Run this in order on your Mac.

### Step 1 — Smoke test Telegram (5 sec)

```bash
cd ~/Desktop/trading-bot-v2
python live/telegram_smoke_test.py
```

Expected : you receive on Telegram :
> ✅ V2 — Telegram intégration testée…

If you don't receive it, **STOP**. Ping me (Cowork) to debug before launching the daemon.

### Step 2 — Launch the daemon (production)

In one terminal, detached so it survives terminal close :

```bash
cd ~/Desktop/trading-bot-v2
nohup bash live/run_daemon.sh > /tmp/v2_daemon.out 2>&1 &
echo "Daemon PID wrapper: $!"
```

Note the wrapper PID. The wrapper itself spawns the actual Python daemon — both will appear in `ps aux | grep paper_funding`.

### Step 3 — Launch the watchdog (production)

In another terminal, also detached :

```bash
cd ~/Desktop/trading-bot-v2
nohup python live/watchdog.py > /tmp/v2_watchdog.out 2>&1 &
echo "Watchdog PID: $!"
```

### Step 4 — Verify both are alive (1 min)

```bash
ps aux | grep -E "paper_funding|watchdog" | grep -v grep
```

You should see **3 processes** :
1. `bash live/run_daemon.sh` (wrapper)
2. `caffeinate -i python …` (daemon under caffeinate)
3. `python live/watchdog.py`

Check the daemon completed its first cycle :
```bash
cat live/state/heartbeat.txt
# should be a UTC ISO timestamp within the last few minutes
```

Check it opened positions (if HL funding is favourable) :
```bash
cat live/state/daemon_state.json | head -20
```

### Step 5 — Send yourself an "all green" Telegram (optional but reassuring)

Just send a `/start` to your bot OR run :
```bash
python -c "from paper_trading.monitoring import TelegramAlerter; TelegramAlerter().send('✅ V2 daemon launched, watchdog running. À dans 10 jours.')"
```

You should receive it within 1 second. **You can leave.**

---

## 3. What's normal during the 10 days

| Day | What you'll see on Telegram | Action |
|---|---|---|
| Every day at 12:00 UTC | 💚 *V2 Day YYYY-MM-DD · N open · realized $X · cycle #N* | None |
| 28 May at 12:00 UTC | 📊 *V2 INTERMEDIATE REPORT* (long format) | Read, no action |
| Otherwise | Nothing | Trust the silence |

Silence = healthy. Heartbeats = healthy. No reply needed.

---

## 4. When to intervene from your iPhone

If you receive any 🚨 ALERT message, here are the cases :

### 🚨 PnL < −10%

The realized paper PnL has crossed −$3 000 (on $30k notional).
- **Probable cause** : major regime shock (flash crash, funding flip)
- **Action** : SSH to Mac and inspect logs. If genuine drawdown, you can let it ride (it's paper). If it looks like a bug, stop the daemon.

### 🚨 API errors > 5 / hour

Hyperliquid API rate-limited us or had an outage.
- **Probable cause** : HL infra issue or our polling too aggressive
- **Action** : usually self-recovers within an hour. If persistent (next heartbeat shows errors still climbing), SSH and stop the daemon.

### 🚨 WATCHDOG — daemon heartbeat stale

The daemon hasn't logged a heartbeat in > 2 h. Could be crashed, Mac woke up from sleep into bad state, or network died.
- **Action from iPhone** : try SSH first.
  ```
  ssh badoun@<your-mac-hostname-or-IP>
  tail -50 ~/Desktop/trading-bot-v2/live/logs/wrapper_*.log
  ```
  If wrapper is alive : it'll auto-restart in a few minutes. Wait.
  If wrapper is dead : `cd ~/Desktop/trading-bot-v2 && nohup bash live/run_daemon.sh > /tmp/v2_daemon.out 2>&1 &`

### Recovery confirmation

When the heartbeat comes back, you'll get a 💚 *V2 WATCHDOG — daemon recovered* message automatically.

---

## 5. How to stop everything (emergency)

From the Mac terminal :
```bash
pkill -f paper_funding_capture
pkill -f watchdog.py
pkill -f "caffeinate -i"
```

From iPhone via SSH :
```bash
ssh badoun@<host> 'pkill -f paper_funding_capture; pkill -f watchdog.py'
```

The state files remain — you can analyse the run later.

---

## 6. Sanity checks before launch (this is what I did in Cowork)

✅ `python -m pytest tests/ -q` → 94/94 passing
✅ `python live/telegram_smoke_test.py` → message sent to your Telegram
✅ `python live/paper_funding_capture.py --once` → daemon opens 3 positions on BTC/ETH/SOL using real HL data
✅ `python live/smoke_long.py --cycles 5` → 5 cycles run, state persists, funding doesn't over-accrue
✅ `bash -n live/run_daemon.sh` → wrapper syntax OK
✅ Watchdog stale-heartbeat detection verified (gap 180 min > 120 threshold → alert path triggered)

---

## 7. What I expect, technically

- ~3 positions open most of the time on BTC/ETH/SOL (current HL funding is ~11 % APR on BTC, well above the 0.5 % threshold)
- ~24 funding events booked per asset per day → ~$30–80 / asset / day in paper P&L
- 10-day run expected realised paper PnL : **+$200 to +$800** if funding stays positive, **−$100 to +$400** if it goes flat/negative for half the period
- 0-2 entries / exits per asset over the whole period (funding regimes are sticky)
- Daemon CPU : <1 % average, RAM <100 MB
- Disk : <50 MB total over 10 days (mostly the funding history parquet)

---

## 8. If something goes really wrong and I can't reach Cowork

Hard fallback : **stop the daemon, save state, do nothing else**.
```bash
pkill -f paper_funding_capture; pkill -f watchdog.py
cp -r ~/Desktop/trading-bot-v2/live/state ~/Desktop/v2_state_$(date +%Y%m%d_%H%M).bak
```
We'll debrief on 3 June.

---

*Generated 2026-05-21 by Cowork V2 session. Last sanity check : commit `<tag>`.*
