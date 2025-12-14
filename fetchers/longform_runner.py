"""定时运行长文分析师，周期性写入 SQLite 缓存。"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import List, Any, Optional

from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from pydantic import SecretStr

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.analysts.crypto_longform_analyst import (
    create_crypto_longform_analyst,
)
from langchain_community.chat_models.tongyi import ChatTongyi


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("longform-runner")


def _initialize_llm(config: dict) -> Any:
    """只启用阿里云百炼 Qwen。"""
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
    return ChatTongyi(model=model, api_key=SecretStr(api_key))


def _run_once(node, assets: List[str], trade_date: str) -> Optional[str]:
    """调用长文分析节点，并返回生成的多资产报告。"""
    if not assets:
        return None
    state = {
        "messages": [
            HumanMessage(
                content=f"请针对以下资产更新 Odaily 长文研究并生成一份统一报告：{', '.join(assets)}。"
            )
        ],
        "trade_date": trade_date,
        "assets_under_analysis": assets,
    }
    result = node(state)
    return result.get("longform_report")


async def _loop(assets: List[str], interval_seconds: int, node) -> None:
    """定时循环执行长文分析，对配置的资产列表一次性生成报告。"""
    while True:
        trade_date = datetime.now(timezone.utc).date().isoformat()
        try:
            logger.info(
                "开始运行长文分析师（assets=%s, date=%s）", ",".join(assets), trade_date
            )
            report = _run_once(node, assets, trade_date)
            if report:
                logger.info("长文分析完成（字数=%d）", len(report))
            else:
                logger.warning("长文分析无输出")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("长文分析执行失败: %s", exc)
        logger.info("完成一轮长文分析，%s 秒后再次运行", interval_seconds)
        await asyncio.sleep(interval_seconds)


def main() -> None:
    load_dotenv()
    config = DEFAULT_CONFIG.copy()
    assets_env = os.getenv("LONGFORM_ASSETS", "BTCUSDT,ETHUSDT")
    assets = [a.strip() for a in assets_env.split(",") if a.strip()]
    if not assets:
        raise ValueError("必须通过 LONGFORM_ASSETS 指定至少一个资产。")

    interval = int(os.getenv("LONGFORM_RUN_INTERVAL", "86400"))  # 默认 24 小时跑一次
    llm = _initialize_llm(config)
    node = create_crypto_longform_analyst(llm)
    logger.info(
        "启动长文分析 runner（资产=%s，间隔=%ss，模型=%s）",
        assets,
        interval,
        getattr(llm, "model_name", None) or getattr(llm, "model", "unknown"),
    )
    asyncio.run(_loop(assets, interval, node))


if __name__ == "__main__":
    main()
