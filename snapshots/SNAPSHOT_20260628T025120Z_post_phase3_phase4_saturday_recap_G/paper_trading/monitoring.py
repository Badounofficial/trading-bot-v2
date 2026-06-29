"""
monitoring.py — Logs structurés + Telegram alerter pour paper trading.

DESIGN CHOICES (Session 6, locked):
1. Logs essentiels uniquement (~10 events/jour) — pas verbeux
2. JSON Lines format (1 objet par ligne) → 1 fichier par jour : logs/YYYY-MM-DD.jsonl
3. Best-effort sur Telegram : si l'envoi fail, on log l'erreur et on continue
   (le bot continue à tourner, pas de crash sur panne Telegram)

PHILOSOPHIE (Cas B confirmé Session 6) :
- Telegram = événements CRITIQUES uniquement (HALT, crash, heartbeat 1×/jour, recap hebdo)
- PAS d'alerte par trade — on respecte l'attention de l'utilisateur
- Logs fichier = TOUT trace pour audit/debug a posteriori

USAGE TYPIQUE :
    mon = Monitor()
    mon.log_cycle_start("2026-05-14T18:00:00Z")
    mon.log_trade_opened("BTC", 0.0015, 80000.0)
    mon.alert_halt("DD breached -15%", current_equity=850.0)
    mon.send_heartbeat(equity=1050.0, n_open=2, pnl_today=15.5)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import requests

from paper_trading import config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    JSON LINES LOGGER
# ════════════════════════════════════════════════════════════════

class JsonLineLogger:
    """Append structured events to logs/YYYY-MM-DD.jsonl.

    One file per UTC day (rotates at 00:00 UTC). Each line is a valid JSON object.

    Format examples (one per line in the file):
        {"ts":"2026-05-14T18:00:00Z","level":"INFO","event":"cycle_start"}
        {"ts":"2026-05-14T18:01:23Z","level":"INFO","event":"trade_opened","asset":"BTC","units":0.001558,"entry_price":80080.0}
        {"ts":"2026-05-14T18:30:45Z","level":"CRITICAL","event":"halt_triggered","reason":"DD breach"}

    Reading later: simply `cat logs/2026-05-14.jsonl` or parse with jq.
    """

    def __init__(self, logs_dir: Optional[Path] = None):
        self.logs_dir = logs_dir or config.LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _current_log_path(self, ts_iso: Optional[str] = None) -> Path:
        """Return the path of the log file for the day of ts_iso (UTC)."""
        if ts_iso is None:
            ts_iso = datetime.now(timezone.utc).isoformat()
        date_str = ts_iso.split("T")[0]  # YYYY-MM-DD
        return self.logs_dir / f"{date_str}.jsonl"

    def log(
        self,
        event: str,
        level: str = "INFO",
        ts: Optional[str] = None,
        **fields: Any,
    ) -> None:
        """Append one event to today's log file.

        Args:
            event: short string identifying the event type (e.g. "cycle_start")
            level: "INFO" | "WARNING" | "ERROR" | "CRITICAL"
            ts: ISO UTC timestamp. Defaults to now.
            **fields: arbitrary extra fields (must be JSON-serializable)

        Never raises — errors are caught and printed to stderr (last resort).
        """
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        record = {"ts": ts, "level": level, "event": event}
        record.update(fields)

        try:
            line = json.dumps(record, default=str, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            # Last resort: log the serialization error itself
            line = json.dumps({
                "ts": ts, "level": "ERROR",
                "event": "logger_serialization_failed",
                "original_event": event,
                "error": str(e),
            })

        try:
            path = self._current_log_path(ts)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            # Filesystem issue — print to stderr so something appears in terminal
            import sys
            print(f"[monitoring] FAILED to write log: {e} — {line}", file=sys.stderr)


# ════════════════════════════════════════════════════════════════
#                    TELEGRAM ALERTER (best-effort)
# ════════════════════════════════════════════════════════════════

@dataclass
class TelegramResult:
    """Result of a Telegram send attempt."""
    ok: bool
    error: Optional[str] = None
    http_status: Optional[int] = None


# Sentinel value: lets us distinguish "argument not passed" from
# "argument explicitly passed as None". This is the canonical Python idiom
# for optional arguments that need to fall back to a default WHEN OMITTED,
# but be respected (even as None) when explicitly passed.
_UNSET = object()


class TelegramAlerter:
    """Send messages to a Telegram bot via the Bot API.

    Best-effort: never raises. If the send fails (network, bad token, etc.),
    we return an unsuccessful result. The caller (Monitor) will log the failure
    but keep the bot running. Trading continues over a Telegram outage.

    To send a message: alerter.send("Hello world").
    """

    BASE_URL = "https://api.telegram.org"

    def __init__(
        self,
        token=_UNSET,
        chat_id=_UNSET,
        timeout: float = 8.0,
    ):
        # If token/chat_id NOT passed → fall back to config (.env).
        # If passed as None explicitly → respect it (used by tests).
        self.token = config.TELEGRAM_BOT_TOKEN if token is _UNSET else token
        self.chat_id = config.TELEGRAM_CHAT_ID if chat_id is _UNSET else chat_id
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        """True if both token and chat_id are configured."""
        return bool(self.token and self.chat_id)

    def send(self, text: str, parse_mode: str = "Markdown") -> TelegramResult:
        """Send a text message to the configured chat.

        Args:
            text: message body (Markdown by default for **bold** etc.)
            parse_mode: "Markdown" | "HTML" | None

        Returns:
            TelegramResult.ok = True on success, with error/http_status on fail.
        """
        if not self.enabled:
            return TelegramResult(ok=False, error="telegram_not_configured")

        url = f"{self.BASE_URL}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                return TelegramResult(ok=True, http_status=200)
            return TelegramResult(
                ok=False,
                http_status=r.status_code,
                error=f"telegram_http_{r.status_code}: {r.text[:200]}",
            )
        except requests.RequestException as e:
            return TelegramResult(ok=False, error=f"telegram_network: {e}")
        except Exception as e:
            # Defensive : we promised "never raises"
            return TelegramResult(ok=False, error=f"telegram_unexpected: {e}")

    def send_photo(
        self,
        photo_path: str,
        caption: str = "",
        parse_mode: str = "Markdown",
    ) -> TelegramResult:
        """Send a photo (PNG/JPEG) with optional caption via Telegram sendPhoto.

        Used by the OB Forward Detection daemon to push annotated charts.
        Best-effort — never raises.

        Args:
            photo_path: absolute path to the image file on disk
            caption: optional caption, max 1024 chars (Telegram limit)
            parse_mode: "Markdown" | "HTML" | None
        """
        if not self.enabled:
            return TelegramResult(ok=False, error="telegram_not_configured")

        if caption and len(caption) > 1024:
            caption = caption[:1020] + "..."

        url = f"{self.BASE_URL}/bot{self.token}/sendPhoto"
        try:
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": self.chat_id}
                if caption:
                    data["caption"] = caption
                if parse_mode:
                    data["parse_mode"] = parse_mode
                r = requests.post(url, data=data, files=files, timeout=self.timeout * 3)
            if r.status_code == 200:
                return TelegramResult(ok=True, http_status=200)
            return TelegramResult(
                ok=False,
                http_status=r.status_code,
                error=f"telegram_photo_http_{r.status_code}: {r.text[:200]}",
            )
        except FileNotFoundError:
            return TelegramResult(ok=False, error=f"telegram_photo_missing_file: {photo_path}")
        except requests.RequestException as e:
            return TelegramResult(ok=False, error=f"telegram_photo_network: {e}")
        except Exception as e:
            return TelegramResult(ok=False, error=f"telegram_photo_unexpected: {e}")


# ════════════════════════════════════════════════════════════════
#                    MESSAGE FORMATTERS (Markdown for Telegram)
# ════════════════════════════════════════════════════════════════

def format_halt_msg(reason: str, current_equity: float, peak_equity: float) -> str:
    """Format the HALT alert Telegram message."""
    return (
        f"🚨 *BOT HALTED*\n\n"
        f"*Reason* : {reason}\n"
        f"*Current equity* : ${current_equity:,.2f}\n"
        f"*Peak equity* : ${peak_equity:,.2f}\n\n"
        f"All open positions have been closed.\n"
        f"Bot will NOT open new trades until manual resume."
    )


def format_crash_msg(error: str, traceback_snippet: str = "") -> str:
    """Format the CRASH alert Telegram message."""
    msg = (
        f"🚨 *BOT CRASHED*\n\n"
        f"*Error* : {error}\n"
    )
    if traceback_snippet:
        # Keep it short — Telegram limit is 4096 chars
        snippet = traceback_snippet[:1500]
        msg += f"\n```\n{snippet}\n```\n"
    msg += "\nCheck logs immediately."
    return msg


def format_heartbeat_msg(
    equity: float,
    n_open_positions: int,
    pnl_today: float,
    n_trades_today: int,
) -> str:
    """Format the daily heartbeat Telegram message (sent at HEARTBEAT_HOUR_UTC)."""
    pnl_sign = "+" if pnl_today >= 0 else ""
    pnl_emoji = "📈" if pnl_today >= 0 else "📉"
    return (
        f"❤️ *Daily heartbeat*\n\n"
        f"*Equity* : ${equity:,.2f}\n"
        f"*Open positions* : {n_open_positions}\n"
        f"*PnL today* : {pnl_emoji} {pnl_sign}${pnl_today:,.2f}\n"
        f"*Trades today* : {n_trades_today}\n\n"
        f"Bot status: RUNNING ✓"
    )


def format_weekly_recap_msg(
    equity_start: float,
    equity_end: float,
    n_trades: int,
    winners: int,
    losers: int,
    total_pnl: float,
    best_asset: Optional[str] = None,
    worst_asset: Optional[str] = None,
) -> str:
    """Format the weekly recap Telegram message (sent Sunday at WEEKLY_RECAP_HOUR)."""
    wr = (winners / n_trades * 100) if n_trades > 0 else 0.0
    return_pct = ((equity_end - equity_start) / equity_start * 100) if equity_start > 0 else 0.0
    sign = "+" if total_pnl >= 0 else ""
    emoji = "📈" if total_pnl >= 0 else "📉"

    msg = (
        f"📊 *Weekly recap*\n\n"
        f"*Equity start* : ${equity_start:,.2f}\n"
        f"*Equity end* : ${equity_end:,.2f}\n"
        f"*Return* : {sign}{return_pct:.2f}%\n"
        f"*PnL* : {emoji} {sign}${total_pnl:,.2f}\n\n"
        f"*Trades* : {n_trades} ({winners}W / {losers}L)\n"
        f"*Win rate* : {wr:.1f}%\n"
    )
    if best_asset:
        msg += f"*Best asset* : {best_asset}\n"
    if worst_asset:
        msg += f"*Worst asset* : {worst_asset}\n"
    return msg


# ════════════════════════════════════════════════════════════════
#                    MONITOR (facade combining logger + alerter)
# ════════════════════════════════════════════════════════════════

class Monitor:
    """Facade for the orchestrator (Bloc 7) — combines structured logging
    and Telegram alerting in one easy-to-use interface.

    Usage:
        mon = Monitor()
        mon.log_cycle_start()                          # → JSON log
        mon.log_trade_opened("BTC", units, price)      # → JSON log
        mon.alert_halt(reason, equity, peak)           # → JSON log + Telegram
        mon.send_heartbeat(equity, n_open, pnl, ...)   # → JSON log + Telegram
        mon.send_weekly_recap(...)                     # → JSON log + Telegram
    """

    def __init__(
        self,
        json_logger: Optional[JsonLineLogger] = None,
        alerter: Optional[TelegramAlerter] = None,
    ):
        self.logger = json_logger or JsonLineLogger()
        self.alerter = alerter or TelegramAlerter()

    # ─── Pure-logging events (no Telegram) ────────────────────────

    def log_cycle_start(self, ts: Optional[str] = None) -> None:
        self.logger.log("cycle_start", ts=ts)

    def log_cycle_end(
        self,
        ts: Optional[str] = None,
        n_open: int = 0,
        equity: Optional[float] = None,
    ) -> None:
        extras: dict = {"n_open_positions": n_open}
        if equity is not None:
            extras["equity"] = equity
        self.logger.log("cycle_end", ts=ts, **extras)

    def log_trade_opened(
        self,
        asset: str,
        units: float,
        entry_price: float,
        entry_fill_price: float,
        sl_price: float,
        tp_price: float,
        ts: Optional[str] = None,
    ) -> None:
        self.logger.log(
            "trade_opened", ts=ts, asset=asset, units=units,
            entry_price=entry_price, entry_fill_price=entry_fill_price,
            sl_price=sl_price, tp_price=tp_price,
        )

    def log_trade_closed(
        self,
        asset: str,
        pnl_dollars: float,
        pnl_pct: float,
        exit_reason: str,
        held_bars: int,
        ts: Optional[str] = None,
    ) -> None:
        self.logger.log(
            "trade_closed", ts=ts, asset=asset,
            pnl_dollars=pnl_dollars, pnl_pct=pnl_pct,
            exit_reason=exit_reason, held_bars=held_bars,
        )

    def log_trade_skipped(
        self,
        asset: str,
        reason: str,
        ts: Optional[str] = None,
    ) -> None:
        self.logger.log("trade_skipped", level="WARNING", ts=ts,
                        asset=asset, reason=reason)

    # ─── Events that ALSO trigger Telegram ────────────────────────

    def alert_halt(
        self,
        reason: str,
        current_equity: float,
        peak_equity: float,
        ts: Optional[str] = None,
    ) -> TelegramResult:
        """Log HALT + send Telegram alert. Returns the Telegram result."""
        self.logger.log(
            "halt_triggered", level="CRITICAL", ts=ts,
            reason=reason, current_equity=current_equity, peak_equity=peak_equity,
        )
        msg = format_halt_msg(reason, current_equity, peak_equity)
        result = self.alerter.send(msg)
        if not result.ok:
            # Log Telegram failure separately, but bot keeps running
            self.logger.log(
                "telegram_send_failed", level="ERROR", ts=ts,
                target_event="halt_triggered", error=result.error,
            )
        return result

    def alert_crash(
        self,
        error: str,
        traceback_snippet: str = "",
        ts: Optional[str] = None,
    ) -> TelegramResult:
        """Log crash + send Telegram alert."""
        self.logger.log(
            "crash", level="CRITICAL", ts=ts,
            error=error, traceback_snippet=traceback_snippet[:1000],
        )
        msg = format_crash_msg(error, traceback_snippet)
        result = self.alerter.send(msg)
        if not result.ok:
            self.logger.log(
                "telegram_send_failed", level="ERROR", ts=ts,
                target_event="crash", error=result.error,
            )
        return result

    def send_heartbeat(
        self,
        equity: float,
        n_open_positions: int,
        pnl_today: float,
        n_trades_today: int,
        ts: Optional[str] = None,
    ) -> TelegramResult:
        """Daily heartbeat: log + Telegram."""
        self.logger.log(
            "heartbeat", ts=ts, equity=equity,
            n_open_positions=n_open_positions,
            pnl_today=pnl_today, n_trades_today=n_trades_today,
        )
        msg = format_heartbeat_msg(equity, n_open_positions, pnl_today, n_trades_today)
        result = self.alerter.send(msg)
        if not result.ok:
            self.logger.log(
                "telegram_send_failed", level="ERROR", ts=ts,
                target_event="heartbeat", error=result.error,
            )
        return result

    def send_weekly_recap(
        self,
        equity_start: float,
        equity_end: float,
        n_trades: int,
        winners: int,
        losers: int,
        total_pnl: float,
        best_asset: Optional[str] = None,
        worst_asset: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> TelegramResult:
        """Weekly recap: log + Telegram."""
        self.logger.log(
            "weekly_recap", ts=ts,
            equity_start=equity_start, equity_end=equity_end,
            n_trades=n_trades, winners=winners, losers=losers,
            total_pnl=total_pnl, best_asset=best_asset, worst_asset=worst_asset,
        )
        msg = format_weekly_recap_msg(
            equity_start, equity_end, n_trades, winners, losers,
            total_pnl, best_asset, worst_asset,
        )
        result = self.alerter.send(msg)
        if not result.ok:
            self.logger.log(
                "telegram_send_failed", level="ERROR", ts=ts,
                target_event="weekly_recap", error=result.error,
            )
        return result


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : démo + live Telegram test
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    print("=" * 64)
    print("  monitoring.py — démo")
    print("=" * 64)

    # Use a temp directory so we don't pollute real logs
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        json_logger = JsonLineLogger(logs_dir=tmp_path)

        # We use the REAL alerter (will hit Telegram if configured)
        alerter = TelegramAlerter()
        mon = Monitor(json_logger=json_logger, alerter=alerter)

        print(f"\nLogs dir (temp) : {tmp_path}")
        print(f"Telegram enabled: {alerter.enabled}")

        # ── Sequence of events ──
        print("\n[1] log_cycle_start")
        mon.log_cycle_start("2026-05-14T18:00:00Z")

        print("[2] log_trade_opened (BTC)")
        mon.log_trade_opened(
            "BTC", units=0.001558, entry_price=80000.0,
            entry_fill_price=80080.0, sl_price=78000.0, tp_price=84000.0,
            ts="2026-05-14T18:00:15Z",
        )

        print("[3] log_trade_closed (BTC TP_HIT)")
        mon.log_trade_closed(
            "BTC", pnl_dollars=5.57, pnl_pct=0.0446,
            exit_reason="TP_HIT", held_bars=4,
            ts="2026-05-14T22:00:00Z",
        )

        print("[4] log_trade_skipped (ETH insufficient capital)")
        mon.log_trade_skipped("ETH", reason="not enough free capital", ts="2026-05-14T22:30:00Z")

        print("[5] send_heartbeat → Telegram")
        result = mon.send_heartbeat(
            equity=1005.57, n_open_positions=0,
            pnl_today=5.57, n_trades_today=1,
            ts="2026-05-14T12:00:00Z",
        )
        print(f"    Telegram result: ok={result.ok}, error={result.error}")

        print("[6] alert_halt → Telegram")
        result = mon.alert_halt(
            reason="DEMO: Drawdown -16% breached",
            current_equity=840.0, peak_equity=1000.0,
            ts="2026-05-14T23:00:00Z",
        )
        print(f"    Telegram result: ok={result.ok}, error={result.error}")

        print("[7] send_weekly_recap → Telegram")
        result = mon.send_weekly_recap(
            equity_start=1000.0, equity_end=1042.30,
            n_trades=5, winners=3, losers=2,
            total_pnl=42.30, best_asset="ETH", worst_asset="ADA",
            ts="2026-05-18T21:00:00Z",
        )
        print(f"    Telegram result: ok={result.ok}, error={result.error}")

        # Show what we logged
        log_file = tmp_path / "2026-05-14.jsonl"
        print(f"\n--- Content of {log_file.name} ---")
        if log_file.exists():
            with open(log_file) as f:
                for i, line in enumerate(f, 1):
                    print(f"  L{i}: {line.rstrip()}")

    print("\n" + "=" * 64)
    print("  monitoring.py OK")
    print("=" * 64)
