
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.dataflows.trace_store import TraceStore

logger = logging.getLogger(__name__)


class PersistenceManager:
    """
    持久化管理器 (PersistenceManager)
    
    职责：
    1. 将 Agent 的运行状态 (State) 转换为结构化的数据记录。
    2. 记录 Trace 日志 (TraceStore)：将思考过程、工具调用、决策逻辑保存为可视化的时间线 (Timeline)。
    3. 记录交易回合摘要 (TraderRoundMemoryStore)：将核心交易决策（Asset, Direction, Thesis）存入历史数据库，供短期记忆检索。
    """

    def __init__(
        self,
        trader_round_store: TraderRoundMemoryStore,
        trace_store: TraceStore,
    ):
        self.trader_round_store = trader_round_store
        self.trace_store = trace_store

    def persist_trace_snapshot(self, state: Dict[str, Any]) -> None:
        """
        记录完整的 Trace 过程快照。
        
        该方法会收集各个 Analyst (Market, News, etc.) 的输出，以及最终的 Trader 决策，
        组合成一个完整的 JSON 对象存入 Trace 库。前端 Focus Page 的 "Agent Thinking" 
        部分就是通过读取这里的数据来展示的。
        """
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text) or {}
        final_decision_text = state.get("final_trade_decision") or ""
        final_decision = self._extract_plan_json(final_decision_text) or {}

        # 只保留一个资产计划摘要，便于前端快速展示。
        trade_plan_summary = None
        per_asset = plan.get("per_asset_decisions") or []
        if per_asset:
            trade_plan_summary = per_asset[0]

        # 从执行结果中提取工具调用，供 Trace 时间线展示。
        risk_control = final_decision.get("risk_control") or {}
        execution = final_decision.get("execution") or []
        tool_calls: list[dict[str, Any]] = []
        for item in execution:
            if not isinstance(item, dict):
                continue
            asset = item.get("asset")
            for key in ("set_leverage", "entry_order", "protection"):
                value = item.get(key)
                if value:
                    tool_calls.append(
                        {
                            "asset": asset,
                            "tool": key,
                            "result": value,
                        }
                    )

        trace_events = [
            {
                "title": "Market Analyst",
                "status": "completed" if state.get("market_report") else "skipped",
                "detail": self._stringify(state.get("market_report")),
            },
            {
                "title": "Newsflash Analyst",
                "status": "completed" if state.get("newsflash_report") else "skipped",
                "detail": self._stringify(state.get("newsflash_report")),
            },
            {
                "title": "Longform Cache",
                "status": "completed" if state.get("longform_report") else "skipped",
                "detail": self._stringify(state.get("longform_report")),
            },
            {
                "title": "Debate",
                "status": "completed",
                "detail": self._stringify(
                    (state.get("investment_debate_state") or {}).get("history")
                ),
            },
            {
                "title": "Trader",
                "status": "completed" if plan else "skipped",
                "detail": self._stringify(plan_text),
            },
            {
                "title": "Risk Control",
                "status": "adjusted" if risk_control.get("adjustments") else "completed",
                "detail": self._stringify(risk_control),
            },
            {
                "title": "Execution",
                "status": "completed" if execution else "skipped",
                "detail": self._stringify(execution),
            },
        ]

        trace_payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "assets": state.get("assets_under_analysis") or [],
            "trace_events": trace_events,
            "plan": trade_plan_summary,
            "final_trade_decision": final_decision,
            "risk_logs": {
                "adjustments": risk_control.get("adjustments") or [],
                "warnings": risk_control.get("warnings") or [],
            },
            "tool_calls": tool_calls,
        }

        try:
            payload_text = json.dumps(trace_payload, ensure_ascii=False)
            self.trace_store.add_trace(payload_text, trace_payload["created_at"])
        except Exception:
            logger.warning("写入 trace 失败", exc_info=True)

    def record_trader_round_summary(self, state: Dict[str, Any]) -> None:
        """
        记录结构化的交易决策摘要到数据库 (TraderRoundMemory)。
        
        这部分数据用于：
        1. Agent 下一轮运行时，检索“最近几轮的决策”，以保持连贯性。
        2. 记录入场时的 Thesis (理由)，以便在平仓时进行复盘对比。
        """
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text) or {}
        summary_data = self._build_trader_round_summary(state, plan)
        if summary_data:
            self.trader_round_store.add_round(**summary_data)
            self.trader_round_store.prune_recent(keep_n=100)

        per_asset = plan.get("per_asset_decisions") or []
        for item in per_asset:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("asset") or "").upper()
            if not symbol:
                continue
            decision = str(item.get("decision") or "")
            risk = item.get("risk_management") or {}
            monitoring_prices = risk.get("monitoring_prices")
            if monitoring_prices is not None and not isinstance(monitoring_prices, str):
                try:
                    monitoring_prices = json.dumps(
                        monitoring_prices, ensure_ascii=False
                    )
                except Exception:
                    monitoring_prices = None
            self.trader_round_store.upsert_monitoring_targets(
                symbol=symbol,
                decision=decision,
                stop_loss=self._coerce_float(risk.get("stop_loss_price")),
                take_profit=self._coerce_float(risk.get("take_profit_price")),
                monitoring_prices=monitoring_prices,
            )

    def build_trade_info_from_open_entry(
        self, symbol: str, action: str, price: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        # 平仓信息与“上次平仓后的第一笔开仓”绑定，避免被后续分析覆盖。
        entry = self.trader_round_store.get_first_open_entry_since_close(symbol)
        if not entry:
            return None
        side = "LONG" if entry.get("decision") == "LONG" else "SHORT"
        entry_price = entry.get("entry_price")
        exit_price = price
        pnl = None
        if entry_price and exit_price:
            direction = 1 if side == "LONG" else -1
            pnl = (exit_price - entry_price) / entry_price * direction
        return {
            "symbol": symbol,
            "side": side,
            "entry_time": entry.get("created_at"),
            "entry_price": entry_price,
            "exit_time": None,  # Will be filled by caller
            "exit_price": exit_price,
            "leverage": entry.get("leverage"),
            "notional": None,  # Not stored in round entry usually
            "pnl": pnl,
            "stop_loss": entry.get("stop_loss"),
            "take_profit": entry.get("take_profit"),
            "notes": "active_close",
        }

    def build_context_snapshot(self, state: Dict[str, Any]) -> str:
        """
        生成简化版的上下文快照 (Context Snapshot)。
        
        当需要进行“交易复盘 (Reflection)”时，我们需要知道当时的市场环境（市场报告、新闻、叙事）。
        这个方法提取最重要的摘要信息，打包成 JSON 字符串，作为交易记忆的一部分存下来。
        """
        market = self._summarize_market_report(state.get("market_report"))
        newsflash = self._summarize_newsflash_report(state.get("newsflash_report"))
        longform = self._summarize_longform_report(state.get("longform_report"))
        snapshot = {
            "market": market,
            "newsflash": newsflash,
            "longform": longform,
        }
        return json.dumps(snapshot, ensure_ascii=False)

    def _build_trader_round_summary(
        self, state: Dict[str, Any], plan: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        per_asset = plan.get("per_asset_decisions") or []
        decision = None
        asset = None
        thesis = None
        execution = None
        risk = None

        for item in per_asset:
            if not isinstance(item, dict):
                continue
            action = str(item.get("decision") or "").upper()
            if action and action != "WAIT":
                decision = action
                asset = item.get("asset")
                thesis = item.get("thesis") or ""
                execution = item.get("execution") or {}
                risk = item.get("risk_management") or {}
                break

        if decision is None:
            decision = "WAIT"

        assets = state.get("assets_under_analysis") or []
        round_id = int(state.get("interaction_round") or 0)
        leverage = execution.get("leverage") if execution else None
        entry_price = execution.get("entry_price") if execution else None
        stop_loss = risk.get("stop_loss_price") if risk else None
        take_profit = risk.get("take_profit_price") if risk else None
             
        invalidations = risk.get("invalidations") if risk else []
        monitoring = risk.get("monitoring") if risk else []

        summary_lines = [
            f"[结论] {asset or '未选择资产'} | {decision} | {thesis or '无明确理由'}",
            f"[仓位] 当前持仓：{state.get('current_positions') or '未获取'}",
            f"[风险] 入场 {entry_price or '未给出'} | 止损 {stop_loss or '未给出'} | 止盈 {take_profit or '未给出'} | 杠杆 {leverage or '未给出'}",
            f"[下轮关注] {', '.join(monitoring or invalidations or ['暂无'])}",
        ]
        summary = "\n".join(summary_lines)
        if decision in {"LONG", "SHORT"}:
            situation = self.build_context_snapshot(state)
        else:
            situation = f"{asset or '多资产'} | {decision} | {thesis or '无'}"

        return {
            "summary": summary,
            "situation": situation,
            "assets": assets,
            "round_id": round_id,
            "decision": decision,
            "asset": asset,
            "is_open_entry": decision in {"LONG", "SHORT"},
            "entry_price": self._coerce_float(entry_price),
            "stop_loss": self._coerce_float(stop_loss),
            "take_profit": self._coerce_float(take_profit),
            "leverage": self._coerce_int(leverage),
        }

    def _extract_report_json(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raw = str(raw)
        raw = raw.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                return None

    def _summarize_market_report(self, raw: Any) -> Dict[str, Any]:
        data = self._extract_report_json(raw) or {}
        per_asset = data.get("per_asset") or []
        highlights = []
        for item in per_asset:
            if not isinstance(item, dict):
                continue
            trend = item.get("trend_view") or {}
            highlights.append(
                {
                    "symbol": item.get("symbol"),
                    "direction": trend.get("direction"),
                    "indicator_summary": item.get("indicator_summary"),
                    "triggers": trend.get("triggers"),
                    "invalidations": trend.get("invalidations"),
                }
            )
        if highlights:
            return {"analysis_date": data.get("analysis_date"), "per_asset": highlights}
        return {"raw": self._truncate_text(raw)}

    def _summarize_newsflash_report(self, raw: Any) -> Dict[str, Any]:
        data = self._extract_report_json(raw) or {}
        sentiment = data.get("sentiment_summary") or {}
        themes = []
        for item in data.get("themes") or []:
            if not isinstance(item, dict):
                continue
            themes.append(
                {
                    "theme": item.get("theme"),
                    "net_effect": item.get("net_effect"),
                    "impacted_assets": item.get("impacted_assets"),
                    "highlights": item.get("highlights"),
                }
            )
        if sentiment or themes:
            return {
                "analysis_date": data.get("analysis_date"),
                "sentiment": sentiment,
                "themes": themes,
            }
        return {"raw": self._truncate_text(raw)}

    def _summarize_longform_report(self, raw: Any) -> Dict[str, Any]:
        data = self._extract_report_json(raw) or {}
        narrative = data.get("narrative_summary") or {}
        implications = data.get("trading_implications") or {}
        if narrative or implications:
            return {
                "analysis_date": data.get("analysis_date"),
                "narrative_summary": narrative,
                "trading_implications": implications,
            }
        return {"raw": self._truncate_text(raw)}

    @staticmethod
    def _truncate_text(text: Any, limit: int = 600) -> str:
        raw = text or ""
        if not isinstance(raw, str):
            raw = str(raw)
        raw = raw.strip()
        if len(raw) <= limit:
            return raw
        return raw[:limit].rstrip() + "..."

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    @staticmethod
    def _extract_plan_json(plan_text: str) -> Optional[Dict[str, Any]]:
        if not plan_text:
            return None
        try:
            return json.loads(plan_text)
        except Exception:
            start = plan_text.find("{")
            end = plan_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(plan_text[start : end + 1])
            except Exception:
                return None

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            text = str(value).strip().lower().replace("usdt", "")
            return float(text)
        except Exception:
            return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            text = str(value).strip().lower().replace("x", "")
            return int(float(text))
        except Exception:
            return None
