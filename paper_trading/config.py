"""
config.py — Single source of truth for all paper trading parameters.

All values are FROZEN at Session 5 baseline (CONFIG A) unless explicitly
documented as a Session 6 paper-trading-specific setting.

DO NOT modify ICC strategy parameters here. They are defined in
strategies/icc_cycle.py and we respect that.

DATA SOURCE NOTE (v2):
Initially designed for Binance public API, switched to Kraken because:
- Binance is geo-blocked in the US (where the user is)
- Kraken is the exchange we backtested in Session 5 (perfect data parity)
- Already used in data/fetch_universe.py with ccxt
"""
from __future__ import annotations
import os
from pathlib import Path

# ════════════════════════════════════════════════════════════════
#                    PATHS & FILESYSTEM
# ════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPER_TRADING_DIR = PROJECT_ROOT / "paper_trading"
LOGS_DIR = PAPER_TRADING_DIR / "logs"
STATE_DB_PATH = PAPER_TRADING_DIR / "state.db"

# Backup paths (Niveau 2 + 3: local snapshots + Telegram sync)
BACKUPS_DIR = PAPER_TRADING_DIR / "backups"
LAST_TELEGRAM_BACKUP_FILE = PAPER_TRADING_DIR / ".last_telegram_backup"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
#                    .ENV LOADING
# ════════════════════════════════════════════════════════════════

def _load_env() -> dict:
    """Load .env file from PROJECT_ROOT into a dict (no external library)."""
    env_path = PROJECT_ROOT / ".env"
    out: dict = {}
    if not env_path.exists():
        return out
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            out[key] = value
    return out


_ENV = _load_env()


def env(key: str, default=None):
    """Read a value from .env (or fall back to OS environment)."""
    return _ENV.get(key, os.environ.get(key, default))


# ════════════════════════════════════════════════════════════════
#                    TELEGRAM
# ════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


# ════════════════════════════════════════════════════════════════
#                    CAPITAL & SIZING (Decision 3)
# ════════════════════════════════════════════════════════════════

INITIAL_CAPITAL = float(env("INITIAL_CAPITAL", "1000"))
MAX_POSITION_PCT_PER_ASSET = 0.125  # 12.5% (8 assets equal weight)


# ════════════════════════════════════════════════════════════════
#                    ASSETS (Decision 2)
# ════════════════════════════════════════════════════════════════

# 8 cryptos backtested in Session 5 — all profitable on walk-forward
ASSETS = ["BTC", "ETH", "SOL", "ADA", "LINK", "DOT", "AVAX", "LTC"]

# Symbol mapping: our internal name → ccxt pair format used by Kraken
# (kept variable name BINANCE_SYMBOLS for backward compat with code,
#  but the values are Kraken/ccxt format now)
BINANCE_SYMBOLS = {
    "BTC":  "BTC/USD",
    "ETH":  "ETH/USD",
    "SOL":  "SOL/USD",
    "ADA":  "ADA/USD",
    "LINK": "LINK/USD",
    "DOT":  "DOT/USD",
    "AVAX": "AVAX/USD",
    "LTC":  "LTC/USD",
}


# ════════════════════════════════════════════════════════════════
#                    FREQUENCY (Decision 1)
# ════════════════════════════════════════════════════════════════

DECISION_INTERVAL_SECONDS = 3600  # 1 hour
POST_BAR_DELAY_SECONDS = 10  # wait this long after XX:00 UTC before fetching


# ════════════════════════════════════════════════════════════════
#                    SLIPPAGE & FEES (Simulated)
# ════════════════════════════════════════════════════════════════

SLIPPAGE_PCT = 0.001  # 0.10%
FEE_PCT_PER_LEG = 0.0016  # 0.16% per entry AND per exit (Kraken standard)


# ════════════════════════════════════════════════════════════════
#                    STOPS AUTOMATIQUES (Decision 4)
# ════════════════════════════════════════════════════════════════

