"""Binance 抓取器入口脚本，循环调用 fetcher 刷新行情。"""

import asyncio
import logging
import os
import sys
from typing import List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fetchers.binance_fetcher import sync_binance_pairs


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("binance-runner")


async def _run_loop(
    symbols: List[str],
    intervals: List[str],
    limit: int,
    refresh_interval: int,
) -> None:
    """无限循环执行同步任务，并在出错时打印日志后重试。"""
    while True:
        try:
            logger.info(
                "开始同步 Binance K 线（symbols=%s, intervals=%s）",
                ",".join(symbols),
                ",".join(intervals),
            )
            summary = sync_binance_pairs(symbols, intervals, limit=limit)
            logger.info("本轮同步摘要: %s", summary)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Binance 同步失败: %s", exc)

        await asyncio.sleep(refresh_interval)


def main() -> None:
    """读取环境变量并启动同步循环。"""
    symbols = [s.strip().upper() for s in os.getenv("BINANCE_SYMBOLS", "BTCUSDT").split(",") if s.strip()]
    intervals = [i.strip() for i in os.getenv("BINANCE_INTERVALS", "1h,4h").split(",") if i.strip()]
    limit = int(os.getenv("BINANCE_SYNC_LIMIT", "50"))
    refresh = int(os.getenv("BINANCE_SYNC_INTERVAL", "900"))  # 默认 15 分钟

    if not symbols or not intervals:
        raise ValueError("必须提供 BINANCE_SYMBOLS 与 BINANCE_INTERVALS 环境变量")

    logger.info(
        "启动 Binance fetcher，symbols=%s intervals=%s limit=%s 刷新间隔=%ss",
        symbols,
        intervals,
        limit,
        refresh,
    )
    asyncio.run(_run_loop(symbols, intervals, limit, refresh))


if __name__ == "__main__":
    main()
