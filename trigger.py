"""定时触发器 - 通过价格预警触发分析任务。"""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_openai import ChatOpenAI

from tradingagents.graph.trading_graph import TradingAgentsGraph, _FallbackChatModel
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.analysts.crypto_longform_analyst import (
    create_crypto_longform_analyst,
)
from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.dataflows.binance_future import get_service

from fetchers.binance_fetcher import sync_binance_pairs
from fetchers.odaily_fetcher import sync_articles, sync_newsflash

# 配置日志（同时输出到控制台和文件）
LOG_DIR = os.getenv("TRADINGAGENTS_LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "tradingagents.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)
formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

if not root_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

file_handler_exists = any(
    isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers
)
if not file_handler_exists:
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

# Reduce noisy framework logs; keep warnings/errors only.
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# 加载环境变量
load_dotenv()

# 配置（默认配置 + 环境变量覆盖）
config = DEFAULT_CONFIG.copy()

# 交易参数
DEFAULT_TICKERS = ["BTCUSDT", "ETHUSDT"]
DEFAULT_CAPITAL = 100.0
DEFAULT_MIN_LEVERAGE = int(config.get("min_leverage", 1))
DEFAULT_MAX_LEVERAGE = int(config.get("max_leverage", 3))

# 初始化交易图（全局，避免重复初始化）
ta: TradingAgentsGraph | None = None
_longform_node = None
_binance_first_run = True
_alert_store: TraderRoundMemoryStore | None = None


def _get_alert_store() -> TraderRoundMemoryStore:
    global _alert_store
    if _alert_store is None:
        _alert_store = TraderRoundMemoryStore(
            config.get("trader_round_db_path")
            or os.path.join(config["results_dir"], "trader_round_memory.db")
        )
    return _alert_store


def init_trading_graph():
    """初始化交易图"""
    global ta
    if ta is None:
        logger.info("正在初始化 TradingAgentsGraph...")
        ta = TradingAgentsGraph(
            debug=True,
            config=config,
            selected_analysts=["market", "newsflash", "longform"],
        )
        logger.info("TradingAgentsGraph 初始化完成")
    return ta


# 全局锁，防止分析任务并发执行
_is_analysis_running = False


def run_analysis():
    """执行 AI 交易分析逻辑"""
    global _is_analysis_running
    if _is_analysis_running:
        logger.info("上一次分析任务仍在进行中，本次跳过。")
        return

    logger.info("========== 开始分析 ==========")
    _is_analysis_running = True
    
    try:
        # 支持从环境变量读取动态配置 (由 Server 注入)
        assets_env = os.getenv("ANALYSIS_ASSETS")
        assets = [s.strip() for s in assets_env.split(",")] if assets_env else DEFAULT_TICKERS
        
        capital = float(os.getenv("ANALYSIS_CAPITAL", str(DEFAULT_CAPITAL)))
        min_lev = int(os.getenv("ANALYSIS_MIN_LEVERAGE", str(DEFAULT_MIN_LEVERAGE)))
        max_lev = int(os.getenv("ANALYSIS_MAX_LEVERAGE", str(DEFAULT_MAX_LEVERAGE)))

        graph = init_trading_graph()
        _, decision = graph.propagate(
            assets,
            available_capital=capital,
            min_leverage=min_lev,
            max_leverage=max_lev,
        )
        logger.info(f"分析完成，决策: {decision[:500]}..." if len(decision) > 500 else f"分析完成，决策: {decision}")
    except Exception as e:
        logger.error(f"分析过程出错: {e}", exc_info=True)
    finally:
        # 无论成功失败，一定要释放锁
        _is_analysis_running = False
    
    logger.info("========== 分析结束 ==========\n")


def _initialize_longform_node():
    """初始化长文分析节点（复用实例，避免重复创建）。"""
    global _longform_node
    if _longform_node is not None:
        return _longform_node

    model = "deepseek-chat"
    base = "https://api.deepseek.com/v1"
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置，无法运行长文分析师。")

    extra_body = {"enable_thinking": False}
    llm = ChatOpenAI(
        model=model,
        base_url=base,
        api_key=SecretStr(api_key),
        extra_body=extra_body,
    )
    _longform_node = create_crypto_longform_analyst(llm)
    return _longform_node


