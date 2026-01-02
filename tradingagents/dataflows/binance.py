"""
币安市场数据工具助手
Utility helpers for pulling market data directly from Binance public endpoints.
We keep the logic here so analysts/tools can fetch OHLCV snapshots and compute
basic technical indicators without relying on legacy equity vendors.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from scipy.signal import find_peaks

# 定义技术指标列规格字典
INDICATOR_COLUMN_SPECS = {
    "ema_5": "REAL",      # 5周期指数移动平均线
    "ema_10": "REAL",     # 10周期指数移动平均线
    "ema_20": "REAL",     # 20周期指数移动平均线
    "macd": "REAL",       # MACD指标值
    "macd_signal": "REAL",# MACD信号线
    "macd_hist": "REAL",  # MACD柱状图
    "boll_mid": "REAL",   # 布林带中轨
    "boll_upper": "REAL", # 布林带上轨
    "boll_lower": "REAL", # 布林带下轨
    "kdj_k": "REAL",      # KDJ指标K值
    "kdj_d": "REAL",      # KDJ指标D值
    "kdj_j": "REAL",      # KDJ指标J值
}
# 将技术指标列名提取为列表
INDICATOR_COLUMNS = list(INDICATOR_COLUMN_SPECS.keys())

# 定义数据存储目录路径
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# 创建数据目录（如果不存在）
DATA_DIR.mkdir(parents=True, exist_ok=True)
# 定义币安数据库文件路径
BINANCE_DB_PATH = DATA_DIR / "binance_cache.db"

DEFAULT_KLINES_TABLE = "klines"
FIFTEEN_MIN_TABLE = "klines_15m"
FOUR_HOUR_TABLE = "klines_4h"
INTERVAL_TABLE_MAP = {
    "15m": FIFTEEN_MIN_TABLE,
    "4h": FOUR_HOUR_TABLE,
}
ALL_KLINE_TABLES = {DEFAULT_KLINES_TABLE}
ALL_KLINE_TABLES.update(INTERVAL_TABLE_MAP.values())


def get_table_for_interval(interval: str) -> str:
    """
    根据周期选择对应的 SQLite 表。
    默认使用 klines，仅 15m 使用独立表，便于与 1h 等数据隔离。
    """
    key = (interval or "").strip().lower()
    return INTERVAL_TABLE_MAP.get(key, DEFAULT_KLINES_TABLE)


def _ensure_indicator_columns(conn: sqlite3.Connection, table: str) -> None:
    """
    确保数据库表中包含所有技术指标列
    """
    if table not in ALL_KLINE_TABLES:
        raise ValueError(f"Unsupported klines table: {table}")
    # 获取表结构信息
    cursor = conn.execute(f"PRAGMA table_info({table})")
    # 提取现有的列名
    existing = {row[1] for row in cursor.fetchall()}
    # 遍历技术指标列规格，为缺失的列添加到表中
    for name, col_type in INDICATOR_COLUMN_SPECS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def _create_klines_table(conn: sqlite3.Connection, table: str) -> None:
    """创建指定的 K 线表，并补充指标列。"""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
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
    _ensure_indicator_columns(conn, table)


def ensure_cache_db() -> None:
    """
    确保币安缓存数据库存在，如果不存在则创建
    """
    # 连接SQLite数据库
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        for table in ALL_KLINE_TABLES:
            _create_klines_table(conn, table)
        # 提交事务
        conn.commit()


def _row_to_kline(row: sqlite3.Row) -> Dict[str, float]:
    """
    将数据库行转换为K线数据字典
    """
    # 将行数据转换为字典
    row_dict = dict(row)
    # 构造K线记录
    record: Dict[str, Any] = {
        "open_time": int(row_dict["open_time"]),      # 开盘时间
        "close_time": int(row_dict["close_time"]),    # 收盘时间
        "open": float(row_dict["open"]),              # 开盘价
        "high": float(row_dict["high"]),              # 最高价
        "low": float(row_dict["low"]),                # 最低价
        "close": float(row_dict["close"]),            # 收盘价
        "volume": float(row_dict["volume"]),          # 成交量
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
    """
    从缓存数据库加载K线数据
    
    Args:
        symbol: 交易对符号，如BTCUSDT
        interval: 时间间隔，如1h, 4h, 1d等
        limit: 返回数据条数限制
    
    Returns:
        K线数据列表，每条数据包含开盘价、收盘价等信息
    """
    # 确保数据库存在
    ensure_cache_db()
    # 选择对应 interval 的表
    table = get_table_for_interval(interval)
    # 连接数据库
    with sqlite3.connect(BINANCE_DB_PATH) as conn:
        # 设置行工厂，使查询结果可以通过列名访问
        conn.row_factory = sqlite3.Row
        # 构造技术指标列选择字符串
        indicator_select = ", ".join(INDICATOR_COLUMNS)
        # 执行查询
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
            FROM {table}
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time DESC
            LIMIT ?
            """,
            (symbol.upper(), interval, limit),
        )
        # 获取所有查询结果
        rows = cursor.fetchall()

    # 将每一行转换为K线数据字典
    klines = [_row_to_kline(row) for row in rows]
    # 反转列表，使时间顺序从早到晚
    return list(reversed(klines))


