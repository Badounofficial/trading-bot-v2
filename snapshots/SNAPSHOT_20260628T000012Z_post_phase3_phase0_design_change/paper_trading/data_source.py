"""
data_source.py — Récupération des bougies depuis Kraken (via ccxt).

Pourquoi Kraken :
- US-friendly (pas de blocage géographique comme Binance)
- C'est l'exchange backtesté en Session 5 → cohérence parfaite
- Free public API, no account needed
- ccxt gère le rate limit, le retry, et le format

Conception :
- ccxt.kraken() avec enableRateLimit=True (~3s entre requêtes max)
- fetch_ohlcv pour les bougies (interval paramétrable : '1m', '1h', '4h', '1d', ...)
- Conversion en DataFrame standard (open, high, low, close, volume)
- Tout en UTC, jamais de timezone locale
- Validation des données (OHLC cohérent, prix > 0, pas de NaN)

Conventions :
- En interne et dans le reste du code, on garde nos noms d'actifs "BTC", "ETH", ...
- ccxt utilise "BTC/USD", "ETH/USD", ... → mapping fait dans config.BINANCE_SYMBOLS
  (renommé en CCXT_SYMBOLS conceptuellement, mais on garde le nom pour rétro-compat)
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import ccxt
import pandas as pd

from paper_trading import config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    EXCEPTIONS DÉDIÉES
# ════════════════════════════════════════════════════════════════

class DataSourceError(Exception):
    """Erreur générique du data source. Toujours catch-able."""


class ExchangeAPIError(DataSourceError):
    """Erreur côté exchange (réseau, 5xx, rate limit)."""


class DataValidationError(DataSourceError):
    """Données reçues mais invalides (prix aberrants, gaps, etc.)."""


# ════════════════════════════════════════════════════════════════
#                    EXCHANGE SINGLETON
# ════════════════════════════════════════════════════════════════

_exchange: Optional[ccxt.Exchange] = None


def get_exchange() -> ccxt.Exchange:
    """Retourne une instance singleton de ccxt.kraken.

    On utilise un singleton pour :
    - Réutiliser la session HTTP (plus rapide)
    - Garder l'état du rate limiter cohérent entre appels
    - Charger les markets une seule fois
    """
    global _exchange
    if _exchange is None:
        _exchange = ccxt.kraken({
            'enableRateLimit': True,  # respecte automatiquement les limites
            'timeout': 15000,  # 15s timeout par requête
        })
        logger.info("Initialized ccxt.kraken (rateLimit=%dms)", _exchange.rateLimit)
    return _exchange


# ════════════════════════════════════════════════════════════════
#                    PING / HEALTHCHECK
# ════════════════════════════════════════════════════════════════

def ping_kraken(timeout: float = 5.0) -> bool:
    """Test de connectivité à Kraken (via fetch_status, méthode standard ccxt).

    Returns:
        True si Kraken répond avec status 'ok', False sinon.
        Ne lève jamais d'exception.
    """
    try:
        ex = get_exchange()
        # ccxt fournit fetch_status qui pinge l'exchange
        status = ex.fetch_status()
        ok = status.get('status') == 'ok'
        if not ok:
            logger.warning("Kraken status unexpected: %s", status)
        return ok
    except Exception as e:
        logger.warning("Kraken ping failed: %s", e)
        return False


# ════════════════════════════════════════════════════════════════
#                    LOW-LEVEL : FETCH OHLCV
# ════════════════════════════════════════════════════════════════

# Map de nos intervals "interne" → format ccxt
# (ccxt utilise les mêmes strings que la plupart des exchanges)
_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h",
    "1d": "1d",
}


def fetch_ohlcv(
    symbol: str,
    interval: str = "1h",
    limit: int = 500,
    since_ms: Optional[int] = None,
    max_retries: int = 3,
) -> list[list]:
    """Récupère des bougies brutes depuis Kraken via ccxt.

    Args:
        symbol: ex. "BTC/USD" (format ccxt standard)
        interval: "1m", "5m", "15m", "30m", "1h", "4h", "1d"
        limit: nombre de bougies (Kraken accepte jusqu'à 720 typiquement)
        since_ms: timestamp ms pour démarrer (None = bougies les plus récentes)
        max_retries: tentatives en cas d'erreur réseau

    Returns:
        Liste de listes au format ccxt standard :
        [[ts_ms, open, high, low, close, volume], ...]

    Raises:
        ExchangeAPIError : après max_retries échecs
        ValueError : interval ou paramètres invalides
    """
    if interval not in _INTERVAL_MAP:
        raise ValueError(
            f"Interval '{interval}' inconnu. Supportés: {list(_INTERVAL_MAP)}"
        )
    if limit < 1 or limit > 1000:
        raise ValueError(f"limit doit être entre 1 et 1000, reçu {limit}")

    ex = get_exchange()
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            candles = ex.fetch_ohlcv(
                symbol=symbol,
                timeframe=_INTERVAL_MAP[interval],
                since=since_ms,
                limit=limit,
            )
            if not isinstance(candles, list):
                raise ExchangeAPIError(
                    f"ccxt returned non-list for {symbol}: {type(candles).__name__}"
                )
            return candles

        except ccxt.NetworkError as e:
            last_error = e
            logger.warning(
                "Network error %d/%d for %s: %s",
                attempt + 1, max_retries, symbol, str(e)[:100],
            )
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
        except ccxt.ExchangeError as e:
            # ExchangeError = erreur Kraken explicite (mauvais symbole, etc.)
            # On ne retry pas — souvent c'est une erreur de paramètre.
            raise ExchangeAPIError(f"Kraken error for {symbol}: {e}") from e

    raise ExchangeAPIError(
        f"Failed to fetch {symbol} {interval} after {max_retries} retries: "
        f"last error = {last_error}"
    )


# ════════════════════════════════════════════════════════════════
#                    PARSING : RAW OHLCV → DATAFRAME
# ════════════════════════════════════════════════════════════════

# Colonnes ccxt standard : [timestamp_ms, open, high, low, close, volume]
_CCXT_OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def ohlcv_to_dataframe(raw: list[list]) -> pd.DataFrame:
    """Convertit la liste brute ccxt en DataFrame standard OHLCV.

    Index : pd.DatetimeIndex en UTC, indexé sur l'ouverture de la bougie.
    Colonnes : open, high, low, close, volume (tous en float).

    Raises:
        DataValidationError : si les données sont vides ou malformées.
    """
    if not raw:
        raise DataValidationError("Empty OHLCV response from exchange")

    df = pd.DataFrame(raw, columns=_CCXT_OHLCV_COLUMNS)

    # Conversion timestamp ms → datetime UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    # Tous les autres en float
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="raise")

    # Index = timestamp, tri chronologique, déduplication
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # Validation : pas de NaN, pas de prix négatifs ou zéro
    if df[["open", "high", "low", "close"]].isna().any().any():
        raise DataValidationError("NaN values in OHLC data")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataValidationError("Non-positive prices detected")

    # Validation OHLC : high >= max(open, close) et low <= min(open, close)
    bad_high = (df["high"] < df[["open", "close"]].max(axis=1))
    bad_low = (df["low"] > df[["open", "close"]].min(axis=1))
    if bad_high.any() or bad_low.any():
        n_bad = int(bad_high.sum() + bad_low.sum())
        raise DataValidationError(
            f"OHLC consistency violation: {n_bad} bars with high<max or low>min"
        )

    return df


# ════════════════════════════════════════════════════════════════
#                    SANITY CHECK : prix sain ?
# ════════════════════════════════════════════════════════════════

def detect_anomalous_jumps(
    df: pd.DataFrame,
    max_jump_pct: float = config.PRICE_SANITY_MAX_JUMP_PCT,
) -> pd.DataFrame:
    """Détecte les sauts de prix anormaux entre 2 clôtures consécutives.

    Returns:
        Sous-DataFrame des lignes anormales (vide si tout est OK).
        Le caller décide : alerter, ignorer, ou halt le bot.
    """
    if len(df) < 2:
        return df.iloc[0:0]
    pct_change = df["close"].pct_change().abs()
    anomalies = df[pct_change > max_jump_pct]
    if len(anomalies):
        logger.warning(
            "%d anomalous price jumps detected (> %.1f%%)",
            len(anomalies), max_jump_pct * 100,
        )
    return anomalies


# ════════════════════════════════════════════════════════════════
#                    HIGH-LEVEL : par actif ICC
# ════════════════════════════════════════════════════════════════

def fetch_recent_h1(asset: str, n_bars: int = 500) -> pd.DataFrame:
    """Récupère les `n_bars` dernières bougies H1 pour un actif ICC.

    Args:
        asset: "BTC", "ETH", "SOL", ... (clé de config.BINANCE_SYMBOLS)
        n_bars: nombre de bougies à récupérer

    Returns:
        DataFrame OHLCV avec index UTC.

    Raises:
        ValueError : si asset inconnu
        ExchangeAPIError, DataValidationError : voir fonctions appelées
    """
    if asset not in config.BINANCE_SYMBOLS:
        raise ValueError(
            f"Unknown asset '{asset}'. Known: {list(config.BINANCE_SYMBOLS)}"
        )
    symbol = config.BINANCE_SYMBOLS[asset]
    raw = fetch_ohlcv(symbol=symbol, interval="1h", limit=n_bars)
    df = ohlcv_to_dataframe(raw)
    logger.info("Fetched %d H1 bars for %s (%s)", len(df), asset, symbol)
    return df


def fetch_all_assets_h1(
    n_bars: int = 500,
    assets: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Récupère les bougies H1 pour tous les actifs (séquentiel).

    On reste séquentiel volontairement :
    - 8 actifs × ~1s (avec rate limit ccxt) = ~8s total, acceptable pour H1
    - Pas de complexité async/thread
    - Plus facile à débugger si un actif pose problème

    Args:
        n_bars: bougies par actif
        assets: liste optionnelle. Par défaut, config.ASSETS.

    Returns:
        Dict {asset: DataFrame}. Les actifs ayant échoué sont ABSENTS du dict.

    Raises:
        DataSourceError : si TOUS les actifs échouent.
    """
    if assets is None:
        assets = config.ASSETS

    out: dict[str, pd.DataFrame] = {}
    for asset in assets:
        try:
            out[asset] = fetch_recent_h1(asset, n_bars=n_bars)
        except (ExchangeAPIError, DataValidationError, ValueError) as e:
            logger.error("Failed to fetch %s: %s", asset, e)
            continue

    if not out:
        raise DataSourceError("All asset fetches failed — Kraken unreachable?")

    missing = set(assets) - set(out.keys())
    if missing:
        logger.warning("Partial fetch: missing %s", sorted(missing))

    return out


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : test rapide en CLI
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print("  data_source.py — test rapide (Kraken via ccxt)")
    print("=" * 60)

    print("\n[1/3] Ping Kraken...")
    if not ping_kraken():
        print("    ❌ Kraken ne répond pas. Vérifie ta connexion.")
        raise SystemExit(1)
    print("    ✅ Kraken répond")

    print("\n[2/3] Fetch 10 dernières bougies H1 BTC...")
    df = fetch_recent_h1("BTC", n_bars=10)
    print(f"    ✅ {len(df)} bougies reçues")
    print(f"    Période : {df.index.min()} → {df.index.max()}")
    print(f"    Dernier close BTC : ${df['close'].iloc[-1]:,.2f}")

    print("\n[3/3] Fetch H1 pour les 8 actifs (séquentiel)...")
    all_data = fetch_all_assets_h1(n_bars=5)
    for asset, df in all_data.items():
        last_close = df["close"].iloc[-1]
        print(f"    ✅ {asset:5s}: {len(df)} bars, last close ${last_close:,.4f}")

    print("\n" + "=" * 60)
    print("  data_source.py OK")
    print("=" * 60)
