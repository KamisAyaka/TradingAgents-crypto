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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS longform_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                report TEXT NOT NULL,
                analysis_date TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(asset, analysis_date)
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
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_longform_analysis_asset_date
                ON longform_analysis(asset, analysis_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_longform_analysis_created_at
                ON longform_analysis(created_at)
            """
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


def _query_newsflash_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT entry_id, title, summary, content, link,
                   published, tags, raw_json, fetched_at,
                   category, author, guid
            FROM newsflash
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


def get_newsflash_candidates(
    limit: int = 20,
    lookback_hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Retrieve recent Odaily newsflash titles with metadata for LLM screening.
    """
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


def get_newsflash_content_by_id(entry_id: str) -> Optional[Dict[str, Any]]:
    return _query_newsflash_by_id(entry_id)


GLOBAL_LONGFORM_KEY = "__GLOBAL_LONGFORM__"


def save_longform_analysis(
    report: str,
    asset: Optional[str] = None,
    analysis_date: Optional[str] = None,
) -> None:
    """Persist a synthesized longform analysis so intraday runs can reuse it."""
    ensure_db()
    timestamp = _utcnow().isoformat()
    asset_key = asset or GLOBAL_LONGFORM_KEY
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO longform_analysis (asset, report, analysis_date, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(asset, analysis_date) DO UPDATE SET
                report=excluded.report,
                created_at=excluded.created_at
            """,
            (asset_key, report, analysis_date, timestamp),
        )
        conn.commit()


def get_latest_longform_analysis(
    asset: Optional[str] = None,
    max_age_days: Optional[int] = 14,
) -> Optional[Dict[str, Any]]:
    """Fetch the newest cached longform analysis (optionally filtered by asset)."""
    ensure_db()
    params: List[Any] = []
    conditions: List[str] = []

    if asset:
        conditions.append("asset = ?")
        params.append(asset)
    if max_age_days is not None:
        cutoff = (_utcnow() - timedelta(days=max_age_days)).isoformat()
        conditions.append("datetime(created_at) >= datetime(?)")
        params.append(cutoff)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT report, analysis_date, created_at
        FROM longform_analysis
        {where_clause}
        ORDER BY datetime(COALESCE(analysis_date, created_at)) DESC,
                 datetime(created_at) DESC
        LIMIT 1
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(query, params).fetchone()
    return dict(row) if row else None
