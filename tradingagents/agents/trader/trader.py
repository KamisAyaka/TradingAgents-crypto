import functools
from tradingagents.constants import DEFAULT_ASSETS


def create_trader(llm, trader_memory):
    def trader_node(state, name):
        investment_debate_state = state["investment_debate_state"]
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        available_capital = state.get("available_capital")
        capital_hint = (
            f"{available_capital}" if available_capital is not None else "未知，默认保持轻仓"
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

        debate_history = investment_debate_state.get("history", "")

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        trader_memories = trader_memory.get_memories(curr_situation, n_matches=4)
        trader_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in trader_memories) or "暂无交易经验总结。"

        prompt = f"""### 角色任务
你是交易员，需要在牛熊辩论与市场研究报告的基础上给出多资产交易计划（资产列表：{asset_list}）。可支配资金：{capital_hint}，允许的杠杆范围：{leverage_hint}。
- 对每个资产说明站队多/空/观望、采纳哪方观点、舍弃哪些论据。
- 指出入场逻辑、触发/失效条件、仓位 sizing、风险控制和监控指标（per-asset）。
- 所有仓位杠杆/保证金使用必须落在上述范围内，如需说明特殊安排请写入 execution.plan。
- 写出组合层面的资本分配、杠杆/保证金使用、事件提醒。
- 输出单行 JSON,字段固定。

### 参考资料
- 牛熊辩论记录：{debate_history or '暂无辩论记录'}
- 市场技术报告：{market_research_report}
- 交易执行经验：{trader_memory_str}

JSON 结构：
{{
  "role": "trader",
  "per_asset_decisions": [
    {{
      "asset": "symbol",
      "decision": "LONG|SHORT|NO_TRADE",
      "thesis": "一句话概括为何站队多/空",
      "supporting_points": ["引用的关键论据"],
      "discarded_points": ["被舍弃的观点及原因"],
        "execution": {{
            "entry_plan": "入场条件/区间",
            "position_size": "仓位与risk单位",
            "leverage": "若适用则说明（保持在 {leverage_hint} 范围内）",
            "time_horizon": "intraday|1-3d|1-2w|longer"
        }},
      "risk_management": {{
        "invalidations": ["失效条件"],
        "stop_rule": "止损/降仓规则",
        "take_profit_rule": "止盈/分批规则",
        "monitoring": ["需要持续跟踪的信号"]
      }}
    }}
  ],
  "portfolio_view": {{
    "capital_allocation": "资金/保证金如何分配（可使用 {capital_hint}）",
    "correlation_notes": ["跨资产联动提醒"],
    "event_watch": ["事件/宏观催化"],
    "sizing_adjustments": "若有持仓或风险限制，如何调整"
  }},
  "communication": {{
    "team_message": "给风险经理/总经理的一句话",
    "belief_update": {{
      "probability": 0.0,
      "key_reasons": ["理由1","理由2","理由3"],
      "change_of_mind": ["何种条件会放弃本计划"]
    }}
  }}
}}"""

        result = llm.invoke(prompt)
        plan_text = result.content if isinstance(result.content, str) else str(result.content)
        combined_plan = plan_text.strip()

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
