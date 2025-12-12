# TradingAgents/graph/setup.py

from typing import Dict, Any
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """负责搭建与编译整套智能体工作流图。"""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        general_manager_memory,
        conditional_logic: ConditionalLogic,
    ):
        """注入所有依赖的 LLM、工具节点、记忆与条件逻辑。"""
        self.quick_thinking_llm: Any = quick_thinking_llm
        self.deep_thinking_llm: Any = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.general_manager_memory = general_manager_memory
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["market", "newsflash", "longform"]
    ):
        """根据配置创建图结构。

        Args:
            selected_analysts (list): 需要启用的分析师节点：
                - "market": 加密市场/技术分析师
                - "newsflash": Odaily 快讯分析师
                - "longform": Odaily 长文研究缓存加载器
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # 初始化分析师节点与工具
        analyst_nodes: Dict[str, Any] = {}
        delete_nodes: Dict[str, Any] = {}
        tool_nodes: Dict[str, ToolNode] = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_crypto_market_analyst(
                self.deep_thinking_llm
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "newsflash" in selected_analysts:
            analyst_nodes["newsflash"] = create_crypto_newsflash_analyst(
                self.deep_thinking_llm
            )
            delete_nodes["newsflash"] = create_msg_delete()
            tool_nodes["newsflash"] = self.tool_nodes["newsflash"]

        if "longform" in selected_analysts:
            analyst_nodes["longform"] = create_longform_cache_loader()
            delete_nodes["longform"] = create_msg_delete()

        # 创建研究员与交易节点
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        trader_node = create_trader(
            self.quick_thinking_llm, self.trader_memory, self.invest_judge_memory
        )

        # 创建风险讨论节点
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )
        manager_node = create_manager(
            self.deep_thinking_llm, self.general_manager_memory
        )

        # 创建状态图
        workflow = StateGraph(AgentState)

        # 将分析师节点加入图并配置工具/清理节点
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            if analyst_type in tool_nodes:
                workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # 添加研究员、交易员、风险团队与法官节点
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risk Manager", risk_manager_node)
        workflow.add_node("Manager", manager_node)

        # 拆分并行/串行的分析师组合，用于 wiring
        parallel_analysts = [
            analyst
            for analyst in ["market", "newsflash"]
            if analyst in selected_analysts
        ]
        remaining_analysts = [
            analyst for analyst in selected_analysts if analyst not in parallel_analysts
        ]

        # 为需要工具调用的分析师创建回路
        def _wire_tool_driven(analyst_type: str):
            cap_name = analyst_type.capitalize()
            current_analyst = f"{cap_name} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {cap_name}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)
            return current_clear

        # 并行分析师的布线：需要等所有并行节点完成才放行
        if parallel_analysts:
            gate_node_name = "Parallel Analyst Gate"
            wait_node_name = "Parallel Analyst Wait"
            workflow.add_node(gate_node_name, lambda state: {})
            workflow.add_node(wait_node_name, lambda state: {})

            next_after_parallel = (
                f"{remaining_analysts[0].capitalize()} Analyst"
                if remaining_analysts
                else "Bull Researcher"
            )

            def _should_release_parallel(state: AgentState):
                if "market" in parallel_analysts and not state["market_report"]:
                    return "wait"
                if "newsflash" in parallel_analysts and not state["newsflash_report"]:
                    return "wait"
                return "proceed"

            for analyst_type in parallel_analysts:
                current_clear = _wire_tool_driven(analyst_type)
                workflow.add_edge(START, f"{analyst_type.capitalize()} Analyst")
                workflow.add_edge(current_clear, gate_node_name)

            workflow.add_conditional_edges(
                gate_node_name,
                _should_release_parallel,
                {
                    "proceed": next_after_parallel,
                    "wait": wait_node_name,
                },
            )
        elif remaining_analysts:
            workflow.add_edge(START, f"{remaining_analysts[0].capitalize()} Analyst")
        else:
            workflow.add_edge(START, "Bull Researcher")

        # 并行段之后的串行分析师
        for idx, analyst_type in enumerate(remaining_analysts):
            cap_name = analyst_type.capitalize()
            current_node = f"{cap_name} Analyst"
            next_node = (
                f"{remaining_analysts[idx+1].capitalize()} Analyst"
                if idx < len(remaining_analysts) - 1
                else "Bull Researcher"
            )

            if analyst_type in ["market", "newsflash"]:
                current_clear = _wire_tool_driven(analyst_type)
                workflow.add_edge(current_clear, next_node)
            elif analyst_type == "longform":
                workflow.add_edge(current_node, f"Msg Clear {cap_name}")
                workflow.add_edge(f"Msg Clear {cap_name}", next_node)
            else:
                workflow.add_edge(current_node, next_node)

        # 牛熊辩论与风险讨论的跳转逻辑
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Trader": "Trader",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Trader": "Trader",
            },
        )
        workflow.add_edge("Trader", "Risk Manager")
        workflow.add_edge("Risk Manager", "Manager")
        workflow.add_edge("Manager", END)

        # Compile and return
        return workflow.compile()
