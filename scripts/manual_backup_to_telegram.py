"""
manual_backup_to_telegram.py — Validate Telegram backup configuration.

WHAT THIS DOES
==============
Manually triggers a Telegram backup using force=True, regardless of the
current UTC hour. This lets you validate that:
1. Telegram bot token and chat_id are correctly configured in .env
2. The bot can connect to Telegram API
3. The file actually arrives on your phone

This script does NOT touch the production state.db. It uses a temporary
fake DB so you can run it any time without side effects on real data.

USAGE
=====
    python -m scripts.manual_backup_to_telegram

WHAT TO EXPECT
==============
- Terminal shows the snapshot being created
- Terminal shows the Telegram send attempt
- If success: you'll receive a .db.gz file on Telegram in seconds
- If failure: error message will tell you what's wrong (token, chat_id, etc.)

If anything goes wrong, check:
- .env file has TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID set correctly
- The bot has been started by you via Telegram (/start) at least once
- Network connectivity to api.telegram.org
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import tempfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from paper_trading import config
from paper_trading.backup import BackupManager


def main():
    print("=" * 64)
    print("  MANUAL BACKUP TO TELEGRAM — validation test")
    print("=" * 64)

    # Check config presence first
    token_set = bool(config.TELEGRAM_BOT_TOKEN)
    chat_id_set = bool(config.TELEGRAM_CHAT_ID)

    print(f"\nTELEGRAM_BOT_TOKEN configured : {'✅ yes' if token_set else '❌ NO'}")
    print(f"TELEGRAM_CHAT_ID configured  : {'✅ yes' if chat_id_set else '❌ NO'}")

    if not token_set or not chat_id_set:
        print("\n❌ Cannot proceed — Telegram credentials missing.")
        print("   Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to your .env file.")
        sys.exit(1)

    # Create a temporary fake DB
    tmpdir = Path(tempfile.mkdtemp(prefix="manual_backup_test_"))
    db_path = tmpdir / "state.db"
    backup_dir = tmpdir / "backups"

    print(f"\nTemp workspace: {tmpdir}")

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test_table (id INTEGER, message TEXT)")
    conn.execute(
        "INSERT INTO test_table VALUES (?, ?)",
        (1, "Manual Telegram backup test — if you got this file, everything works!"),
    )
    conn.commit()
    conn.close()
    db_size = db_path.stat().st_size
    print(f"Fake DB created: {db_path.name} ({db_size} bytes)")

    # Create a BackupManager pointing to the temp workspace
    bm = BackupManager(
        db_path=db_path,
        backup_dir=backup_dir,
        max_keep=10,
        telegram_enabled=True,
    )

    # Step 1: take a snapshot
    print("\n[1/2] Creating snapshot...")
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    snap = bm.snapshot(timestamp_iso=now_iso)
    if not snap.ok:
        print(f"   ❌ Snapshot failed: {snap.error}")
        sys.exit(1)
    print(f"   ✅ Snapshot created: {snap.path.name} ({snap.size_bytes} bytes)")

    # Step 2: force-send to Telegram
    print("\n[2/2] Sending to Telegram (force=True, ignoring schedule)...")
    result = bm.maybe_send_to_telegram(timestamp_iso=now_iso, force=True)

    print()
    if result.ok and not result.skipped:
        print("=" * 64)
        print("  ✅ SUCCESS — Telegram backup sent!")
        print("=" * 64)
        print(f"\n  HTTP status : {result.http_status}")
        print(f"  Check your Telegram now — you should have a .db.gz file.")
        print(f"\n  Snapshot name: {snap.path.name}")
        print(f"  Snapshot size: {snap.size_bytes} bytes")
    elif result.skipped:
        print("=" * 64)
        print(f"  ⚠️  SKIPPED — {result.skip_reason}")
        print("=" * 64)
        print("\n  This shouldn't happen with force=True. Check the code.")
        sys.exit(1)
    else:
        print("=" * 64)
        print("  ❌ FAILED")
        print("=" * 64)
        print(f"\n  Error      : {result.error}")
        print(f"  HTTP status: {result.http_status}")
        print("\n  Common causes:")
        print("  - Invalid TELEGRAM_BOT_TOKEN (check format: number:letters)")
        print("  - Invalid TELEGRAM_CHAT_ID (must be your numeric chat id)")
        print("  - You haven't started the bot conversation (/start in Telegram)")
        print("  - Network issue")
        sys.exit(1)

    print(f"\n  Temp workspace remains at: {tmpdir}")
    print(f"  (You can rm -rf it manually when done inspecting)")


if __name__ == "__main__":
    main()
