import functools

from tradingagents.agents.utils.dialogue import parse_structured_reply


def create_trader(llm, trader_memory, invest_judge_memory):
    def trader_node(state, name):
        investment_debate_state = state["investment_debate_state"]
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        debate_history = investment_debate_state.get("history", "")

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        trader_memories = trader_memory.get_memories(curr_situation, n_matches=2)
        judge_memories = invest_judge_memory.get_memories(curr_situation, n_matches=2)

        trader_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in trader_memories) or "暂无交易经验总结。"
        judge_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in judge_memories) or "暂无研究裁决经验。"

        prompt = f"""### 角色任务
        你是一个加密货币的交易员，同时负责(1)凝练牛熊辩论并做出立场,(2)根据市场分析报告输出可执行的仓位/风控计划。
        - 明确挑选买入或卖出证据，说明舍弃对立观点的原因。
        - 在 Action Plan 中写出执行步骤、仓位规模、触发/失效条件。
        - 在 Team Message 中写出与风控团队与经理的交易理由。
        - 在 Belief Update 中总结你对市场的最新认知。

        ### 参考资料
        - 牛熊辩论记录：{debate_history or '暂无辩论记录'}
        - 市场技术报告：{market_research_report}
        - 研究裁决经验：{judge_memory_str}
        - 交易执行经验：{trader_memory_str}

        请严格按 ``Action Plan / Team Message / Belief Update`` 模板作答。"""

        result = llm.invoke(prompt)
        structured = parse_structured_reply(result.content)

        combined_plan = (
            "Trader-Manager:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        updated_invest_state = dict(investment_debate_state)
        updated_invest_state["current_response"] = combined_plan

        return {
            "messages": [result],
            "trader_investment_plan": combined_plan,
            "investment_debate_state": updated_invest_state,
            "sender": name,
            "interaction_round": next_round,
        }

    return functools.partial(trader_node, name="Trader")
