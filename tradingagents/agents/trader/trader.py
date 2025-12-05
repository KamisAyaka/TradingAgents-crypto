import functools

from tradingagents.agents.utils.dialogue import (
    build_observation_block,
    parse_structured_reply,
    register_team_message,
)


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

        observation = build_observation_block(state, "研究裁决兼交易执行代理")
        prompt = f"""{observation}

### 角色任务
你同时负责（1）凝练牛熊辩论并做出立场，（2）输出可执行的仓位/风控计划。
- 明确挑选买入或卖出证据，说明舍弃对立观点的原因。
- 在 Action Plan 中写出执行步骤、仓位规模、触发/失效条件。
- 在 Belief Update 中总结你对市场的最新认知。
- 句末必须包含 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`。

### 参考资料
- 牛熊辩论记录：{debate_history or '暂无辩论记录'}
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

        team_messages, next_round = register_team_message(
            state, "Trader", structured
        )

        updated_invest_state = dict(investment_debate_state)
        updated_invest_state["current_response"] = combined_plan

        return {
            "messages": [result],
            "trader_investment_plan": combined_plan,
            "investment_debate_state": updated_invest_state,
            "sender": name,
            "team_messages": team_messages,
            "interaction_round": next_round,
        }

    return functools.partial(trader_node, name="Trader")
