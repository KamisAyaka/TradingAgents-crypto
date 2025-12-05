from langchain_core.messages import AIMessage
import time
import json

from tradingagents.agents.utils.dialogue import (
    build_observation_block,
    parse_structured_reply,
    register_team_message,
)


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        observation = build_observation_block(state, "看跌分析师")
        prompt = f"""{observation}

### 角色任务
你是一名专注加密货币领域的看跌分析师，需要陈述反对投资该代币/项目的论点。聚焦链上与链下风险、挑战和负面信号，逐条反驳看涨分析师：{current_response}

必须输出：
- **风险/挑战**：指出宏观、合规、流动性或结构性问题。
- **负面指标**：引用链上数据、资金流、市场趋势或社区情绪。
- **互动式反驳**：逐条拆解看涨论证，保持辩论语气。

### 研究全文
- 市场技术分析：{market_research_report}
- Odaily 快讯：{newsflash_report}
- 长篇叙事：{longform_report}
- 辩论完整记录：{history}
- 经验反思：{past_memory_str}

请严格依照 ``Action Plan / Team Message / Belief Update`` 模板答复。"""

        response = llm.invoke(prompt)

        structured = parse_structured_reply(response.content)
        argument = (
            "Bear Analyst:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        team_messages, next_round = register_team_message(
            state, "Bear Analyst", structured
        )

        return {
            "investment_debate_state": new_investment_debate_state,
            "team_messages": team_messages,
            "interaction_round": next_round,
        }

    return bear_node
