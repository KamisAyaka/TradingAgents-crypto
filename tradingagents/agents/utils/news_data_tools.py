from langchain_core.tools import tool
import re
from typing import Annotated, List, Dict
from tradingagents.dataflows.odaily import (
    get_newsflash_candidates,
    get_newsflash_content_by_id,
    get_article_content_by_id,
    get_article_candidates,
)


def _parse_entry_ids(raw: str) -> List[str]:
    """规范化逗号/换行分隔的 entry ID。"""
    if not raw:
        return []
    normalized = raw.replace("\n", ",")
    parsed: List[str] = []
    for token in normalized.split(","):
        candidate = token.strip()
        if not candidate:
            continue
        # 允许 "ID=123" 或 URL 末尾带数字等格式
        if "=" in candidate:
            candidate = candidate.split("=", 1)[1].strip()
        last_segment = candidate.split("/")[-1].strip()
        last_segment = last_segment.rstrip(")., ")
        if last_segment.isdigit():
            parsed.append(last_segment)
            continue
        match = re.search(r"(\d+)", last_segment)
        if match:
            parsed.append(match.group(1))
    return parsed


@tool
def get_crypto_newsflash_candidates(
    limit: Annotated[int, "返回标题数量"] = 40,
    lookback_hours: Annotated[int, "回溯窗口（小时）"] = 6,
) -> str:
    """
    获取最近的 Odaily 快讯标题与元数据，供 LLM 筛选。
    """
    entries = get_newsflash_candidates(limit=limit, lookback_hours=lookback_hours)
    if not entries:
        return "No recent news flashes available."
    lines = ["Recent Odaily news flashes (ID + Title):"]
    for idx, entry in enumerate(entries, 1):
        lines.append(f"{idx}. ID={entry['entry_id']} | Title: {entry['title']}")
    return "\n".join(lines)


@tool
def get_crypto_newsflash_content(
    entry_ids: Annotated[str, "候选列表返回的 entry_id（逗号分隔）"],
) -> str:
    """
    根据 entry_id 列表获取 Odaily 快讯的关键字段（标题、摘要、发布时间）。
    """
    parsed_ids = _parse_entry_ids(entry_ids)
    if not parsed_ids:
        return "No valid entry IDs were provided."

    chunks: List[str] = []
    for entry_id in parsed_ids:
        newsflash = get_newsflash_content_by_id(entry_id)
        if not newsflash:
            chunks.append(f"Entry ID {entry_id}: not found.")
            continue
        published = newsflash.get("published") or "Unknown"
        summary = newsflash.get("summary") or ""
        title = newsflash.get("title") or ""
        chunks.append(
            f"Title: {title}\n"
            f"Entry ID: {newsflash.get('entry_id')}\n"
            f"Published: {published}\n\n"
            f"Summary: {summary}"
        )

    return "\n\n".join(chunks)


@tool
def get_crypto_longform_candidates(
    limit: Annotated[int, "返回标题数量"] = 20,
    lookback_days: Annotated[int, "回溯窗口（天）"] = 7,
) -> str:
    """
    获取最近的 Odaily 长文标题与元数据，供 LLM 筛选。
    """
    entries = get_article_candidates(limit=limit, lookback_days=lookback_days)
    if not entries:
        return "No recent long-form articles available."
    lines = ["Recent Odaily long-form articles (ID + Title):"]
    for idx, entry in enumerate(entries, 1):
        lines.append(f"{idx}. ID={entry['entry_id']} | Title: {entry['title']}")
    return "\n".join(lines)


@tool
def get_crypto_article_content(
    entry_id: Annotated[str, "候选列表返回的 entry_id"],
) -> str:
    """
    根据 entry_id 获取 Odaily 长文的关键字段（标题、摘要、发布时间）。
    """
    article = get_article_content_by_id(entry_id)
    if not article:
        return f"No article found for entry_id={entry_id}"
    published = article.get("published") or "Unknown"
    summary = article.get("summary") or ""
    title = article.get("title") or ""
    return (
        f"Title: {title}\n"
        f"Entry ID: {article.get('entry_id')}\n"
        f"Published: {published}\n\n"
        f"Summary: {summary}"
    )
