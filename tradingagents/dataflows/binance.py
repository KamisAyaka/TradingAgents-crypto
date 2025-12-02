"""
Utility helpers for pulling market data directly from Binance public endpoints.
We keep the logic here so analysts/tools can fetch OHLCV snapshots and compute
basic technical indicators without relying on legacy equity vendors.
"""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

BINANCE_KLINES = os.getenv(
    "BINANCE_KLINES_URL", "https://api.binance.com/api/v3/klines"
)
BINANCE_KLINES_GLOBAL = os.getenv(
    "BINANCE_KLINES_GLOBAL_URL", "https://data.binance.com/api/v3/klines"
)
BINANCE_KLINES_MIRROR = os.getenv(
    "BINANCE_KLINES_MIRROR_URL", "https://data-api.binance.vision/api/v3/klines"
)

CACHE_DIR = Path(__file__).resolve().parent / "data_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
BINANCE_DB_PATH = CACHE_DIR / "binance_cache.db"


def _ensure_cache_db() -> None:
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
        conn.commit()


def _row_to_kline(row: sqlite3.Row) -> Dict[str, float]:
    return {
        "open_time": int(row[0]),
        "close_time": int(row[1]),
        "open": float(row[2]),
        "high": float(row[3]),
        "low": float(row[4]),
        "close": float(row[5]),
        "volume": float(row[6]),
        "quote_volume": float(row[7]) if row[7] is not None else 0.0,
        "trade_count": int(row[8]) if row[8] is not None else 0,
        "taker_buy_base": float(row[9]) if row[9] is not None else 0.0,
        "taker_buy_quote": float(row[10]) if row[10] is not None else 0.0,
    }


def _load_cached_klines(symbol: str, interval: str, limit: int) -> List[Dict[str, float]]:
    _ensure_cache_db()
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
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
                taker_buy_quote
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


