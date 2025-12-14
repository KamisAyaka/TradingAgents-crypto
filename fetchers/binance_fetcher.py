"""
Binance 行情抓取工具。

主要职责：
1. 通过公网 REST 接口抓取指定交易对/周期的 K 线。
2. 将最新行情与计算好的技术指标写入本地 SQLite 缓存，供 dataflow 读取。
这样 agent 分析阶段无需再调用外部接口或现算指标即可直接使用结果。
"""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import talib

from tradingagents.dataflows.binance import (
    BINANCE_DB_PATH,
    INDICATOR_COLUMNS,
    ensure_cache_db,
)

# 每次回填指标时最多只回溯最近 N 根，避免整库重算。
INDICATOR_RECALC_MIN_ROWS = 400
INDICATOR_RECALC_BUFFER = 50

BINANCE_KLINES = os.getenv(
    "BINANCE_KLINES_URL", "https://api.binance.com/api/v3/klines"
)
BINANCE_KLINES_GLOBAL = os.getenv(
    "BINANCE_KLINES_GLOBAL_URL", "https://data.binance.com/api/v3/klines"
)
BINANCE_KLINES_MIRROR = os.getenv(
    "BINANCE_KLINES_MIRROR_URL", "https://data-api.binance.vision/api/v3/klines"
)

_MA_TYPE = getattr(talib, "MA_Type", None)
MA_TYPE_SMA: Any
MA_TYPE_EMA: Any
if _MA_TYPE is not None:
    MA_TYPE_SMA = getattr(_MA_TYPE, "SMA", 0)
    MA_TYPE_EMA = getattr(_MA_TYPE, "EMA", 1)
else:
    MA_TYPE_SMA = 0
    MA_TYPE_EMA = 1


class BinanceAPIError(RuntimeError):
    """当 Binance 接口返回错误时抛出，方便上层统一处理。"""


def _store_klines(symbol: str, interval: str, klines: List[Dict[str, Any]]) -> None:
    """把 K 线写入 SQLite，若主键冲突则更新最新行情。"""
    if not klines:
        return
    ensure_cache_db()
    updated_at = datetime.utcnow().isoformat()
    payloads = []
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


def _klines_to_dataframe(klines: List[Dict[str, Any]]) -> pd.DataFrame:
    """把 Python 字典列表转换成按 close_time 排序的 DataFrame，方便指标计算。"""
    df = pd.DataFrame(klines)
    if df.empty:
        return df
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df.set_index("close_time").sort_index()


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """根据 DataFrame 计算 EMA/MACD/布林/KDJ 等指标，并返回带新列的数据。"""
    if df.empty:
        return df
    df = df.copy()
    close = df["close"].astype(float).to_numpy(copy=False)
    high = df["high"].astype(float).to_numpy(copy=False)
    low = df["low"].astype(float).to_numpy(copy=False)

    df["ema_5"] = talib.EMA(close, timeperiod=5)
    df["ema_10"] = talib.EMA(close, timeperiod=10)
    df["ema_20"] = talib.EMA(close, timeperiod=20)

    macd_line, signal_line, hist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = hist

    upper, mid, lower = talib.BBANDS(
        close,
        timeperiod=20,
        nbdevup=2,
        nbdevdn=2,
        matype=MA_TYPE_SMA,
    )
    df["boll_mid"] = mid
    df["boll_upper"] = upper
    df["boll_lower"] = lower

    k, d = talib.STOCH(
        high,
        low,
        close,
        fastk_period=9,
        slowk_period=3,
        slowk_matype=MA_TYPE_EMA,
        slowd_period=3,
        slowd_matype=MA_TYPE_EMA,
    )
    df["kdj_k"] = k
    df["kdj_d"] = d
    df["kdj_j"] = 3 * k - 2 * d
    return df


def _nan_to_none(value: Optional[float]) -> Optional[float]:
    """将 numpy 产生的 NaN 统一转为 None，避免写入数据库时报错。"""
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except TypeError:
        return float(value)
    return float(value)


