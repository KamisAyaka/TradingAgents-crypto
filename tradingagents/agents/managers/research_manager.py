import time
import json


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""你是研究经理兼辩论主持人，需要对当前这轮牛熊辩论做出评估，并给出最终立场：支持看涨、看跌，或在极充分理由下选择观望。

请先凝练双方的关键要点，强调最具说服力的证据或推理。你的结论（买入/卖出/观望）必须明确且可执行，不能因为双方都有道理就草率地默认观望，而是要根据最有力的论据作出选择。

同时，请为交易员制定一份可执行的投资计划，至少包含：
- 最终建议：基于核心论据给出清晰结论。
- 理由说明：解释为何这些论据支撑你的选择。
- 执行步骤：给出落实建议的具体行动、仓位或风控指引。

务必复盘你在类似情境中的错误，并融入这些经验（如下所示）以改进判断，语言风格保持自然对话即可，无需特殊格式。

过往反思与经验：
\"{past_memory_str}\"

本轮辩论记录：
{history}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
