"""
watchdog.py — Independent process that watches the daemon's heartbeat.

Why a separate process: if the main daemon froze or crashed-without-restart,
it can't alert. The watchdog is the only thing that can notice silence.

Behaviour:
  - Every WATCHDOG_INTERVAL_SEC (default 600 = 10 min)
  - Reads live/state/heartbeat.txt
  - If the timestamp is older than ANOMALY_HEARTBEAT_MAX_GAP_MIN minutes
    → send Telegram alert ONCE, then sleep 1h before re-checking
  - When heartbeat recovers → send "recovered" message ONCE

Usage:
  python live/watchdog.py            # foreground
  nohup python live/watchdog.py &    # detached

Run alongside the main daemon. The watchdog has zero state-write
responsibility — it can run any number of instances safely.
"""
from __future__ import annotations
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_trading import config as pt_config
from paper_trading.monitoring import TelegramAlerter

HEARTBEAT_PATH = ROOT / "live" / "state" / "heartbeat.txt"
WATCHDOG_INTERVAL_SEC = 600
MAX_GAP_MIN = 120
RECOVERY_BACKOFF_SEC = 3600   # don't spam — wait 1h between alerts of same type


def read_heartbeat() -> datetime | None:
    if not HEARTBEAT_PATH.exists():
        return None
    try:
        ts_iso = HEARTBEAT_PATH.read_text().strip()
        return datetime.fromisoformat(ts_iso)
    except Exception:
        return None


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [WATCHDOG] %(message)s",
    )
    alerter = TelegramAlerter() if pt_config.TELEGRAM_ENABLED else None
    if alerter is None:
        logging.warning("Telegram disabled — watchdog will log only.")

    last_alert_kind: str | None = None      # 'stale' or 'recovered' or None
    last_alert_ts: datetime | None = None

    while True:
        try:
            hb = read_heartbeat()
            now = datetime.now(timezone.utc)
            if hb is None:
                gap_min = None
                state = "no_heartbeat_file"
            else:
                # Ensure tz-aware
                if hb.tzinfo is None:
                    hb = hb.replace(tzinfo=timezone.utc)
                gap_min = (now - hb).total_seconds() / 60
                state = "stale" if gap_min > MAX_GAP_MIN else "fresh"

            logging.info("heartbeat=%s gap=%s state=%s", hb, gap_min, state)

            # Decide whether to alert
            if state in ("stale", "no_heartbeat_file"):
                if last_alert_kind != "stale" or (last_alert_ts and (now - last_alert_ts).total_seconds() > RECOVERY_BACKOFF_SEC):
                    msg = (f"🚨 V2 WATCHDOG — daemon heartbeat {state}. "
                           f"Last seen {hb} ({gap_min:.0f} min ago). "
                           f"SSH the Mac and check: `tail live/logs/wrapper_*.log`. "
                           f"To restart: `bash live/run_daemon.sh`.")
                    if alerter:
                        try:
                            alerter.send(msg)
                            last_alert_kind = "stale"; last_alert_ts = now
                        except Exception as e:
                            logging.warning("alert send failed: %s", e)
                    else:
                        logging.warning("ALERT (no Telegram): %s", msg)
            else:  # fresh
                if last_alert_kind == "stale":
                    msg = f"💚 V2 WATCHDOG — daemon recovered. Heartbeat fresh ({gap_min:.0f} min ago)."
                    if alerter:
                        try:
                            alerter.send(msg)
                            last_alert_kind = "recovered"; last_alert_ts = now
                        except Exception as e:
                            logging.warning("recovery msg failed: %s", e)
                    else:
                        logging.info("RECOVERED (no Telegram): %s", msg)

        except Exception as e:
            logging.exception("watchdog loop error: %s", e)

        time.sleep(WATCHDOG_INTERVAL_SEC)


if __name__ == "__main__":
    main()
