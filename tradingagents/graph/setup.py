# TradingAgents/graph/setup.py

from typing import Dict, Any
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

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
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm: Any = quick_thinking_llm
        self.deep_thinking_llm: Any = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic

    def setup_graph(
        self, selected_analysts=["market", "newsflash", "longform"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Crypto market/technical analyst
                - "newsflash": Odaily short-form news analyst
                - "longform": Cached Odaily long-form research loader
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
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
                self.quick_thinking_llm
            )
            delete_nodes["newsflash"] = create_msg_delete()
            tool_nodes["newsflash"] = self.tool_nodes["newsflash"]

        if "longform" in selected_analysts:
            analyst_nodes["longform"] = create_longform_cache_loader()
            delete_nodes["longform"] = create_msg_delete()

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            if analyst_type in tool_nodes:
                workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define analyst execution order
        parallel_analysts = [
            analyst
            for analyst in ["market", "newsflash"]
            if analyst in selected_analysts
        ]
        remaining_analysts = [
            analyst for analyst in selected_analysts if analyst not in parallel_analysts
        ]

        # Helper to wire tool-driven analysts
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

        # Parallel stage wiring
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

        # Sequential analysts after the parallel stage
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

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()
