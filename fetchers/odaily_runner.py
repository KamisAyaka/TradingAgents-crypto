"""Odaily 抓取器入口，负责定时同步快讯与文章。"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fetchers.odaily_fetcher import sync_articles, sync_newsflash


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("odaily-runner")


async def _run_task(name: str, interval_seconds: int, func) -> None:
    """按固定间隔运行同步函数，并记录耗时及异常。"""
    while True:
        try:
            start = datetime.utcnow()
            logger.info("开始执行 %s 同步任务", name)
            func()
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.info("%s 同步完成，用时 %.2f 秒", name, elapsed)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("%s 同步出错: %s", name, exc)

        await asyncio.sleep(interval_seconds)


async def run_loop(
    newsflash_interval: int = 900,
    article_interval: int = 3600,
) -> None:
    """并发运行快讯与文章的同步循环。"""
    await asyncio.gather(
        _run_task("newsflash", newsflash_interval, sync_newsflash),
        _run_task("articles", article_interval, sync_articles),
    )


def main(
    newsflash_interval: Optional[int] = None,
    article_interval: Optional[int] = None,
) -> None:
    """
    脚本入口：可传入自定义的同步间隔（秒），默认快讯 900 秒、文章 3600 秒。
    """
    nf_interval = newsflash_interval or 900
    art_interval = article_interval or 3600
    logger.info(
        "启动 Odaily fetcher（快讯 %ss/次，文章 %ss/次）",
        nf_interval,
        art_interval,
    )
    asyncio.run(run_loop(nf_interval, art_interval))


if __name__ == "__main__":
    main()
