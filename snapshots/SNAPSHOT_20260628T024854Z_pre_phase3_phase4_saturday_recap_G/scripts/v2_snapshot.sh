#!/usr/bin/env bash
# v2_snapshot.sh — P31 reversibility checkpoint
# Captures git state + daemon state + heartbeat + processes BEFORE any mutating action.
# Usage : bash scripts/v2_snapshot.sh [label]
# Output : snapshots/SNAPSHOT_<UTC_TS>_<label>/ with ROLLBACK.md procedure inside.
#
# Per Principle 31 (Backup-Before-Action) and V2 PRINCIPLES.md P15:
#   "Pas de rollback = pas d'action."
# Every script that mutates live/state/*.json or strategies/*.py MUST
# invoke this snapshot beforehand. Convention enforced manually Phase 1,
# pre-commit hook Phase 2.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LABEL="${1:-manual}"
TS="$(date -u +"%Y%m%dT%H%M%SZ")"
DIR="snapshots/SNAPSHOT_${TS}_${LABEL}"
mkdir -p "$DIR"

# 1. Git state (HEAD, status, uncommitted diff, stash hash if applicable)
git rev-parse HEAD                  > "$DIR/git_head.txt"           2>&1 || echo "git rev-parse failed" > "$DIR/git_head.txt"
git status --short                  > "$DIR/git_status.txt"         2>&1 || true
git diff                            > "$DIR/git_uncommitted.diff"   2>&1 || true
git stash create                    > "$DIR/git_stash_sha.txt"      2>&1 || true
git branch --show-current           > "$DIR/git_branch.txt"         2>&1 || true

# 2. Daemon state (balance, positions, funding accrued, heartbeat, trade ledger)
if [ -f "live/state/daemon_state.json" ]; then
  cp "live/state/daemon_state.json" "$DIR/"
fi
if [ -f "live/state/heartbeat.txt" ]; then
  cp "live/state/heartbeat.txt" "$DIR/"
fi
if [ -f "live/state/trades.jsonl" ]; then
  cp "live/state/trades.jsonl" "$DIR/"
fi

# 3. Live process state (which V2 processes are running at snapshot time)
ps aux 2>/dev/null \
  | grep -E "paper_funding|watchdog|ob_forward_dispatcher|caffeinate|run_daemon" \
  | grep -v grep                    > "$DIR/processes.txt"          2>&1 || true

# 4. Manifest with ROLLBACK procedure embedded
cat > "$DIR/ROLLBACK.md" <<EOF
# Rollback procedure — Snapshot ${TS} (label: ${LABEL})

## To restore V2 to the state captured in this snapshot :

### Step 1 — Stop all live V2 processes
\`\`\`bash
pkill -f paper_funding_capture
pkill -f watchdog.py
pkill -f ob_forward_dispatcher
pkill -f "caffeinate -i"
\`\`\`

### Step 2 — Restore git state
\`\`\`bash
cd ~/Desktop/trading-bot-v2
# Reset working tree to the commit captured at snapshot time
git reset --hard \$(cat snapshots/SNAPSHOT_${TS}_${LABEL}/git_head.txt)

# If uncommitted changes were captured in a stash, reapply
STASH_SHA=\$(cat snapshots/SNAPSHOT_${TS}_${LABEL}/git_stash_sha.txt)
[ -n "\$STASH_SHA" ] && git stash apply "\$STASH_SHA"
\`\`\`

### Step 3 — Restore daemon state files
\`\`\`bash
cp snapshots/SNAPSHOT_${TS}_${LABEL}/daemon_state.json live/state/ 2>/dev/null || true
cp snapshots/SNAPSHOT_${TS}_${LABEL}/heartbeat.txt    live/state/ 2>/dev/null || true
cp snapshots/SNAPSHOT_${TS}_${LABEL}/trades.jsonl     live/state/ 2>/dev/null || true
\`\`\`

### Step 4 — Restart V2 daemons
\`\`\`bash
cd ~/Desktop/trading-bot-v2
nohup bash live/run_daemon.sh                 > /tmp/v2_daemon.out      2>&1 &
nohup python3 live/watchdog.py                > /tmp/v2_watchdog.out    2>&1 &
nohup python3 live/ob_forward_dispatcher.py   > /tmp/v2_ob_forward.out  2>&1 &
\`\`\`

### Step 5 — Verify
\`\`\`bash
ps aux | grep -E "paper_funding|watchdog|ob_forward_dispatcher|caffeinate" | grep -v grep
cat live/state/heartbeat.txt   # should be fresh within minutes
\`\`\`

---
*Snapshot captured automatically by scripts/v2_snapshot.sh per Principle 31.*
EOF

# 5. Summary line to stdout
echo "✓ Snapshot saved → $DIR"
echo "✓ Rollback procedure → $DIR/ROLLBACK.md"
echo "✓ HEAD captured     → $(cat "$DIR/git_head.txt")"
