# TradingAgents/graph/trading_graph.py

import os
import json
from pathlib import Path
import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, Optional, cast

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
)
from tradingagents.dataflows.trader_round_memory import TraderRoundMemoryStore
from tradingagents.dataflows.trace_store import TraceStore
from tradingagents.agents.reflection.trade_cycle_reflector import TradeCycleReflector

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_crypto_market_batch,
    get_support_resistance_batch,
    get_crypto_newsflash_candidates,
    get_crypto_longform_candidates,
    get_crypto_article_content,
    get_crypto_newsflash_content,
)
from tradingagents.agents.utils.binance_trade_tools import (
    set_binance_leverage,
    open_binance_position_usdt,
    close_binance_position,
    set_binance_take_profit_stop_loss,
)
from tradingagents.dataflows.binance_future import get_service

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator


class TradingAgentsGraph:
    """交易多智能体框架的主控制类。"""

    def __init__(
        self,
        selected_analysts=["market", "newsflash", "longform"],
        debug=False,
        config: Optional[Dict[str, Any]] = None,
    ):
        """初始化整个图及各组件。

        Args:
            selected_analysts: 需要启动的分析师节点列表
            debug: 是否开启调试模式（输出完整流）
            config: 配置字典，None 时使用默认配置
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        
        quick_provider = (
            self.config.get("quick_llm_provider") or self.config["llm_provider"]
        )
        deep_provider = (
            self.config.get("deep_llm_provider") or self.config["llm_provider"]
        )
        quick_backend = (
            self.config.get("quick_backend_url") or self.config["backend_url"]
        )
        deep_backend = (
            self.config.get("deep_backend_url") or self.config["backend_url"]
        )

        self.quick_thinking_llm = self._initialize_llm(
            provider=quick_provider,
            model_name=self.config["quick_think_llm"],
            backend_url=quick_backend,
        )
        self.deep_thinking_llm = self._initialize_llm(
            provider=deep_provider,
            model_name=self.config["deep_think_llm"],
            backend_url=deep_backend,
        )
        self.trade_memory = FinancialSituationMemory("trade_memory", self.config)
        self.trade_reflector = TradeCycleReflector(self.deep_thinking_llm)
        
        self.trader_round_store = TraderRoundMemoryStore(
            self.config.get("trader_round_db_path")
            or os.path.join(self.config["results_dir"], "trader_round_memory.db")
        )
        self.trace_store = TraceStore(
            self.config.get("trace_db_path")
            or os.path.join(self.config["results_dir"], "trace_store.db")
        )
        # 创建工具节点
        self.tool_nodes = self._create_tool_nodes()

        # 初始化调度组件
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.trader_round_store,
            self.conditional_logic,
        )

        self.propagator = Propagator(self.config.get("max_recur_limit", 100))
        # 状态记录
        self.curr_state = None
        self.ticker = None

        # 构建 LangGraph 工作流
        self.graph = self.graph_setup.setup_graph(selected_analysts)
        self.logger = logging.getLogger(__name__)

    def _initialize_llm(self, provider: str, model_name: str, backend_url: Optional[str]):
        provider = provider.lower()
        extra_body: Dict[str, Any] = {"enable_thinking": False}
        if provider in ("openai", "ollama", "openrouter"):
            base = backend_url or "https://api.openai.com/v1"
            if provider == "openrouter" and backend_url is None:
                base = "https://openrouter.ai/api/v1"
            return ChatOpenAI(model=model_name, base_url=base, extra_body=extra_body)
        if provider == "deepseek":
            base = backend_url or "https://api.deepseek.com/v1"
            api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "DEEPSEEK_API_KEY 未设置，无法初始化 DeepSeek LLM。请在 .env 中提供。"
                )
            return ChatOpenAI(
                model=model_name,
                base_url=base,
                api_key=SecretStr(api_key),
                extra_body=extra_body,
            )
        if provider == "google":
            return ChatGoogleGenerativeAI(model=model_name)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """为不同数据源创建工具节点。"""
        return {
            "market": ToolNode(
                [
                    get_crypto_market_batch,
                    get_support_resistance_batch,
                ]
            ),
            "newsflash": ToolNode(
                [
                    get_crypto_newsflash_candidates,
                    get_crypto_newsflash_content,
                ]
            ),
            "longform": ToolNode(
                [
                    get_crypto_longform_candidates,
                    get_crypto_article_content,
                ]
            ),
        }

    def propagate(
        self,
        asset_symbols,
        trade_date: Optional[str] = None,
        available_capital: Optional[float] = None,
        min_leverage: Optional[int] = None,
        max_leverage: Optional[int] = None,
    ):
        """在指定加密货币/交易对和日期上运行整套图。"""

        self.ticker = asset_symbols

        trade_date = trade_date or date.today().isoformat()
        available_capital = 10000.0 if available_capital is None else available_capital
        def _normalize_leverage(value: Any, label: str) -> int:
            if isinstance(value, str):
                raw = value.strip()
                if not raw:
                    raise ValueError(f"{label} 不能为空。")
                if not raw.lstrip("-").isdigit():
                    raise ValueError(f"{label} 必须为整数，收到 {value!r}")
                ivalue = int(raw)
            elif isinstance(value, int):
                ivalue = value
            elif isinstance(value, float):
                if not value.is_integer():
                    raise ValueError(f"{label} 必须为整数杠杆，不支持 {value}")
                ivalue = int(value)
            else:
                raise ValueError(f"{label} 必须为整数，收到 {value!r}")
            if ivalue <= 0:
                raise ValueError(f"{label} 必须大于 0。")
            return ivalue

        config_min_leverage = _normalize_leverage(
            self.config.get("min_leverage", 1), "min_leverage"
        )
        config_max_leverage = _normalize_leverage(
            self.config.get("max_leverage", config_min_leverage), "max_leverage"
        )
        resolved_min = (
            config_min_leverage
            if min_leverage is None
            else _normalize_leverage(min_leverage, "min_leverage")
        )
        resolved_max = (
            config_max_leverage
            if max_leverage is None
            else _normalize_leverage(max_leverage, "max_leverage")
        )
        if resolved_max < resolved_min:
            resolved_min, resolved_max = resolved_max, resolved_min

        # 初始化图状态
        init_agent_state = cast(
            AgentState,
            self.propagator.create_initial_state(asset_symbols, trade_date),
        )
        init_agent_state["available_capital"] = available_capital
        init_agent_state["min_leverage"] = resolved_min
        init_agent_state["max_leverage"] = resolved_max
        args = self.propagator.get_graph_args()

        # 标准模式运行图
        final_state = self.graph.invoke(init_agent_state, **args)
        final_state = self._apply_risk_controls_and_execute(final_state)

        # 保存最终状态，供反思用
        self.curr_state = final_state
        self._record_trader_round_summary(final_state)
        self._persist_trace_snapshot(final_state)

        # 返回完整状态与提炼后的最终信号
        pending = final_state.pop("_pending_trade_info", None)
        if pending:
            for info in pending:
                try:
                    self.record_trade_reflection(info)
                except Exception as exc:  # pragma: no cover
                    self.logger.warning("自动复盘失败: %s", exc)
        return final_state, final_state["final_trade_decision"]

    def _apply_risk_controls_and_execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text)
        adjustments: list[str] = []
        warnings: list[str] = []
        execution_results: list[Dict[str, Any]] = []

        if not plan:
            warnings.append("未能解析交易员计划 JSON，跳过风控与执行。")
            state["final_trade_decision"] = json.dumps(
                {
                    "risk_control": {"warnings": warnings},
                    "execution": execution_results,
                    "trader_plan_raw": plan_text,
                },
                ensure_ascii=False,
            )
            return state

        per_asset = plan.get("per_asset_decisions") or []
        for decision in per_asset:
            if not isinstance(decision, dict):
                continue
            action = str(decision.get("decision") or "").upper()
            if action not in {"LONG", "SHORT"}:
                continue

            execution = decision.get("execution") or {}
            risk = decision.get("risk_management") or {}
            entry_price = self._coerce_float(execution.get("entry_price"))
            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._coerce_float(risk.get("stop_loss_price"))

            if entry_price is None or leverage is None or leverage <= 0:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 entry_price 或 leverage，无法校验 10% 规则。"
                )
                continue
            if stop_loss_price is None or stop_loss_price <= 0:
                warnings.append(
                    f"{decision.get('asset')}: 缺少 stop_loss_price，无法校验 10% 规则。"
                )
                continue

            distance_pct = abs(stop_loss_price - entry_price) / entry_price
            leveraged_loss = distance_pct * leverage
            if leveraged_loss > 0.10:
                allowed_distance = 0.10 / leverage
                if action == "LONG":
                    adjusted_stop = entry_price * (1 - allowed_distance)
                else:
                    adjusted_stop = entry_price * (1 + allowed_distance)
                risk["stop_loss_price"] = round(adjusted_stop, 8)
                decision["risk_management"] = risk
                adjustments.append(
                    f"{decision.get('asset')}: 止损风险 {leveraged_loss:.2%} > 10%，已调整为 {risk['stop_loss_price']}。"
                )

        available_capital = state.get("available_capital") or 0.0
        execution_results = self._execute_plan(plan, available_capital, warnings)

        state["trader_investment_plan"] = json.dumps(plan, ensure_ascii=False)
        state["final_trade_decision"] = json.dumps(
            {
                "risk_control": {
                    "max_loss_per_trade": 0.10,
                    "adjustments": adjustments,
                    "warnings": warnings,
                },
                "execution": execution_results,
                "trader_plan": plan,
            },
            ensure_ascii=False,
        )
        pending = [item["trade_info"] for item in execution_results if item.get("trade_info")]
        if pending:
            state["_pending_trade_info"] = pending
        return state

    def _execute_plan(
        self,
        plan: Dict[str, Any],
        available_capital: float,
        warnings: list[str],
    ) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        per_asset = plan.get("per_asset_decisions") or []
        for decision in per_asset:
            if not isinstance(decision, dict):
                continue
            asset = str(decision.get("asset") or "")
            action = str(decision.get("decision") or "").upper()
            exec_action = action
            trade_info = None
            if action in {"CLOSE_LONG", "CLOSE_SHORT"}:
                exec_action = "CLOSE"
            execution = decision.get("execution") or {}
            risk = decision.get("risk_management") or {}

            leverage = self._coerce_int(execution.get("leverage"))
            stop_loss_price = self._coerce_float(risk.get("stop_loss_price"))
            take_profit_targets = risk.get("take_profit_targets") or []
            take_profit_price = None
            if isinstance(take_profit_targets, list) and take_profit_targets:
                take_profit_price = self._coerce_float(take_profit_targets[0])

            entry_result = ""
            leverage_result = ""
            protection_result = ""

            if exec_action in {"LONG", "SHORT"}:
                if not asset:
                    warnings.append("存在未提供 asset 的交易决策，已跳过执行。")
                    continue
                if leverage is None or leverage <= 0:
                    warnings.append(f"{asset}: 未提供有效 leverage，跳过执行。")
                    continue
                notional = float(available_capital) * float(leverage)
                if notional <= 0:
                    warnings.append(f"{asset}: 可用本金不足，跳过执行。")
                    continue

                leverage_result = set_binance_leverage.invoke(
                    {"symbol": asset, "leverage": leverage}
                )
                side = "BUY" if exec_action == "LONG" else "SELL"
                entry_result = open_binance_position_usdt.invoke(
                    {"symbol": asset, "side": side, "notional_usdt": notional}
                )
                if stop_loss_price or take_profit_price:
                    protection_result = set_binance_take_profit_stop_loss.invoke(
                        {
                            "symbol": asset,
                            "stop_loss_price": stop_loss_price or 0.0,
                            "take_profit_price": take_profit_price or 0.0,
                            "working_type": "MARK_PRICE",
                        }
                    )
            elif exec_action == "CLOSE":
                if not asset:
                    warnings.append("存在未提供 asset 的平仓决策，已跳过执行。")
                    continue
                entry_result = close_binance_position.invoke({"symbol": asset})
                self.trader_round_store.delete_position_state(asset)
                trade_info = self._build_trade_info_from_open_entry(
                    asset, exec_action, None
                )
                if trade_info:
                    trade_info["exit_price"] = self._safe_mark_price(asset)
                    trade_info["exit_time"] = datetime.now(timezone.utc).isoformat()
                    trade_info["notes"] = "active_close"

            if exec_action in {"LONG", "SHORT", "CLOSE"}:
                results.append(
                    {
                        "asset": asset,
                        "action": action,
                        "set_leverage": leverage_result,
                        "entry_order": entry_result,
                        "protection": protection_result,
                        "trade_info": trade_info if exec_action == "CLOSE" else None,
                    }
                )
        return results

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

    def record_trade_reflection(self, trade_info: Dict[str, Any]) -> Optional[str]:
        """
        使用 trade_info（symbol, side, entry/exit 等信息）生成一次交易复盘，并写入 trade_memory。
        期望 trade_info 包含：
            {
                "symbol": str,
                "side": "LONG"/"SHORT",
                "entry_time": str,
                "entry_price": float,
                "exit_time": str,
                "exit_price": float,
                "leverage": int,
                "notional": float,
                "pnl": float,
                "stop_loss": str/float,
                "take_profit": str/float,
                "notes": str,
            }
        """
        if not trade_info:
            return None
        state_snapshot = dict(self.curr_state or {})
        symbol = trade_info.get("symbol") or ""
        if symbol:
            open_entry = self.trader_round_store.get_latest_open_entry(symbol)
            if open_entry:
                state_snapshot["open_position_context"] = (
                    f"{open_entry.get('summary')}\n\n{open_entry.get('situation')}"
                )
        state_snapshot["close_position_context"] = self._build_context_snapshot(
            state_snapshot
        )
        try:
            result = self.trade_reflector.reflect(trade_info, state_snapshot)
        except Exception as exc:  # pragma: no cover
            self.logger.warning("生成交易复盘失败：%s", exc)
            return None
        summary = result.get("summary")
        context = result.get("context")
        if not summary or not context:
            return None
        raw_metadata = {
            "memory_type": "trade",
            "symbol": trade_info.get("symbol"),
            "side": trade_info.get("side"),
            "entry_time": trade_info.get("entry_time"),
            "exit_time": trade_info.get("exit_time"),
            "pnl": trade_info.get("pnl"),
            "leverage": trade_info.get("leverage"),
            "notional": trade_info.get("notional"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Filter out None values to prevent vector store errors (e.g. ChromaDB constraint)
        metadata = {k: v for k, v in raw_metadata.items() if v is not None}
        self.trade_memory.add_situations(
            [(context, summary)],
            metadata_list=[metadata],
        )
        return summary

    def _record_trader_round_summary(self, state: Dict[str, Any]) -> None:
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text) or {}
        summary_data = self._build_trader_round_summary(state, plan)
        if not summary_data:
            return
        self.trader_round_store.add_round(**summary_data)
        self.trader_round_store.prune_recent(keep_n=100)

    def _persist_trace_snapshot(self, state: Dict[str, Any]) -> None:
        plan_text = state.get("trader_investment_plan") or ""
        plan = self._extract_plan_json(plan_text) or {}
        final_decision_text = state.get("final_trade_decision") or ""
        final_decision = self._extract_plan_json(final_decision_text) or {}

        trade_plan_summary = None
        per_asset = plan.get("per_asset_decisions") or []
        if per_asset:
            trade_plan_summary = per_asset[0]

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

        def _stringify(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)

        trace_events = [
            {
                "title": "Market Analyst",
                "status": "completed" if state.get("market_report") else "skipped",
                "detail": _stringify(state.get("market_report")),
            },
            {
                "title": "Newsflash Analyst",
                "status": "completed" if state.get("newsflash_report") else "skipped",
                "detail": _stringify(state.get("newsflash_report")),
            },
            {
                "title": "Longform Cache",
                "status": "completed" if state.get("longform_report") else "skipped",
                "detail": _stringify(state.get("longform_report")),
            },
            {
                "title": "Debate",
                "status": "completed",
                "detail": _stringify(
                    (state.get("investment_debate_state") or {}).get("history")
                ),
            },
            {
                "title": "Trader",
                "status": "completed" if plan else "skipped",
                "detail": _stringify(plan_text),
            },
            {
                "title": "Risk Control",
                "status": "adjusted" if risk_control.get("adjustments") else "completed",
                "detail": _stringify(risk_control),
            },
            {
                "title": "Execution",
                "status": "completed" if execution else "skipped",
                "detail": _stringify(execution),
            },
        ]

        thread = []
        debate = state.get("investment_debate_state") or {}
        if state.get("market_report"):
            thread.append(
                {
                    "role": "Analyst",
                    "name": "Market",
                    "content": _stringify(state.get("market_report")),
                }
            )
        if state.get("newsflash_report"):
            thread.append(
                {
                    "role": "Analyst",
                    "name": "Newsflash",
                    "content": _stringify(state.get("newsflash_report")),
                }
            )
        if state.get("longform_report"):
            thread.append(
                {
                    "role": "Analyst",
                    "name": "Longform",
                    "content": _stringify(state.get("longform_report")),
                }
            )
        if debate.get("history"):
            thread.append(
                {
                    "role": "Debate",
                    "name": "Bull vs Bear",
                    "content": _stringify(debate.get("history")),
                }
            )
        if plan_text:
            thread.append(
                {
                    "role": "Trader",
                    "name": "Trader",
                    "content": _stringify(plan_text),
                }
            )

        trace_payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "assets": state.get("assets_under_analysis") or [],
            "trace_events": trace_events,
            "thread": thread,
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
            self.logger.warning("写入 trace 失败", exc_info=True)

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
        take_profit = None
        targets = risk.get("take_profit_targets") if risk else None
        if isinstance(targets, list) and targets:
            take_profit = targets[0]
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
            situation = self._build_context_snapshot(state)
        else:
            situation = f"{asset or '多资产'} | {decision} | {thesis or '无'}"

        alert_low = None
        alert_high = None
        stop_val = self._coerce_float(stop_loss)
        take_val = self._coerce_float(take_profit)
        if stop_val:
            alert_low = stop_val
        if take_val:
            alert_high = take_val

        return {
            "summary": summary,
            "situation": situation,
            "assets": assets,
            "round_id": round_id,
            "decision": decision,
            "asset": asset,
            "is_open_entry": decision in {"LONG", "SHORT"},
            "alert_low": alert_low,
            "alert_high": alert_high,
            "entry_price": self._coerce_float(entry_price),
            "stop_loss": self._coerce_float(stop_loss),
            "take_profit": self._coerce_float(take_profit),
            "leverage": self._coerce_int(leverage),
        }

    @staticmethod
    def _truncate_text(text: Any, limit: int = 600) -> str:
        raw = text or ""
        if not isinstance(raw, str):
            raw = str(raw)
        raw = raw.strip()
        if len(raw) <= limit:
            return raw
        return raw[:limit].rstrip() + "..."

    def _build_context_snapshot(self, state: Dict[str, Any]) -> str:
        debate = state.get("investment_debate_state") or {}
        market = self._summarize_market_report(state.get("market_report"))
        newsflash = self._summarize_newsflash_report(state.get("newsflash_report"))
        longform = self._summarize_longform_report(state.get("longform_report"))
        snapshot = {
            "market": market,
            "newsflash": newsflash,
            "longform": longform,
        }
        return json.dumps(snapshot, ensure_ascii=False)

    def _build_trade_info_from_open_entry(
        self, symbol: str, action: str, price: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        entry = self.trader_round_store.get_latest_open_entry(symbol)
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
            "exit_time": None,
            "exit_price": exit_price,
            "leverage": entry.get("leverage"),
            "notional": None,
            "pnl": pnl,
            "stop_loss": entry.get("stop_loss"),
            "take_profit": entry.get("take_profit"),
            "notes": "",
        }

    def _safe_mark_price(self, symbol: str) -> Optional[float]:
        try:
            return get_service().get_mark_price(symbol)
        except Exception:
            return None

    def run_analysts_only(self, asset_symbols) -> Dict[str, Any]:
        trade_date = date.today().isoformat()
        state = cast(
            AgentState,
            self.propagator.create_initial_state(asset_symbols, trade_date),
        )
        market_node = create_crypto_market_analyst(self.deep_thinking_llm)
        news_node = create_crypto_newsflash_analyst(self.quick_thinking_llm)
        longform_node = create_longform_cache_loader()

        state = cast(
            AgentState,
            {
                **state,
                **cast(Dict[str, Any], market_node(state)),
                **cast(Dict[str, Any], news_node(state)),
                **cast(Dict[str, Any], longform_node(state)),
            },
        )
        return cast(Dict[str, Any], state)

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
