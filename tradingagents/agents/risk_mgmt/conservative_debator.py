
from tradingagents.agents.utils.dialogue import (
    build_observation_block,
    parse_structured_reply,
    register_team_message,
)


def create_safe_debator(llm):
    def safe_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        trader_decision = state["trader_investment_plan"]

        observation = build_observation_block(state, "保守风险分析师")
        prompt = f"""{observation}

### 角色任务
守住资产安全、降低波动。对激进派观点逐条回应：
- 激进派：{current_risky_response or '尚无发言'}

资料来源：
- 市场技术：{market_research_report}
- Odaily 快讯：{newsflash_report}
- 长线叙事：{longform_report}
- 交易员方案：{trader_decision}
- 历史记录：{history}

构建低风险或降杠杆替代方案，强调风控触发与观望标准，并使用 ``Action Plan / Team Message / Belief Update`` 格式回答。"""

        response = llm.invoke(prompt)

        structured = parse_structured_reply(response.content)
        argument = (
            "Safe Analyst:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        team_messages, next_round = register_team_message(
            state, "Safe Analyst", structured
        )

        return {
            "risk_debate_state": new_risk_debate_state,
            "team_messages": team_messages,
            "interaction_round": next_round,
        }

    return safe_node