def run_binance_fetcher(symbols: list[str] | None = None):
    """执行一次 Binance 行情同步。"""
    global _binance_first_run
    if not symbols:
        symbols = [
            s.strip().upper()
            for s in os.getenv("BINANCE_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
            if s.strip()
        ]
    intervals = [
        i.strip()
        for i in os.getenv("BINANCE_INTERVALS", "15m,1h,4h").split(",")
        if i.strip()
    ]
    limit = int(os.getenv("BINANCE_SYNC_LIMIT", "50"))
    initial_limit = int(os.getenv("BINANCE_SYNC_INITIAL_LIMIT", "500"))
    current_limit = initial_limit if _binance_first_run and initial_limit > 0 else limit

    if not symbols or not intervals:
        logger.error("BINANCE_SYMBOLS 或 BINANCE_INTERVALS 缺失，跳过 Binance 同步。")
        return

    try:
        logger.info(
            "开始同步 Binance K 线（symbols=%s, intervals=%s, limit=%s）",
            ",".join(symbols),
            ",".join(intervals),
            current_limit,
        )
        summary = sync_binance_pairs(symbols, intervals, limit=current_limit)
        logger.info("Binance 同步完成: %s", summary)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Binance 同步失败: %s", exc)
    finally:
        _binance_first_run = False


def run_odaily_newsflash_fetcher():
    """执行一次 Odaily 快讯同步。"""
    try:
        logger.info("开始同步 Odaily 快讯")
        records = sync_newsflash()
        logger.info("Odaily 快讯同步完成（%d 条）", len(records))
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Odaily 快讯同步失败: %s", exc)


def run_odaily_article_fetcher():
    """执行一次 Odaily 文章同步。"""
    try:
        logger.info("开始同步 Odaily 文章")
        records = sync_articles()
        logger.info("Odaily 文章同步完成（%d 条）", len(records))
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Odaily 文章同步失败: %s", exc)


def run_longform_analysis(assets: list[str] | None = None):
    """执行一次长文分析并写入缓存。"""
    if not assets:
        assets_env = os.getenv("LONGFORM_ASSETS", "BTCUSDT,ETHUSDT")
        assets = [a.strip() for a in assets_env.split(",") if a.strip()]
    
    if not assets:
        logger.error("LONGFORM_ASSETS 未配置，跳过长文分析。")
        return

    # Check for existing analysis within the last 24 hours to avoid redundant runs
    from tradingagents.dataflows.odaily import get_latest_longform_analysis
    
    # Check globally or per-asset if we were iterating. Currently we run one batch analysis.
    # The graph saves it with asset="__GLOBAL_LONGFORM__" or specific asset if customized.
    # The longform node currently saves with the trade date.
    # Let's check the latest entry regardless of asset for now, or use the global key.
    # The current implementation in crypto_longform_analyst.py doesn't pass a specific asset to save_longform_analysis,
    # so it defaults to __GLOBAL_LONGFORM__ via save_longform_analysis default or caller.
    # Inspecting crypto_longform_analyst.py again implies it calls: save_longform_analysis(report, analysis_date=current_date)
    # This means asset defaults to None -> __GLOBAL_LONGFORM__.
    
    latest = get_latest_longform_analysis()
    if latest:
        created_at_iso = latest.get("created_at")
        if created_at_iso:
            try:
                created_at = datetime.fromisoformat(created_at_iso)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                # Check if less than 24 hours (86400 seconds)
                elapsed = (datetime.now(timezone.utc) - created_at).total_seconds()
                if elapsed < 86400:
                    logger.info(f"长文分析跳过: 现有报告生成于 {elapsed/3600:.1f} 小时前 (小于 24h)")
                    return
            except Exception as e:
                logger.warning(f"无法解析长文分析时间戳: {e}")

    try:
        node = _initialize_longform_node()
        trade_date = datetime.now(timezone.utc).date().isoformat()
        logger.info("开始运行长文分析师（assets=%s, date=%s）", ",".join(assets), trade_date)
        state = {
            "messages": [
                (
                    "human",
                    f"请针对以下资产更新 Odaily 长文研究并生成一份统一报告：{', '.join(assets)}。",
                )
            ],
            "trade_date": trade_date,
            "assets_under_analysis": assets,
        }
        result = node(state)
        report = result.get("longform_report") if isinstance(result, dict) else None
        if report:
            logger.info("长文分析完成（字数=%d）", len(report))
        else:
            logger.warning("长文分析无输出")
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("长文分析执行失败: %s", exc)


def _check_timeout_trigger(store: TraderRoundMemoryStore) -> tuple[bool, bool]:
    """检查是否需要因超时触发分析，并返回是否处于冷却期。"""
    last_run_iso = store.get_last_round_time()
    should_run_by_timeout = False
    is_cooldown = False

    if last_run_iso:
        try:
            last_run_time = datetime.fromisoformat(last_run_iso)
            # Ensure timezone awareness compatibility
            if last_run_time.tzinfo is None:
                last_run_time = last_run_time.replace(tzinfo=timezone.utc)

            elapsed_seconds = (datetime.now(timezone.utc) - last_run_time).total_seconds()

            # 冷却逻辑：如果距离上次分析不足 15 分钟 (900秒)，则视为冷却中
            is_cooldown = elapsed_seconds < 900

            # 4小时 = 14400秒
            if elapsed_seconds >= 14400:
                should_run_by_timeout = True
                logger.info(
                    "触发原因: 超时未分析 (距上次已过 %.1f 小时)",
                    elapsed_seconds / 3600,
                )
        except Exception as e:
            logger.warning("解析上次运行时间失败: %s", e)
            # 如果解析失败，默认不冷却，也不超时
            is_cooldown = False
    else:
        # 无记录视为无需冷却
        is_cooldown = False
        logger.info("触发原因: 无历史记录 (首次运行)")
        should_run_by_timeout = True

    return should_run_by_timeout, is_cooldown


def _check_price_alert(
    store: TraderRoundMemoryStore,
) -> tuple[bool, Optional[str], Optional[str], float]:
    """检查价格预警触发情况。"""
    targets = store.get_monitoring_targets()
    price_trigger_hit = False
    reason = None
    symbol = None
    price = 0
    threshold_pct = float(os.getenv("PRICE_ALERT_THRESHOLD_PCT", "0.005"))

    for target in targets:
        symbol = target.get("symbol")
        if not symbol:
            continue
        stop_loss = target.get("stop_loss")
        take_profit = target.get("take_profit")
        decision = str(target.get("decision") or "").upper()
        side = "SHORT" if decision == "SHORT" else "LONG"

        try:
            price = get_service().get_mark_price(symbol)
            if price <= 0:
                continue
        except Exception as exc:
            logger.warning("检查价格预警失败 %s: %s", symbol, exc)
            continue

        near_low = False
        near_high = False
        reached_low = False
        reached_high = False

        if stop_loss is not None or take_profit is not None:
            reached_low = stop_loss is not None and price <= float(stop_loss)
            reached_high = take_profit is not None and price >= float(take_profit)
            if reached_low or reached_high:
                price_trigger_hit = True
            else:
                if stop_loss:
                    near_low = (
                        abs(price - float(stop_loss)) / float(stop_loss)
                        <= threshold_pct
                    )
                if take_profit:
                    near_high = (
                        abs(price - float(take_profit)) / float(take_profit)
                        <= threshold_pct
                    )
                if near_low or near_high:
                    price_trigger_hit = True

            if price_trigger_hit:
                if side == "LONG":
                    if reached_low:
                        reason = "stop_loss_hit"
                    elif reached_high:
                        reason = "take_profit_hit"
                    else:
                        reason = "near_stop_loss" if near_low else "near_take_profit"
                else:
                    if reached_low:
                        reason = "take_profit_hit"
                    elif reached_high:
                        reason = "stop_loss_hit"
                    else:
                        reason = "near_take_profit" if near_low else "near_stop_loss"

                logger.info(
                    "价格预警触发: %s (%s) 现价=%s stop_loss=%s take_profit=%s reason=%s",
                    symbol,
                    side,
                    price,
                    stop_loss,
                    take_profit,
                    reason,
                )
                return price_trigger_hit, reason, symbol, price

        if decision != "WAIT":
            continue

        raw_prices = target.get("monitoring_prices")
        nodes = []
        if raw_prices:
            if isinstance(raw_prices, str):
                try:
                    nodes = json.loads(raw_prices)
                except Exception:
                    nodes = []
            elif isinstance(raw_prices, list):
                nodes = raw_prices
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_price = node.get("price")
            condition = str(node.get("condition") or "touch").lower()
            note = node.get("note") or node.get("reason") or "monitoring_price"
            if node_price is None:
                continue
            try:
                node_price = float(node_price)
            except (TypeError, ValueError):
                continue
            hit = False
            if condition == "above":
                hit = price >= node_price
            elif condition == "below":
                hit = price <= node_price
            else:
                hit = abs(price - node_price) / node_price <= threshold_pct
            if hit:
                reason = f"monitoring:{note}"
                logger.info(
                    "价格预警触发: %s 现价=%s monitoring_price=%s reason=%s",
                    symbol,
                    price,
                    node_price,
                    reason,
                )
                return True, reason, symbol, price

    return price_trigger_hit, reason, symbol, price


def run_market_monitor():
    """综合市场监控：检查价格预警 OR 检查是否超时（4小时）。"""
    store = _get_alert_store()

    # 1. 检查是否超时（4小时未分析）
    should_run_by_timeout, is_cooldown = _check_timeout_trigger(store)

    # 2. 检查价格预警
    price_trigger_hit, reason, symbol, price = _check_price_alert(store)

    # 3. 综合判断是否触发分析
    # 冷却期内不触发分析。
    if is_cooldown:
        return

    should_run = should_run_by_timeout or price_trigger_hit

    if should_run:
        trigger_reason = f"timeout={should_run_by_timeout}, price_alert={reason}"
        logger.info(f"触发交易分析: {trigger_reason}")
        run_analysis()

        # 更新最后触发状态，避免短时间内重复触发
        if symbol and price > 0:
            store.set_alert_state(
                symbol, datetime.now(timezone.utc).isoformat(), reason or "timeout", price
            )



def configure_scheduler(scheduler):
    """配置调度器任务 - 供 main 和 server.py 复用"""
    
    # Binance 行情同步（默认 900 秒）
    scheduler.add_job(
        run_binance_fetcher,
        IntervalTrigger(
            seconds=int(os.getenv("BINANCE_SYNC_INTERVAL", "900")),
        ),
        id="binance_fetcher_job",
        name="Binance 行情同步",
        replace_existing=True,
    )

    # Odaily 快讯/文章同步
    scheduler.add_job(
        run_odaily_newsflash_fetcher,
        IntervalTrigger(
            seconds=int(os.getenv("ODAILY_NEWSFLASH_INTERVAL", "900")),
        ),
        id="odaily_newsflash_job",
        name="Odaily 快讯同步",
        replace_existing=True,
    )
    scheduler.add_job(
        run_odaily_article_fetcher,
        IntervalTrigger(
            seconds=int(os.getenv("ODAILY_ARTICLE_INTERVAL", "3600")),
        ),
        id="odaily_article_job",
        name="Odaily 文章同步",
        replace_existing=True,
    )

    # 长文分析（默认 86400 秒）
    scheduler.add_job(
        run_longform_analysis,
        IntervalTrigger(
            seconds=int(os.getenv("LONGFORM_RUN_INTERVAL", "86400")),
        ),
        id="longform_analysis_job",
        name="长文分析",
        replace_existing=True,
    )

    # 改为 unified market monitor (每 60 秒运行一次)
    scheduler.add_job(
        run_market_monitor,
        IntervalTrigger(seconds=60),
        id="market_monitor_job",
        name="市场监控 (价格/超时)",
        replace_existing=True,
    )


def execute_startup_tasks():
    """执行启动时的初始化任务 - 供 main 和 server.py 复用"""
    logger.info("执行启动初始化任务...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(run_binance_fetcher),
            executor.submit(run_odaily_newsflash_fetcher),
            executor.submit(run_odaily_article_fetcher),
            executor.submit(run_longform_analysis),
        ]
        for future in futures:
            try:
                future.result()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("启动初始化任务执行失败: %s", exc)
    run_market_monitor() 



def main():
    """主函数 - 启动调度器"""
    logger.info("启动定时触发器...")
    
    # 预初始化交易图
    init_trading_graph()
    
    scheduler = BlockingScheduler(
        executors={"default": ThreadPoolExecutor(max_workers=6)},
        job_defaults={"coalesce": True, "max_instances": 2},
    )
    configure_scheduler(scheduler)
    
    # 打印所有任务
    logger.info("已配置的定时任务:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")
    
    # 启动时立即执行一次
    execute_startup_tasks()
    
    logger.info("调度器开始运行，按 Ctrl+C 停止")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")


if __name__ == "__main__":
    main()
