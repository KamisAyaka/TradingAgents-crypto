from langchain_core.messages import SystemMessage

from tradingagents.constants import DEFAULT_ASSETS


def create_trader(llm, trader_round_store):
    """
    Trader node 直接获取持仓信息并生成交易计划，不使用 ToolNode。
    """

    def trader_node(state):
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

        debate_history = investment_debate_state.get("history", "")
        positions_info = state.get("current_positions") or "未获取仓位信息"

        recent_rounds = trader_round_store.get_recent_rounds(limit=2)
        recent_summary = (
            "\n\n".join(
                f"[{item.get('created_at')}] {item.get('summary')}" for item in recent_rounds
            )
            if recent_rounds
            else "暂无最近轮次总结。"
        )
        open_context = trader_round_store.get_open_position_context()
        open_context_summary = (
            open_context.get("summary") if open_context else "暂无未平仓开仓总结。"
        )

        system_message = f"""### 角色任务
你是交易员，需要在牛熊辩论与市场研究报告的基础上给出资产交易计划（资产列表：{asset_list}）。可支配资金：{capital_hint}，允许的杠杆范围：{leverage_hint}。

### 工作流程
1. 使用系统提供的当前持仓信息（可能为空仓），判断是否需要继续持有、减仓、平仓，并说明与本轮计划的关系。
2. 综合所有资料，对比多个资产的胜率/盈亏比，只选出最有把握的 1 个资产执行（其余资产一律 WAIT 或平仓）。如果执行交易，**必须将全部本金集中在单一资产**，严禁分散资金。
3. 为候选资产给出“全额本金（{capital_hint} USDT）× 杠杆”后的交易方案，明确选择的杠杆倍数（整数 5-25x）与方向，并说明为何舍弃其他币种。
4. 必须给出**明确的数值入场价**、止损价与至少一个止盈价，并写明触发/失效条件、仓位 sizing、风险控制和监控指标（per-asset）。
5. 风控硬约束：按入场价与杠杆折算的最大亏损不得超过本金的 10%。若止损距离超过该上限，系统将强制调整止损，请提前给出合理数值。
6. 说明当价格触达止损/止盈价时系统应执行的动作（被动触发也需要说明如何记录与复盘）。
7. 输出单行 JSON，字段固定。

### 参考资料
- 牛熊辩论记录：{debate_history or '暂无辩论记录'}
- 市场技术报告：{market_research_report}
- 最近轮次总结：{recent_summary}
- 未平仓开仓总结：{open_context_summary}
- 当前持仓：{positions_info}

JSON 结构：
{{
  "role": "trader",
  "current_positions_summary": "当前持仓摘要（从系统持仓中提取）",
  "per_asset_decisions": [
    {{
      "asset": "symbol",
      "existing_position": "当前仓位（若有）",
      "decision": "LONG|SHORT|WAIT|CLOSE_LONG|CLOSE_SHORT",
      "thesis": "一句话概括为何站队多/空",
      "supporting_points": ["引用的关键论据"],
      "discarded_points": ["被舍弃的观点及原因"],
      "execution": {{
          "entry_plan": "入场条件/区间",
          "entry_price": "计划入场价（USDT，数值）",
          "entry_range": "允许的入场区间（USDT，可选）",
          "leverage": "选择的整数杠杆（{leverage_hint} 范围内）",
      }},
      "risk_management": {{
        "invalidations": ["失效条件"],
        "stop_rule": "止损/降仓规则（包含具体价格）",
        "stop_loss_price": "建议的止损价格（USDT，数值）",
        "take_profit_rule": "止盈/分批规则（包含价格）",
        "take_profit_targets": ["止盈价1","止盈价2（USDT，数值）"],
        "monitoring": ["需要持续跟踪的信号"],
        "alert_action": "触发止损/止盈价后系统应执行的动作说明"
      }}
    }}
  ],
}}"""
        conversation = list(state["messages"])
        conversation.append(("human", f"请根据资产列表 {asset_list} 给出交易计划。"))

        response = llm.invoke([SystemMessage(content=system_message)] + conversation)
        plan_text = response.content if isinstance(response.content, str) else str(response.content)
        combined_plan = plan_text.strip()

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        updated_invest_state = dict(investment_debate_state)
        updated_invest_state["current_response"] = combined_plan

        return {
            "messages": [response],
            "trader_investment_plan": combined_plan,
            "current_positions": positions_info,
            "investment_debate_state": updated_invest_state,
            "sender": "Trader",
            "interaction_round": next_round,
        }

    return trader_node
