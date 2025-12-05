from tradingagents.agents.utils.dialogue import (
    build_observation_block,
    parse_structured_reply,
    register_team_message,
)


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        observation = build_observation_block(state, "风险法官")
        prompt = f"""{observation}

### 角色任务
审视激进与保守两位风险分析师的讨论，为交易员提供最终的买入 / 卖出 / 观望结论；只有在证据不足时才可观望。

### 决策指引
1. 萃取两位分析师最有力的论据，并指出盲点。
2. 以交易员原方案 **{trader_plan}** 为基线，对风险/仓位做必要修订。
3. 在 Belief Update 中说明如何吸收以下历史反思：{past_memory_str}
4. 输出必须以 ``Action Plan / Team Message / Belief Update`` 模板呈现。

### 讨论记录
{history}

请给出明确的 buy/sell/hold 结论及执行细节。"""

        response = llm.invoke(prompt)

        structured = parse_structured_reply(response.content)
        judge_text = (
            "Risk Judge:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        new_risk_debate_state = {
            "judge_decision": judge_text,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "count": risk_debate_state["count"],
        }

        team_messages, next_round = register_team_message(
            state, "Risk Judge", structured
        )

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": judge_text,
            "team_messages": team_messages,
            "interaction_round": next_round,
        }

    return risk_manager_node
