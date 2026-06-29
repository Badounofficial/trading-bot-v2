#!/usr/bin/env bash
# check_v2_heartbeat_secondary.sh — Phase 3 Safeguard B
# ======================================================
# Independent 2nd-tier watchdog for the V2 daemon, designed to run from the
# Hetzner Storage Box (NOT from the VPS itself). Orthogonal infra means a
# VPS-level failure that kills both the daemon and its primary watchdog still
# triggers an alert from a different host.
#
# Architecture
# ------------
#   Storage Box (cron */5)
#       │  (1) SSH to VPS with restricted key
#       ▼
#   VPS reads live/state/heartbeat.txt
#       │  (2) returns ISO timestamp
#       ▼
#   Compute age = now - heartbeat_ts
#   If age > V2_HEARTBEAT_MAX_AGE_MIN → curl Telegram with a SEPARATE bot token
#   Log all outcomes to a rotated file under V2_WATCHDOG_LOG_DIR.
#
# Orthogonality
# -------------
# The Telegram credentials used here MUST come from a separate bot than the
# V2 daemon's primary alerter. Same chat_id is fine (Sebastien sees both),
# but a different bot token ensures that if Telegram blocks the V2 daemon's
# bot for any reason (rate limits, suspension), this watchdog still reaches
# him.
#
# Idempotency
# -----------
# Re-firing every 5 min while the heartbeat is stale for hours would spam
# Sebastien. The script tracks last-alert-sent timestamp in a state file and
# enforces a minimum re-fire interval (V2_WATCHDOG_REFIRE_INTERVAL_MIN).
#
# Env loading
# -----------
# Reads ~/.config/v2_watchdog/secondary.env (see DEPLOYMENT.md). The file must
# exist; the script aborts cleanly with non-zero exit if not.
#
# Required env vars
# -----------------
#   V2_VPS_HOST                  → IP or hostname (e.g. 5.161.246.190)
#   V2_VPS_USER                  → SSH user on VPS (e.g. badoun)
#   V2_VPS_HEARTBEAT_PATH        → absolute path to heartbeat.txt on VPS
#   V2_SSH_KEY                   → path to SSH private key (e.g. ~/.ssh/v2_vps_id_ed25519)
#   V2_WATCHDOG_TG_BOT_TOKEN     → SEPARATE bot token (not V2 daemon's)
#   V2_WATCHDOG_TG_CHAT_ID       → recipient chat_id (Sebastien)
#   V2_HEARTBEAT_MAX_AGE_MIN     → alert threshold (default 15)
#   V2_WATCHDOG_REFIRE_INTERVAL_MIN → min interval between repeated alerts (default 60)
#   V2_WATCHDOG_LOG_DIR          → log directory (default ~/storagebox_cron_log)
#   V2_WATCHDOG_STATE_DIR        → state directory (default ~/storagebox_cron_state)
#
# Author: V2 agent, 2026-06-28 (Phase 3 Safeguard B implementation)

set -uo pipefail

# ──────────────────────────────────────────────────────────────────────────
# Env loading
# ──────────────────────────────────────────────────────────────────────────
ENV_FILE="${V2_WATCHDOG_ENV_FILE:-$HOME/.config/v2_watchdog/secondary.env}"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FATAL env file missing: $ENV_FILE" >&2
    exit 2
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# Defaults
: "${V2_HEARTBEAT_MAX_AGE_MIN:=15}"
: "${V2_WATCHDOG_REFIRE_INTERVAL_MIN:=60}"
: "${V2_WATCHDOG_LOG_DIR:=$HOME/storagebox_cron_log}"
: "${V2_WATCHDOG_STATE_DIR:=$HOME/storagebox_cron_state}"

# Mandatory env vars — abort if any missing
for var in V2_VPS_HOST V2_VPS_USER V2_VPS_HEARTBEAT_PATH V2_SSH_KEY \
           V2_WATCHDOG_TG_BOT_TOKEN V2_WATCHDOG_TG_CHAT_ID; do
    if [[ -z "${!var:-}" ]]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FATAL missing env: $var" >&2
        exit 2
    fi
done

mkdir -p "$V2_WATCHDOG_LOG_DIR" "$V2_WATCHDOG_STATE_DIR"
LOG_FILE="$V2_WATCHDOG_LOG_DIR/v2_heartbeat_secondary.log"
LAST_ALERT_FILE="$V2_WATCHDOG_STATE_DIR/last_alert_sent.ts"

# Simple log rotation: if log > 5 MB, roll to .old (one rotation deep)
if [[ -f "$LOG_FILE" ]] && [[ $(stat -c %s "$LOG_FILE" 2>/dev/null || echo 0) -gt 5242880 ]]; then
    mv -f "$LOG_FILE" "${LOG_FILE}.old"
fi

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

# ──────────────────────────────────────────────────────────────────────────
# Telegram send (best-effort, never fail the script)
# ──────────────────────────────────────────────────────────────────────────
send_telegram_alert() {
    local message="$1"
    local response
    response=$(curl -s -m 10 \
        -X POST "https://api.telegram.org/bot${V2_WATCHDOG_TG_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${V2_WATCHDOG_TG_CHAT_ID}" \
        --data-urlencode "text=${message}" \
        -d "parse_mode=HTML" 2>&1 || true)
    if echo "$response" | grep -q '"ok":true'; then
        log "telegram alert sent OK"
        date -u +%s > "$LAST_ALERT_FILE"
        return 0
    fi
    log "TELEGRAM SEND FAIL response=${response:0:200}"
    return 1
}

