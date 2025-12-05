# TradingAgents/graph/conditional_logic.py

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """负责图中各节点的条件判断与跳转。"""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """根据配置初始化最大辩论轮数与风险讨论轮数。"""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """判断市场分析节点是否需要继续（即是否还有工具调用）。"""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_newsflash(self, state: AgentState):
        """判断快讯分析节点是否需要继续。"""
        messages = state["messages"]
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools_newsflash"
        return "Msg Clear Newsflash"

    def should_continue_longform(self, state: AgentState):
        """判断长文分析是否继续。由于缓存读取不会触发工具调用，直接清理消息即可。"""
        return "Msg Clear Longform"

    def should_continue_debate(self, state: AgentState) -> str:
        """决定牛熊辩论是继续还是交给交易员。"""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 达到设定轮次后交给交易员裁决
            return "Trader"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """判断风险讨论是否继续，或转交风险法官。"""
        if (
            state["risk_debate_state"]["count"] >= 2 * self.max_risk_discuss_rounds
        ):
            return "Risk Judge"
        last = state["risk_debate_state"].get("latest_speaker", "")
        if last.startswith("Risky"):
            return "Safe Analyst"
        return "Risky Analyst"
