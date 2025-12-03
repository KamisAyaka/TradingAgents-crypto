"""
Utility helpers for pulling market data directly from Binance public endpoints.
We keep the logic here so analysts/tools can fetch OHLCV snapshots and compute
basic technical indicators without relying on legacy equity vendors.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

INDICATOR_COLUMN_SPECS = {
    "ema_5": "REAL",
    "ema_10": "REAL",
    "ema_20": "REAL",
    "macd": "REAL",
    "macd_signal": "REAL",
    "macd_hist": "REAL",
    "boll_mid": "REAL",
    "boll_upper": "REAL",
    "boll_lower": "REAL",
    "kdj_k": "REAL",
    "kdj_d": "REAL",
    "kdj_j": "REAL",
}
INDICATOR_COLUMNS = list(INDICATOR_COLUMN_SPECS.keys())

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BINANCE_DB_PATH = DATA_DIR / "binance_cache.db"


def _ensure_indicator_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(klines)")
    existing = {row[1] for row in cursor.fetchall()}
    for name, col_type in INDICATOR_COLUMN_SPECS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE klines ADD COLUMN {name} {col_type}")


def ensure_cache_db() -> None:
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS klines (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                quote_volume REAL,
                trade_count INTEGER,
                taker_buy_base REAL,
                taker_buy_quote REAL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(symbol, interval, open_time)
            )
            """
        )
        _ensure_indicator_columns(conn)
        conn.commit()


def _row_to_kline(row: sqlite3.Row) -> Dict[str, float]:
    row_dict = dict(row)
    record: Dict[str, Any] = {
        "open_time": int(row_dict["open_time"]),
        "close_time": int(row_dict["close_time"]),
        "open": float(row_dict["open"]),
        "high": float(row_dict["high"]),
        "low": float(row_dict["low"]),
        "close": float(row_dict["close"]),
        "volume": float(row_dict["volume"]),
        "quote_volume": float(row_dict["quote_volume"]) if row_dict["quote_volume"] is not None else 0.0,
        "trade_count": int(row_dict["trade_count"]) if row_dict["trade_count"] is not None else 0,
        "taker_buy_base": float(row_dict["taker_buy_base"]) if row_dict["taker_buy_base"] is not None else 0.0,
        "taker_buy_quote": float(row_dict["taker_buy_quote"]) if row_dict["taker_buy_quote"] is not None else 0.0,
    }
    for column in INDICATOR_COLUMNS:
        value = row_dict.get(column)
        record[column] = float(value) if value is not None else None
    return record


def load_cached_klines(symbol: str, interval: str, limit: int) -> List[Dict[str, float]]:
    ensure_cache_db()
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        indicator_select = ", ".join(INDICATOR_COLUMNS)
        cursor = conn.execute(
            f"""
            SELECT
                open_time,
                close_time,
                open,
                high,
                low,
                close,
                volume,
                quote_volume,
                trade_count,
                taker_buy_base,
                taker_buy_quote,
                {indicator_select}
            FROM klines
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time DESC
            LIMIT ?
            """,
            (symbol.upper(), interval, limit),
        )
        rows = cursor.fetchall()

    klines = [_row_to_kline(row) for row in rows]
    return list(reversed(klines))


def get_cached_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
) -> List[Dict[str, float]]:
    """Public helper for retrieving klines directly from the SQLite cache."""
    return load_cached_klines(symbol, interval, limit)


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()


