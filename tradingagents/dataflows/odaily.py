import json
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

import feedparser

ODAILY_NEWSFLASH_URL = "https://rss.odaily.news/rss/newsflash"
ODAILY_ARTICLE_URL = "https://rss.odaily.news/rss/post"

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "odaily_rss.db"
TAG_RE = re.compile(r"<[^>]+>")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]) -> None:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def _ensure_db() -> None:
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


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, time.struct_time):
        return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc).isoformat()
    return str(value)


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    text = TAG_RE.sub("", value)
    return unescape(text).strip()


def _entry_to_record(entry: Any) -> Dict[str, Any]:
    entry_id = getattr(entry, "id", None) or entry.get("id")
    fallback_id = entry.get("link") or entry.get("title")
    entry_id = entry_id or fallback_id
    published_iso = None
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        published_iso = datetime.fromtimestamp(
            time.mktime(published_parsed), tz=timezone.utc
        ).isoformat()

    tags = []
    for tag in entry.get("tags", []):
        term = tag.get("term") if isinstance(tag, dict) else getattr(tag, "term", None)
        if term:
            tags.append(term)

    if "content" in entry and entry["content"]:
        content_parts = [
            part.get("value", "") for part in entry["content"] if isinstance(part, dict)
        ]
        content = "\n\n".join(filter(None, content_parts))
    else:
        content = entry.get("summary", "")

    summary_html = entry.get("summary", "")
    summary = _strip_html(summary_html)
    raw_json = json.dumps(entry, default=_serialize_value)
    category = entry.get("category", "")
    author = entry.get("author") or entry.get("dc_creator") or ""
    guid = entry.get("guid") or entry.get("id") or entry.get("link") or ""

    return {
        "entry_id": entry_id,
        "title": entry.get("title", "").strip(),
        "summary": summary.strip(),
        "content": content.strip(),
        "link": entry.get("link", ""),
        "published": published_iso,
        "tags": ",".join(tags),
        "raw_json": raw_json,
        "fetched_at": _utcnow().isoformat(),
        "category": category,
        "author": author,
        "guid": guid,
    }


def _upsert(table: str, record: Dict[str, Any]) -> None:
    _ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"""
            INSERT INTO {table} (
                entry_id, title, summary, content, link,
                published, tags, raw_json, fetched_at,
                category, author, guid
            ) VALUES (
                :entry_id, :title, :summary, :content, :link,
                :published, :tags, :raw_json, :fetched_at,
                :category, :author, :guid
            )
            ON CONFLICT(entry_id) DO UPDATE SET
                title=excluded.title,
                summary=excluded.summary,
                content=excluded.content,
                link=excluded.link,
                published=excluded.published,
                tags=excluded.tags,
                raw_json=excluded.raw_json,
                fetched_at=excluded.fetched_at,
                category=excluded.category,
                author=excluded.author,
                guid=excluded.guid
            """,
            record,
        )
        conn.commit()


def _fetch_and_store(feed_url: str, table: str) -> List[Dict[str, Any]]:
    parsed = feedparser.parse(feed_url)
    entries: List[Dict[str, Any]] = []
    for entry in parsed.entries:
        record = _entry_to_record(entry)
        if record["entry_id"]:
            _upsert(table, record)
            entries.append(record)
    return entries


def sync_newsflash() -> List[Dict[str, Any]]:
    return _fetch_and_store(ODAILY_NEWSFLASH_URL, "newsflash")


def sync_articles() -> List[Dict[str, Any]]:
    return _fetch_and_store(ODAILY_ARTICLE_URL, "articles")


def _query_entries(
    table: str,
    limit: int,
    cutoff: Optional[datetime],
) -> List[Dict[str, Any]]:
    _ensure_db()
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
    _ensure_db()
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