def _store_klines(symbol: str, interval: str, klines: List[Dict[str, float]]) -> None:
    if not klines:
        return
    _ensure_cache_db()
    payloads = []
    updated_at = datetime.utcnow().isoformat()
    for item in klines:
        payloads.append(
            (
                symbol.upper(),
                interval,
                int(item["open_time"]),
                int(item["close_time"]),
                float(item["open"]),
                float(item["high"]),
                float(item["low"]),
                float(item["close"]),
                float(item["volume"]),
                float(item.get("quote_volume") or 0),
                int(item.get("trade_count") or 0),
                float(item.get("taker_buy_base") or 0),
                float(item.get("taker_buy_quote") or 0),
                updated_at,
            )
        )

    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO klines (
                symbol, interval, open_time, close_time, open, high,
                low, close, volume, quote_volume, trade_count,
                taker_buy_base, taker_buy_quote, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                close_time=excluded.close_time,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                quote_volume=excluded.quote_volume,
                trade_count=excluded.trade_count,
                taker_buy_base=excluded.taker_buy_base,
                taker_buy_quote=excluded.taker_buy_quote,
                updated_at=excluded.updated_at
            """,
            payloads,
        )
        conn.commit()


class BinanceAPIError(RuntimeError):
    """Raised when Binance responds with an error payload."""


def _ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()


def _request_klines_api(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
) -> List[Dict[str, float]]:
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    endpoints = [BINANCE_KLINES]
    for alt in (BINANCE_KLINES_GLOBAL, BINANCE_KLINES_MIRROR):
        if alt and alt not in endpoints:
            endpoints.append(alt)

    last_error = None
    payload = None
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, params=params, timeout=15)
        except requests.RequestException as exc:
            last_error = f"Failed to call Binance endpoint {endpoint}: {exc}"
            continue

        if resp.status_code == 200:
            payload = resp.json()
            break

        last_error = (
            f"Binance responded with {resp.status_code} from {endpoint}: {resp.text[:200]}"
        )
        if resp.status_code == 451:
            continue

    if payload is None:
        raise BinanceAPIError(last_error or "Unknown error calling Binance")

    if isinstance(payload, dict) and payload.get("code"):
        raise BinanceAPIError(f"Binance API error: {payload}")

    klines: List[Dict[str, float]] = []
    for item in payload:
        open_time = int(item[0])
        close_time = int(item[6])
        klines.append(
            {
                "open_time": open_time,
                "close_time": close_time,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "quote_volume": float(item[7]),
                "trade_count": int(item[8]),
                "taker_buy_base": float(item[9]),
                "taker_buy_quote": float(item[10]),
            }
        )
    return klines


def fetch_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
) -> List[Dict[str, float]]:
    """Return klines from cache when available, otherwise fetch from Binance."""
    cached = _load_cached_klines(symbol, interval, limit)
    if len(cached) >= limit:
        return cached[-limit:]

    klines = _request_klines_api(symbol, interval=interval, limit=limit)
    _store_klines(symbol, interval, klines)
    return klines


def klines_to_dataframe(klines: List[Dict[str, float]]) -> pd.DataFrame:
    df = pd.DataFrame(klines)
    if df.empty:
        return df
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df.set_index("close_time").sort_index()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _bollinger(df: pd.DataFrame, window: int = 20, num_std: int = 2):
    mid = df["close"].rolling(window).mean()
    std = df["close"].rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _kdj(df: pd.DataFrame, window: int = 9, smooth: int = 3):
    low_min = df["low"].rolling(window).min()
    high_max = df["high"].rolling(window).max()
    rsv = (df["close"] - low_min) / (high_max - low_min)
    rsv = (rsv.replace([np.inf, -np.inf], np.nan).fillna(0) * 100).clip(0, 100)
    k = rsv.ewm(alpha=1 / smooth, adjust=False).mean()
    d = k.ewm(alpha=1 / smooth, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append a curated indicator set to the dataframe."""
    if df.empty:
        return df

    df = df.copy()
    df["ema_5"] = _ema(df["close"], 5)
    df["ema_10"] = _ema(df["close"], 10)
    df["ema_20"] = _ema(df["close"], 20)
    macd_line, signal_line, hist = _macd(df["close"])
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = hist
    mid, upper, lower = _bollinger(df)
    df["boll_mid"] = mid
    df["boll_upper"] = upper
    df["boll_lower"] = lower
    k, d, j = _kdj(df)
    df["kdj_k"] = k
    df["kdj_d"] = d
    df["kdj_j"] = j
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
    klines = fetch_klines(symbol, interval=interval, limit=limit)
    df = compute_indicators(klines_to_dataframe(klines))
    return summarize_market(df, symbol=symbol, interval=interval)


def get_indicator_readout(
    symbol: str,
    interval: str = "1h",
    indicators: Optional[List[str]] = None,
    limit: int = 240,
) -> str:
    klines = fetch_klines(symbol, interval=interval, limit=limit)
    df = compute_indicators(klines_to_dataframe(klines))
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
    klines = fetch_klines(symbol, interval=interval, limit=limit)
    df = compute_indicators(klines_to_dataframe(klines))
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


def sync_binance_pairs(
    symbols: List[str],
    intervals: List[str],
    limit: int = 500,
) -> Dict[str, Any]:
    """Refresh cached klines for multiple symbol/interval combinations."""
    results: Dict[str, Any] = {}
    for symbol in symbols:
        sym_summary: Dict[str, Any] = {}
        for interval in intervals:
            try:
                klines = _request_klines_api(symbol, interval=interval, limit=limit)
                _store_klines(symbol, interval, klines)
                sym_summary[interval] = {
                    "count": len(klines),
                    "latest_close": klines[-1]["close_time"] if klines else None,
                }
            except Exception as exc:  # pylint: disable=broad-except
                sym_summary[interval] = {"error": str(exc)}
        results[symbol.upper()] = sym_summary
    return results
