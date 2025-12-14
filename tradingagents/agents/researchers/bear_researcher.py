from tradingagents.agents.utils.dialogue import parse_structured_reply
from tradingagents.constants import DEFAULT_ASSETS


def create_bear_researcher(llm, memory):
    def bear_node(state) -> dict:
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
        bear_history = investment_debate_state.get("bear_history", "")

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
你是一名专注加密货币领域的看跌分析师，需要针对以下资产列表提出防御性论点：{asset_list}，并逐条回应看涨分析师：{current_response}

必须完成：
- 指出每个资产在宏观、合规、流动性、叙事方面的风险，引用市场/快讯/长文数据。
- 提醒潜在的跨资产共振或事件风险，强调仓位控制或对冲策略。
- 逐条反驳最近一次看涨观点，标注哪些论据失效或过度乐观。
- 给交易员 per-asset 的对冲/减仓/观望建议及触发条件。
- 用单行 JSON 输出，字段固定。

### 研究全文
- 市场技术分析：{market_research_report}
- Odaily 快讯：{newsflash_report}
- 长篇叙事：{longform_report}
- 辩论完整记录：{history}
- 经验反思：{past_memory_str}

JSON 结构：
{{
  "speaker": "bear_researcher",
  "per_asset_warnings": [
    {{
      "asset": "symbol",
      "stance": "strong_bear|bear|cautious",
      "action_plan": {{
        "recommended_action": "short|hedge|reduce|wait",
        "triggers": ["触发条件"],
        "invalidations": ["失效条件"],
        "hedge_or_reduction": "如何对冲/减仓"
      }},
      "risk_summary": {{
        "macro_or_regulatory": ["风险点"],
        "market_structure": ["结构性威胁"],
        "liquidity_or_flow": ["资金流/流动性问题"],
        "narrative_breaks": ["叙事崩塌迹象"]
      }},
      "rebuttals": [
        {{
          "bull_point": "引用对方观点要点",
          "bear_response": "你的逐条反驳",
          "reference_source": "引用的报告/数据"
        }}
      ]
    }}
  ],
  "cross_asset_risks": [
    {{
      "observation": "多资产共振或系统性风险",
      "implication": "组合层面的警示"
    }}
  ],
  "team_message": "留给 Trader/Manager 的一句话",
  "belief_update": {{
    "probability": 0.0,
    "key_reasons": ["理由1","理由2","理由3"],
    "change_of_mind": ["什么情况下转多"]
  }}
}}"""

        response = llm.invoke(prompt)
        raw_content = response.content if isinstance(response.content, str) else str(response.content)

        argument = raw_content.strip()

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
            "last_speaker": "bear",
        }

        current_round = int(state.get("interaction_round", 1))
        next_round = current_round + 1

        return {
            "investment_debate_state": new_investment_debate_state,
            "interaction_round": next_round,
        }

    return bear_node