def _recompute_and_store_indicators(
    symbol: str,
    interval: str,
    recent_count: Optional[int] = None,
) -> None:
    """
    仅读取最近若干根 K 线重新计算指标并批量更新。
    recent_count 会根据本次抓取数量动态扩大窗口，避免全量重算。
    """
    ensure_cache_db()
    limit = max(INDICATOR_RECALC_MIN_ROWS, (recent_count or 0) + INDICATOR_RECALC_BUFFER)
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
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
            FROM (
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
            )
            ORDER BY open_time ASC
            """,
            (symbol.upper(), interval, limit),
        ).fetchall()

    klines = [
        {
            "open_time": row["open_time"],
            "close_time": row["close_time"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "quote_volume": row["quote_volume"],
            "trade_count": row["trade_count"],
            "taker_buy_base": row["taker_buy_base"],
            "taker_buy_quote": row["taker_buy_quote"],
        }
        for row in rows
    ]
    if not klines:
        return

    # 使用最新的整段数据重新计算指标（含历史），确保所有记录都同步到一致的指标版本。
    df = _compute_indicators(_klines_to_dataframe(klines))
    if df.empty:
        return
    df_reset = df.reset_index()
    payloads: List[List[Any]] = []
    for row in df_reset.itertuples(index=False):
        open_time_ts = getattr(row, "open_time", None)
        if open_time_ts is None:
            continue
        open_time_ms = int(open_time_ts.value // 1_000_000)
        entry: List[Any] = []
        for column in INDICATOR_COLUMNS:
            entry.append(_nan_to_none(getattr(row, column, None)))
        entry.extend([symbol.upper(), interval, open_time_ms])
        payloads.append(entry)

    if not payloads:
        return

    set_clause = ", ".join(f"{col}=?" for col in INDICATOR_COLUMNS)
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        conn.executemany(
            f"""
            UPDATE klines
            SET {set_clause}
            WHERE symbol = ? AND interval = ? AND open_time = ?
            """,
            payloads,
        )
        conn.commit()


def _request_klines_api(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """调用 Binance REST 接口获取原始 K 线列表，带有主备域名轮询和错误容忍。"""
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

    klines: List[Dict[str, Any]] = []
    for item in payload:
        klines.append(
            {
                "open_time": int(item[0]),
                "close_time": int(item[6]),
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


def fetch_and_store_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    针对单个交易对执行一次“抓取 -> 写库 -> 计算指标”的完整流程。
    返回最新抓取的 K 线，方便上层 runner 输出日志或调试。
    """
    klines = _request_klines_api(symbol, interval=interval, limit=limit)
    _store_klines(symbol, interval, klines)
    # 指标需要依赖完整历史，因此写完 K 线后再统一回填指标列。
    _recompute_and_store_indicators(symbol, interval, recent_count=len(klines))
    return klines


def _sync_single(symbol: str, interval: str, limit: int) -> Dict[str, Any]:
    """内部辅助：抓取并返回单个 symbol/interval 的结果摘要。"""
    klines = fetch_and_store_klines(symbol, interval=interval, limit=limit)
    return {
        "count": len(klines),
        "latest_close_time": klines[-1]["close_time"] if klines else None,
    }


def sync_binance_pairs(
    symbols: List[str],
    intervals: List[str],
    limit: int = 500,
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    """
    批量刷新多个交易对/周期的行情（并发抓取）。
    返回 {symbol: {interval: {count/latest_close_time}}} 结构，便于 runner 记录结果。
    """
    if not symbols or not intervals:
        return {}

    total_tasks = len(symbols) * len(intervals)
    worker_count = max_workers or min(8, total_tasks)
    worker_count = max(worker_count, 1)

    results: Dict[str, Any] = {symbol.upper(): {} for symbol in symbols}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {}
        for symbol in symbols:
            for interval in intervals:
                future = executor.submit(_sync_single, symbol, interval, limit)
                future_map[future] = (symbol.upper(), interval)

        for future in as_completed(future_map):
            symbol, interval = future_map[future]
            try:
                summary = future.result()
            except Exception as exc:  # pylint: disable=broad-except
                summary = {"error": str(exc)}
            results[symbol][interval] = summary

    return results
