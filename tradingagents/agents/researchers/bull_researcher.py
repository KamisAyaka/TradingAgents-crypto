from tradingagents.agents.utils.dialogue import parse_structured_reply


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        # 兼容上游状态缺失的情况，必要时重新初始化辩论状态
        raw_state = state.get("investment_debate_state") or {}
        if not isinstance(raw_state, dict):
            raw_state = {}
        investment_debate_state = {
            "history": raw_state.get("history", ""),
            "bull_history": raw_state.get("bull_history", ""),
            "bear_history": raw_state.get("bear_history", ""),
            "current_response": raw_state.get("current_response", ""),
            "count": raw_state.get("count", 0),
        }
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

        prompt = f"""### 角色任务
        你是一名专注加密货币领域的看涨分析师，负责为投资代币提供支持。构建有力且有据可依的论证，善用提供的研究与数据，回应疑虑并有效反驳看跌观点。

        必须覆盖：
        - 成长潜力：强调市场机会、需求、生态扩张与可扩展性。
        - 正向指标：引用链上数据、资金流入、行业趋势及近期利好消息。
        - 针对性反驳：逐条回应最近一次看跌观点：{current_response}
        - 互动语气：直接点名并回应看跌分析师，保持辩论式表达。

        ### 研究全文（供引用）
        - 市场技术分析：{market_research_report}
        - Odaily 快讯：{newsflash_report}
        - 长篇叙事：{longform_report}
        - 辩论完整记录：{history}
        - 经验教训：{past_memory_str}

        请严格用 ``Action Plan / Team Message / Belief Update`` 格式回复。"""

        response = llm.invoke(prompt)

        structured = parse_structured_reply(response.content)
        argument = (
            "Bull Analyst:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        return {
            "investment_debate_state": new_investment_debate_state,
            "interaction_round": next_round,
        }

    return bull_node
