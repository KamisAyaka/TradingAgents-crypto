from tradingagents.agents.utils.dialogue import parse_structured_reply


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:
        raw_state = state.get("risk_review_state") or {}
        if not isinstance(raw_state, dict):
            raw_state = {}

        history = raw_state.get("history", "")
        count = int(raw_state.get("count", 0) or 0)

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
你是该交易团队的风险经理，负责审查交易员策略 **{trader_plan or "尚未给出"}** 是否符合仓位与杠杆边界。

### 输入资料
- 市场/技术研究：{market_research_report or "暂无"}
- Odaily 快讯：{newsflash_report or "暂无"}
- 长文本研究：{longform_report or "暂无"}
- 历史风险记录：{history or "暂无"}
- 风控经验库：{past_memory_str or "暂无"}

### 输出要求
1. 明确建议的仓位规模、杠杆范围、止损/止盈或对冲手段。
2. 指出关键风险触发条件及监控指标。
3. 以 ``Action Plan / Team Message / Belief Update`` 模板输出，方便后续节点引用。"""

        response = llm.invoke(prompt)
        structured = parse_structured_reply(response.content)

        analyst_text = (
            "Risk Manager:\n"
            f"Action Plan: {structured.get('Action Plan:', '')}\n"
            f"Belief Update: {structured.get('Belief Update:', '')}\n"
            f"Team Message: \"{structured.get('Team Message:', '')}\""
        )

        updated_history = (history + "\n" + analyst_text).strip() if history else analyst_text

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        return {
            "risk_review_state": {
                "history": updated_history,
                "analyst_report": analyst_text,
                "manager_summary": raw_state.get("manager_summary", ""),
                "count": count + 1,
            },
            "interaction_round": next_round,
        }

    return risk_manager_node
