from tradingagents.constants import DEFAULT_ASSETS


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:
        raw_state = state.get("risk_review_state") or {}
        if not isinstance(raw_state, dict):
            raw_state = {}

        history = raw_state.get("history", "")
        count = int(raw_state.get("count", 0) or 0)

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
你是该交易团队的风险经理，负责审查交易员针对资产 {asset_list} 制定的多资产策略：{trader_plan or "尚未给出"}。本次可支配资金：{capital_hint}，允许杠杆范围：{leverage_hint}。

### 输入资料
- Odaily 快讯：{newsflash_report or "暂无"}
- 长文本研究：{longform_report or "暂无"}
- 历史风险记录：{history or "暂无"}
- 风控经验库：{past_memory_str or "暂无"}

### 输出要求
1. 针对每个资产评估仓位、杠杆（确保处于 {leverage_hint} 区间）、止损/止盈、对冲策略是否合理，必要时给出修改建议。
2. 列出跨资产可能的共振风险、事件触发条件与监控指标。
3. 给出总体裁决，并注明需要 Trader/Manager 调整的条款。
4. 仅输出单行 JSON，字段固定。

JSON 结构：
{{
  "speaker": "risk_manager",
  "per_asset_risk": [
    {{
      "asset": "symbol",
      "verdict": "ALLOW|ALLOW_WITH_CHANGES|REJECT",
      "rationale": ["引用市场/长文/快讯数据说明理由"],
      "required_adjustments": [
        {{
          "item": "要调整的要素（仓位/杠杆/止损等）",
          "instruction": "明确修改建议"
        }}
      ],
      "risk_dashboard": {{
        "position_risk": "仓位/杠杆是否符合边界",
        "event_risk": "重大事件或宏观触发",
        "liquidity_risk": "流动性/成交量关注点",
        "data_gaps": ["缺失或需确认的信息"]
      }},
      "kill_switches": ["出现哪些信号必须立即撤出"],
      "monitoring_plan": ["需要持续监控的指标"]
    }}
  ],
  "portfolio_overview": {{
    "cross_asset_risks": ["跨资产共振或相关性风险"],
    "capital_utilization": "保证金/杠杆占用评估（与 {capital_hint} 对比）",
    "event_watch": ["事件窗口提醒"],
    "global_verdict": "ALLOW|ALLOW_WITH_CHANGES|REJECT"
  }},
  "team_message": "给 Manager 的一句话说明",
  "belief_update": {{
    "probability": 0.0,
    "key_reasons": ["理由1","理由2","理由3"],
    "change_of_mind": ["何时会修改当前裁决"]
  }}
}}"""

        response = llm.invoke(prompt)
        analyst_text = response.content if isinstance(response.content, str) else str(response.content)

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
