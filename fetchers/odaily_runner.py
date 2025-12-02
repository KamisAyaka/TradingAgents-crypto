import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tradingagents.dataflows.odaily import sync_articles, sync_newsflash


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("odaily-runner")


async def _run_task(name: str, interval_seconds: int, func) -> None:
    """Run a sync function periodically."""
    while True:
        try:
            start = datetime.utcnow()
            logger.info("Starting %s sync", name)
            func()
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info("Completed %s sync in %.2f seconds", name, elapsed)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Error during %s sync: %s", name, exc)

        await asyncio.sleep(interval_seconds)


async def run_loop(
    newsflash_interval: int = 900,
    article_interval: int = 3600,
) -> None:
    """Run newsflash and article sync loops concurrently."""
    await asyncio.gather(
        _run_task("newsflash", newsflash_interval, sync_newsflash),
        _run_task("articles", article_interval, sync_articles),
    )


def main(
    newsflash_interval: Optional[int] = None,
    article_interval: Optional[int] = None,
) -> None:
    """
    Entry point for running Odaily fetcher in parallel loops.
    Set custom intervals (seconds) via parameters; defaults are 5 min for newsflash and 15 min for articles.
    """
    nf_interval = newsflash_interval or 900
    art_interval = article_interval or 3600
    logger.info(
        "Launching Odaily fetcher (newsflash every %ss, articles every %ss)",
        nf_interval,
        art_interval,
    )
    asyncio.run(run_loop(nf_interval, art_interval))


if __name__ == "__main__":
    main()
