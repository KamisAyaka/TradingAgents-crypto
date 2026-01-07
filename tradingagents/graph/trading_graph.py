
# TradingAgents/graph/trading_graph.py

import os
import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, Optional, cast

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.agent_states import (
    AgentState,
)
from tradingagents.agents.utils.memory import FinancialSituationMemory
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

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .execution_manager import ExecutionManager
from .persistence_manager import PersistenceManager


class _FallbackChatModel(BaseChatModel):
    """
    带有回退机制的聊天模型包装器 (Fallback Wrapper)。
    
    设计目的：
    主要用于处理 DeepSeek API 不稳定或限流的情况。当 Primary Model (DeepSeek) 
    调用失败时，自动切换到 Fallback Model (通常是官方 DeepSeek 或其他备用源)，
    确保交易系统的高可用性 (High Availability)。
    """
    def __init__(
        self,
        primary: BaseChatModel,
        fallback: BaseChatModel,
        fallback_base: Optional[str],
    ) -> None:
        super().__init__()
        self._primary = primary
        self._fallback = fallback
        self._fallback_base = fallback_base

    def _format_error(self, error: Exception) -> str:
        base = self._fallback_base or "<unknown>"
        return f"DeepSeek primary failed: {error}. Falling back to {base}."

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            return self._primary._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning(self._format_error(exc))
            return self._fallback._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            return await self._primary._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning(self._format_error(exc))
            return await self._fallback._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    def bind_tools(self, tools, **kwargs):
        import openai
        primary_bound = self._primary.bind_tools(tools, **kwargs)
        fallback_bound = self._fallback.bind_tools(tools, **kwargs)
        # Explicitly handle RateLimitError to trigger fallback
        return primary_bound.with_fallbacks(
            [fallback_bound], 
            exceptions_to_handle=(openai.RateLimitError, Exception)
        )

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"


