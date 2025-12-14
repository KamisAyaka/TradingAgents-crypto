from tradingagents.constants import DEFAULT_ASSETS


def create_manager(llm, memory):
    def manager_node(state) -> dict:
        risk_state = state.get("risk_review_state") or {}
        if not isinstance(risk_state, dict):
            risk_state = {}

        risk_history = risk_state.get("history", "")
        analyst_report = risk_state.get("analyst_report", "")

        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        available_capital = state.get("available_capital")
        capital_hint = (
            f"{available_capital}" if available_capital is not None else "未知"
        )
        min_leverage = state.get("min_leverage")
        max_leverage = state.get("max_leverage")
        leverage_hint = (
            f"{min_leverage}x - {max_leverage}x"
            if min_leverage is not None and max_leverage is not None
            else "默认 1x"
        )
        asset_list = ", ".join(assets)

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
你是该团队的总经理（最终裁决者），需要在交易员方案与风险经理报告基础上，为以下资产做出决策并准备执行：{asset_list}。可支配资金：{capital_hint}，可用杠杆区间：{leverage_hint}。

### 参考资料
- 交易员方案：{trader_plan or "暂无"}
- 风险经理最新报告：{analyst_report or "暂无"}
- 历史风险记录：{risk_history or "暂无"}
- 总经理经验库：{past_memory_str or "暂无"}

### 输出要求
1. 针对每个资产指明采纳/调整交易员要点，明确最终动作（open/close/wait）及执行条件，确保计划中的杠杆保持在 {leverage_hint}。
2. 记录需要传递给执行工具的字段（动作、尺寸、杠杆、止损止盈、备注）。
3. 给出组合层面的资本配置、监测价位与风险提醒。
4. 仅输出单行 JSON，字段固定。

JSON 结构：
{{
  "speaker": "manager",
  "per_asset_final": [
    {{
      "asset": "symbol",
      "final_decision": "LONG|SHORT|HOLD|NO_TRADE",
      "approved_plan": {{
        "sourced_from_trader": ["被采纳的要点"],
        "adjustments": ["按照风控建议修改的部分"],
        "execution_requirements": ["执行前必须满足的条件"]
      }},
      "execution_intent": {{
        "action": "open_long|open_short|close_long|close_short|wait",
        "size_or_leverage": "若要执行，计划的仓位/杠杆",
        "notes_for_tool": "给执行工具的说明"
      }},
      "monitoring_prices": {{
        "watch_above": "高于当前报价的监控价位",
        "watch_below": "低于当前报价的监控价位"
      }},
      "conditions": {{
        "execute_if": ["执行条件"],
        "abort_if": ["中止条件"]
      }}
    }}
  ],
  "portfolio_guidance": {{
    "capital_plan": "整体资金/杠杆配置（基于 {capital_hint}）",
    "cross_asset_notes": ["跨资产联动提醒"],
  }},
  "team_message": "给全体的简短沟通",
  "belief_update": {{
    "probability": 0.0,
    "key_reasons": ["理由1","理由2","理由3"]
  }}
}}"""

        response = llm.invoke(prompt)
        manager_text = response.content if isinstance(response.content, str) else str(response.content)

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
