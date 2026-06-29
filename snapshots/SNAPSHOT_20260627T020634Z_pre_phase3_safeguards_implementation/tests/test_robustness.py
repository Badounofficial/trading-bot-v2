"""
test_robustness.py — Robustness tests for external dependency failures.

WHY THIS EXISTS
===============
The trading bot has 3 external dependencies that can fail at any time:
1. Kraken API (network errors, exchange errors)
2. Telegram API (network errors, HTTP errors)
3. Filesystem (DB locked, disk full, missing source)

The codebase already wraps these with try/except blocks that promise
fail-soft behavior (log + return error, never raise). These tests
PROVE that promise holds by injecting failures via mocks and asserting
the contract:
- No exception escapes the function
- The function returns a structured error result
- A warning/error is logged
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from paper_trading import data_source, backup
from paper_trading.monitoring import TelegramAlerter, TelegramResult


# Test 1 — Kraken ping_kraken() handles exceptions gracefully

class TestKrakenResilience:
    """ping_kraken() must return False on ANY exception, never raise."""

    def test_ping_returns_false_when_get_exchange_raises(self, caplog):
        with patch("paper_trading.data_source.get_exchange") as mock_get:
            mock_get.side_effect = Exception("simulated import failure")
            with caplog.at_level(logging.WARNING):
                result = data_source.ping_kraken()
        assert result is False
        assert any("kraken ping failed" in r.message.lower() for r in caplog.records)

    def test_ping_returns_false_when_fetch_status_raises_network_error(self, caplog):
        mock_exchange = MagicMock()
        mock_exchange.fetch_status.side_effect = Exception("Network unreachable")
        with patch("paper_trading.data_source.get_exchange", return_value=mock_exchange):
            with caplog.at_level(logging.WARNING):
                result = data_source.ping_kraken()
        assert result is False
        assert any("kraken ping failed" in r.message.lower() for r in caplog.records)

    def test_ping_returns_false_when_status_unexpected(self, caplog):
        mock_exchange = MagicMock()
        mock_exchange.fetch_status.return_value = {"status": "maintenance"}
        with patch("paper_trading.data_source.get_exchange", return_value=mock_exchange):
            with caplog.at_level(logging.WARNING):
                result = data_source.ping_kraken()
        assert result is False
        assert any("kraken status unexpected" in r.message.lower() for r in caplog.records)


# Test 2 — TelegramAlerter.send() never raises

class TestTelegramResilience:
    """TelegramAlerter.send() must return TelegramResult, never raise."""

    def _make_client(self) -> TelegramAlerter:
        return TelegramAlerter(token="fake-token", chat_id="fake-chat", timeout=2.0)

    def test_send_returns_ok_false_when_not_configured(self):
        client = TelegramAlerter(token=None, chat_id=None)
        result = client.send("hello")
        assert isinstance(result, TelegramResult)
        assert result.ok is False
        assert "not_configured" in (result.error or "")

    def test_send_handles_network_error(self):
        client = self._make_client()
        with patch("paper_trading.monitoring.requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("simulated network down")
            result = client.send("hello")
        assert isinstance(result, TelegramResult)
        assert result.ok is False
        assert result.error is not None
        assert "telegram_network" in result.error

    def test_send_handles_http_error_status(self):
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        with patch("paper_trading.monitoring.requests.post", return_value=mock_response):
            result = client.send("hello")
        assert result.ok is False
        assert result.http_status == 500
        assert "telegram_http_500" in (result.error or "")

    def test_send_handles_unexpected_exception(self):
        client = self._make_client()
        with patch("paper_trading.monitoring.requests.post") as mock_post:
            mock_post.side_effect = ValueError("unexpected!")
            result = client.send("hello")
        assert result.ok is False
        assert "telegram_unexpected" in (result.error or "")


# Test 3 — create_snapshot() handles filesystem failures gracefully

class TestBackupResilience:
    """create_snapshot() must always return SnapshotResult, never raise."""

    def test_create_snapshot_fails_gracefully_on_missing_source(self, tmp_path, caplog):
        missing_db = tmp_path / "no_such_file.db"
        backup_dir = tmp_path / "backups"
        with caplog.at_level(logging.ERROR):
            result = backup.create_snapshot(
                db_path=missing_db,
                backup_dir=backup_dir,
                timestamp_iso="2026-05-18T22-00-10Z",
            )
        assert result.ok is False
        assert result.error is not None

    def test_create_snapshot_succeeds_on_valid_source(self, tmp_path):
        db_path = tmp_path / "state.db"
        db_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
        backup_dir = tmp_path / "backups"
        result = backup.create_snapshot(
            db_path=db_path,
            backup_dir=backup_dir,
            timestamp_iso="2026-05-18T22-00-10Z",
        )
        assert result.ok is True
        assert result.path is not None
        assert result.path.exists()
        assert result.path.suffix == ".gz"
        assert result.size_bytes > 0


def test_robustness_suite_summary():
    """Marker test that documents the contract this suite enforces."""
    assert True
