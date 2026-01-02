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
                    is_open_entry INTEGER DEFAULT 0
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

    def add_round(
        self,
        summary: str,
        situation: str,
        assets: List[str],
        round_id: int,
        decision: Optional[str] = None,
        asset: Optional[str] = None,
        is_open_entry: bool = False,
        created_at: Optional[str] = None,
    ) -> None:
        created_at = created_at or _utcnow_iso()
        assets_text = ",".join(assets or [])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO trader_rounds (
                    created_at, round_id, assets, situation, summary,
                    decision, asset, is_open_entry
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            conn.commit()

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
