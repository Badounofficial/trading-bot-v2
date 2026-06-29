"""
telegram_smoke_test.py — One-shot validation of the Telegram alert chain.

Reads credentials from ~/.config/badoun/telegram.env (via paper_trading.config),
sends the agreed smoke-test message, prints the outcome.

Usage (run on Badoun's Mac):
    cd ~/Desktop/trading-bot-v2
    python live/telegram_smoke_test.py

Exit codes:
    0 — message sent OK
    1 — credentials missing
    2 — Telegram API rejected the message (token / chat_id invalid)
    3 — network / unexpected error
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from paper_trading import config


MESSAGE = (
    "✅ V2 — Telegram intégration testée.\n"
    "Heartbeats quotidiens prévus à 12h UTC.\n"
    "Rapport intermédiaire le 28 mai.\n"
    "Alertes uniquement si PnL < -10% ou bug critique.\n"
    "Tu peux partir tranquille."
)


def main() -> int:
    print(f"[smoke] credentials loaded from : ~/.config/badoun/telegram.env (+ project .env if present)")
    print(f"[smoke] TELEGRAM_ENABLED        : {config.TELEGRAM_ENABLED}")
    if not config.TELEGRAM_ENABLED:
        print("[smoke] FAIL — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        print("[smoke] Check the file at ~/.config/badoun/telegram.env contains both keys.")
        return 1

    print(f"[smoke] chat_id                 : {config.TELEGRAM_CHAT_ID}")
    print(f"[smoke] sending message …")
    try:
        import requests
    except ImportError:
        print("[smoke] FAIL — `requests` not installed. Run: pip install requests")
        return 3

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": MESSAGE,
            "disable_notification": False,
        }, timeout=10)
    except Exception as e:
        print(f"[smoke] FAIL — network/HTTP error: {e}")
        return 3

    if r.status_code == 200 and r.json().get("ok"):
        print("[smoke] OK — message sent. Check your Telegram now.")
        return 0
    else:
        print(f"[smoke] FAIL — Telegram API rejected: {r.status_code} {r.text[:200]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
