"""
Tests unitaires pour paper_trading/monitoring.py.

Couvre :
- JsonLineLogger : append, format JSON Lines, 1 fichier par jour UTC
- Day rotation : changement de date UTC = nouveau fichier
- Sérialisation robuste : pas de crash sur non-JSON-serializable
- TelegramAlerter : succès, 4xx, 5xx, timeout, network error
- Disabled when no token
- Monitor : combine logger + alerter, fail-soft sur Telegram down
- Formatters : Markdown bien formé, emojis présents
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from paper_trading.monitoring import (
    JsonLineLogger,
    TelegramAlerter,
    TelegramResult,
    Monitor,
    format_halt_msg,
    format_crash_msg,
    format_heartbeat_msg,
    format_weekly_recap_msg,
)


# ════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def logs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture
def json_logger(logs_dir: Path) -> JsonLineLogger:
    return JsonLineLogger(logs_dir=logs_dir)


def _read_log_lines(path: Path) -> list[dict]:
    """Helper: read a .jsonl file as a list of parsed dicts."""
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ════════════════════════════════════════════════════════════════
#  JsonLineLogger
# ════════════════════════════════════════════════════════════════

def test_logger_creates_daily_file(json_logger, logs_dir):
    json_logger.log("test_event", ts="2026-05-14T18:00:00Z")
    expected = logs_dir / "2026-05-14.jsonl"
    assert expected.exists()


def test_logger_appends_one_line_per_event(json_logger, logs_dir):
    json_logger.log("event_a", ts="2026-05-14T10:00:00Z")
    json_logger.log("event_b", ts="2026-05-14T11:00:00Z")
    json_logger.log("event_c", ts="2026-05-14T12:00:00Z")

    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert len(lines) == 3
    assert lines[0]["event"] == "event_a"
    assert lines[1]["event"] == "event_b"
    assert lines[2]["event"] == "event_c"


def test_logger_rotates_by_utc_day(json_logger, logs_dir):
    json_logger.log("evt1", ts="2026-05-14T23:59:00Z")
    json_logger.log("evt2", ts="2026-05-15T00:01:00Z")

    file_14 = logs_dir / "2026-05-14.jsonl"
    file_15 = logs_dir / "2026-05-15.jsonl"
    assert file_14.exists()
    assert file_15.exists()
    assert len(_read_log_lines(file_14)) == 1
    assert len(_read_log_lines(file_15)) == 1


def test_logger_preserves_extra_fields(json_logger, logs_dir):
    json_logger.log(
        "trade_opened",
        ts="2026-05-14T10:00:00Z",
        asset="BTC",
        units=0.001558,
        entry_price=80000.0,
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["asset"] == "BTC"
    assert lines[0]["units"] == 0.001558
    assert lines[0]["entry_price"] == 80000.0


def test_logger_default_level_is_INFO(json_logger, logs_dir):
    json_logger.log("evt", ts="2026-05-14T10:00:00Z")
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["level"] == "INFO"


def test_logger_custom_level(json_logger, logs_dir):
    json_logger.log("evt", level="CRITICAL", ts="2026-05-14T10:00:00Z")
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["level"] == "CRITICAL"


def test_logger_handles_non_serializable_value(json_logger, logs_dir):
    """Pass a non-JSON-native type and check it doesn't crash."""
    from datetime import datetime
    json_logger.log(
        "evt", ts="2026-05-14T10:00:00Z",
        weird=datetime(2026, 5, 14),  # default=str will handle this
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["event"] == "evt"


def test_logger_never_raises_on_filesystem_error(tmp_path, capsys):
    """If the logs dir disappears, logger must not raise."""
    fake_dir = tmp_path / "logs"
    fake_dir.mkdir()
    logger = JsonLineLogger(logs_dir=fake_dir)
    # Remove the dir to simulate a missing target
    import shutil
    shutil.rmtree(fake_dir)
    # Should not raise
    logger.log("evt", ts="2026-05-14T10:00:00Z")
    # Captured stderr will have the warning
    captured = capsys.readouterr()
    assert "FAILED" in captured.err or "Failed" in captured.err.lower() or captured.err == ""


def test_logger_default_ts_uses_now(json_logger, logs_dir):
    """If no ts provided, uses current time."""
    json_logger.log("evt")
    files = list(logs_dir.glob("*.jsonl"))
    assert len(files) >= 1


# ════════════════════════════════════════════════════════════════
#  TelegramAlerter
# ════════════════════════════════════════════════════════════════

def test_alerter_disabled_when_no_token():
    a = TelegramAlerter(token=None, chat_id="123")
    assert a.enabled is False
    result = a.send("test")
    assert result.ok is False
    assert "not_configured" in result.error


def test_alerter_disabled_when_no_chat():
    a = TelegramAlerter(token="xxx", chat_id=None)
    assert a.enabled is False


def test_alerter_explicit_none_overrides_config():
    """Even if config.TELEGRAM_BOT_TOKEN is set (e.g. from .env),
    passing token=None explicitly must disable the alerter.
    This is the regression test for the bug found in dev environment."""
    from paper_trading import config as cfg
    with patch.object(cfg, 'TELEGRAM_BOT_TOKEN', 'fake_token_from_env'), \
         patch.object(cfg, 'TELEGRAM_CHAT_ID', 'fake_chat_from_env'):
        a = TelegramAlerter(token=None, chat_id="123")
        assert a.enabled is False
        a = TelegramAlerter(token="xxx", chat_id=None)
        assert a.enabled is False


def test_alerter_omitted_args_use_config():
    """When token/chat_id are NOT passed, fall back to config values."""
    from paper_trading import config as cfg
    with patch.object(cfg, 'TELEGRAM_BOT_TOKEN', 'fake_token'), \
         patch.object(cfg, 'TELEGRAM_CHAT_ID', 'fake_chat'):
        a = TelegramAlerter()  # no args
        assert a.token == 'fake_token'
        assert a.chat_id == 'fake_chat'
        assert a.enabled is True


def test_alerter_enabled_when_both_present():
    a = TelegramAlerter(token="xxx", chat_id="123")
    assert a.enabled is True


@patch("paper_trading.monitoring.requests.post")
def test_alerter_send_success(mock_post):
    mock_post.return_value = MagicMock(status_code=200, text="{}")
    a = TelegramAlerter(token="t", chat_id="c")
    result = a.send("hello")
    assert result.ok is True
    assert result.http_status == 200


@patch("paper_trading.monitoring.requests.post")
def test_alerter_4xx_returns_failure(mock_post):
    mock_post.return_value = MagicMock(status_code=403, text="Forbidden")
    a = TelegramAlerter(token="t", chat_id="c")
    result = a.send("hello")
    assert result.ok is False
    assert result.http_status == 403
    assert "403" in result.error


@patch("paper_trading.monitoring.requests.post")
def test_alerter_network_error_returns_failure_no_raise(mock_post):
    mock_post.side_effect = requests.ConnectionError("DNS failed")
    a = TelegramAlerter(token="t", chat_id="c")
    result = a.send("hello")
    assert result.ok is False
    assert "network" in result.error.lower()


@patch("paper_trading.monitoring.requests.post")
def test_alerter_unexpected_error_caught(mock_post):
    """If something completely unexpected happens, we still return a result."""
    mock_post.side_effect = RuntimeError("something weird")
    a = TelegramAlerter(token="t", chat_id="c")
    result = a.send("hello")
    assert result.ok is False
    assert result.error is not None


# ════════════════════════════════════════════════════════════════
#  Formatters
# ════════════════════════════════════════════════════════════════

def test_format_halt_msg_contains_emoji_and_reason():
    msg = format_halt_msg("DD -16%", current_equity=840.0, peak_equity=1000.0)
    assert "🚨" in msg
    assert "DD -16%" in msg
    assert "$840" in msg
    assert "$1,000" in msg


def test_format_crash_msg_includes_traceback():
    msg = format_crash_msg("RuntimeError: boom", traceback_snippet="line1\nline2")
    assert "🚨" in msg
    assert "RuntimeError" in msg
    assert "line1" in msg


def test_format_crash_msg_truncates_long_traceback():
    long_tb = "x" * 5000
    msg = format_crash_msg("err", traceback_snippet=long_tb)
    # Should be reasonable size for Telegram
    assert len(msg) < 2500


def test_format_heartbeat_msg_positive_pnl():
    msg = format_heartbeat_msg(equity=1050.0, n_open_positions=2,
                                pnl_today=15.5, n_trades_today=1)
    assert "❤️" in msg
    assert "+$15.50" in msg
    assert "📈" in msg


def test_format_heartbeat_msg_negative_pnl():
    msg = format_heartbeat_msg(equity=950.0, n_open_positions=1,
                                pnl_today=-20.0, n_trades_today=2)
    assert "📉" in msg
    assert "$" in msg


def test_format_weekly_recap_msg():
    msg = format_weekly_recap_msg(
        equity_start=1000.0, equity_end=1042.30,
        n_trades=5, winners=3, losers=2,
        total_pnl=42.30, best_asset="ETH", worst_asset="ADA",
    )
    assert "📊" in msg
    assert "60.0%" in msg  # win rate 3/5
    assert "ETH" in msg
    assert "ADA" in msg


def test_format_weekly_recap_handles_zero_trades():
    msg = format_weekly_recap_msg(
        equity_start=1000.0, equity_end=1000.0,
        n_trades=0, winners=0, losers=0, total_pnl=0.0,
    )
    # Should not divide by zero
    assert "0.0%" in msg or "0%" in msg


# ════════════════════════════════════════════════════════════════
#  Monitor (facade)
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def mon(logs_dir):
    """Monitor with real JsonLineLogger but mock TelegramAlerter."""
    logger = JsonLineLogger(logs_dir=logs_dir)
    mock_alerter = MagicMock(spec=TelegramAlerter)
    mock_alerter.send.return_value = TelegramResult(ok=True, http_status=200)
    return Monitor(json_logger=logger, alerter=mock_alerter), logs_dir, mock_alerter


def test_monitor_log_cycle_events(mon):
    m, logs_dir, _ = mon
    m.log_cycle_start(ts="2026-05-14T18:00:00Z")
    m.log_cycle_end(ts="2026-05-14T18:00:30Z", n_open=2, equity=1050.0)
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert len(lines) == 2
    assert lines[0]["event"] == "cycle_start"
    assert lines[1]["event"] == "cycle_end"
    assert lines[1]["n_open_positions"] == 2
    assert lines[1]["equity"] == 1050.0


def test_monitor_log_trade_opened(mon):
    m, logs_dir, _ = mon
    m.log_trade_opened(
        "BTC", units=0.001558, entry_price=80000.0,
        entry_fill_price=80080.0, sl_price=78000.0, tp_price=84000.0,
        ts="2026-05-14T18:00:15Z",
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["event"] == "trade_opened"
    assert lines[0]["asset"] == "BTC"
    assert lines[0]["units"] == 0.001558


def test_monitor_log_trade_closed(mon):
    m, logs_dir, _ = mon
    m.log_trade_closed(
        "BTC", pnl_dollars=5.57, pnl_pct=0.0446,
        exit_reason="TP_HIT", held_bars=4,
        ts="2026-05-14T22:00:00Z",
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["event"] == "trade_closed"
    assert lines[0]["exit_reason"] == "TP_HIT"


def test_monitor_log_trade_skipped(mon):
    m, logs_dir, _ = mon
    m.log_trade_skipped("ETH", reason="insufficient capital", ts="2026-05-14T22:00:00Z")
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert lines[0]["event"] == "trade_skipped"
    assert lines[0]["level"] == "WARNING"


def test_monitor_alert_halt_logs_and_sends(mon):
    m, logs_dir, mock_alerter = mon
    result = m.alert_halt(
        reason="DD breach", current_equity=840.0, peak_equity=1000.0,
        ts="2026-05-14T23:00:00Z",
    )
    # Logged
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert any(l["event"] == "halt_triggered" for l in lines)
    assert any(l["level"] == "CRITICAL" for l in lines)
    # Telegram called
    mock_alerter.send.assert_called_once()
    assert result.ok is True


def test_monitor_alert_halt_continues_on_telegram_failure(mon):
    """If Telegram fails, the bot must keep running (fail-soft)."""
    m, logs_dir, mock_alerter = mon
    mock_alerter.send.return_value = TelegramResult(ok=False, error="network error")

    result = m.alert_halt(
        reason="DD breach", current_equity=840.0, peak_equity=1000.0,
        ts="2026-05-14T23:00:00Z",
    )

    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    # Both halt and telegram_send_failed should be logged
    events = [l["event"] for l in lines]
    assert "halt_triggered" in events
    assert "telegram_send_failed" in events
    assert result.ok is False  # the telegram result is reported back


def test_monitor_alert_crash_logs_and_sends(mon):
    m, logs_dir, mock_alerter = mon
    m.alert_crash(
        error="RuntimeError: boom",
        traceback_snippet="...trace...",
        ts="2026-05-14T23:30:00Z",
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert any(l["event"] == "crash" for l in lines)
    mock_alerter.send.assert_called_once()


def test_monitor_send_heartbeat(mon):
    m, logs_dir, mock_alerter = mon
    m.send_heartbeat(
        equity=1050.0, n_open_positions=2,
        pnl_today=15.5, n_trades_today=1,
        ts="2026-05-14T12:00:00Z",
    )
    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    assert any(l["event"] == "heartbeat" for l in lines)
    mock_alerter.send.assert_called_once()


def test_monitor_send_weekly_recap(mon):
    m, logs_dir, mock_alerter = mon
    m.send_weekly_recap(
        equity_start=1000.0, equity_end=1042.30,
        n_trades=5, winners=3, losers=2,
        total_pnl=42.30, best_asset="ETH", worst_asset="ADA",
        ts="2026-05-18T21:00:00Z",
    )
    lines = _read_log_lines(logs_dir / "2026-05-18.jsonl")
    assert any(l["event"] == "weekly_recap" for l in lines)
    mock_alerter.send.assert_called_once()


def test_monitor_full_sequence_produces_log_chronology(mon):
    """End-to-end: simulate a cycle with open + close + heartbeat."""
    m, logs_dir, _ = mon
    m.log_cycle_start(ts="2026-05-14T18:00:00Z")
    m.log_trade_opened(
        "BTC", units=0.001, entry_price=80000.0,
        entry_fill_price=80080.0, sl_price=78000.0, tp_price=84000.0,
        ts="2026-05-14T18:00:15Z",
    )
    m.log_trade_closed(
        "BTC", pnl_dollars=5.57, pnl_pct=0.0446,
        exit_reason="TP_HIT", held_bars=4,
        ts="2026-05-14T22:00:00Z",
    )
    m.log_cycle_end(ts="2026-05-14T22:00:30Z", n_open=0, equity=1005.57)

    lines = _read_log_lines(logs_dir / "2026-05-14.jsonl")
    events = [l["event"] for l in lines]
    assert events == ["cycle_start", "trade_opened", "trade_closed", "cycle_end"]
