from langchain_core.tools import tool
from typing import Annotated, List

from tradingagents.dataflows.binance import (
    get_market_snapshot,
    analyze_support_resistance,
)


def _parse_symbol_list(raw: str) -> List[str]:
    """Parse comma/newline separated symbols into a clean uppercase list."""
    if not raw:
        return []
    normalized = raw.replace("\n", ",")
    return [
        token.strip().upper()
        for token in normalized.split(",")
        if token.strip()
    ]


@tool
def get_crypto_market_batch(
    symbols: Annotated[str, "Comma-separated Binance symbols, e.g. BTCUSDT,ETHUSDT"],
    interval: Annotated[str, "Binance interval such as 15m/1h/4h/1d"] = "1h",
    limit: Annotated[int, "Number of klines to fetch (max 1000)"] = 240,
) -> str:
    """
    Retrieve OHLCV snapshots for multiple symbols in a single call to reduce tool churn.
    """
    symbol_list = _parse_symbol_list(symbols)
    if not symbol_list:
        return "No valid Binance symbols were provided."

    chunks: List[str] = []
    for symbol in symbol_list:
        snapshot = get_market_snapshot(symbol, interval=interval, limit=limit)
        chunks.append(f"=== {symbol} ===\n{snapshot}")
    return "\n\n".join(chunks)


@tool
def get_support_resistance_batch(
    symbols: Annotated[str, "Comma-separated Binance symbols, e.g. BTCUSDT,ETHUSDT"],
    interval: Annotated[str, "Binance interval such as 15m/1h/4h/1d"] = "1h",
    limit: Annotated[int, "Number of klines to analyze"] = 240,
) -> str:
    """Retrieve support/resistance analysis for multiple symbols in one response."""
    symbol_list = _parse_symbol_list(symbols)
    if not symbol_list:
        return "No valid Binance symbols were provided for support/resistance."

    chunks: List[str] = []
    for symbol in symbol_list:
        sr = analyze_support_resistance(symbol, interval=interval, limit=limit)
        chunks.append(f"=== {symbol} ===\n{sr}")
    return "\n\n".join(chunks)
