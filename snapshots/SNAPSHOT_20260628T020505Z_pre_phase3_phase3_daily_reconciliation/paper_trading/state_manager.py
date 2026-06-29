"""
state_manager.py — Persistance SQLite de l'état du paper trading.

DESIGN CHOICES (Session 6, locked):
1. Transaction par cycle H1: pendant un cycle, on accumule les changements
   en mémoire et on commit en bloc à la fin → atomicité totale
2. Schéma normalisé en 4 tables : open_positions, closed_trades,
   equity_snapshots, bot_state
3. Crash if corrupt: au démarrage, on vérifie la cohérence de la DB et
   on refuse de démarrer si quelque chose cloche (jamais de réparation auto)

PERSISTANCE GUARANTEE :
À tout moment du cycle, on peut tuer le process (kill -9, coupure courant).
Au redémarrage, on aura :
- Soit l'état du début du cycle (tout est rollback)
- Soit l'état de la fin du cycle (tout est commité)
Jamais un état "à mi-chemin".

USAGE TYPIQUE (orchestré par paper_trader.py au Bloc 7) :
    sm = StateManager()
    sm.open_cycle()  # begin transaction
    try:
        sm.open_position(...)
        sm.close_position(...)
        sm.record_equity_snapshot(...)
        sm.close_cycle()  # commit
    except Exception:
        sm.rollback_cycle()
        raise
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterator

from paper_trading import config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#                    EXCEPTIONS
# ════════════════════════════════════════════════════════════════

class StateManagerError(Exception):
    """Generic state manager error."""


class DatabaseCorruptError(StateManagerError):
    """The database is in an inconsistent state. Refuses to operate."""


class NoActiveCycleError(StateManagerError):
    """Tried to write data outside of an open cycle."""


# ════════════════════════════════════════════════════════════════
#                    DATACLASSES (representation in code)
# ════════════════════════════════════════════════════════════════

@dataclass
class OpenPosition:
    """A trade currently in the market (paper)."""
    position_id: str        # unique, e.g. "BTC_20260513T180000"
    asset: str              # "BTC", "ETH", ...
    direction: str          # "BUY" (long) for Session 6
    entry_timestamp: str    # ISO UTC, e.g. "2026-05-13T18:00:00Z"
    entry_price: float      # the strategy's requested price (H1 close)
    entry_fill_price: float # after slippage
    units: float
    initial_capital_used: float  # gross + fees at entry
    sl_price: float
    tp_price: float
    sl_source: Optional[str] = None  # "V1_H1_close_prev_HL" etc.
    tp_source: Optional[str] = None  # "OB_H4", "MEASURED_MOVE", ...
    sl_history: list = field(default_factory=list)  # list of (ts, price)
    partial_taken: bool = False  # 85% partial done already?


@dataclass
class ClosedTrade:
    """A completed trade (entry + exit recorded)."""
    trade_id: str           # same as position_id when it was open
    asset: str
    direction: str
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    entry_fill_price: float
    exit_price: float       # strategy's exit price (SL/TP/trailing)
    exit_fill_price: float  # after slippage
    units: float
    pnl_dollars: float
    pnl_pct: float
    total_fees: float
    total_slippage: float
    exit_reason: str        # "TP_HIT" | "SL_HIT" | "TRAILING_HIT" | "MANUAL"
    held_bars: int


@dataclass
class EquitySnapshot:
    """Snapshot of equity at a point in time (one per H1 cycle typically)."""
    timestamp: str          # ISO UTC
    cash: float             # available USD
    open_positions_value: float  # mark-to-market value of open positions
    equity: float           # cash + open_positions_value
    peak_equity: float      # all-time high water mark
    drawdown_pct: float     # (equity - peak) / peak, always <= 0


@dataclass
class BotState:
    """High-level state of the bot."""
    status: str             # "RUNNING" | "HALTED"
    halt_reason: Optional[str] = None  # filled when HALTED
    halt_timestamp: Optional[str] = None
    last_cycle_timestamp: Optional[str] = None  # last successfully completed cycle
    equity_at_day_start_utc: Optional[float] = None  # for daily loss check
    day_start_timestamp: Optional[str] = None  # YYYY-MM-DD that we anchored on


# ════════════════════════════════════════════════════════════════
#                    SQL SCHEMA
# ════════════════════════════════════════════════════════════════

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS open_positions (
    position_id           TEXT PRIMARY KEY,
    asset                 TEXT NOT NULL,
    direction             TEXT NOT NULL,
    entry_timestamp       TEXT NOT NULL,
    entry_price           REAL NOT NULL,
    entry_fill_price      REAL NOT NULL,
    units                 REAL NOT NULL,
    initial_capital_used  REAL NOT NULL,
    sl_price              REAL NOT NULL,
    tp_price              REAL NOT NULL,
    sl_source             TEXT,
    tp_source             TEXT,
    sl_history_json       TEXT NOT NULL DEFAULT '[]',
    partial_taken         INTEGER NOT NULL DEFAULT 0,
    CHECK (direction IN ('BUY', 'SELL')),
    CHECK (units > 0),
    CHECK (entry_price > 0),
    CHECK (sl_price > 0),
    CHECK (tp_price > 0)
);

CREATE INDEX IF NOT EXISTS idx_open_positions_asset ON open_positions(asset);

CREATE TABLE IF NOT EXISTS closed_trades (
    trade_id              TEXT PRIMARY KEY,
    asset                 TEXT NOT NULL,
    direction             TEXT NOT NULL,
    entry_timestamp       TEXT NOT NULL,
    exit_timestamp        TEXT NOT NULL,
    entry_price           REAL NOT NULL,
    entry_fill_price      REAL NOT NULL,
    exit_price            REAL NOT NULL,
    exit_fill_price       REAL NOT NULL,
    units                 REAL NOT NULL,
    pnl_dollars           REAL NOT NULL,
    pnl_pct               REAL NOT NULL,
    total_fees            REAL NOT NULL,
    total_slippage        REAL NOT NULL,
    exit_reason           TEXT NOT NULL,
    held_bars             INTEGER NOT NULL,
    CHECK (direction IN ('BUY', 'SELL')),
    CHECK (units > 0)
);

CREATE INDEX IF NOT EXISTS idx_closed_trades_asset ON closed_trades(asset);
CREATE INDEX IF NOT EXISTS idx_closed_trades_exit_ts ON closed_trades(exit_timestamp);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    timestamp             TEXT PRIMARY KEY,
    cash                  REAL NOT NULL,
    open_positions_value  REAL NOT NULL,
    equity                REAL NOT NULL,
    peak_equity           REAL NOT NULL,
    drawdown_pct          REAL NOT NULL,
    CHECK (drawdown_pct <= 0.00001)  -- allow tiny float fuzz at the peak
);

CREATE TABLE IF NOT EXISTS bot_state (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    status                      TEXT NOT NULL,
    halt_reason                 TEXT,
    halt_timestamp              TEXT,
    last_cycle_timestamp        TEXT,
    equity_at_day_start_utc     REAL,
    day_start_timestamp         TEXT,
    CHECK (status IN ('RUNNING', 'HALTED'))
);
"""


