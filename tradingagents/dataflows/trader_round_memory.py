import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


DEFAULT_DB_NAME = "trader_round_memory.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraderRoundMemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        base_dir = os.path.dirname(self.db_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trader_rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    round_id INTEGER,
                    assets TEXT,
                    situation TEXT,
                    summary TEXT NOT NULL,
                    decision TEXT,
                    asset TEXT,
                    is_open_entry INTEGER DEFAULT 0,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    leverage INTEGER
                )
                """
            )
            self._ensure_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS price_alert_state (
                    symbol TEXT PRIMARY KEY,
                    last_trigger_at TEXT,
                    last_reason TEXT,
                    last_price REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trader_rounds_created_at ON trader_rounds(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trader_rounds_asset ON trader_rounds(asset)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trader_rounds_decision ON trader_rounds(decision)"
            )
            conn.commit()

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(trader_rounds)")}
        if "entry_price" not in existing:
            conn.execute("ALTER TABLE trader_rounds ADD COLUMN entry_price REAL")
        if "stop_loss" not in existing:
            conn.execute("ALTER TABLE trader_rounds ADD COLUMN stop_loss REAL")
        if "take_profit" not in existing:
            conn.execute("ALTER TABLE trader_rounds ADD COLUMN take_profit REAL")
        if "leverage" not in existing:
            conn.execute("ALTER TABLE trader_rounds ADD COLUMN leverage INTEGER")

    def add_round(
        self,
        summary: str,
        situation: str,
        assets: List[str],
        round_id: int,
        decision: Optional[str] = None,
        asset: Optional[str] = None,
        is_open_entry: bool = False,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        leverage: Optional[int] = None,
        created_at: Optional[str] = None,
    ) -> None:
        created_at = created_at or _utcnow_iso()
        assets_text = ",".join(assets or [])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trader_rounds (
                    created_at, round_id, assets, situation, summary,
                    decision, asset, is_open_entry, entry_price, stop_loss,
                    take_profit, leverage
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    round_id,
                    assets_text,
                    situation,
                    summary,
                    decision,
                    asset,
                    1 if is_open_entry else 0,
                    entry_price,
                    stop_loss,
                    take_profit,
                    leverage,
                ),
            )
            conn.commit()

    def get_last_round_time(self) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT created_at FROM trader_rounds
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return row["created_at"] if row else None

    def get_recent_rounds(self, limit: int = 2) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM trader_rounds
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_open_position_context(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT r.*
                FROM trader_rounds r
                WHERE r.is_open_entry = 1
                  AND r.asset IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM trader_rounds c
                      WHERE c.asset = r.asset
                        AND c.created_at > r.created_at
                        AND c.decision IN ('CLOSE_LONG', 'CLOSE_SHORT')
                  )
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def get_latest_open_entry(self, asset: str) -> Optional[Dict[str, Any]]:
        if not asset:
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM trader_rounds
                WHERE asset = ?
                  AND decision IN ('LONG', 'SHORT')
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (asset,),
            ).fetchone()
        return dict(row) if row else None

    def get_first_open_entry_since_close(self, asset: str) -> Optional[Dict[str, Any]]:
        if not asset:
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM trader_rounds
                WHERE asset = ?
                  AND decision IN ('LONG', 'SHORT')
                  AND created_at > COALESCE(
                      (
                          SELECT MAX(created_at)
                          FROM trader_rounds
                          WHERE asset = ?
                            AND decision IN ('CLOSE_LONG', 'CLOSE_SHORT')
                      ),
                      ''
                  )
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (asset, asset),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_alert_band(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT *
                FROM trader_rounds
                WHERE decision IN ('LONG', 'SHORT')
                  AND (stop_loss IS NOT NULL OR take_profit IS NOT NULL)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def get_alert_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not symbol:
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM price_alert_state WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        return dict(row) if row else None

    def set_alert_state(
        self, symbol: str, last_trigger_at: str, last_reason: str, last_price: float
    ) -> None:
        if not symbol:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO price_alert_state (symbol, last_trigger_at, last_reason, last_price)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    last_trigger_at=excluded.last_trigger_at,
                    last_reason=excluded.last_reason,
                    last_price=excluded.last_price
                """,
                (symbol, last_trigger_at, last_reason, last_price),
            )
            conn.commit()

    def prune_recent(self, keep_n: int = 100) -> None:
        if keep_n <= 0:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                DELETE FROM trader_rounds
                WHERE id NOT IN (
                    SELECT id FROM trader_rounds
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (keep_n,),
            )
            conn.commit()
