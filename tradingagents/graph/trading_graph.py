# TradingAgents/graph/trading_graph.py

import os
import json
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
        self.suppress_console_output = self.config.get("suppress_console_output", False)


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
        model_kwargs: Dict[str, Any] = {"extra_body": {"enable_thinking": False}}
        if provider in ("openai", "ollama", "openrouter"):
            base = backend_url or "https://api.openai.com/v1"
            if provider == "openrouter" and backend_url is None:
                base = "https://openrouter.ai/api/v1"
            return ChatOpenAI(model=model_name, base_url=base, model_kwargs=model_kwargs)
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
                model_kwargs=model_kwargs,
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

        # 返回完整状态与提炼后的最终信号
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
            exec_action = action
            if action in {"CLOSE_LONG", "CLOSE_SHORT"}:
                exec_action = "CLOSE"
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

            if exec_action in {"LONG", "SHORT", "CLOSE"}:
                results.append(
                    {
                        "asset": asset,
                        "action": action,
                        "set_leverage": leverage_result,
                        "entry_order": entry_result,
                        "protection": protection_result,
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
        try:
            result = self.trade_reflector.reflect(trade_info, self.curr_state or {})
        except Exception as exc:  # pragma: no cover
            self.logger.warning("生成交易复盘失败：%s", exc)
            return None
        summary = result.get("summary")
        context = result.get("context")
        if not summary or not context:
            return None
        metadata = {
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
        situation = f"{asset or '多资产'} | {decision} | {thesis or '无'}"

        return {
            "summary": summary,
            "situation": situation,
            "assets": assets,
            "round_id": round_id,
            "decision": decision,
            "asset": asset,
            "is_open_entry": decision in {"LONG", "SHORT"},
        }

    def _serialize_message(self, message):
        """将 LangChain 消息尽力序列化为 JSON 结构。"""

        def _safe_content(content):
            if isinstance(content, (str, int, float, type(None))):
                return content
            try:
                json.dumps(content)
                return content
            except TypeError:
                return str(content)

        # 处理元组形式的消息（如初始 human 消息）
        if isinstance(message, tuple) and len(message) == 2:
            entry: Dict[str, Any] = {
                "message_type": message[0],  # "human" 或其他类型
                "name": None,
                "content": _safe_content(message[1]),
            }
            return entry
            
        # 处理字典形式的消息
        if isinstance(message, dict):
            entry: Dict[str, Any] = {
                "message_type": message.get("type", "unknown"),
                "name": message.get("name", None),
                "content": _safe_content(message.get("content", "")),
            }
            
            tool_calls = message.get("tool_calls", None)
            if tool_calls:
                entry["tool_calls"] = tool_calls
                
            additional = message.get("additional_kwargs", None)
            if additional:
                entry["additional_kwargs"] = additional
                
            metadata = message.get("response_metadata", None)
            if metadata:
                entry["response_metadata"] = metadata
                
            return entry

        # 处理 LangChain 消息对象
        entry: Dict[str, Any] = {
            "message_type": getattr(message, "type", message.__class__.__name__),
            "name": getattr(message, "name", None),
            "content": _safe_content(getattr(message, "content", str(message))),
        }

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            serialized_calls = []
            for call in tool_calls:
                if isinstance(call, dict):
                    serialized_calls.append(call)
                else:
                    serialized_calls.append(
                        {
                            "id": getattr(call, "id", None),
                            "name": getattr(call, "name", None),
                            "args": _safe_content(
                                getattr(call, "args", getattr(call, "arguments", None))
                            ),
                        }
                    )
            entry["tool_calls"] = serialized_calls

        additional = getattr(message, "additional_kwargs", None)
        if additional:
            entry["additional_kwargs"] = additional

        metadata = getattr(message, "response_metadata", None)
        if metadata:
            entry["response_metadata"] = metadata

        return entry
