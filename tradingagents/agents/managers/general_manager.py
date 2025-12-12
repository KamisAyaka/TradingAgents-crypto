from tradingagents.agents.utils.dialogue import parse_structured_reply


def create_manager(llm, memory):
    def manager_node(state) -> dict:
        risk_state = state.get("risk_review_state") or {}
        if not isinstance(risk_state, dict):
            risk_state = {}

        risk_history = risk_state.get("history", "")
        analyst_report = risk_state.get("analyst_report", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for rec in past_memories:
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""### 角色定位
你是该团队的总经理（最终裁决者），需要在交易员方案 **{trader_plan or "尚未给出"}** 与风险经理最新报告基础上，做出 BUY / SELL / HOLD 决策。

### 参考资料
- 市场/技术：{market_research_report or "暂无"}
- Odaily 快讯：{newsflash_report or "暂无"}
- 长文本研究：{longform_report or "暂无"}
- 风险经理最新报告：{analyst_report or "暂无"}
- 历史风险记录：{risk_history or "暂无"}
- 总经理经验库：{past_memory_str or "暂无"}

### 输出要求
1. 先确认交易员方案哪些要点被采纳 / 调整。
2. 说明在何种市场触发条件下需要重新评估。
3. 以 ``Action Plan / Team Message / Belief Update`` 模板输出，并给出明确的 BUY / SELL / HOLD 文本。"""

        response = llm.invoke(prompt)
        structured = parse_structured_reply(response.content)

        manager_text = (
            "Manager:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        new_risk_state = {
            "history": risk_history,
            "analyst_report": analyst_report,
            "manager_summary": manager_text,
            "count": risk_state.get("count", 0),
        }

        return {
            "risk_review_state": new_risk_state,
            "final_trade_decision": manager_text,
            "interaction_round": next_round,
        }

    return manager_node
