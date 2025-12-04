import time
import json


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["asset_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]
        trader_plan = state["investment_plan"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""你是风控法官兼辩论主持人，需要审视激进、保守、中性三位风险分析师的讨论，为交易员提供最终的买入 / 卖出 / 观望结论。只有在有充分理由时才允许选择观望；请保持判断明确并具可执行性。

决策指引：
1. **萃取要点**：概括每位分析师最有力、最贴合当前情境的论据。
2. **给出依据**：引用辩论中的关键论断或反驳，支撑你的立场。
3. **调整交易方案**：以交易员原计划 **{trader_plan}** 为起点，根据本轮讨论进行必要的修订。
4. **吸取历史教训**：参考以下反思 **{past_memory_str}**，避免重复过往失误，确保 buy/sell/hold 的判断更稳妥。

输出要求：
- 明确且可执行的结论：买入 / 卖出 / 观望。
- 结合辩论要点与历史经验的详细理由。

---

**风险辩论记录：**  
{history}

---

请聚焦可执行性的建议，持续迭代你的风险管理思路。"""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node