# ──────────────────────────────────────────────────────────────────────────
# Idempotency check — should we re-fire?
# ──────────────────────────────────────────────────────────────────────────
should_refire_alert() {
    if [[ ! -f "$LAST_ALERT_FILE" ]]; then
        return 0   # never alerted → fire
    fi
    local last_alert_epoch
    last_alert_epoch=$(cat "$LAST_ALERT_FILE" 2>/dev/null || echo 0)
    local now_epoch
    now_epoch=$(date -u +%s)
    local elapsed_min=$(( (now_epoch - last_alert_epoch) / 60 ))
    if [[ $elapsed_min -ge $V2_WATCHDOG_REFIRE_INTERVAL_MIN ]]; then
        return 0   # interval expired → fire
    fi
    log "refire suppressed (last alert ${elapsed_min}min ago < ${V2_WATCHDOG_REFIRE_INTERVAL_MIN}min interval)"
    return 1
}

# ──────────────────────────────────────────────────────────────────────────
# SSH + heartbeat fetch
# ──────────────────────────────────────────────────────────────────────────
SSH_OPTS=(-i "$V2_SSH_KEY" -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
HEARTBEAT_RAW=$(ssh "${SSH_OPTS[@]}" "${V2_VPS_USER}@${V2_VPS_HOST}" \
    "cat ${V2_VPS_HEARTBEAT_PATH}" 2>&1)
SSH_EXIT=$?

if [[ $SSH_EXIT -ne 0 ]]; then
    log "SSH FAIL exit=${SSH_EXIT} response=${HEARTBEAT_RAW:0:300}"
    if should_refire_alert; then
        send_telegram_alert "🚨 V2 2ND WATCHDOG (Storage Box) — SSH to VPS FAILED. Cannot read heartbeat. VPS may be down or unreachable. Exit=${SSH_EXIT}. Refire interval ${V2_WATCHDOG_REFIRE_INTERVAL_MIN}min."
    fi
    exit 0   # cron should not retry; the next tick handles transients
fi

# Sanitize heartbeat (single-line ISO timestamp expected)
HEARTBEAT_TS=$(echo "$HEARTBEAT_RAW" | head -n1 | tr -d '[:space:]')
if [[ -z "$HEARTBEAT_TS" ]]; then
    log "EMPTY heartbeat received from VPS"
    if should_refire_alert; then
        send_telegram_alert "🚨 V2 2ND WATCHDOG — heartbeat.txt on VPS is EMPTY. Daemon may have crashed before writing first heartbeat."
    fi
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────
# Age computation
# ──────────────────────────────────────────────────────────────────────────
# Convert ISO 8601 timestamp to epoch using GNU date (Storage Box runs Linux).
HEARTBEAT_EPOCH=$(date -u -d "$HEARTBEAT_TS" +%s 2>/dev/null || echo 0)
if [[ $HEARTBEAT_EPOCH -eq 0 ]]; then
    log "INVALID heartbeat timestamp: $HEARTBEAT_TS"
    if should_refire_alert; then
        send_telegram_alert "🚨 V2 2ND WATCHDOG — heartbeat.txt has INVALID timestamp format: ${HEARTBEAT_TS:0:80}"
    fi
    exit 0
fi

NOW_EPOCH=$(date -u +%s)
AGE_SEC=$(( NOW_EPOCH - HEARTBEAT_EPOCH ))
AGE_MIN=$(( AGE_SEC / 60 ))

# ──────────────────────────────────────────────────────────────────────────
# Decision: alert or quiet success
# ──────────────────────────────────────────────────────────────────────────
if [[ $AGE_MIN -ge $V2_HEARTBEAT_MAX_AGE_MIN ]]; then
    log "STALE heartbeat: age=${AGE_MIN}min >= threshold ${V2_HEARTBEAT_MAX_AGE_MIN}min (hb=${HEARTBEAT_TS})"
    if should_refire_alert; then
        send_telegram_alert "🚨 V2 2ND WATCHDOG (Storage Box) — heartbeat STALE ${AGE_MIN} min (threshold ${V2_HEARTBEAT_MAX_AGE_MIN} min). Primary watchdog may also be down. Last heartbeat: ${HEARTBEAT_TS}. VPS may need investigation."
    fi
    exit 0
fi

# Healthy path — log only (no Telegram on every 5min healthy cycle).
log "OK age=${AGE_MIN}min (hb=${HEARTBEAT_TS})"

# If we previously fired an alert, send an "all-clear" recovery message once.
if [[ -f "$LAST_ALERT_FILE" ]]; then
    log "recovery detected — sending all-clear and clearing alert state"
    send_telegram_alert "✅ V2 2ND WATCHDOG — heartbeat RECOVERED (age ${AGE_MIN}min). Last heartbeat: ${HEARTBEAT_TS}."
    rm -f "$LAST_ALERT_FILE"
fi

exit 0
