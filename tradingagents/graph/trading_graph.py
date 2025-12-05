# TradingAgents/graph/trading_graph.py

import os
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, cast

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
    get_crypto_market_data,
    get_support_resistance_levels,
    get_crypto_newsflash,
    get_crypto_longform_candidates,
    get_crypto_article_content,
)

from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


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
        self.text_log_enabled = self.config.get("text_log_enabled", False)
        self.text_log_dir = self.config.get("text_log_dir")


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
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

        # 创建工具节点
        self.tool_nodes = self._create_tool_nodes()

        # 初始化调度组件
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1),
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
        )

        self.propagator = Propagator(self.config.get("max_recur_limit", 100))
        self.reflector = Reflector(self.quick_thinking_llm) # type: ignore
        self.signal_processor = SignalProcessor(self.quick_thinking_llm) # type: ignore

        # 状态记录
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # 构建 LangGraph 工作流
        self.graph = self.graph_setup.setup_graph(selected_analysts)

    def _initialize_llm(self, provider: str, model_name: str, backend_url: Optional[str]):
        provider = provider.lower()
        if provider in ("openai", "ollama", "openrouter"):
            base = backend_url or "https://api.openai.com/v1"
            if provider == "openrouter" and backend_url is None:
                base = "https://openrouter.ai/api/v1"
            return ChatOpenAI(model=model_name, base_url=base)
        if provider == "deepseek":
            base = backend_url or "https://api.deepseek.com/v1"
            api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "DEEPSEEK_API_KEY 未设置，无法初始化 DeepSeek LLM。请在 .env 中提供。"
                )
            return ChatOpenAI(model=model_name, base_url=base, api_key=SecretStr(api_key))
        if provider == "google":
            return ChatGoogleGenerativeAI(model=model_name)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """为不同数据源创建工具节点。"""
        return {
            "market": ToolNode(
                [
                    get_crypto_market_data,
                    get_support_resistance_levels,
                ]
            ),
            "newsflash": ToolNode(
                [
                    get_crypto_newsflash,
                ]
            ),
            "longform": ToolNode(
                [
                    get_crypto_longform_candidates,
                    get_crypto_article_content,
                ]
            ),
        }

    def propagate(self, company_name, trade_date):
        """在指定标的和日期上运行整套图。"""

        self.ticker = company_name

        # 初始化图状态
        init_agent_state = cast(
            AgentState,
            self.propagator.create_initial_state(company_name, trade_date),
        )
        args = self.propagator.get_graph_args()

        debug_transcript: List[Dict[str, Any]] = []

        if self.debug:
            # 调试模式：记录所有流式消息，方便定位。
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    continue
                last_message = chunk["messages"][-1]
                debug_transcript.append(self._serialize_message(last_message))
                trace.append(chunk)

            if trace:
                final_state = trace[-1]
            else:
                final_state = self.graph.invoke(init_agent_state, **args)
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(init_agent_state, **args)

        # 保存最终状态，供反思用
        self.curr_state = final_state

        # 写入日志
        log_dir = self._log_state(trade_date, final_state)

        if self.debug and debug_transcript:
            self._write_debug_transcript(trade_date, debug_transcript, log_dir)

        # 返回完整状态与提炼后的最终信号
        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """把最终状态落盘为 JSON，并返回日志目录。"""
        self.log_states_dict[str(trade_date)] = {
            "asset_of_interest": final_state["asset_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "newsflash_report": final_state["newsflash_report"],
            "longform_report": final_state["longform_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "risky_history": final_state["risk_debate_state"]["risky_history"],
                "safe_history": final_state["risk_debate_state"]["safe_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # 持久化到文件
        directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4, ensure_ascii=False)

        self._write_text_log(trade_date, final_state, directory)
        return directory

    def reflect_and_remember(self, returns_losses):
        """根据收益/亏损对各角色进行反思，并写入记忆。"""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def _write_text_log(self, trade_date, final_state, base_dir: Path):
        """如已启用文本日志，生成一份 Markdown 纪要。"""
        if not self.text_log_enabled:
            return

        log_dir = Path(self.text_log_dir) if self.text_log_dir else base_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        file_path = log_dir / f"analysis_transcript_{trade_date}_{timestamp}.md"

        market_report = final_state.get("market_report") or ""
        newsflash_report = final_state.get("newsflash_report") or ""
        longform_report = final_state.get("longform_report") or ""
        invest_state = final_state.get("investment_debate_state", {})
        risk_state = final_state.get("risk_debate_state", {})

        sections = [
            f"# TradingAgents 分析记录 - {trade_date}",
            f"- 资产：{final_state.get('asset_of_interest', '')}",
            f"- 最终交易决定：{final_state.get('final_trade_decision', '')}",
            f"- 交易计划：{final_state.get('trader_investment_plan', '')}",
        ]

        if market_report:
            sections.append("## 市场技术分析\n" + market_report)
        if newsflash_report:
            sections.append("## 快讯分析\n" + newsflash_report)
        if longform_report:
            sections.append("## 长文研究（缓存）\n" + longform_report)

        if invest_state.get("history"):
            sections.append("## 看涨/看跌辩论记录\n" + invest_state["history"])
        if final_state.get("trader_investment_plan"):
            sections.append("## 交易员计划\n" + final_state["trader_investment_plan"])
        if risk_state.get("history"):
            sections.append("## 风险讨论记录\n" + risk_state["history"])
        if final_state.get("final_trade_decision"):
            sections.append("## 最终裁决\n" + final_state["final_trade_decision"])

        file_path.write_text("\n\n".join(sections), encoding="utf-8")

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

        entry: Dict[str, Any] = {
            "message_type": getattr(message, "type", message.__class__.__name__),
            "name": getattr(message, "name", None),
            "content": _safe_content(message.content),
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

    def _write_debug_transcript(
        self,
        trade_date: str,
        transcript: List[Dict[str, Any]],
        base_dir: Path,
    ) -> None:
        """将调试用的流式 transcript 写入 JSON，以便复盘。"""

        debug_dir = self.config.get("debug_log_dir")
        log_dir = Path(debug_dir) if debug_dir else base_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%H%M%S")
        file_path = log_dir / f"debug_transcript_{trade_date}_{timestamp}.json"
        file_path.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def process_signal(self, full_signal):
        """调用 SignalProcessor 抽取 BUY/SELL/HOLD。"""
        return self.signal_processor.process_signal(full_signal)