class TradingAgentsGraph:
    """
    交易多智能体图 (TradingAgentsGraph) - Lean Version
    
    这是整个系统的主控制器，负责编排 LangGraph 工作流。
    
    主要组件：
    1. LLM 初始化: 支持 DeepSeek (Primary) + OpenAI/Others (Fallback) 的双模型架构。
    2. Tool Nodes: 封装市场数据、新闻、长文分析等工具。
    3. Managers:
       - ExecutionManager: 负责通过 Binance API 执行交易。
       - PersistenceManager: 负责保存 Trace 和 Memories。
    4. Graph Setup: 定义 Agent 之间的流转逻辑 (State Graph)。
    """

    def __init__(
        self,
        selected_analysts=["market", "newsflash", "longform"],
        debug=False,
        config: Optional[Dict[str, Any]] = None,
    ):
        """初始化整个图及各组件。"""
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
        self.trade_reflector = TradeCycleReflector(self._initialize_deepseek_official_llm())
        
        self.trader_round_store = TraderRoundMemoryStore(
            self.config.get("trader_round_db_path")
            or os.path.join(self.config["results_dir"], "trader_round_memory.db")
        )
        self.trace_store = TraceStore(
            self.config.get("trace_db_path")
            or os.path.join(self.config["results_dir"], "trace_store.db")
        )
        # Managers
        self.execution_manager = ExecutionManager(self.trader_round_store)
        self.persistence_manager = PersistenceManager(
            self.trader_round_store, self.trace_store
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
            return self._initialize_deepseek_llm(model_name, backend_url, extra_body)
        if provider == "google":
            return ChatGoogleGenerativeAI(model=model_name)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _initialize_deepseek_llm(
        self, model_name: str, backend_url: Optional[str], extra_body: Dict[str, Any]
    ):
        primary_key = os.getenv("OPENAI_API_KEY")
        if not primary_key:
            raise ValueError(
                "OPENAI_API_KEY 未设置，无法初始化 ModelScope DeepSeek。请在 .env 中提供。"
            )
        base = backend_url or "https://api.deepseek.com/v1"
        fallback_base = self.config.get("deep_fallback_backend_url")
        fallback_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_FALLBACK_API_KEY")
        if not fallback_key:
            fallback_key = primary_key

        primary = ChatOpenAI(
            model=model_name,
            base_url=base,
            api_key=SecretStr(primary_key),
            extra_body=extra_body,
        )
        # 如果使用官方 URL 作为 fallback，强制使用标准的 deepseek-chat 模型名
        # 因为 ModelScope 的模型名（如 deepseek-ai/DeepSeek-V3.2）在官方 API 会报 400
        fallback_url = fallback_base or "https://api.deepseek.com/v1"
        fallback_model = model_name
        if "api.deepseek.com" in fallback_url and "/" in model_name:
            fallback_model = "deepseek-chat"

        fallback = ChatOpenAI(
            model=fallback_model,
            base_url=fallback_url,
            api_key=SecretStr(fallback_key),
            extra_body=extra_body,
        )
        return _FallbackChatModel(primary, fallback, fallback_base)

    def _initialize_deepseek_official_llm(self):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 未设置，无法初始化复盘模型。")
        return ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=SecretStr(api_key),
            extra_body={"enable_thinking": False},
        )

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
        """
        执行核心交易流程 (Propagate)。
        
        这是外部调用 Agent 系统的主要入口。
        
        参数:
            asset_symbols: 要交易的资产列表 (e.g. ["BTCUSDT", "ETHUSDT"])。
            trade_date: 模拟/回测日期 (默认今天)。
            available_capital: 可用本金 (默认 10000)。
            min_leverage / max_leverage: 杠杆范围限制。
            
        流程:
            1. 规范化配置参数 (Capital, Leverage)。
            2. 初始化 LangGraph 状态 (State Initialization)。
            3. 运行 Agent Graph (`self.graph.invoke`) -> 产出分析报告和计划。
            4. ExecutionManager 执行风控与下单 (`apply_risk_controls_and_execute`)。
            5. PersistenceManager 保存状态与 Trace (`persist_trace_snapshot`)。
            6. 如果有平仓操作，触发自动复盘 (`record_trade_reflection`)。
            
        返回:
            final_state, final_trade_decision
        """

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

        # 运行完整的 Agent 图，产出分析报告和交易计划。
        final_state = self.graph.invoke(init_agent_state, **args)
        
        # 基于计划执行风控校验，并下发交易/保护指令。
        final_state = self.execution_manager.apply_risk_controls_and_execute(final_state)

        # 保存最终状态，供反思用
        self.curr_state = final_state
        
        # 写入摘要与 Trace，供前端展示与历史追踪。
        self.persistence_manager.record_trader_round_summary(final_state)
        self.persistence_manager.persist_trace_snapshot(final_state)

        # 如有平仓记录，触发复盘并写入记忆库。
        pending = final_state.pop("_pending_trade_info", None)
        if pending:
            for info in pending:
                try:
                    self.record_trade_reflection(info)
                except Exception as exc:  # pragma: no cover
                    self.logger.warning("自动复盘失败: %s", exc)
        return final_state, final_state["final_trade_decision"]

    def record_trade_reflection(self, trade_info: Dict[str, Any]) -> Optional[str]:
        """
        执行交易复盘 (Trade Reflection)。
        
        触发时机：当 ExecutionManager 检测到平仓 (Close) 行为时。
        
        功能：
        1. 检索该笔交易的开仓上下文 (Open Context) - 当时为什么开仓？
        2. 检索当前的平仓上下文 (Close Context) - 现在为什么平仓？
        3. 调用 `trade_reflector` (LLM) 进行深度自我反思。
        4. 将反思结果 (Summary) 存入 `trade_memory` (Vector Store)，供未来决策参考。
        """
        if not trade_info:
            return None
        state_snapshot = dict(self.curr_state or {})
        symbol = trade_info.get("symbol") or ""
        if symbol:
            open_entry = self.trader_round_store.get_first_open_entry_since_close(symbol)
            if open_entry:
                state_snapshot["open_position_context"] = (
                    f"{open_entry.get('summary')}\n\n{open_entry.get('situation')}"
                )
        
        # 构建平仓时的上下文快照，供复盘模型引用。
        state_snapshot["close_position_context"] = self.persistence_manager.build_context_snapshot(
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

    def run_analysts_only(self, asset_symbols) -> Dict[str, Any]:
        """仅运行分析师节点（用于测试或缓存刷新）"""
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
