from langchain_core.messages import AIMessage
import time
import json


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

        prompt = f"""你是一名专注加密货币领域的看跌分析师，需要陈述反对投资该代币/项目的观点。你的目标是提出一套逻辑严密的论点，强调链上与链下的风险、挑战和负面信号。善用提供的研究与数据，凸显潜在缺陷，并有效反驳看涨论点。

重点关注：

- 风险与挑战：指出市场饱和、经济逆风、合规压力等可能阻碍代币表现的因素。
- 负面指标：结合链上数据、市场趋势、资金流动、社区情绪或近期负面新闻，为你的立场提供证据。
- 回应看涨观点：以具体数据和严谨推理批判看涨论点，揭示其中的漏洞或过度乐观假设。
- 互动性：以对话式口吻呈现观点，直接回应看涨分析师的论据，进行辩论，而不是简单罗列事实。

可用资源：

市场技术分析：{market_research_report}
Odaily 快讯：{newsflash_report}
长篇叙事报告：{longform_report}
辩论对话记录：{history}
最近一次看涨观点：{current_response}
相似情境的反思与经验：{past_memory_str}
使用以上信息，输出具有说服力的看跌论点，反驳看涨方的主张，并展开富有动态性的辩论，凸显投资该加密货币的风险与弱点。同时务必吸取过去的经验教训，回应相关反思。
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
