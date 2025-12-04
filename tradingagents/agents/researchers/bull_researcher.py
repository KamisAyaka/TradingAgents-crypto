from langchain_core.messages import AIMessage
import time
import json


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""你是一名专注加密货币领域的看涨分析师，负责为投资该代币提供支持。你的任务是构建一套有力且有据可依的论证，竞争优势与正面市场信号。善用提供的研究与数据，回应疑虑并有效反驳看跌观点。

重点关注：
- 成长潜力：强调协议的市场机会、代币需求、生态扩张与可扩展性。
- 正向指标：引用链上数据、资金流入、行业趋势及近期利好消息等证据。
- 回应看跌观点：用具体数据与严谨推理分析看跌论点，充分回应疑虑，说明看涨观点为何更有说服力。
- 互动性：以对话式口吻呈现论点，直接回应看跌分析师的观点，进行有效辩论，而非仅罗列数据。

可用资源：
市场技术分析：{market_research_report}
Odaily 快讯：{newsflash_report}
长篇叙事报告：{longform_report}
辩论对话记录：{history}
最近一次看跌观点：{current_response}
相似情境的反思与经验：{past_memory_str}
使用以上信息，输出具有说服力的看涨论点，反驳看跌方的顾虑，并展开富有动态性的辩论，彰显看涨立场的优势。同时务必吸取过去的经验教训，回应相关反思。
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