MAX_DRAWDOWN_PCT = 0.15  # 15%
MAX_DAILY_LOSS_PCT = 0.10  # 10%


# ════════════════════════════════════════════════════════════════
#                    DATA SOURCE (Decision 6 — Kraken)
# ════════════════════════════════════════════════════════════════

# Number of H1 bars to keep in rolling buffer (enough context for ICC)
# ICC daily structure needs ~30 days = 30*24 = 720 H1 bars minimum
# Take double for safety: 1500 H1 bars (~2 months)
ROLLING_BUFFER_SIZE = 1500


# ════════════════════════════════════════════════════════════════
#                    LOGGING & MONITORING (Decision 5)
# ════════════════════════════════════════════════════════════════

LOG_LEVEL = env("LOG_LEVEL", "INFO")

HEARTBEAT_HOUR_UTC = 12
WEEKLY_RECAP_DAY = 6   # 0=Monday, 6=Sunday
WEEKLY_RECAP_HOUR = 21


# ════════════════════════════════════════════════════════════════
#                    BACKUP (Niveau 2 + 3)
# ════════════════════════════════════════════════════════════════

# Niveau 2 — Local rotating snapshots (after each successful cycle)
#
# Snapshots are taken AFTER each cycle's transaction commits (in
# paper_trader._post_cycle_backup). They are NOT taken mid-cycle in
# _exec_close because the SQLite transaction is still open — a snapshot
# would capture incoherent state. The post-cycle snapshot already
# captures all closes of the cycle anyway.
BACKUP_MAX_KEEP = 24            # Garde les N derniers snapshots locaux (24 = 1 jour de cycles H1)

# Niveau 3 — Telegram backup (granularité 6h)
TELEGRAM_BACKUP_HOURS_UTC = [0, 6, 12, 18]   # Envoi DB sur Telegram à ces heures UTC
TELEGRAM_BACKUP_ENABLED = True   # Si True ET TELEGRAM_* set dans .env → envoi automatique


# ════════════════════════════════════════════════════════════════
#                    SAFETY GUARDS
# ════════════════════════════════════════════════════════════════

ABSOLUTE_MAX_EXPOSURE = 1.0  # No leverage in paper
PRICE_SANITY_MAX_JUMP_PCT = 0.30  # 30% in one bar = anomaly


# ════════════════════════════════════════════════════════════════
#                    DEV / DEBUG TOGGLES
# ════════════════════════════════════════════════════════════════

DEV_FAST_MODE = bool(env("DEV_FAST_MODE", ""))


# ════════════════════════════════════════════════════════════════
#                    SUMMARY
# ════════════════════════════════════════════════════════════════

def summary() -> str:
    """Human-readable summary of the configuration."""
    return f"""
╔══════════════════════════════════════════════════════════════╗
║         PAPER TRADING — Session 6 Configuration               ║
╠══════════════════════════════════════════════════════════════╣
║ Capital                : ${INITIAL_CAPITAL:,.2f}
║ Assets                 : {len(ASSETS)} ({', '.join(ASSETS)})
║ Frequency              : H1 (every {DECISION_INTERVAL_SECONDS}s)
║ Slippage simulated     : {SLIPPAGE_PCT*100:.2f}%
║ Fees simulated         : {FEE_PCT_PER_LEG*100:.2f}% per leg (round-trip {FEE_PCT_PER_LEG*2*100:.2f}%)
║ Max drawdown halt      : {MAX_DRAWDOWN_PCT*100:.1f}%
║ Max daily loss halt    : {MAX_DAILY_LOSS_PCT*100:.1f}%
║ Telegram enabled       : {TELEGRAM_ENABLED}
║ Data source            : Kraken (via ccxt, US-friendly)
║ State DB               : {STATE_DB_PATH}
║ Logs dir               : {LOGS_DIR}
║ Dev fast mode          : {DEV_FAST_MODE}
╚══════════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    print(summary())
