from tradingagents.constants import DEFAULT_ASSETS


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        # 兼容上游状态缺失的情况，必要时重新初始化辩论状态
        raw_state = state.get("investment_debate_state") or {}
        if not isinstance(raw_state, dict):
            raw_state = {}
        investment_debate_state = {
            "history": raw_state.get("history", ""),
            "bull_history": raw_state.get("bull_history", ""),
            "bear_history": raw_state.get("bear_history", ""),
            "current_response": raw_state.get("current_response", ""),
            "count": raw_state.get("count", 0),
            "last_speaker": raw_state.get("last_speaker", ""),
        }
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        assets = state.get("assets_under_analysis") or list(DEFAULT_ASSETS)
        asset_list = ", ".join(assets)

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        prompt = f"""### 角色任务
你是一名专注加密货币的看涨分析师，需要针对以下资产列表逐一提出进攻性论证：{asset_list}。
- 结合市场/快讯/长文中出现的多资产信息，说明每个资产的上行动力、需求增长、生态扩张或可扩展性等正面因素。
- 逐条回应 Bear 最新观点（{current_response}），指出哪些论点不成立，并按资产拆解。
- 给 Trader 清晰的 per-asset 建仓/加仓/等待计划，写清触发与终止条件。
- 输出单行 JSON，字段固定。

### 研究全文（供引用）
- 市场技术分析：{market_research_report}
- Odaily 快讯：{newsflash_report}
- 长篇叙事：{longform_report}
- 辩论完整记录：{history}
- 经验教训：{past_memory_str}

JSON 结构：
{{
  "speaker": "bull_researcher",
  "per_asset_views": [
    {{
      "asset": "symbol",
      "stance": "strong_bull|bull|neutral",
      "action_plan": {{
        "recommended_action": "build_long|scale_in|wait",
        "triggers": ["触发条件"],
        "invalidations": ["失效条件"],
        "targets": ["目标区间"]
      }},
      "growth_drivers": {{
        "demand_or_adoption": ["需求/用户/生态扩张证据"],
        "capital_or_flow": ["资金流/链上数据亮点"],
        "narrative_catalysts": ["催化剂或事件"]
      }},
      "rebuttals": [
        {{
          "bear_point": "引用看跌论点",
          "bull_response": "你的反驳",
          "reference_source": "引用的报告/数据"
        }}
      ]
    }}
  ],
  "cross_asset_notes": [
    {{
      "observation": "资产之间的共振或分歧",
      "implication": "对组合或轮动的提示"
    }}
  ],
  "team_message": "给 Trader/Manager 的一句话",
  "belief_update": {{
    "probability": 0.0,
    "key_reasons": ["理由1","理由2","理由3"],
    "change_of_mind": ["在何种情况下转为空"]
  }}
}}"""

        response = llm.invoke(prompt)
        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        argument = raw_content.strip()

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
            "last_speaker": "bull",
        }

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        return {
            "investment_debate_state": new_investment_debate_state,
            "interaction_round": next_round,
        }

    return bull_node
