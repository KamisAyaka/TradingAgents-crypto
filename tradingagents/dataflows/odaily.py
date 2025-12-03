import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "odaily_rss.db"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def ensure_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS newsflash (
                entry_id TEXT PRIMARY KEY,
                title TEXT,
                summary TEXT,
                content TEXT,
                link TEXT,
                published TEXT,
                tags TEXT,
                raw_json TEXT,
                fetched_at TEXT,
                category TEXT,
                author TEXT,
                guid TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                entry_id TEXT PRIMARY KEY,
                title TEXT,
                summary TEXT,
                content TEXT,
                link TEXT,
                published TEXT,
                tags TEXT,
                raw_json TEXT,
                fetched_at TEXT,
                category TEXT,
                author TEXT,
                guid TEXT
            )
            """
        )
        _ensure_columns(
            conn,
            "newsflash",
            {"category": "TEXT", "author": "TEXT", "guid": "TEXT"},
        )
        _ensure_columns(
            conn,
            "articles",
            {"category": "TEXT", "author": "TEXT", "guid": "TEXT"},
        )
        conn.commit()


def _query_entries(
    table: str,
    limit: int,
    cutoff: Optional[datetime],
) -> List[Dict[str, Any]]:
    ensure_db()
    query = f"""
        SELECT entry_id, title, summary, content, link,
               published, tags, raw_json, fetched_at,
               category, author, guid
        FROM {table}
    """
    params: List[Any] = []
    if cutoff:
        query += " WHERE datetime(COALESCE(published, fetched_at)) >= datetime(?)"
        params.append(cutoff.isoformat())
    query += " ORDER BY datetime(COALESCE(published, fetched_at)) DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    results: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["tags"] = (
            record["tags"].split(",") if record.get("tags") else []
        )
        results.append(record)
    return results


def _query_article_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT entry_id, title, summary, content, link,
                   published, tags, raw_json, fetched_at,
                   category, author, guid
            FROM articles
            WHERE entry_id = ? OR guid = ?
            LIMIT 1
            """,
            (entry_id, entry_id),
        ).fetchone()
    return dict(row) if row else None


def get_newsflash(
    limit: int = 20,
    lookback_hours: int = 24,
) -> List[Dict[str, Any]]:
    cutoff = None
    if lookback_hours:
        cutoff = _utcnow() - timedelta(hours=lookback_hours)
    return _query_entries("newsflash", limit, cutoff)


def get_articles(
    limit: int = 10,
    lookback_days: int = 7,
) -> List[Dict[str, Any]]:
    cutoff = None
    if lookback_days:
        cutoff = _utcnow() - timedelta(days=lookback_days)
    return _query_entries("articles", limit, cutoff)


def get_article_candidates(
    limit: int = 20,
    lookback_days: int = 7,
) -> List[Dict[str, Any]]:
    rows = get_articles(limit=limit, lookback_days=lookback_days)
    candidates = []
    for row in rows:
        candidates.append(
            {
                "entry_id": row["entry_id"],
                "title": row["title"],
            }
        )
    return candidates


def get_article_content_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    return _query_article_by_id(entry_id)
