from tradingagents.agents.utils.dialogue import (
    build_observation_block,
    parse_structured_reply,
    register_team_message,
)


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        trader_decision = state["trader_investment_plan"]

        observation = build_observation_block(state, "激进风险分析师")
        prompt = f"""{observation}

### 角色任务
强调高收益策略的潜在价值，哪怕意味着更高波动。请直接回应保守分析师的最新观点：
- 保守派：{current_safe_response or '尚无发言'}

引用以下资料支撑立场：
- 市场技术报告：{market_research_report}
- Odaily 快讯：{newsflash_report}
- 长线叙事：{longform_report}
- 交易员当前方案：{trader_decision}
- 讨论历史：{history}

突出进取策略如何获取不对称收益，并严格按 ``Action Plan / Team Message / Belief Update`` 回复。"""

        response = llm.invoke(prompt)

        structured = parse_structured_reply(response.content)
        argument = (
            "Risky Analyst:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "count": risk_debate_state["count"] + 1,
        }

        team_messages, next_round = register_team_message(
            state, "Risky Analyst", structured
        )

        return {
            "risk_debate_state": new_risk_debate_state,
            "team_messages": team_messages,
            "interaction_round": next_round,
        }

    return risky_node