def klines_to_dataframe(klines: List[Dict[str, float]]) -> pd.DataFrame:
    """
    将K线数据列表转换为Pandas DataFrame
    
    Args:
        klines: K线数据列表
    
    Returns:
        包含K线数据的DataFrame
    """
    # 创建DataFrame
    df = pd.DataFrame(klines)
    # 如果DataFrame为空，直接返回
    if df.empty:
        return df
    # 将时间戳转换为日期时间格式
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    # 设置索引并按时间排序
    return df.set_index("close_time").sort_index()


def ensure_indicator_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保DataFrame中包含所有技术指标列
    
    Args:
        df: 输入的DataFrame
    
    Returns:
        确保包含所有技术指标列的DataFrame
    """
    # 如果DataFrame为空，直接返回
    if df.empty:
        return df
    # 复制DataFrame
    df = df.copy()
    # 为缺失的技术指标列添加NaN值
    for col in INDICATOR_COLUMNS:
        if col not in df.columns:
            df[col] = math.nan
    return df


def summarize_market(
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    window: int = 30,
) -> str:
    """
    生成市场摘要信息
    
    Args:
        df: 包含市场数据的DataFrame
        symbol: 交易对符号
        interval: 时间间隔
        window: 窗口大小，默认为30
    
    Returns:
        市场摘要字符串
    """
    # 如果DataFrame为空，返回提示信息
    if df.empty:
        return f"No Binance market data returned for {symbol} ({interval})."

    # 获取最近的数据
    recent = df.tail(window)
    # 获取起始和结束收盘价
    start_close = recent["close"].iloc[0]
    end_close = recent["close"].iloc[-1]
    # 计算百分比变化
    pct = ((end_close - start_close) / start_close) * 100 if start_close else 0
    # 获取最高价和最低价
    high = recent["high"].max()
    low = recent["low"].min()
    # 计算平均成交量
    avg_vol = recent["volume"].mean()

    # 获取最新数据行
    latest = recent.iloc[-1]
    # 判断趋势
    trend = "up" if pct > 0.5 else "down" if pct < -0.5 else "sideways"
    # 返回市场摘要
    return (
        f"Binance {symbol} ({interval}) snapshot over last {window} bars:\n"
        f"- Close moved from {start_close:.4f} to {end_close:.4f} ({pct:.2f}% {trend}).\n"
        f"- Range high/low: {high:.4f} / {low:.4f}.\n"
        f"- Avg volume: {avg_vol:.2f} {symbol.split('USDT')[-1]}.\n"
        f"- EMA(5/10/20): {latest.get('ema_5', math.nan):.4f} / {latest.get('ema_10', math.nan):.4f} / {latest.get('ema_20', math.nan):.4f}\n"
        f"- BOLL(mid/upper/lower): {latest.get('boll_mid', math.nan):.4f} / {latest.get('boll_upper', math.nan):.4f} / {latest.get('boll_lower', math.nan):.4f}\n"
        f"- KDJ K {latest.get('kdj_k', math.nan):.2f} / D {latest.get('kdj_d', math.nan):.2f} / J {latest.get('kdj_j', math.nan):.2f}.\n"
        f"- MACD {latest.get('macd', math.nan):.4f} vs signal {latest.get('macd_signal', math.nan):.4f} "
        f"(hist {latest.get('macd_hist', math.nan):.4f})."
    )


def get_market_snapshot(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> str:
    """
    获取市场快照
    
    Args:
        symbol: 交易对符号
        interval: 时间间隔，默认为1小时
        limit: 数据条数限制，默认为240条
    
    Returns:
        市场快照字符串
    """
    # 获取缓存的K线数据
    klines = load_cached_klines(symbol, interval=interval, limit=limit)
    # 将K线数据转换为DataFrame并确保包含技术指标列
    df = ensure_indicator_data(klines_to_dataframe(klines))
    # 生成市场摘要
    return summarize_market(df, symbol=symbol, interval=interval, window=limit)


def get_support_resistance_levels(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> Dict[str, Any]:
    """
    返回下游代理的结构化支撑/阻力信息（使用简化算法）。
    
    Args:
        symbol: 交易对符号
        interval: 时间间隔，默认为1小时
        limit: 数据条数限制，默认为240条
    
    Returns:
        包含支撑位、阻力位信息的字典
    """
    # 获取缓存的K线数据
    klines = load_cached_klines(symbol, interval=interval, limit=limit)
    # 将K线数据转换为DataFrame并确保包含技术指标列
    df = ensure_indicator_data(klines_to_dataframe(klines))
    # 初始化基础字典
    base: Dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "supports": [],      # 支撑位列表
        "resistances": [],   # 阻力位列表
    }
    # 如果DataFrame为空，添加消息并返回
    if df.empty:
        base["message"] = f"No Binance market data returned for {symbol} ({interval})."
        return base

    # 获取当前收盘价
    current_close = df["close"].iloc[-1]
    
    # 1. 识别强峰值（阻力位）
    strong_resistance_peaks, _ = find_peaks(
        df['high'], 
        distance=60, 
        prominence=200
    )
    
    # 提取强峰值的对应高值
    strong_resistances = df.iloc[strong_resistance_peaks]['high'].tolist()
    
    # 包括近期最高价作为额外的强峰值
    recent_high = df['high'].iloc[-min(252, len(df)):].max()
    strong_resistances.append(recent_high)
    
    # 去重
    strong_resistances = list(set(strong_resistances))
    
    # 2. 识别强谷值（支撑位）
    strong_support_troughs, _ = find_peaks(
        -df['low'], 
        distance=60, 
        prominence=200
    )
    
    # 提取强谷值的对应低值
    strong_supports = df.iloc[strong_support_troughs]['low'].tolist()
    
    # 包括近期最低价作为额外的强谷值
    recent_low = df['low'].iloc[-min(252, len(df)):].min()
    strong_supports.append(recent_low)
    
    # 去重
    strong_supports = list(set(strong_supports))
    
    # 根据当前价格过滤支撑位和阻力位
    # 支撑位应该是当前价格下方的价格水平
    filtered_supports = [s for s in strong_supports if s <= current_close]
    # 阻力位应该是当前价格上方的价格水平
    filtered_resistances = [r for r in strong_resistances if r >= current_close]
    
    # 直接使用价格列表
    base["supports"] = [float(s) for s in filtered_supports]
    base["resistances"] = [float(r) for r in filtered_resistances]
    # 添加当前收盘价
    base["current_close"] = current_close
    # 添加最新收盘时间
    base["latest_close_time"] = df.index[-1].isoformat()
    
    # 返回基础字典
    return base


def analyze_support_resistance(
    symbol: str,
    interval: str = "1h",
    limit: int = 240,
) -> str:
    """
    通过简化算法生成支撑/阻力位视图
    
    Args:
        symbol: 交易对符号
        interval: 时间间隔，默认为1小时
        limit: 数据条数限制，默认为240条
    
    Returns:
        支撑/阻力位分析字符串
    """
    # 获取支撑/阻力位级别
    levels = get_support_resistance_levels(symbol, interval=interval, limit=limit)
    # 如果只有消息而没有支撑位和阻力位，返回消息
    if levels.get("message") and not levels.get("supports") and not levels.get("resistances"):
        return levels["message"]

    # 构造输出行
    lines = [
        f"{symbol} ({interval}) 支撑/压力位分析：",
    ]
    
    # 获取支撑位和阻力位
    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])
    current_close = levels.get("current_close", math.nan)
    
    # 添加最新的OHLCV数据
    # 获取最新的K线数据用于展示完整OHLCV信息
    klines = load_cached_klines(symbol, interval=interval, limit=1)
    if klines:
        latest_kline = klines[-1]
        lines.append(f"最新价格数据:")
        lines.append(f"  开盘价: {latest_kline.get('open', math.nan):.4f}")
        lines.append(f"  最高价: {latest_kline.get('high', math.nan):.4f}")
        lines.append(f"  最低价: {latest_kline.get('low', math.nan):.4f}")
        lines.append(f"  收盘价: {latest_kline.get('close', math.nan):.4f}")
        lines.append(f"  成交量: {latest_kline.get('volume', math.nan):.2f}")
    else:
        lines.append(f"当前价格: {current_close:.4f}")
    
    # 添加支撑位信息
    if supports:
        lines.append("支撑位：")
        for price in sorted(supports, reverse=True):  # 从高到低排序
            lines.append(f"  - {price:.4f}")
    else:
        lines.append("支撑位：暂无强支撑位")

    # 添加阻力位信息
    if resistances:
        lines.append("压力位：")
        for price in sorted(resistances):  # 从低到高排序
            lines.append(f"  - {price:.4f}")
    else:
        lines.append("压力位：暂无强阻力位")

    # 返回连接的输出行
    return "\n".join(lines)
