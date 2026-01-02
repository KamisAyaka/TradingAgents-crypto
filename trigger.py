"""
定时触发器 - 按美国纽约时间调度运行交易分析

调度规则：
- 纽约时间周一到周五 8:00-20:00：每15分钟触发一次
- 其他时间：每1小时触发一次
"""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from pydantic import SecretStr
from langchain_community.chat_models.tongyi import ChatTongyi

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.analysts.crypto_longform_analyst import (
    create_crypto_longform_analyst,
)

from fetchers.binance_fetcher import sync_binance_pairs
from fetchers.odaily_fetcher import sync_articles, sync_newsflash

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 纽约时区
NY_TZ = ZoneInfo("America/New_York")

# 加载环境变量
load_dotenv()

# 配置 LLM
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["quick_llm_provider"] = "openai"
config["deep_llm_provider"] = "openai"
config["quick_think_llm"] = "Qwen/Qwen2.5-14B-Instruct"
config["deep_think_llm"] = "Qwen/Qwen3-14B"
config["backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["quick_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["deep_backend_url"] = "https://api-inference.modelscope.cn/v1/"
config["max_debate_rounds"] = 1
config["use_chroma_memory"] = True

# 交易参数
DEFAULT_TICKERS = ["BTCUSDT", "ETHUSDT"]
DEFAULT_CAPITAL = 10000.0
DEFAULT_MIN_LEVERAGE = int(config.get("min_leverage", 1))
DEFAULT_MAX_LEVERAGE = int(config.get("max_leverage", 3))

# 初始化交易图（全局，避免重复初始化）
ta: TradingAgentsGraph | None = None
_longform_node = None
_binance_first_run = True


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


def run_analysis():
    """执行一次交易分析"""
    now_ny = datetime.now(NY_TZ)
    logger.info(f"========== 开始分析 (纽约时间: {now_ny.strftime('%Y-%m-%d %H:%M:%S')}) ==========")
    
    try:
        graph = init_trading_graph()
        _, decision = graph.propagate(
            DEFAULT_TICKERS,
            available_capital=DEFAULT_CAPITAL,
            min_leverage=DEFAULT_MIN_LEVERAGE,
            max_leverage=DEFAULT_MAX_LEVERAGE,
        )
        logger.info(f"分析完成，决策: {decision[:500]}..." if len(decision) > 500 else f"分析完成，决策: {decision}")
    except Exception as e:
        logger.error(f"分析过程出错: {e}", exc_info=True)
    
    logger.info("========== 分析结束 ==========\n")


def _initialize_longform_node():
    """初始化长文分析节点（复用实例，避免重复创建）。"""
    global _longform_node
    if _longform_node is not None:
        return _longform_node

    provider = os.getenv(
        "LONGFORM_LLM_PROVIDER",
        config.get("longform_llm_provider", "dashscope"),
    ).lower()
    if provider != "dashscope":
        raise ValueError("长文分析仅支持 DashScope/Qwen，请设置 LONGFORM_LLM_PROVIDER=dashscope")

    model = os.getenv(
        "LONGFORM_LLM_MODEL",
        config.get("longform_llm_model", "qwen-plus"),
    )
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未设置，无法运行长文分析师。")

    llm = ChatTongyi(model=model, api_key=SecretStr(api_key))
    _longform_node = create_crypto_longform_analyst(llm)
    return _longform_node


def run_binance_fetcher():
    """执行一次 Binance 行情同步。"""
    global _binance_first_run
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


def run_longform_analysis():
    """执行一次长文分析并写入缓存。"""
    assets_env = os.getenv("LONGFORM_ASSETS", "BTCUSDT,ETHUSDT")
    assets = [a.strip() for a in assets_env.split(",") if a.strip()]
    if not assets:
        logger.error("LONGFORM_ASSETS 未配置，跳过长文分析。")
        return

    try:
        node = _initialize_longform_node()
        trade_date = datetime.utcnow().date().isoformat()
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


def is_trading_hours() -> bool:
    """判断当前是否在纽约交易时段（周一到周五 8:00-20:00）"""
    now_ny = datetime.now(NY_TZ)
    # 周一=0, 周日=6
    is_weekday = now_ny.weekday() < 5
    is_trading_time = 8 <= now_ny.hour < 20
    return is_weekday and is_trading_time


def main():
    """主函数 - 启动调度器"""
    logger.info("启动定时触发器...")
    logger.info(f"当前纽约时间: {datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 预初始化交易图
    init_trading_graph()
    
    scheduler = BlockingScheduler(timezone=NY_TZ)
    
    # 交易时段：周一到周五 8:00-19:45，每15分钟
    # (8:00, 8:15, 8:30, ..., 19:45)
    scheduler.add_job(
        run_analysis,
        CronTrigger(
            day_of_week="mon-fri",
            hour="8-19",
            minute="0,15,30,45",
            timezone=NY_TZ,
        ),
        id="trading_hours_job",
        name="交易时段分析 (每15分钟)",
        replace_existing=True,
    )
    
    # 非交易时段：
    # 1. 周一到周五 0:00-7:00 和 20:00-23:00，每小时整点
    scheduler.add_job(
        run_analysis,
        CronTrigger(
            day_of_week="mon-fri",
            hour="0-7,20-23",
            minute="0",
            timezone=NY_TZ,
        ),
        id="off_hours_weekday_job",
        name="工作日非交易时段分析 (每小时)",
        replace_existing=True,
    )
    
    # 2. 周末全天，每小时整点
    scheduler.add_job(
        run_analysis,
        CronTrigger(
            day_of_week="sat,sun",
            hour="*",
            minute="0",
            timezone=NY_TZ,
        ),
        id="weekend_job",
        name="周末分析 (每小时)",
        replace_existing=True,
    )
    
    # Binance 行情同步（默认 900 秒）
    scheduler.add_job(
        run_binance_fetcher,
        IntervalTrigger(
            seconds=int(os.getenv("BINANCE_SYNC_INTERVAL", "900")),
            timezone=NY_TZ,
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
            timezone=NY_TZ,
        ),
        id="odaily_newsflash_job",
        name="Odaily 快讯同步",
        replace_existing=True,
    )
    scheduler.add_job(
        run_odaily_article_fetcher,
        IntervalTrigger(
            seconds=int(os.getenv("ODAILY_ARTICLE_INTERVAL", "3600")),
            timezone=NY_TZ,
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
            timezone=NY_TZ,
        ),
        id="longform_analysis_job",
        name="长文分析",
        replace_existing=True,
    )
    
    # 打印所有任务
    logger.info("已配置的定时任务:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")
    
    # 启动时立即执行一次
    logger.info("启动时执行一次分析...")
    run_analysis()
    run_binance_fetcher()
    run_odaily_newsflash_fetcher()
    run_odaily_article_fetcher()
    run_longform_analysis()
    
    logger.info("调度器开始运行，按 Ctrl+C 停止")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")


if __name__ == "__main__":
    main()
