from langchain_core.tools import tool
from typing import Annotated, List

from tradingagents.dataflows.binance import (
    get_market_snapshot,
    analyze_support_resistance,
)

@tool
def get_crypto_market_data(
    symbol: Annotated[str, "Binance symbol, e.g. BTCUSDT"],
    interval: Annotated[str, "Binance interval such as 15m/1h/4h/1d"] = "1h",
    limit: Annotated[int, "Number of klines to fetch (max 1000)"] = 240,
) -> str:
    """
    Retrieve OHLCV snapshot plus key stats for a crypto pair from Binance.
    """
    return get_market_snapshot(symbol, interval=interval, limit=limit)

@tool
def get_support_resistance_levels(
    symbol: Annotated[str, "Binance symbol, e.g. BTCUSDT"],
    interval: Annotated[str, "Binance interval such as 15m/1h/4h/1d"] = "1h",
    limit: Annotated[int, "Number of klines to analyze"] = 240,
) -> str:
    """Retrieve blended支撑/压力分析结果，含 swing/成交密集区与指标确认。"""
    return analyze_support_resistance(symbol, interval=interval, limit=limit)
