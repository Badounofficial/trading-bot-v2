"""
Tests unitaires pour paper_trading/data_source.py (version ccxt/Kraken).

Tous les tests offline (mocks) sauf marqueurs `live` qui hit la vraie API.
Run normal      : pytest tests/test_data_source.py
Run avec live   : pytest -m live tests/test_data_source.py
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import ccxt
import pytest
import pandas as pd

from paper_trading import data_source as ds


# ════════════════════════════════════════════════════════════════
#  Fixtures : exemples de réponses ccxt réalistes
# ════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_exchange_singleton():
    """Réinitialise le singleton entre chaque test."""
    ds._exchange = None
    yield
    ds._exchange = None


@pytest.fixture
def valid_ohlcv_response() -> list[list]:
    """3 bougies H1 BTC valides, format brut ccxt :
    [timestamp_ms, open, high, low, close, volume]
    """
    return [
        [1700000000000, 37000.0, 37500.0, 36800.0, 37200.0, 100.5],
        [1700003600000, 37200.0, 37800.0, 37100.0, 37700.0, 120.0],
        [1700007200000, 37700.0, 38000.0, 37600.0, 37900.0, 95.3],
    ]


@pytest.fixture
def invalid_ohlc_response() -> list[list]:
    """1 bougie avec high < close (incohérence OHLC)."""
    return [
        [1700000000000, 37000.0, 36900.0, 36800.0, 37200.0, 100.5],
    ]


# ════════════════════════════════════════════════════════════════
#  ohlcv_to_dataframe : conversion + validation
# ════════════════════════════════════════════════════════════════

def test_ohlcv_to_dataframe_basic(valid_ohlcv_response):
    df = ds.ohlcv_to_dataframe(valid_ohlcv_response)
    assert len(df) == 3
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"


def test_ohlcv_to_dataframe_sorted_by_time(valid_ohlcv_response):
    df = ds.ohlcv_to_dataframe(valid_ohlcv_response)
    assert df.index.is_monotonic_increasing


def test_ohlcv_to_dataframe_dtypes(valid_ohlcv_response):
    df = ds.ohlcv_to_dataframe(valid_ohlcv_response)
    for col in ("open", "high", "low", "close", "volume"):
        assert df[col].dtype.kind == "f"


def test_ohlcv_to_dataframe_empty_raises():
    with pytest.raises(ds.DataValidationError):
        ds.ohlcv_to_dataframe([])


def test_ohlcv_to_dataframe_invalid_ohlc_raises(invalid_ohlc_response):
    with pytest.raises(ds.DataValidationError, match="consistency"):
        ds.ohlcv_to_dataframe(invalid_ohlc_response)


def test_ohlcv_to_dataframe_negative_price_raises():
    bad = [[1700000000000, -37000.0, 37500.0, -37000.0, 37200.0, 100.5]]
    with pytest.raises(ds.DataValidationError, match="Non-positive"):
        ds.ohlcv_to_dataframe(bad)


def test_ohlcv_to_dataframe_dedupes_duplicate_timestamps():
    # Deux bougies avec le même timestamp → on garde la 1ère
    raw = [
        [1700000000000, 37000.0, 37500.0, 36800.0, 37200.0, 100.5],
        [1700000000000, 99999.0, 99999.0, 99999.0, 99999.0, 0.0],
    ]
    df = ds.ohlcv_to_dataframe(raw)
    assert len(df) == 1
    assert df["close"].iloc[0] == 37200.0


# ════════════════════════════════════════════════════════════════
#  detect_anomalous_jumps
# ════════════════════════════════════════════════════════════════

def test_detect_anomalous_jumps_none_when_calm(valid_ohlcv_response):
    df = ds.ohlcv_to_dataframe(valid_ohlcv_response)
    anomalies = ds.detect_anomalous_jumps(df, max_jump_pct=0.30)
    assert len(anomalies) == 0


def test_detect_anomalous_jumps_catches_50pct_drop():
    raw = [
        [1700000000000, 37000.0, 37500.0, 36800.0, 37200.0, 100.5],
        [1700003600000, 37200.0, 37300.0, 17000.0, 18000.0, 120.0],
    ]
    df = ds.ohlcv_to_dataframe(raw)
    anomalies = ds.detect_anomalous_jumps(df, max_jump_pct=0.30)
    assert len(anomalies) == 1


# ════════════════════════════════════════════════════════════════
#  fetch_ohlcv : mock ccxt.kraken
# ════════════════════════════════════════════════════════════════

@patch("paper_trading.data_source.ccxt.kraken")
def test_fetch_ohlcv_success(mock_kraken_class, valid_ohlcv_response):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_ohlcv.return_value = valid_ohlcv_response
    mock_kraken_class.return_value = mock_instance

    out = ds.fetch_ohlcv("BTC/USD", interval="1h", limit=3)
    assert out == valid_ohlcv_response
    mock_instance.fetch_ohlcv.assert_called_once()


@patch("paper_trading.data_source.ccxt.kraken")
def test_fetch_ohlcv_exchange_error_raises_no_retry(mock_kraken_class):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_ohlcv.side_effect = ccxt.ExchangeError("Bad symbol")
    mock_kraken_class.return_value = mock_instance

    with pytest.raises(ds.ExchangeAPIError, match="Kraken error"):
        ds.fetch_ohlcv("BADSYM/USD", interval="1h", limit=3)
    assert mock_instance.fetch_ohlcv.call_count == 1  # pas de retry


@patch("paper_trading.data_source.time.sleep", return_value=None)
@patch("paper_trading.data_source.ccxt.kraken")
def test_fetch_ohlcv_network_error_retries(mock_kraken_class, mock_sleep, valid_ohlcv_response):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    # 2 erreurs réseau puis succès
    mock_instance.fetch_ohlcv.side_effect = [
        ccxt.NetworkError("Timeout"),
        ccxt.NetworkError("DNS failed"),
        valid_ohlcv_response,
    ]
    mock_kraken_class.return_value = mock_instance

    out = ds.fetch_ohlcv("BTC/USD", interval="1h", limit=3, max_retries=3)
    assert out == valid_ohlcv_response
    assert mock_instance.fetch_ohlcv.call_count == 3


@patch("paper_trading.data_source.time.sleep", return_value=None)
@patch("paper_trading.data_source.ccxt.kraken")
def test_fetch_ohlcv_persistent_network_error_raises(mock_kraken_class, mock_sleep):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_ohlcv.side_effect = ccxt.NetworkError("Down")
    mock_kraken_class.return_value = mock_instance

    with pytest.raises(ds.ExchangeAPIError, match="after"):
        ds.fetch_ohlcv("BTC/USD", max_retries=2)
    assert mock_instance.fetch_ohlcv.call_count == 2


def test_fetch_ohlcv_invalid_interval():
    with pytest.raises(ValueError, match="Interval"):
        ds.fetch_ohlcv("BTC/USD", interval="2h")


def test_fetch_ohlcv_invalid_limit():
    with pytest.raises(ValueError):
        ds.fetch_ohlcv("BTC/USD", limit=0)
    with pytest.raises(ValueError):
        ds.fetch_ohlcv("BTC/USD", limit=5000)


# ════════════════════════════════════════════════════════════════
#  ping_kraken
# ════════════════════════════════════════════════════════════════

@patch("paper_trading.data_source.ccxt.kraken")
def test_ping_kraken_ok(mock_kraken_class):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_status.return_value = {"status": "ok"}
    mock_kraken_class.return_value = mock_instance
    assert ds.ping_kraken() is True


@patch("paper_trading.data_source.ccxt.kraken")
def test_ping_kraken_status_not_ok(mock_kraken_class):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_status.return_value = {"status": "maintenance"}
    mock_kraken_class.return_value = mock_instance
    assert ds.ping_kraken() is False


@patch("paper_trading.data_source.ccxt.kraken")
def test_ping_kraken_exception_returns_false(mock_kraken_class):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_status.side_effect = Exception("DNS failed")
    mock_kraken_class.return_value = mock_instance
    assert ds.ping_kraken() is False


# ════════════════════════════════════════════════════════════════
#  fetch_recent_h1 : intégration mock
# ════════════════════════════════════════════════════════════════

@patch("paper_trading.data_source.ccxt.kraken")
def test_fetch_recent_h1_ok(mock_kraken_class, valid_ohlcv_response):
    mock_instance = MagicMock()
    mock_instance.rateLimit = 3000
    mock_instance.fetch_ohlcv.return_value = valid_ohlcv_response
    mock_kraken_class.return_value = mock_instance

    df = ds.fetch_recent_h1("BTC", n_bars=3)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3


def test_fetch_recent_h1_unknown_asset():
    with pytest.raises(ValueError, match="Unknown"):
        ds.fetch_recent_h1("DOGE")


# ════════════════════════════════════════════════════════════════
#  fetch_all_assets_h1
# ════════════════════════════════════════════════════════════════

@patch("paper_trading.data_source.fetch_recent_h1")
def test_fetch_all_assets_partial_failure(mock_fetch):
    def side_effect(asset, n_bars):
        if asset == "SOL":
            raise ds.ExchangeAPIError("Down for SOL")
        return pd.DataFrame({"close": [100.0]})

    mock_fetch.side_effect = side_effect
    out = ds.fetch_all_assets_h1(n_bars=5, assets=["BTC", "ETH", "SOL"])
    assert "BTC" in out
    assert "ETH" in out
    assert "SOL" not in out


@patch("paper_trading.data_source.fetch_recent_h1")
def test_fetch_all_assets_total_failure_raises(mock_fetch):
    mock_fetch.side_effect = ds.ExchangeAPIError("All down")
    with pytest.raises(ds.DataSourceError, match="All"):
        ds.fetch_all_assets_h1(n_bars=5, assets=["BTC", "ETH"])


# ════════════════════════════════════════════════════════════════
#  Test live (réseau requis) — désactivé par défaut
# ════════════════════════════════════════════════════════════════

@pytest.mark.live
def test_kraken_live_smoke():
    """Test smoke contre la vraie API Kraken. Run: pytest -m live"""
    assert ds.ping_kraken() is True
    df = ds.fetch_recent_h1("BTC", n_bars=5)
    assert len(df) == 5
    assert df["close"].iloc[-1] > 0