def klines_to_dataframe(klines: List[Dict[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(klines)
    if df.empty:
        return df
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df.set_index("close_time").sort_index()


def ensure_indicator_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure indicator columns exist on the dataframe.
    The actual indicator calculation happens in the fetcher when data is ingested.
    """
    if df.empty:
        return df
    df = df.copy()
    for col in INDICATOR_COLUMNS:
        if col not in df.columns:
            df[col] = math.nan
    return df


def _indicator_alignment(price: float, latest_row: pd.Series) -> Optional[str]:
    """Describe whether a price aligns with key moving averages or Bollinger bands."""
    hints = []
    for label in ("ema_5", "ema_10", "ema_20", "boll_upper", "boll_lower"):
        ref = latest_row.get(label)
        if pd.isna(ref) or not ref:
            continue
        diff_pct = abs(price - ref) / price
        if diff_pct <= 0.005:  # within 0.5%
            hints.append(f"接近 {label} ({ref:.2f})")
    if not hints:
        return None
    return "，并且" + "、".join(hints)


def _find_swing_levels(
    df: pd.DataFrame,
    column: str,
    window: int = 3,
    kind: str = "high",
) -> List[Dict[str, Any]]:
    """
    Identify local highs or lows as potential swing points.
    """
    prices = df[column]
    volumes = df["volume"]
    timestamps = df.index
    levels: List[Dict[str, object]] = []
    for i in range(window, len(prices) - window):
        slice_ = prices.iloc[i - window : i + window + 1]
        current = prices.iloc[i]
        if kind == "high" and current >= slice_.max():
            levels.append(
                {
                    "price": current,
                    "timestamp": timestamps[i],
                    "volume": volumes.iloc[i],
                    "source": "swing_high",
                }
            )
        elif kind == "low" and current <= slice_.min():
            levels.append(
                {
                    "price": current,
                    "timestamp": timestamps[i],
                    "volume": volumes.iloc[i],
                    "source": "swing_low",
                }
            )
    return levels


def _volume_congestion_zones(df: pd.DataFrame, bins: int = 18) -> List[Dict[str, Any]]:
    """
    Approximate volume profile by binning closes and aggregating volumes.
    """
    if df.empty:
        return []
    prices = df["close"].to_numpy()
    vols = df["volume"].to_numpy()
    hist, edges = np.histogram(prices, bins=bins, weights=vols)
    zones: List[Dict[str, float]] = []
    for idx, vol in enumerate(hist):
        if vol <= 0:
            continue
        mid_price = (edges[idx] + edges[idx + 1]) / 2
        zones.append({"price": mid_price, "volume": vol, "source": "volume_cluster"}) # type: ignore
    zones.sort(key=lambda x: x["volume"], reverse=True)
    return zones


def summarize_market(
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    window: int = 30,
) -> str:
    if df.empty:
        return f"No Binance market data returned for {symbol} ({interval})."

    recent = df.tail(window)
    start_close = recent["close"].iloc[0]
    end_close = recent["close"].iloc[-1]
    pct = ((end_close - start_close) / start_close) * 100 if start_close else 0
    high = recent["high"].max()
    low = recent["low"].min()
    avg_vol = recent["volume"].mean()

    latest = recent.iloc[-1]
    trend = "up" if pct > 0.5 else "down" if pct < -0.5 else "sideways"
    return (
        f"Binance {symbol} ({interval}) snapshot over last {window} bars:\n"
        f"- Close moved from {start_close:.4f} to {end_close:.4f} ({pct:.2f}% {trend}).\n"
        f"- Range high/low: {high:.4f} / {low:.4f}.\n"
        f"- Avg volume: {avg_vol:.2f} {symbol.split('USDT')[-1]}.\n"
        f"- KDJ K {latest.get('kdj_k', math.nan):.2f} / D {latest.get('kdj_d', math.nan):.2f} / J {latest.get('kdj_j', math.nan):.2f}.\n"
        f"- MACD {latest.get('macd', math.nan):.4f} vs signal {latest.get('macd_signal', math.nan):.4f} "
        f"(hist {latest.get('macd_hist', math.nan):.4f})."
    )


def get_market_snapshot(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> str:
    klines = get_cached_klines(symbol, interval=interval, limit=limit)
    df = ensure_indicator_data(klines_to_dataframe(klines))
    return summarize_market(df, symbol=symbol, interval=interval)


def get_indicator_readout(
    symbol: str,
    interval: str = "1h",
    indicators: Optional[List[str]] = None,
    limit: int = 240,
) -> str:
    klines = get_cached_klines(symbol, interval=interval, limit=limit)
    df = ensure_indicator_data(klines_to_dataframe(klines))
    if df.empty:
        return f"No indicator data for {symbol}."

    latest = df.iloc[-1]
    indicators = indicators or [
        "ema_5",
        "ema_10",
        "ema_20",
        "macd",
        "macd_signal",
        "macd_hist",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "boll_upper",
        "boll_lower",
    ]
    lines = [
        f"Latest indicator readout for {symbol} ({interval}, close {_ts_to_iso(int(df.index[-1].timestamp() * 1000))}):"
    ]
    for name in indicators:
        value = latest.get(name)
        if pd.isna(value):
            continue
        lines.append(f"- {name}: {float(value):.4f}")
    return "\n".join(lines)


def analyze_support_resistance(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> str:
    """
    Produce a blended support/resistance view by combining:
    1) price action swing levels & congestion zones,
    2) indicator confirmation (EMA / Bollinger / KDJ / MACD).
    """
    levels = get_support_resistance_levels(symbol, interval=interval, limit=limit)
    if levels.get("message") and not levels.get("supports") and not levels.get("resistances"):
        return levels["message"]

    def _format_level(level) -> str:
        ts_str = level.get("timestamp")
        base = f"{level['price']:.4f}"
        if ts_str:
            base += f"（{ts_str}）"
        if level.get("volume"):
            base += f"，伴随成交量 {level['volume']:.2f}"
        if level.get("indicator_alignment"):
            base += f"，{level['indicator_alignment']}"
        if level.get("source"):
            base += f"，来源：{level['source']}"
        return base

    lines = [
        f"{symbol} ({interval}) 支撑/压力位分析：",
        "1. 价格行为（前高/前低与成交密集区）",
    ]
    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])
    if supports:
        lines.append("   支撑位：")
        for lvl in supports:
            lines.append("   - " + _format_level(lvl))
    else:
        lines.append("   支撑位：暂无显著 swing 低点。")

    if resistances:
        lines.append("   压力位：")
        for lvl in resistances:
            lines.append("   - " + _format_level(lvl))
    else:
        lines.append("   压力位：暂无显著 swing 高点。")

    lines.append("2. 技术指标确认")
    indicators = levels.get("indicators", {})
    ema = indicators.get("ema", {})
    boll = indicators.get("bollinger", {})
    kdj = indicators.get("kdj", {})
    macd = indicators.get("macd", {})
    current_close = levels.get("current_close", math.nan)
    lines.append(
        f"   - 最新收盘价 {current_close:.4f}，EMA5/10/20 分别为 "
        f"{ema.get('ema_5', math.nan):.2f} / "
        f"{ema.get('ema_10', math.nan):.2f} / "
        f"{ema.get('ema_20', math.nan):.2f}；"
        f"布林带上/下轨 {boll.get('upper', math.nan):.2f} / "
        f"{boll.get('lower', math.nan):.2f}。"
    )
    lines.append(
        f"   - KDJ：K {kdj.get('k', math.nan):.2f} / D {kdj.get('d', math.nan):.2f} / "
        f"J {kdj.get('j', math.nan):.2f}；MACD：{macd.get('macd', math.nan):.4f} "
        f"vs Signal {macd.get('signal', math.nan):.4f}。"
    )

    return "\n".join(lines)


def get_support_resistance_levels(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> Dict[str, Any]:
    """
    Return structured support/resistance information for downstream agents.
    """
    klines = get_cached_klines(symbol, interval=interval, limit=limit)
    df = ensure_indicator_data(klines_to_dataframe(klines))
    base: Dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "supports": [],
        "resistances": [],
    }
    if df.empty:
        base["message"] = f"No Binance market data returned for {symbol} ({interval})."
        return base

    current_close = df["close"].iloc[-1]
    latest = df.iloc[-1]
    swing_highs = _find_swing_levels(df, "high", window=4, kind="high")
    swing_lows = _find_swing_levels(df, "low", window=4, kind="low")
    volume_zones = _volume_congestion_zones(df, bins=18)[:6]

    supports_raw = [
        lvl for lvl in swing_lows + volume_zones if lvl["price"] <= current_close
    ][:5]
    resistances_raw = [
        lvl for lvl in swing_highs + volume_zones if lvl["price"] >= current_close
    ][:5]

    def _structure_level(level: Dict[str, Any]) -> Dict[str, Any]:
        ts = level.get("timestamp")
        timestamp_str = (
            ts.strftime("%Y-%m-%d %H:%M")
            if isinstance(ts, pd.Timestamp)
            else None
        )
        volume = (
            float(level.get("volume") or 0)
            if level.get("volume") is not None
            else None
        )
        return {
            "price": float(level["price"]),
            "timestamp": timestamp_str,
            "volume": volume,
            "source": level.get("source"),
            "indicator_alignment": _indicator_alignment(level["price"], latest),
        }

    base["supports"] = [_structure_level(lvl) for lvl in supports_raw]
    base["resistances"] = [_structure_level(lvl) for lvl in resistances_raw]
    base["current_close"] = current_close
    base["latest_close_time"] = df.index[-1].isoformat()
    base["indicators"] = {
        "ema": {
            "ema_5": latest.get("ema_5", math.nan),
            "ema_10": latest.get("ema_10", math.nan),
            "ema_20": latest.get("ema_20", math.nan),
        },
        "bollinger": {
            "mid": latest.get("boll_mid", math.nan),
            "upper": latest.get("boll_upper", math.nan),
            "lower": latest.get("boll_lower", math.nan),
        },
        "kdj": {
            "k": latest.get("kdj_k", math.nan),
            "d": latest.get("kdj_d", math.nan),
            "j": latest.get("kdj_j", math.nan),
        },
        "macd": {
            "macd": latest.get("macd", math.nan),
            "signal": latest.get("macd_signal", math.nan),
            "hist": latest.get("macd_hist", math.nan),
        },
    }
    return base
