"""LLM-based trade cycle reflection helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from typing import Any


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_normalize_content(item) for item in content)
    if content is None:
        return ""
    return str(content)


class TradeCycleReflector:
    """Generate reflections for a complete trade (entry -> exit)."""

    def __init__(self, llm: Any):
        self.llm = llm
        self.system_prompt = (
            "你是一名资深交易复盘官。给定一次完整的交易信息（入场、"
            "持仓过程、平仓结果与损益），请输出：\n"
            "1) 交易背景与初衷（引用市场/研究报告中的关键信息）。\n"
            "2) 执行表现：入场是否按计划、杠杆/仓位是否恰当、止损/止盈运行情况。\n"
            "3) 结果评估：收益/亏损的主要驱动因素，策略假设是否成立。\n"
            "4) 改进建议：下一次遇到类似场景时在入场、杠杆、止损、监控方面应如何调整。\n"
            "5) 一句话摘要（< 200 字）。\n"
            "请用中文分段输出，强调可执行要点。"
        )

    def _build_trade_context(self, trade_info: Dict[str, Any]) -> str:
        entry_time = trade_info.get("entry_time") or ""
        exit_time = trade_info.get("exit_time") or ""
        pnl = trade_info.get("pnl") or 0.0
        return (
            f"标的: {trade_info.get('symbol')}\n"
            f"方向: {trade_info.get('side')}\n"
            f"杠杆: {trade_info.get('leverage')}x\n"
            f"名义金额: {trade_info.get('notional')} USDT\n"
            f"入场时间/价格: {entry_time} / {trade_info.get('entry_price')}\n"
            f"平仓时间/价格: {exit_time} / {trade_info.get('exit_price')}\n"
            f"止损: {trade_info.get('stop_loss')}  止盈: {trade_info.get('take_profit')}\n"
            f"实际盈亏: {pnl} USDT\n"
            f"其他备注: {trade_info.get('notes') or '无'}"
        )

    def _build_market_context(self, state: Dict[str, Any]) -> str:
        market_report = state.get("market_report") or "暂无市场报告"
        news_report = state.get("newsflash_report") or "暂无快讯"
        longform_report = state.get("longform_report") or "暂无长文"
        debate = state.get("investment_debate_state") or {}
        trader_plan = state.get("trader_investment_plan") or "暂无交易计划"
        execution_result = state.get("final_trade_decision") or "暂无执行结果"
        return (
            f"市场技术报告:\n{market_report}\n\n"
            f"新闻/快讯:\n{news_report}\n\n"
            f"长文研究:\n{longform_report}\n\n"
            f"辩论记录:\n{debate.get('history') or '暂无'}\n\n"
            f"交易员计划:\n{trader_plan}\n\n"
            f"执行结果:\n{execution_result}"
        )

    def reflect(self, trade_info: Dict[str, Any], state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        market_context = self._build_market_context(state or {})
        trade_context = self._build_trade_context(trade_info)
        messages: Sequence = [
            ("system", self.system_prompt),
            (
                "human",
                f"以下是交易信息与当时的市场上下文，请生成结构化复盘：\n\n"
                f"【交易信息】\n{trade_context}\n\n【市场上下文】\n{market_context}",
            ),
        ]
        raw = self.llm.invoke(messages).content
        summary = _normalize_content(raw).strip()
        context = f"{trade_context}\n\n{market_context}"
        return {"summary": summary, "context": context}
