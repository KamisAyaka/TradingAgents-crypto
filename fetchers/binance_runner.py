import asyncio
import logging
import os
import sys
from typing import List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tradingagents.dataflows.binance import sync_binance_pairs


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
    while True:
        try:
            logger.info(
                "Syncing Binance klines (symbols=%s, intervals=%s)",
                ",".join(symbols),
                ",".join(intervals),
            )
            summary = sync_binance_pairs(symbols, intervals, limit=limit)
            logger.info("Sync summary: %s", summary)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Binance sync failed: %s", exc)

        await asyncio.sleep(refresh_interval)


def main() -> None:
    symbols = [s.strip().upper() for s in os.getenv("BINANCE_SYMBOLS", "BTCUSDT").split(",") if s.strip()]
    intervals = [i.strip() for i in os.getenv("BINANCE_INTERVALS", "1h,4h").split(",") if i.strip()]
    limit = int(os.getenv("BINANCE_SYNC_LIMIT", "500"))
    refresh = int(os.getenv("BINANCE_SYNC_INTERVAL", "300"))

    if not symbols or not intervals:
        raise ValueError("BINANCE_SYMBOLS and BINANCE_INTERVALS must not be empty")

    logger.info(
        "Starting Binance fetcher with symbols=%s, intervals=%s, limit=%s, interval=%ss",
        symbols,
        intervals,
        limit,
        refresh,
    )
    asyncio.run(_run_loop(symbols, intervals, limit, refresh))


if __name__ == "__main__":
    main()
