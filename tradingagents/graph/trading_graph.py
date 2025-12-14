# TradingAgents/graph/trading_graph.py

import os
import json
from datetime import date
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
from .reflection import Reflector


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
        
        # 初始化各角色记忆
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)
        self.general_manager_memory = FinancialSituationMemory("general_manager_memory", self.config)

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
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.risk_manager_memory,
            self.general_manager_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator(self.config.get("max_recur_limit", 100))
        self.reflector = Reflector(self.quick_thinking_llm) # type: ignore

        # 状态记录
        self.curr_state = None
        self.ticker = None

        # 构建 LangGraph 工作流
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _initialize_llm(self, provider: str, model_name: str, backend_url: Optional[str]):
        provider = provider.lower()
        shared_kwargs = {"extra_body": {"enable_thinking": False}}
        if provider in ("openai", "ollama", "openrouter"):
            base = backend_url or "https://api.openai.com/v1"
            if provider == "openrouter" and backend_url is None:
                base = "https://openrouter.ai/api/v1"
            return ChatOpenAI(model=model_name, base_url=base, **shared_kwargs)
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
                **shared_kwargs,
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
        min_leverage: Optional[float] = None,
        max_leverage: Optional[float] = None,
    ):
        """在指定加密货币/交易对和日期上运行整套图。"""

        self.ticker = asset_symbols

        trade_date = trade_date or date.today().isoformat()
        available_capital = 10000.0 if available_capital is None else available_capital
        config_min_leverage = self.config.get("min_leverage", 1.0)
        config_max_leverage = self.config.get("max_leverage", config_min_leverage)
        min_leverage = config_min_leverage if min_leverage is None else min_leverage
        max_leverage = config_max_leverage if max_leverage is None else max_leverage
        if max_leverage is not None and min_leverage is not None and max_leverage < min_leverage:
            min_leverage, max_leverage = max_leverage, min_leverage

        # 初始化图状态
        init_agent_state = cast(
            AgentState,
            self.propagator.create_initial_state(asset_symbols, trade_date),
        )
        init_agent_state["available_capital"] = available_capital
        init_agent_state["min_leverage"] = float(min_leverage)
        init_agent_state["max_leverage"] = float(max_leverage)
        args = self.propagator.get_graph_args()

        # 标准模式运行图
        final_state = self.graph.invoke(init_agent_state, **args)

        # 保存最终状态，供反思用
        self.curr_state = final_state

        # 返回完整状态与提炼后的最终信号
        return final_state, final_state["final_trade_decision"]

    def reflect_and_remember(self, returns_losses):
        """根据收益/亏损对各角色进行反思，并写入记忆。"""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )
        self.reflector.reflect_manager(
            self.curr_state, returns_losses, self.general_manager_memory
        )

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
