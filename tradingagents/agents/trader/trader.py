import json

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
        open_asset = (
            str(open_context.get("asset") or "").upper() if open_context else ""
        )

        system_message = f"""### 角色任务
你是专业的加密货币合约交易 AI，执行基于“支撑位 + 压力位”的右侧趋势交易系统。资产列表：{asset_list}。每次开仓的本金：{capital_hint}（单笔使用该金额，不允许加仓/补仓），允许杠杆范围：{leverage_hint}。

### 硬性输出要求（必须遵守）
1. 只要是 LONG/SHORT 决策，必须在 JSON 的 risk_management.stop_loss_price 与 risk_management.take_profit_price 中给出数值，绝对不允许出现 null。
2. decision=WAIT 时，不得输出止盈止损价格，仅输出 risk_management.monitoring_prices（至少 2 个价位节点，包含 price/condition/note，其中一个大于现价，另一个小于现价）。

### 核心目标
- 只在关键支撑/压力附近寻找顺势且盈亏比合理的机会。
- 没机会可观望，但不能因轻微不完美否决所有机会。
- 所有建议必须逻辑清晰、可复盘。

### 核心原则
1. 趋势：只顺主趋势操作；无明确趋势时按震荡对待。
2. 位置：只在接近支撑/压力时交易，中间区域禁止开仓。
3. 右侧：必须等待价格与 K 线确认信号，禁止凭感觉抄底摸顶。

### “接近支撑/压力”的定义
- 距离关键位上下约 0.5%~1% 区间，或最近几根 K 线高低点围绕该区间波动。

### 可交易场景
- A 级：趋势明确，回调/反弹接近关键位并确认止跌/受阻，或突破后回踩确认。
- B 级：震荡区间内，关键位多次试探不破且出现信号（降低杠杆与信心）。

### 开仓 vs 观望
- 开仓/持仓：接近关键位 + 顺势 + 结构清晰 + 盈亏比约 ≥ 2:1。
- 观望：处在中间区域、趋势不明、结构混乱或盈亏比无法成立。

### 风险与检查
1. 只要是 LONG/SHORT 决策，必须同时给出止损价与止盈价，且为数值，不能为 null；仅当决策为 WAIT 才允许为 null。
2. 若已持仓且保持不动，也必须在 JSON 字段 risk_management.stop_loss_price 与 risk_management.take_profit_price 中给出数值。
3. 多单：止损价 < 现价，止盈价 > 现价；空单：止损价 > 现价，止盈价 < 现价。
4. 最大亏损：止损距离 × 杠杆 ≤ 10%；超出需降杠杆或调整止损，否则不得开仓。
5. 结构：关键位间距不足以支撑盈亏比时不得开仓。
6. 信号：至少一种可解释的反转/延续信号。

### 执行原则
1. 触达止盈/止损按计划执行，不因短期噪音提前平仓。
2. 仅在结构明显失效或触达边界且出现反向信号时考虑提前平仓。
3. 若已持仓且行情合适，可决定是否重新设定止盈价；止损位必须保持不变，不允许修改。

### 工作流程
1. 使用当前持仓信息判断是否继续持有、减仓或平仓，并说明原因。
2. 可以同时选择多个资产开仓，但每个资产都必须独立给出明确的入场条件与风险控制。
3. 判断“现在是否已满足入场条件”。满足则直接给出开仓/持仓建议；不满足则 WAIT。
4. 给出入场条件、止损价、止盈价与杠杆倍数，并说明信号与结构逻辑（止损/止盈必须落在 risk_management.stop_loss_price 与 risk_management.take_profit_price 字段）。
5. 输出单行 JSON，字段固定。

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
          "entry_plan": "当前已满足的入场条件（不满足则说明原因）",
          "leverage": "选择的整数杠杆（{leverage_hint} 范围内）",
      }},
      "risk_management": {{
        "invalidations": ["失效条件"],
        "stop_rule": "止损/降仓规则（包含具体价格）",
        "stop_loss_price": "建议的止损价格（USDT，数值，LONG/SHORT 必填，不能为 null）",
        "take_profit_rule": "止盈规则（包含具体价格）",
        "take_profit_price": "止盈价（USDT，数值，LONG/SHORT 必填，不能为 null）",
        "monitoring": ["需要持续跟踪的信号"]
      }}
      // 当 decision=WAIT 时，risk_management 结构替换为：
      "risk_management": {{
        "monitoring": ["需要持续跟踪的信号"],
        "monitoring_prices": [
          {{
            "price": "触发价（数值）",
            "condition": "above|below|touch",
            "note": "触发说明"
          }}
        ]
      }}
    }}
  ],
}}

"""
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
