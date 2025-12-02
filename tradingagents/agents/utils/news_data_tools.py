from langchain_core.tools import tool
from typing import Annotated, List, Dict
from tradingagents.dataflows.odaily import (
    get_newsflash as fetch_odaily_newsflash,
    get_articles as fetch_odaily_articles,
    get_article_candidates,
    get_article_content_by_id,
)


def _format_odaily_entries(entries: List[Dict], entry_type: str) -> str:
    if not entries:
        return f"No {entry_type} entries found for the requested window."

    lines = [f"{entry_type.title()} entries ({len(entries)}):"]
    for entry in entries:
        published = entry.get("published") or entry.get("fetched_at")
        title = entry.get("title") or "Untitled"
        summary = entry.get("summary") or ""
        lines.append(
            f"- [{published}] {title}\n  Summary: {summary}"
        )
    return "\n".join(lines)


@tool
def get_crypto_newsflash(
    limit: Annotated[int, "Maximum number of news flashes to return"] = 20,
    lookback_hours: Annotated[int, "Lookback window in hours"] = 24,
) -> str:
    """
    Retrieve crypto market news flashes from Odaily RSS and store cached copies in SQLite.
    """
    entries = fetch_odaily_newsflash(limit=limit, lookback_hours=lookback_hours)
    return _format_odaily_entries(entries, "newsflash")


@tool
def get_crypto_longform_articles(
    limit: Annotated[int, "Maximum number of articles to return"] = 3,
    lookback_days: Annotated[int, "Lookback window in days"] = 7,
) -> str:
    """
    Retrieve longer-form crypto articles from Odaily RSS and store cached copies in SQLite.
    """
    entries = fetch_odaily_articles(limit=limit, lookback_days=lookback_days)
    return _format_odaily_entries(entries, "article")


@tool
def get_crypto_longform_candidates(
    limit: Annotated[int, "Number of titles to retrieve"] = 20,
    lookback_days: Annotated[int, "Lookback window in days"] = 7,
) -> str:
    """
    Retrieve recent Odaily long-form article titles with metadata for LLM screening.
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
    entry_id: Annotated[str, "Entry ID returned from candidate list"],
) -> str:
    """
    Retrieve key fields (title, summary, published) from Odaily by entry_id.
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
