"""LLM-based trade cycle reflection helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Sequence


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    return str(content)


def _extract_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = _normalize_content(raw).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"raw": text}
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return {"raw": text}


class TradeCycleReflector:
    """Generate reflections for a complete trade (entry -> exit)."""

    def __init__(self, llm: Any):
        self.llm = llm
        self.system_prompt = (
            "你是一名资深交易复盘官。请根据开仓上下文与平仓上下文做对比复盘，"
            "并输出单行 JSON（不要额外文字），字段固定如下：\n"
            "{\n"
            '  "summary": "一句话结论（<120字）",\n'
            '  "hypothesis_check": "核心假设是否成立及原因",\n'
            '  "execution_review": "入场/止损/止盈执行是否符合计划",\n'
            '  "value_assessment": "这笔交易是否有价值（高/中/低）及理由",\n'
            '  "mistake_tags": ["错误类型标签"],\n'
            '  "next_rules": ["下次可执行规则"]\n'
            "}\n"
            "重点：聚焦可复用的结论，不复述长文。"
        )

    def _build_trade_context(self, trade_info: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": trade_info.get("symbol"),
            "side": trade_info.get("side"),
            "leverage": trade_info.get("leverage"),
            "notional": trade_info.get("notional"),
            "entry_time": trade_info.get("entry_time"),
            "entry_price": trade_info.get("entry_price"),
            "exit_time": trade_info.get("exit_time"),
            "exit_price": trade_info.get("exit_price"),
            "stop_loss": trade_info.get("stop_loss"),
            "take_profit": trade_info.get("take_profit"),
            "pnl": trade_info.get("pnl"),
            "notes": trade_info.get("notes"),
        }

    def _build_market_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "open_position_context": state.get("open_position_context") or "",
            "close_position_context": state.get("close_position_context") or "",
        }

    def reflect(self, trade_info: Dict[str, Any], state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        market_context = self._build_market_context(state or {})
        trade_context = self._build_trade_context(trade_info)
        messages: Sequence = [
            ("system", self.system_prompt),
            (
                "human",
                "以下是交易信息与市场上下文，请输出 JSON 复盘：\n"
                f"TRADE_INFO={json.dumps(trade_context, ensure_ascii=False)}\n"
                f"CONTEXT={json.dumps(market_context, ensure_ascii=False)}",
            ),
        ]
        raw = self.llm.invoke(messages).content
        parsed = _extract_json(raw)
        summary = json.dumps(parsed, ensure_ascii=False)
        context = json.dumps(
            {"trade_info": trade_context, "context": market_context},
            ensure_ascii=False,
        )
        return {"summary": summary, "context": context}
