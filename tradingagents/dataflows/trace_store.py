import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_TRACE_DB = "trace_store.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceStore:
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
                CREATE TABLE IF NOT EXISTS trace_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trace_runs_created_at ON trace_runs(created_at)"
            )
            conn.commit()

    def add_trace(self, payload: str, created_at: Optional[str] = None) -> None:
        created_at = created_at or _utcnow_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO trace_runs (created_at, payload) VALUES (?, ?)",
                (created_at, payload),
            )
            conn.commit()

    def get_latest_trace(self) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT payload
                FROM trace_runs
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return {"payload": row["payload"]}

    def get_trace_history(self, limit: int = 20, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) AS cnt FROM trace_runs").fetchone()
            rows = conn.execute(
                """
                SELECT id, created_at, payload
                FROM trace_runs
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        total_count = int(total["cnt"]) if total else 0
        records = [
            {"id": row["id"], "created_at": row["created_at"], "payload": row["payload"]}
            for row in rows
        ]
        return records, total_count
