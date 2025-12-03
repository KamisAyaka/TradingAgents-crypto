"""
Odaily RSS 抓取工具。

职责：
1. 定时从 Odaily 的快讯/文章 RSS 源读取内容。
2. 将结构化后的文本写入 SQLite，供 dataflow 直接读取而无需再联网。
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List

import feedparser

from tradingagents.dataflows.odaily import DB_PATH, ensure_db

ODAILY_NEWSFLASH_URL = "https://rss.odaily.news/rss/newsflash"
ODAILY_ARTICLE_URL = "https://rss.odaily.news/rss/post"
TAG_RE = re.compile(r"<[^>]+>")


def _serialize_value(value: Any) -> Any:
    """递归把 feedparser 的复杂对象转换成可序列化的基础类型。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, time.struct_time):
        return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc).isoformat()
    return str(value)


def _strip_html(value: str | None) -> str:
    """移除 summary/内容里的 HTML 标签，返回干净文本。"""
    if not value:
        return ""
    text = TAG_RE.sub("", value)
    return unescape(text).strip()


def _entry_to_record(entry: Any) -> Dict[str, Any]:
    """把 RSS entry 转成数据库行字段，附带去重 ID、标签等信息。"""
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
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "author": author,
        "guid": guid,
    }


def _upsert(table: str, record: Dict[str, Any]) -> None:
    """向指定表写入记录，已存在则更新，确保重复内容不会插入多条。"""
    ensure_db()
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
    """抓取单个 RSS 源并写入数据库，返回本次处理的记录列表。"""
    parsed = feedparser.parse(feed_url)
    entries: List[Dict[str, Any]] = []
    for entry in parsed.entries:
        record = _entry_to_record(entry)
        if record["entry_id"]:
            _upsert(table, record)
            entries.append(record)
    return entries


def sync_newsflash() -> List[Dict[str, Any]]:
    """同步快讯 RSS。"""
    return _fetch_and_store(ODAILY_NEWSFLASH_URL, "newsflash")


def sync_articles() -> List[Dict[str, Any]]:
    """同步长文 RSS。"""
    return _fetch_and_store(ODAILY_ARTICLE_URL, "articles")
