# Storage Box 2nd Watchdog — Deployment Guide (Phase 3 Safeguard B)

**Purpose** : independent 2nd-tier watchdog for the V2 daemon, running on the Hetzner Storage Box (orthogonal infra to the VPS). Closes the silent-failure gap where both the daemon and the primary VPS watchdog die together.

**Cadence** : every 5 minutes (cron). Alert threshold: heartbeat stale > 15 min. Re-fire suppression: 60 min between repeated alerts of the same condition. Recovery alert sent once when heartbeat returns to normal.

---

## Prerequisites

1. **Storage Box account active** (Hetzner) with SSH access enabled. The Storage Box ID looks like `u123456`. Backups script likely already configured (per Sebastien's existing setup).
2. **Linux shell on Storage Box** : Hetzner Storage Boxes support `bash` + `curl` + `ssh` + `cron` + `date` (GNU coreutils). Verify with `ssh u123456@u123456.your-storagebox.de "bash --version && curl --version && date --version"`.
3. **SSH key pair from Storage Box → VPS** :
    - If you already have a key configured for daily backup pulls from Storage Box to VPS, reuse it.
    - If not, generate one on the Storage Box (or locally, then upload pub key to VPS):
      ```bash
      # On Storage Box (via SSH):
      ssh-keygen -t ed25519 -f ~/.ssh/v2_vps_id_ed25519 -N "" -C "v2-watchdog-storagebox"
      # Then copy the .pub line to VPS ~/.ssh/authorized_keys for the badoun user.
      ```
    - **Recommended VPS-side hardening** : restrict this key in `authorized_keys` to read-only heartbeat fetch:
      ```
      command="cat /home/badoun/trading-bot-v2/live/state/heartbeat.txt",no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... v2-watchdog-storagebox
      ```
      This way, even if the key is compromised, it can ONLY read the heartbeat file.
4. **SEPARATE Telegram bot** (orthogonality requirement). Create a new bot via @BotFather. Name it e.g. "V2 Watchdog Secondary". Save its token. **Do NOT reuse the V2 daemon's primary bot token.** Use the same recipient `chat_id` as Sebastien (same person, different bot).

---

## Five-step deployment

### Step 1 — Copy the script to Storage Box

From your Mac (or another machine with both repos):

```bash
scp ~/Desktop/trading-bot-v2/infra/storagebox_cron/check_v2_heartbeat_secondary.sh \
    u123456@u123456.your-storagebox.de:~/storagebox_cron/
```

(Adjust `u123456` and `your-storagebox` to your actual Storage Box ID + region.)

### Step 2 — Make it executable on Storage Box

```bash
ssh u123456@u123456.your-storagebox.de
cd ~/storagebox_cron
chmod +x check_v2_heartbeat_secondary.sh
```

### Step 3 — Verify SSH from Storage Box to VPS works

```bash
ssh -i ~/.ssh/v2_vps_id_ed25519 badoun@5.161.246.190 \
    "cat /home/badoun/trading-bot-v2/live/state/heartbeat.txt"
```

Expected output: a single ISO 8601 timestamp like `2026-06-28T12:34:56+00:00`. If you get a permission error, fix the key setup (Prerequisites step 3). If you get "file not found", the daemon has never run — start it on the VPS first.

### Step 4 — Configure environment file on Storage Box

```bash
mkdir -p ~/.config/v2_watchdog
chmod 700 ~/.config/v2_watchdog
cat > ~/.config/v2_watchdog/secondary.env << 'EOF'
# V2 2nd Watchdog — Storage Box environment
# DO NOT commit this file anywhere. Tokens are secrets.

# VPS reachability
V2_VPS_HOST=5.161.246.190
V2_VPS_USER=badoun
V2_VPS_HEARTBEAT_PATH=/home/badoun/trading-bot-v2/live/state/heartbeat.txt
V2_SSH_KEY=/home/u123456/.ssh/v2_vps_id_ed25519

# Telegram — SEPARATE bot token (NOT V2 daemon's token!)
V2_WATCHDOG_TG_BOT_TOKEN=<paste new bot token from @BotFather here>
V2_WATCHDOG_TG_CHAT_ID=<paste Sebastien's chat_id here — same person, different bot>

# Thresholds (defaults shown — override only if you have a reason)
V2_HEARTBEAT_MAX_AGE_MIN=15
V2_WATCHDOG_REFIRE_INTERVAL_MIN=60

# Local paths on Storage Box
V2_WATCHDOG_LOG_DIR=/home/u123456/storagebox_cron_log
V2_WATCHDOG_STATE_DIR=/home/u123456/storagebox_cron_state
EOF
chmod 600 ~/.config/v2_watchdog/secondary.env
```

Replace `<paste new bot token...>` and `<paste Sebastien's chat_id here>` with actual values. Adjust `/home/u123456/` to your real Storage Box home path.

### Step 5 — Configure cron and verify

```bash
# Run once manually to validate everything works:
~/storagebox_cron/check_v2_heartbeat_secondary.sh
tail -10 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected: "OK age=Xmin (hb=...)" if VPS daemon is healthy.

# If output is as expected, install cron:
crontab -e
# Add this line (every 5 min):
*/5 * * * * /home/u123456/storagebox_cron/check_v2_heartbeat_secondary.sh

# Verify cron is loaded:
crontab -l | grep check_v2_heartbeat
```

---

## Manual test steps (post-deploy validation)

Run each of these from the Storage Box shell to confirm the watchdog reacts as expected. Each should produce both a log line and a Telegram message in the expected case.

### Test M1 — Healthy path (no alert expected)

```bash
~/storagebox_cron/check_v2_heartbeat_secondary.sh
tail -1 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected: "OK age=Xmin (hb=...)"
# NO Telegram should arrive.
```

### Test M2 — Stale heartbeat alert

Temporarily set a very small max-age via env override (NOT in the persistent env file):

```bash
V2_HEARTBEAT_MAX_AGE_MIN=0 ~/storagebox_cron/check_v2_heartbeat_secondary.sh
tail -2 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected log: "STALE heartbeat: age=Xmin >= threshold 0min..."
# Expected log: "telegram alert sent OK"
# Expected Telegram message: "🚨 V2 2ND WATCHDOG (Storage Box) — heartbeat STALE..."
```

### Test M3 — Idempotency (re-fire suppression)

Immediately after M2, re-run with same override:

```bash
V2_HEARTBEAT_MAX_AGE_MIN=0 ~/storagebox_cron/check_v2_heartbeat_secondary.sh
tail -2 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected log: "refire suppressed (last alert Xmin ago < 60min interval)"
# NO new Telegram should arrive.
```

### Test M4 — Recovery / all-clear

After M2/M3, clear the override (so threshold is back to 15min) and run normally:

```bash
~/storagebox_cron/check_v2_heartbeat_secondary.sh
tail -3 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected log: "OK age=Xmin..."
# Expected log: "recovery detected — sending all-clear and clearing alert state"
# Expected Telegram message: "✅ V2 2ND WATCHDOG — heartbeat RECOVERED..."
# State file should now be gone:
ls -la ~/storagebox_cron_state/last_alert_sent.ts
# → "No such file or directory"
```

### Test M5 — SSH failure simulation

Temporarily break the SSH path to confirm graceful failure:

```bash
V2_VPS_HOST=192.0.2.1 ~/storagebox_cron/check_v2_heartbeat_secondary.sh
# 192.0.2.1 is the TEST-NET-1 RFC 5737 address — guaranteed unreachable.
tail -2 ~/storagebox_cron_log/v2_heartbeat_secondary.log
# Expected log: "SSH FAIL exit=255 response=..."
# Expected log: "telegram alert sent OK" (if no prior alert in last 60min)
# Expected Telegram message: "🚨 V2 2ND WATCHDOG (Storage Box) — SSH to VPS FAILED..."
```

### Test M6 — Missing env file

```bash
mv ~/.config/v2_watchdog/secondary.env ~/.config/v2_watchdog/secondary.env.bak
~/storagebox_cron/check_v2_heartbeat_secondary.sh; echo "exit=$?"
# Expected stderr: "FATAL env file missing: /home/.../secondary.env"
# Expected exit code: 2
mv ~/.config/v2_watchdog/secondary.env.bak ~/.config/v2_watchdog/secondary.env
```

---

## Operational notes

- **Log rotation** : the script auto-rotates `v2_heartbeat_secondary.log` to `.old` when it exceeds 5 MB. One generation deep — older logs are overwritten on next rotation. If you need longer history, set up `logrotate` separately.
- **State file cleanup** : `last_alert_sent.ts` is auto-deleted on recovery. If you want to force a fresh state, `rm ~/storagebox_cron_state/last_alert_sent.ts`.
- **Cron silent failures** : crontab does NOT send mail on failed runs by default. Always check `~/storagebox_cron_log/v2_heartbeat_secondary.log` regularly OR set `MAILTO=` at the top of your crontab if you have local mail.
- **Token rotation** : if you ever rotate the V2 daemon's primary bot token, the watchdog token can stay the same (and vice versa). This is the whole point of orthogonality.
- **Cron timing drift** : a 5-min cron fires up to 60s late typically. Combined with the 15-min heartbeat threshold, this gives at most a 16-min window before alert — well within the spec budget.

## Failure modes covered

| Failure mode | Detection latency | Alert source |
|---|---|---|
| V2 daemon crashed | ≤ 20 min (15min threshold + 5min cron + propagation) | Storage Box (this script) + primary watchdog (VPS) |
| V2 daemon AND primary watchdog both dead | ≤ 20 min | Storage Box (this script) — sole detector |
| VPS network unreachable | ≤ 5 min (SSH timeout 10s + cron) | Storage Box (SSH FAIL path) |
| VPS reboot in progress | covered by recovery flow once heartbeat returns | Storage Box (alert then all-clear) |
| Storage Box itself dead | NOT detected by this script (single point of failure on the watchdog watchdog) | Future Phase: add cloud cron-job.org as 3rd tier if needed |

The remaining uncovered failure (Storage Box itself down) is acceptable for Phase 3 since Storage Box infrastructure is independent from Sebastien's VPS provider and Hetzner is unlikely to have simultaneous outages on both products.

---

*Deployment guide written by V2 agent, 2026-06-28, for Phase 3 Safeguard B. After deployment, run all 6 manual tests above and confirm in your Telegram chat that the expected messages arrive. Tick each test off in `analysis/phase3_safeguards_sandbox_test_results.md` (Phase 6 deliverable).*