# ════════════════════════════════════════════════════════════════
#                    STATE MANAGER CLASS
# ════════════════════════════════════════════════════════════════

class StateManager:
    """Thin layer over SQLite providing transactional persistence.

    Usage pattern (orchestrated by paper_trader.py later):
        sm = StateManager()  # auto-init schema if needed
        sm.open_cycle()
        # ... reads + writes ...
        sm.close_cycle()  # commit

    Or use the context manager:
        with sm.cycle():
            sm.open_position(...)
            sm.record_equity_snapshot(...)
        # auto-commit on success, auto-rollback on exception
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.STATE_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._cycle_open: bool = False
        self._init_db()

    # ─── Connection helpers ───────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh connection (or reuse existing)."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            # isolation_level=None means we control transactions manually
            self._conn = sqlite3.connect(
                str(self.db_path),
                isolation_level=None,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._conn.row_factory = sqlite3.Row
            # Enforce CHECK constraints, enable WAL for crash safety
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        return self._conn

    def close(self) -> None:
        """Close the DB connection. Idempotent."""
        if self._conn is not None:
            if self._cycle_open:
                logger.warning("Closing connection with cycle still open — rolling back")
                self.rollback_cycle()
            self._conn.close()
            self._conn = None

    # ─── Schema init + integrity check ────────────────────────────

    def _init_db(self) -> None:
        """Create tables if needed, then verify integrity."""
        conn = self._connect()
        # Schema creation is a DDL; we run it as autocommit (no cycle needed)
        conn.executescript(_SCHEMA_SQL)
        # Record schema version on first init
        existing = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(_SCHEMA_VERSION),),
            )
        elif int(existing["value"]) != _SCHEMA_VERSION:
            raise DatabaseCorruptError(
                f"Schema version mismatch: DB has v{existing['value']}, "
                f"code expects v{_SCHEMA_VERSION}"
            )
        # Ensure bot_state has a singleton row
        has_bot_state = conn.execute(
            "SELECT 1 FROM bot_state WHERE id = 1"
        ).fetchone()
        if not has_bot_state:
            conn.execute(
                "INSERT INTO bot_state (id, status) VALUES (1, 'RUNNING')"
            )
        # Run integrity check (SQLite native)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise DatabaseCorruptError(
                f"SQLite integrity_check failed: {result[0] if result else 'no result'}"
            )

    # ─── Cycle / transaction management ───────────────────────────

    def open_cycle(self) -> None:
        """Begin a new transaction. Must be paired with close_cycle or rollback_cycle."""
        if self._cycle_open:
            raise StateManagerError("A cycle is already open")
        conn = self._connect()
        conn.execute("BEGIN")
        self._cycle_open = True

    def close_cycle(self) -> None:
        """Commit the current cycle."""
        if not self._cycle_open:
            raise NoActiveCycleError("close_cycle called without open_cycle")
        self._connect().execute("COMMIT")
        self._cycle_open = False

    def rollback_cycle(self) -> None:
        """Discard all writes made since open_cycle."""
        if not self._cycle_open:
            return
        try:
            self._connect().execute("ROLLBACK")
        finally:
            self._cycle_open = False

    @contextmanager
    def cycle(self) -> Iterator['StateManager']:
        """Context-manager wrapper: auto-commits or rollback on exception."""
        self.open_cycle()
        try:
            yield self
            self.close_cycle()
        except Exception:
            self.rollback_cycle()
            raise

    def _require_cycle(self) -> None:
        if not self._cycle_open:
            raise NoActiveCycleError(
                "This write requires an open cycle. Call open_cycle() first."
            )

    # ─── OPEN POSITIONS ───────────────────────────────────────────

    def open_position(self, pos: OpenPosition) -> None:
        """Insert a new open position."""
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO open_positions (
                position_id, asset, direction, entry_timestamp,
                entry_price, entry_fill_price, units, initial_capital_used,
                sl_price, tp_price, sl_source, tp_source,
                sl_history_json, partial_taken
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos.position_id, pos.asset, pos.direction, pos.entry_timestamp,
                pos.entry_price, pos.entry_fill_price, pos.units,
                pos.initial_capital_used,
                pos.sl_price, pos.tp_price, pos.sl_source, pos.tp_source,
                json.dumps(pos.sl_history),
                1 if pos.partial_taken else 0,
            ),
        )

    def update_position_sl(
        self,
        position_id: str,
        new_sl: float,
        timestamp: str,
        sl_source: Optional[str] = None,
    ) -> None:
        """Update SL on an existing open position (e.g. trailing)."""
        self._require_cycle()
        conn = self._connect()
        # Read current sl_history to append
        row = conn.execute(
            "SELECT sl_history_json FROM open_positions WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise StateManagerError(f"No open position with id {position_id}")
        history = json.loads(row["sl_history_json"])
        history.append([timestamp, new_sl])
        conn.execute(
            """
            UPDATE open_positions
            SET sl_price = ?, sl_source = COALESCE(?, sl_source),
                sl_history_json = ?
            WHERE position_id = ?
            """,
            (new_sl, sl_source, json.dumps(history), position_id),
        )

    def mark_partial_taken(self, position_id: str) -> None:
        """Record that the 85% partial close has been done (so we won't redo it)."""
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            "UPDATE open_positions SET partial_taken = 1 WHERE position_id = ?",
            (position_id,),
        )

    def get_open_positions(self) -> list[OpenPosition]:
        """Read all currently open positions (no cycle required, read-only)."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM open_positions ORDER BY entry_timestamp"
        ).fetchall()
        return [
            OpenPosition(
                position_id=r["position_id"],
                asset=r["asset"],
                direction=r["direction"],
                entry_timestamp=r["entry_timestamp"],
                entry_price=r["entry_price"],
                entry_fill_price=r["entry_fill_price"],
                units=r["units"],
                initial_capital_used=r["initial_capital_used"],
                sl_price=r["sl_price"],
                tp_price=r["tp_price"],
                sl_source=r["sl_source"],
                tp_source=r["tp_source"],
                sl_history=json.loads(r["sl_history_json"]),
                partial_taken=bool(r["partial_taken"]),
            )
            for r in rows
        ]

    def get_open_position(self, position_id: str) -> Optional[OpenPosition]:
        for p in self.get_open_positions():
            if p.position_id == position_id:
                return p
        return None

    def remove_open_position(self, position_id: str) -> None:
        """Delete an open position (after it has been closed and recorded)."""
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            "DELETE FROM open_positions WHERE position_id = ?",
            (position_id,),
        )

    # ─── CLOSED TRADES ────────────────────────────────────────────

    def record_closed_trade(self, trade: ClosedTrade) -> None:
        """Insert a completed trade into the historical log."""
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO closed_trades (
                trade_id, asset, direction, entry_timestamp, exit_timestamp,
                entry_price, entry_fill_price, exit_price, exit_fill_price,
                units, pnl_dollars, pnl_pct, total_fees, total_slippage,
                exit_reason, held_bars
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.trade_id, trade.asset, trade.direction,
                trade.entry_timestamp, trade.exit_timestamp,
                trade.entry_price, trade.entry_fill_price,
                trade.exit_price, trade.exit_fill_price,
                trade.units, trade.pnl_dollars, trade.pnl_pct,
                trade.total_fees, trade.total_slippage,
                trade.exit_reason, trade.held_bars,
            ),
        )

    def get_closed_trades(
        self,
        asset: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[ClosedTrade]:
        """Read closed trades, optionally filtered."""
        conn = self._connect()
        sql = "SELECT * FROM closed_trades"
        params: list = []
        if asset is not None:
            sql += " WHERE asset = ?"
            params.append(asset)
        sql += " ORDER BY exit_timestamp DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = conn.execute(sql, params).fetchall()
        return [
            ClosedTrade(
                trade_id=r["trade_id"], asset=r["asset"],
                direction=r["direction"],
                entry_timestamp=r["entry_timestamp"],
                exit_timestamp=r["exit_timestamp"],
                entry_price=r["entry_price"],
                entry_fill_price=r["entry_fill_price"],
                exit_price=r["exit_price"],
                exit_fill_price=r["exit_fill_price"],
                units=r["units"],
                pnl_dollars=r["pnl_dollars"], pnl_pct=r["pnl_pct"],
                total_fees=r["total_fees"], total_slippage=r["total_slippage"],
                exit_reason=r["exit_reason"], held_bars=r["held_bars"],
            )
            for r in rows
        ]

    # ─── EQUITY SNAPSHOTS ─────────────────────────────────────────

    def record_equity_snapshot(self, snap: EquitySnapshot) -> None:
        """Record an equity snapshot (typically once per H1 cycle)."""
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO equity_snapshots
            (timestamp, cash, open_positions_value, equity, peak_equity, drawdown_pct)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snap.timestamp, snap.cash, snap.open_positions_value,
                snap.equity, snap.peak_equity, snap.drawdown_pct,
            ),
        )

    def get_latest_equity_snapshot(self) -> Optional[EquitySnapshot]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM equity_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return EquitySnapshot(
            timestamp=row["timestamp"], cash=row["cash"],
            open_positions_value=row["open_positions_value"],
            equity=row["equity"], peak_equity=row["peak_equity"],
            drawdown_pct=row["drawdown_pct"],
        )

    def get_peak_equity(self) -> float:
        """Highest equity ever recorded (for drawdown calc)."""
        conn = self._connect()
        row = conn.execute(
            "SELECT MAX(peak_equity) AS peak FROM equity_snapshots"
        ).fetchone()
        return float(row["peak"]) if row["peak"] is not None else 0.0

    # ─── BOT STATE ────────────────────────────────────────────────

    def get_bot_state(self) -> BotState:
        conn = self._connect()
        row = conn.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
        if row is None:
            raise DatabaseCorruptError("bot_state singleton row is missing")
        return BotState(
            status=row["status"],
            halt_reason=row["halt_reason"],
            halt_timestamp=row["halt_timestamp"],
            last_cycle_timestamp=row["last_cycle_timestamp"],
            equity_at_day_start_utc=row["equity_at_day_start_utc"],
            day_start_timestamp=row["day_start_timestamp"],
        )

    def set_bot_state(self, state: BotState) -> None:
        self._require_cycle()
        conn = self._connect()
        conn.execute(
            """
            UPDATE bot_state
            SET status = ?, halt_reason = ?, halt_timestamp = ?,
                last_cycle_timestamp = ?,
                equity_at_day_start_utc = ?, day_start_timestamp = ?
            WHERE id = 1
            """,
            (
                state.status, state.halt_reason, state.halt_timestamp,
                state.last_cycle_timestamp,
                state.equity_at_day_start_utc, state.day_start_timestamp,
            ),
        )

    def halt(self, reason: str, timestamp: Optional[str] = None) -> None:
        """Convenience: set bot to HALTED with a reason. Must be in cycle."""
        self._require_cycle()
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        current = self.get_bot_state()
        current.status = "HALTED"
        current.halt_reason = reason
        current.halt_timestamp = ts
        self.set_bot_state(current)

    def resume(self) -> None:
        """Convenience: set bot back to RUNNING (manual operator action)."""
        self._require_cycle()
        current = self.get_bot_state()
        current.status = "RUNNING"
        current.halt_reason = None
        current.halt_timestamp = None
        self.set_bot_state(current)

    # ─── HEALTH / DEBUG ───────────────────────────────────────────

    def summary(self) -> dict:
        """Quick stats for logging / debug."""
        conn = self._connect()
        n_open = conn.execute("SELECT COUNT(*) AS n FROM open_positions").fetchone()["n"]
        n_closed = conn.execute("SELECT COUNT(*) AS n FROM closed_trades").fetchone()["n"]
        n_snaps = conn.execute("SELECT COUNT(*) AS n FROM equity_snapshots").fetchone()["n"]
        state = self.get_bot_state()
        return {
            "db_path": str(self.db_path),
            "open_positions": n_open,
            "closed_trades": n_closed,
            "equity_snapshots": n_snaps,
            "bot_status": state.status,
            "halt_reason": state.halt_reason,
            "last_cycle": state.last_cycle_timestamp,
        }


# ════════════════════════════════════════════════════════════════
#                    SCRIPT MODE : quick demo
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile, os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    # Use a temp file so we don't pollute the real DB
    tmpf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmpf.close()
    tmp_path = Path(tmpf.name)

    print("=" * 64)
    print("  state_manager.py — démo (DB temporaire)")
    print("=" * 64)
    print(f"  DB: {tmp_path}")

    sm = StateManager(db_path=tmp_path)
    print(f"\n[init] {sm.summary()}")

    # Cycle 1: open a position
    print("\n[cycle 1] open BTC position + equity snapshot")
    with sm.cycle():
        sm.open_position(OpenPosition(
            position_id="BTC_20260513T180000",
            asset="BTC", direction="BUY",
            entry_timestamp="2026-05-13T18:00:00Z",
            entry_price=80000.0, entry_fill_price=80080.0,
            units=0.001558, initial_capital_used=125.0,
            sl_price=78000.0, tp_price=84000.0,
            sl_source="V1_H1_close_prev_HL", tp_source="OB_H4",
        ))
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T18:00:00Z",
            cash=875.0, open_positions_value=125.0,
            equity=1000.0, peak_equity=1000.0, drawdown_pct=0.0,
        ))
        st = sm.get_bot_state()
        st.last_cycle_timestamp = "2026-05-13T18:00:00Z"
        sm.set_bot_state(st)
    print(f"  After commit: {sm.summary()}")

    # Cycle 2: trailing SL update
    print("\n[cycle 2] trailing SL from 78000 → 81500")
    with sm.cycle():
        sm.update_position_sl(
            "BTC_20260513T180000",
            new_sl=81500.0,
            timestamp="2026-05-13T20:00:00Z",
            sl_source="V1_H1_close_prev_HL",
        )
    pos = sm.get_open_position("BTC_20260513T180000")
    print(f"  SL is now: {pos.sl_price}, history: {pos.sl_history}")

    # Cycle 3: close the trade
    print("\n[cycle 3] close trade at TP")
    with sm.cycle():
        sm.record_closed_trade(ClosedTrade(
            trade_id="BTC_20260513T180000",
            asset="BTC", direction="BUY",
            entry_timestamp="2026-05-13T18:00:00Z",
            exit_timestamp="2026-05-13T22:00:00Z",
            entry_price=80000.0, entry_fill_price=80080.0,
            exit_price=84000.0, exit_fill_price=83916.0,
            units=0.001558,
            pnl_dollars=5.57, pnl_pct=0.0446,
            total_fees=0.41, total_slippage=0.26,
            exit_reason="TP_HIT", held_bars=4,
        ))
        sm.remove_open_position("BTC_20260513T180000")
        sm.record_equity_snapshot(EquitySnapshot(
            timestamp="2026-05-13T22:00:00Z",
            cash=1005.57, open_positions_value=0.0,
            equity=1005.57, peak_equity=1005.57, drawdown_pct=0.0,
        ))
    print(f"  {sm.summary()}")

    # Cycle 4: rollback test
    print("\n[cycle 4] testing rollback")
    try:
        with sm.cycle():
            sm.open_position(OpenPosition(
                position_id="ETH_20260513T230000",
                asset="ETH", direction="BUY",
                entry_timestamp="2026-05-13T23:00:00Z",
                entry_price=2200.0, entry_fill_price=2202.2,
                units=0.05, initial_capital_used=125.0,
                sl_price=2150.0, tp_price=2300.0,
            ))
            raise RuntimeError("Simulated mid-cycle crash!")
    except RuntimeError as e:
        print(f"  Caught expected: {e}")
    # After rollback, the ETH position should NOT be there
    if sm.get_open_position("ETH_20260513T230000") is None:
        print("  ✅ Rollback worked: ETH position not persisted")
    else:
        print("  ❌ Rollback FAILED: ETH position is still there!")

    # HALT test
    print("\n[cycle 5] HALT bot, then resume")
    with sm.cycle():
        sm.halt("Drawdown exceeded 15%", "2026-05-14T00:00:00Z")
    state = sm.get_bot_state()
    print(f"  Status: {state.status}, reason: {state.halt_reason}")
    with sm.cycle():
        sm.resume()
    state = sm.get_bot_state()
    print(f"  After resume: {state.status}")

    # Closed trades query
    print("\n[query] closed trades:")
    for t in sm.get_closed_trades():
        print(f"  {t.asset} {t.exit_reason}: PnL ${t.pnl_dollars:.2f} ({t.pnl_pct*100:.2f}%)")

    sm.close()
    os.unlink(tmp_path)

    print("\n" + "=" * 64)
    print("  state_manager.py OK")
    print("=" * 64)
