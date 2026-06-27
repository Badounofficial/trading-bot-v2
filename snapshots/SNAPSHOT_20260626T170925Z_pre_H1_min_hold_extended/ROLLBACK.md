# Rollback procedure — Snapshot 20260626T170925Z (label: pre_H1_min_hold_extended)

## To restore V2 to the state captured in this snapshot :

### Step 1 — Stop all live V2 processes
```bash
pkill -f paper_funding_capture
pkill -f watchdog.py
pkill -f ob_forward_dispatcher
pkill -f "caffeinate -i"
```

### Step 2 — Restore git state
```bash
cd ~/Desktop/trading-bot-v2
# Reset working tree to the commit captured at snapshot time
git reset --hard $(cat snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/git_head.txt)

# If uncommitted changes were captured in a stash, reapply
STASH_SHA=$(cat snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/git_stash_sha.txt)
[ -n "$STASH_SHA" ] && git stash apply "$STASH_SHA"
```

### Step 3 — Restore daemon state files
```bash
cp snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/daemon_state.json live/state/ 2>/dev/null || true
cp snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/heartbeat.txt    live/state/ 2>/dev/null || true
cp snapshots/SNAPSHOT_20260626T170925Z_pre_H1_min_hold_extended/trades.jsonl     live/state/ 2>/dev/null || true
```

### Step 4 — Restart V2 daemons
```bash
cd ~/Desktop/trading-bot-v2
nohup bash live/run_daemon.sh                 > /tmp/v2_daemon.out      2>&1 &
nohup python3 live/watchdog.py                > /tmp/v2_watchdog.out    2>&1 &
nohup python3 live/ob_forward_dispatcher.py   > /tmp/v2_ob_forward.out  2>&1 &
```

### Step 5 — Verify
```bash
ps aux | grep -E "paper_funding|watchdog|ob_forward_dispatcher|caffeinate" | grep -v grep
cat live/state/heartbeat.txt   # should be fresh within minutes
```

---
*Snapshot captured automatically by scripts/v2_snapshot.sh per Principle 31.*
