"""
run_production.py — Production entry point for the trading bot.

WHAT THIS DOES
==============
Launches the paper trader in continuous production mode:
- Uses the persistent state.db at paper_trading/state.db
- Runs run_forever() with NO max_cycles (infinite loop)
- Real Kraken data, real Telegram alerter, real backup system

This is the script you run when the bot should trade for real.
To stop: Ctrl+C (state is preserved in the DB, you can restart safely).

USAGE
=====
    python -m scripts.run_production

Optional environment variables:
    LOG_LEVEL=INFO (default) or DEBUG for verbose output

WHAT TO EXPECT
==============
1. Initial state dump (current equity, open positions, etc.)
2. "Sleeping XXs until next cycle..." (waits for next XX:00:10 UTC)
3. At XX:00:10 UTC: cycle runs (fetch + process + snapshot)
4. Loop forever until Ctrl+C

LOGS YOU'LL SEE EACH CYCLE
==========================
- INFO: "Fetched 720 H1 bars for {asset}" (8x)
- INFO: "Multi-TF prepared: ..." (8x)
- INFO: "Snapshot created: state_...db.gz"
- INFO: "Telegram backup skipped (expected): hour_X_not_scheduled" (most hours)
  OR
- INFO: "Telegram backup sent: state_...db.gz (X.X KB)" (at 0, 6, 12, 18 UTC)

PHONE NOTIFICATIONS
===================
- Heartbeat: once a day at HEARTBEAT_HOUR_UTC (=12 UTC by default)
- Backup .db.gz file: 4x/day at [0, 6, 12, 18] UTC
- HALT alert: only if drawdown >= 15% or daily loss >= 10%
"""
from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from paper_trading import config
from paper_trading.paper_trader import PaperTrader
from paper_trading.state_manager import StateManager


def main():
    print("=" * 72)
    print("  TRADING BOT — PRODUCTION MODE")
    print("=" * 72)
    print(f"\nAssets:       {', '.join(config.ASSETS)}")
    print(f"Capital:      ${config.INITIAL_CAPITAL:,.2f}")
    print(f"DB path:      {config.STATE_DB_PATH}")
    print(f"Backups dir:  {config.BACKUPS_DIR}")
    print(f"Telegram backup hours UTC: {config.TELEGRAM_BACKUP_HOURS_UTC}")
    print(f"Heartbeat hour UTC:        {config.HEARTBEAT_HOUR_UTC}")

    # Show current state if DB exists
    sm = StateManager()
    open_positions = sm.get_open_positions()
    closed_trades = sm.get_closed_trades()
    latest = sm.get_latest_equity_snapshot()
    bot_state = sm.get_bot_state()

    print(f"\n── Current state ──")
    print(f"Bot status:        {bot_state.status}")
    if bot_state.halt_reason:
        print(f"⚠ Halt reason:    {bot_state.halt_reason}")
    print(f"Open positions:    {len(open_positions)}")
    print(f"Closed trades:     {len(closed_trades)}")
    if latest:
        print(f"Last equity:       ${latest.equity:.2f}")
        print(f"Last snapshot:     {latest.timestamp}")
    else:
        print(f"Last equity:       (no snapshot yet — first launch)")

    if bot_state.status == "HALTED":
        print("\n⚠ ⚠ ⚠  BOT IS IN HALTED STATE  ⚠ ⚠ ⚠")
        print("It will not open new trades. Manual resume required.")
        print("To resume, use the state_manager API to set bot_state.status = 'RUNNING'.")
        print()
        response = input("Continue anyway (the loop will run but no trades)? [y/N]: ")
        if response.lower() != "y":
            print("Aborting.")
            sys.exit(0)

    print(f"\n── Launching forever loop ──")
    print(f"(Ctrl+C to stop. State is preserved in {config.STATE_DB_PATH}.)\n")

    # Real trader, real adapter, real fetcher, real backup, real Telegram
    trader = PaperTrader(state_manager=sm)

    try:
        trader.run_forever()  # No max_cycles = run until Ctrl+C
    except KeyboardInterrupt:
        print("\n\n──────────────────────────────────────")
        print("  Interrupted by user.")
        print("  State preserved in DB. Safe to restart anytime.")
        print("──────────────────────────────────────\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
