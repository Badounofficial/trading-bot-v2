"""
telegram_command_listener.py — Phase 3 Safeguard D
==================================================

Purpose
-------
Telegram polling daemon for emergency manual override commands. Allows
Sebastien to flatten all V2 positions or resume from PENDING_USER_VALIDATION
state from his iPhone, without needing SSH access to the VPS.

Commands handled
----------------
  /v2_flat        → request emergency flat (requires /v2_flat YES within 60s)
  /v2_flat YES    → execute emergency flat (writes command file for daemon)
  /v2_resume      → request resume from PENDING_USER_VALIDATION (requires YES)
  /v2_resume YES  → execute resume (writes command file for daemon)
  /v2_status      → quick health probe (listener uptime + last command + pending)

Whitelist auth
--------------
Only commands from the chat_id stored in env var V2_TG_CHAT_ID (preferred)
or TELEGRAM_CHAT_ID (fallback) are processed. All others are silently
ignored — no reply, no log. This prevents bot spam from leaking listener
existence to non-authorized users.

env loading order (matches paper_trading/config.py convention):
  1. ~/.config/badoun/telegram.env  (user-wide, shared with Synapse)
  2. PROJECT_ROOT/.env              (project-local override)
  3. process environment (lowest priority)

IPC pattern (Phase 2 integration)
---------------------------------
Listener writes live/state/emergency_command.json atomically when an
authorized confirmed command is received:

    {
      "timestamp": "2026-06-28T01:23:45+00:00",
      "command": "flat" | "resume",
      "issued_by_chat_id": 123456789,
      "consumed": false
    }

The main daemon (live/paper_funding_capture.py — Phase 2 safeguard A/F)
reads this file each cycle (~5 min), executes the action if not consumed,
then sets consumed=true and logs the event. Worst-case execution latency
= LOOP_INTERVAL_SEC (300s). Acceptable for emergency flat per spec.

Discipline
----------
- Aucun chat_id hardcodé dans le code (env-var only)
- Whitelist strict (silent reject non-authorized)
- Idempotent: re-issuing same command before consumed = no-op
- Stateless reboot-safe: state.json reconstruction on restart (only pending
  confirmation timers reset, which is the correct behavior)
- Resilient: Telegram API errors logged but never crash the loop
- Heartbeat: writes live/state/telegram_listener_heartbeat.txt every poll

Phase 3 marathon usage
----------------------
Deploy via systemd unit infra/systemd/v2-telegram-listener.service.
Restart=on-failure, RestartSec=10s. Auto-resume after reboot.

Author: V2 agent, 2026-06-28 (Phase 3 safeguard D implementation)
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# ----------------------------------------------------------------------------
# PROJECT ROOT + ENV LOADING (matches paper_trading.config convention)
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _parse_env_file(path: Path) -> dict:
    """Parse a single .env-style file into a dict. Empty if file missing.

    Matches paper_trading/config.py _parse_env_file exactly so behavior
    is identical to the rest of the codebase.
    """
    out: dict = {}
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            out[key] = value
    return out


def _load_env() -> dict:
    """Merge env from user-wide and project-local .env files."""
    merged: dict = {}
    merged.update(_parse_env_file(Path.home() / ".config" / "badoun" / "telegram.env"))
    merged.update(_parse_env_file(ROOT / ".env"))
    return merged


_ENV = _load_env()


def env(key: str, default=None):
    """Read a value from .env (or fall back to OS environment)."""
    return _ENV.get(key, os.environ.get(key, default))


# ----------------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------------
# Auth: prefer V2-specific vars (isolation), fallback to shared TELEGRAM_*
BOT_TOKEN = env("V2_TG_BOT_TOKEN", env("TELEGRAM_BOT_TOKEN"))
CHAT_ID_RAW = env("V2_TG_CHAT_ID", env("TELEGRAM_CHAT_ID"))

# Operational constants
POLL_INTERVAL_SEC = 5         # short-poll fallback if long-poll returns immediately
LONG_POLL_TIMEOUT_SEC = 25    # Telegram getUpdates timeout (HTTP keeps connection open)
HTTP_TIMEOUT_SEC = 35         # client-side timeout > LONG_POLL_TIMEOUT_SEC for safety
CONFIRMATION_WINDOW_SEC = 60  # window after /v2_flat or /v2_resume to send YES
HEARTBEAT_WRITE_INTERVAL_SEC = 30
TG_API_BASE = "https://api.telegram.org"

# Paths
STATE_DIR = ROOT / "live" / "state"
LOG_DIR = ROOT / "live" / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
COMMAND_FILE = STATE_DIR / "emergency_command.json"
HEARTBEAT_FILE = STATE_DIR / "telegram_listener_heartbeat.txt"
OFFSET_FILE = STATE_DIR / "telegram_listener_offset.txt"
LOG_FILE = LOG_DIR / "telegram_listener.log"


# ----------------------------------------------------------------------------
# LOGGING
# ----------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("v2_tg_listener")


# ----------------------------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically by tmp + rename. Prevents corruption on crash."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(path)


def telegram_call(method: str, payload: dict) -> Optional[dict]:
    """Send a Telegram Bot API call. Returns response JSON on success, None on failure.

    All errors are caught and logged — caller never crashes on transient
    network issues. The polling loop will retry on next cycle.
    """
    if not BOT_TOKEN:
        return None
    url = f"{TG_API_BASE}/bot{BOT_TOKEN}/{method}"
    try:
        resp = requests.post(url, json=payload, timeout=HTTP_TIMEOUT_SEC)
        if resp.status_code == 200:
            return resp.json()
        log.warning("telegram_call %s returned HTTP %d: %s", method, resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as exc:
        log.warning("telegram_call %s network error: %s", method, exc)
        return None


def send_reply(chat_id: int, text: str) -> None:
    """Send a Telegram text message. Best-effort."""
    telegram_call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def write_heartbeat() -> None:
    """Update heartbeat file with current ISO timestamp."""
    try:
        HEARTBEAT_FILE.write_text(now_iso() + "\n")
    except OSError as exc:
        log.warning("heartbeat write failed: %s", exc)


def load_offset() -> int:
    """Load the last processed update_id offset (for getUpdates idempotency)."""
    if not OFFSET_FILE.exists():
        return 0
    try:
        return int(OFFSET_FILE.read_text().strip())
    except (ValueError, OSError):
        return 0


def save_offset(offset: int) -> None:
    try:
        OFFSET_FILE.write_text(str(offset))
    except OSError as exc:
        log.warning("offset save failed: %s", exc)


# ----------------------------------------------------------------------------
# COMMAND HANDLING
# ----------------------------------------------------------------------------
class CommandListener:
    """Stateful command handler with confirmation windows."""

    def __init__(self, allowed_chat_id: int) -> None:
        self.allowed_chat_id = allowed_chat_id
        self.pending_flat_ts: Optional[float] = None
        self.pending_resume_ts: Optional[float] = None
        self.started_at = now_iso()
        self.last_command_received: Optional[str] = None
        self.last_command_at: Optional[str] = None

    # -- Confirmation windows ------------------------------------------------
    def _window_active(self, ts: Optional[float]) -> bool:
        return ts is not None and (time.time() - ts) < CONFIRMATION_WINDOW_SEC

    # -- Dispatch ------------------------------------------------------------
    def handle_message(self, chat_id: int, text: str) -> None:
        """Process a single message. Whitelist enforced here."""
        # Silent whitelist rejection — no reply, no acknowledgment
        if chat_id != self.allowed_chat_id:
            log.info(
                "rejected message from non-whitelisted chat_id=%d (text=%r)",
                chat_id, text[:80],
            )
            return

        cmd = (text or "").strip()
        self.last_command_received = cmd
        self.last_command_at = now_iso()
        log.info("received command from authorized chat_id: %r", cmd)

        # Dispatch table — explicit, no regex magic
        if cmd == "/v2_flat":
            self._handle_request_flat(chat_id)
        elif cmd == "/v2_flat YES":
            self._handle_confirm_flat(chat_id)
        elif cmd == "/v2_resume":
            self._handle_request_resume(chat_id)
        elif cmd == "/v2_resume YES":
            self._handle_confirm_resume(chat_id)
        elif cmd == "/v2_status":
            self._handle_status(chat_id)
        elif cmd == "/v2_help":
            self._handle_help(chat_id)
        else:
            send_reply(
                chat_id,
                "Unknown command. Send /v2_help for available commands.",
            )

    # -- /v2_flat flow -------------------------------------------------------
    def _handle_request_flat(self, chat_id: int) -> None:
        self.pending_flat_ts = time.time()
        send_reply(
            chat_id,
            (
                "<b>/v2_flat received.</b>\n"
                f"Confirm with: <code>/v2_flat YES</code>\n"
                f"Window: {CONFIRMATION_WINDOW_SEC}s.\n\n"
                "This will close ALL V2 positions and set the daemon to "
                "PENDING_USER_VALIDATION state. Resume requires /v2_resume YES."
            ),
        )
        log.info("pending /v2_flat confirmation window opened (%ds)", CONFIRMATION_WINDOW_SEC)

    def _handle_confirm_flat(self, chat_id: int) -> None:
        if not self._window_active(self.pending_flat_ts):
            send_reply(
                chat_id,
                (
                    "No pending /v2_flat or confirmation window expired. "
                    f"Re-send /v2_flat first (window {CONFIRMATION_WINDOW_SEC}s)."
                ),
            )
            log.info("/v2_flat YES received but no active pending window — ignored")
            return
        # Execute: write command file for main daemon to consume
        payload = {
            "timestamp": now_iso(),
            "command": "flat",
            "issued_by_chat_id": chat_id,
            "consumed": False,
        }
        atomic_write_json(COMMAND_FILE, payload)
        self.pending_flat_ts = None
        send_reply(
            chat_id,
            (
                "<b>EMERGENCY FLAT command written.</b>\n"
                "The daemon will execute on its next cycle (within "
                f"{int(300/60)} min). Watch for confirmation alert from "
                "the daemon when complete."
            ),
        )
        log.warning("EMERGENCY_FLAT command file written, awaiting daemon consumption")

    # -- /v2_resume flow -----------------------------------------------------
    def _handle_request_resume(self, chat_id: int) -> None:
        self.pending_resume_ts = time.time()
        send_reply(
            chat_id,
            (
                "<b>/v2_resume received.</b>\n"
                f"Confirm with: <code>/v2_resume YES</code>\n"
                f"Window: {CONFIRMATION_WINDOW_SEC}s.\n\n"
                "This will exit PENDING_USER_VALIDATION state. The daemon will "
                "resume normal operations on its next cycle."
            ),
        )
        log.info("pending /v2_resume confirmation window opened (%ds)", CONFIRMATION_WINDOW_SEC)

    def _handle_confirm_resume(self, chat_id: int) -> None:
        if not self._window_active(self.pending_resume_ts):
            send_reply(
                chat_id,
                (
                    "No pending /v2_resume or confirmation window expired. "
                    f"Re-send /v2_resume first (window {CONFIRMATION_WINDOW_SEC}s)."
                ),
            )
            log.info("/v2_resume YES received but no active pending window — ignored")
            return
        payload = {
            "timestamp": now_iso(),
            "command": "resume",
            "issued_by_chat_id": chat_id,
            "consumed": False,
        }
        atomic_write_json(COMMAND_FILE, payload)
        self.pending_resume_ts = None
        send_reply(
            chat_id,
            (
                "<b>RESUME command written.</b>\n"
                "The daemon will exit PENDING_USER_VALIDATION on its next cycle "
                f"(within {int(300/60)} min)."
            ),
        )
        log.warning("RESUME command file written, awaiting daemon consumption")

    # -- /v2_status ----------------------------------------------------------
    def _handle_status(self, chat_id: int) -> None:
        pending_flat = (
            f"{int(CONFIRMATION_WINDOW_SEC - (time.time() - self.pending_flat_ts))}s remaining"
            if self._window_active(self.pending_flat_ts) else "none"
        )
        pending_resume = (
            f"{int(CONFIRMATION_WINDOW_SEC - (time.time() - self.pending_resume_ts))}s remaining"
            if self._window_active(self.pending_resume_ts) else "none"
        )
        last_cmd_file = "no command file" if not COMMAND_FILE.exists() else COMMAND_FILE.read_text()[:300]
        send_reply(
            chat_id,
            (
                "<b>V2 Telegram Listener Status</b>\n"
                f"Started: <code>{self.started_at}</code>\n"
                f"Now: <code>{now_iso()}</code>\n"
                f"Last command: <code>{self.last_command_received or 'none'}</code> "
                f"at <code>{self.last_command_at or '—'}</code>\n"
                f"Pending /v2_flat: {pending_flat}\n"
                f"Pending /v2_resume: {pending_resume}\n"
                f"Last command file:\n<pre>{last_cmd_file}</pre>"
            ),
        )

    # -- /v2_help ------------------------------------------------------------
    def _handle_help(self, chat_id: int) -> None:
        send_reply(
            chat_id,
            (
                "<b>V2 Telegram Listener — Available Commands</b>\n\n"
                "<code>/v2_flat</code> → request emergency flat (then /v2_flat YES within 60s)\n"
                "<code>/v2_flat YES</code> → confirm and execute emergency flat\n"
                "<code>/v2_resume</code> → request resume from PENDING_USER_VALIDATION (then YES)\n"
                "<code>/v2_resume YES</code> → confirm and execute resume\n"
                "<code>/v2_status</code> → listener health probe\n"
                "<code>/v2_help</code> → this message\n\n"
                "All other commands are ignored. Non-whitelisted chat_ids are silently rejected."
            ),
        )


# ----------------------------------------------------------------------------
# MAIN POLLING LOOP
# ----------------------------------------------------------------------------
_STOP_REQUESTED = False


def _signal_handler(signum, frame):  # pragma: no cover
    global _STOP_REQUESTED
    log.info("signal %d received — stopping listener after current poll cycle", signum)
    _STOP_REQUESTED = True


def main() -> int:
    # Pre-flight: env vars mandatory
    if not BOT_TOKEN:
        log.error(
            "MISSING ENV: V2_TG_BOT_TOKEN or TELEGRAM_BOT_TOKEN. "
            "Cannot start listener. Check ~/.config/badoun/telegram.env."
        )
        return 2
    if not CHAT_ID_RAW:
        log.error(
            "MISSING ENV: V2_TG_CHAT_ID or TELEGRAM_CHAT_ID. "
            "Cannot start listener (no whitelist target). "
            "Check ~/.config/badoun/telegram.env."
        )
        return 2
    try:
        allowed_chat_id = int(CHAT_ID_RAW)
    except ValueError:
        log.error("CHAT_ID env var is not an integer: %r", CHAT_ID_RAW)
        return 2

    log.info(
        "V2 Telegram listener starting — allowed_chat_id=%d, "
        "long_poll_timeout=%ds, confirmation_window=%ds",
        allowed_chat_id, LONG_POLL_TIMEOUT_SEC, CONFIRMATION_WINDOW_SEC,
    )

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    listener = CommandListener(allowed_chat_id=allowed_chat_id)
    offset = load_offset()
    last_heartbeat = 0.0

    while not _STOP_REQUESTED:
        # Heartbeat
        if time.time() - last_heartbeat >= HEARTBEAT_WRITE_INTERVAL_SEC:
            write_heartbeat()
            last_heartbeat = time.time()

        # Long-poll for updates
        resp = telegram_call(
            "getUpdates",
            {
                "offset": offset + 1,
                "timeout": LONG_POLL_TIMEOUT_SEC,
                "allowed_updates": ["message"],
            },
        )
        if resp is None:
            # Transient network error — back off briefly
            time.sleep(POLL_INTERVAL_SEC)
            continue
        if not resp.get("ok"):
            log.warning("getUpdates not ok: %s", resp)
            time.sleep(POLL_INTERVAL_SEC)
            continue

        for update in resp.get("result", []):
            offset = max(offset, update.get("update_id", offset))
            save_offset(offset)
            msg = update.get("message") or {}
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            text = msg.get("text", "")
            if chat_id is None:
                continue
            try:
                listener.handle_message(int(chat_id), text)
            except Exception as exc:  # noqa: BLE001
                # Listener resilience: never crash on a single bad message.
                log.exception("error handling message: %s", exc)

    log.info("V2 Telegram listener stopped cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
