"""
config.py — Single source of truth for all paper trading parameters.

All values are FROZEN at Session 5 baseline (CONFIG A) unless explicitly
documented as a Session 6 paper-trading-specific setting.

DO NOT modify ICC strategy parameters here. They are defined in
strategies/icc_cycle.py and we respect that.
"""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field

# ════════════════════════════════════════════════════════════════
#                    PATHS & FILESYSTEM
# ════════════════════════════════════════════════════════════════

# Root of the trading-bot-v2 project (parent of paper_trading/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Where paper_trading state and logs live
PAPER_TRADING_DIR = PROJECT_ROOT / "paper_trading"
LOGS_DIR = PAPER_TRADING_DIR / "logs"
STATE_DB_PATH = PAPER_TRADING_DIR / "state.db"

# Ensure logs directory exists at startup
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════
#                    .ENV LOADING (Telegram, etc.)
# ════════════════════════════════════════════════════════════════

def _load_env() -> dict[str, str]:
    """Load .env file from PROJECT_ROOT into a dict (no external library)."""
    env_path = PROJECT_ROOT / ".env"
    out: dict[str, str] = {}
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


def env(key: str, default: str | None = None) -> str | None:
    """Read a value from .env (or fall back to OS environment)."""
    return _ENV.get(key, os.environ.get(key, default))


# ════════════════════════════════════════════════════════════════
#                    TELEGRAM
# ════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

# At least logs work even without Telegram
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


# ════════════════════════════════════════════════════════════════
#                    CAPITAL & SIZING (Decision 3)
# ════════════════════════════════════════════════════════════════

# Session 6 starts here. Easy to change later.
INITIAL_CAPITAL = float(env("INITIAL_CAPITAL", "1000"))

# How to split across assets — equal weight by default
# 8 assets => each can hold up to 12.5% of capital
MAX_POSITION_PCT_PER_ASSET = 0.125  # 12.5%


# ════════════════════════════════════════════════════════════════
#                    ASSETS (Decision 2)
# ════════════════════════════════════════════════════════════════

# 8 cryptos backtested in Session 5 — all profitable on walk-forward
# IMPORTANT: Binance uses USDT pairs (not USD). Mapping below.
ASSETS = ["BTC", "ETH", "SOL", "ADA", "LINK", "DOT", "AVAX", "LTC"]

# Symbol mapping: our internal name → Binance symbol
BINANCE_SYMBOLS = {
    "BTC":  "BTCUSDT",
    "ETH":  "ETHUSDT",
    "SOL":  "SOLUSDT",
    "ADA":  "ADAUSDT",
    "LINK": "LINKUSDT",
    "DOT":  "DOTUSDT",
    "AVAX": "AVAXUSDT",
    "LTC":  "LTCUSDT",
}


# ════════════════════════════════════════════════════════════════
#                    FREQUENCY (Decision 1)
# ════════════════════════════════════════════════════════════════

# H1 = 1 decision per hour (aligned with backtest)
DECISION_INTERVAL_SECONDS = 3600  # 1 hour

# After H1 bar closes at XX:00 UTC, wait this many seconds before fetching
# (give Binance time to finalize the bar)
POST_BAR_DELAY_SECONDS = 10


# ════════════════════════════════════════════════════════════════
#                    SLIPPAGE & FEES (Simulated)
# ════════════════════════════════════════════════════════════════

# Conservative slippage estimate (median of 0.05% to 0.15% range)
SLIPPAGE_PCT = 0.001  # 0.10%

# Binance maker/taker fees (standard tier, before VIP discounts)
FEE_PCT_PER_LEG = 0.001  # 0.10% per entry AND per exit
# Total round-trip fees = ~0.20% per trade


# ════════════════════════════════════════════════════════════════
#                    STOPS AUTOMATIQUES (Decision 4)
# ════════════════════════════════════════════════════════════════

# Global drawdown stop: if equity falls 15% below peak → HALT bot
MAX_DRAWDOWN_PCT = 0.15  # 15%

# Daily loss stop: if equity falls 10% from 00:00 UTC level → HALT bot
MAX_DAILY_LOSS_PCT = 0.10  # 10%


# ════════════════════════════════════════════════════════════════
#                    DATA SOURCES (Decision 6)
# ════════════════════════════════════════════════════════════════

# Primary: Binance public API (no account needed)
BINANCE_BASE_URL = "https://api.binance.com"
BINANCE_KLINES_ENDPOINT = "/api/v3/klines"
BINANCE_PING_ENDPOINT = "/api/v3/ping"

# Number of H1 bars to keep in rolling buffer (enough context for ICC)
# ICC daily structure needs ~30 days = 30*24 = 720 H1 bars minimum
# Take double for safety: 1500 H1 bars (~2 months)
ROLLING_BUFFER_SIZE = 1500

# Fallback: Kraken public if Binance down (NOT IMPLEMENTED in Bloc 2,
# left as TODO for resilience phase)
ENABLE_KRAKEN_FALLBACK = False


# ════════════════════════════════════════════════════════════════
#                    LOGGING & MONITORING (Decision 5)
# ════════════════════════════════════════════════════════════════

LOG_LEVEL = env("LOG_LEVEL", "INFO")

# Heartbeat: send "still alive" message once per day at this UTC hour
HEARTBEAT_HOUR_UTC = 12

# Weekly recap: send weekly P&L summary on Sunday at this UTC hour
WEEKLY_RECAP_DAY = 6   # 0=Monday, 6=Sunday
WEEKLY_RECAP_HOUR = 21


# ════════════════════════════════════════════════════════════════
#                    SAFETY GUARDS
# ════════════════════════════════════════════════════════════════

# Never trade more than this fraction of available capital at once
# (protection against runaway sizing bugs)
ABSOLUTE_MAX_EXPOSURE = 1.0  # 100% — we never use leverage in paper

# Halt the bot if the live price diverges by more than this % from
# the last seen price (protection against data glitches)
PRICE_SANITY_MAX_JUMP_PCT = 0.30  # 30% in one bar = something is wrong


# ════════════════════════════════════════════════════════════════
#                    DEV / DEBUG TOGGLES
# ════════════════════════════════════════════════════════════════

# Set to True during development to skip the H1 wait and process
# multiple historical bars in fast succession (for testing only)
DEV_FAST_MODE = bool(env("DEV_FAST_MODE", ""))


# ════════════════════════════════════════════════════════════════
#                    SUMMARY (printed on bot start)
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
║ Data source            : Binance public ({BINANCE_BASE_URL})
║ State DB               : {STATE_DB_PATH}
║ Logs dir               : {LOGS_DIR}
║ Dev fast mode          : {DEV_FAST_MODE}
╚══════════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    print(summary())
