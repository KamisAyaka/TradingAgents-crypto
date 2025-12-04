import time
import json


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""你是中性风险分析师，职责是提供平衡视角：既要识别进取策略的收益空间，也要评估风险，寻找兼顾增长与防守的方案。

任务要点：
1. 交易员当前方案：{trader_decision}
2. 使用以下资料支撑你的判断：
   - 市场技术报告：{market_research_report}
   - Odaily 快讯：{newsflash_report}
   - 长线叙事报告：{longform_report}
3. 讨论历史：{history}
   - 激进派最新观点：{current_risky_response}
   - 保守派最新观点：{current_safe_response}
   若对手尚未发言，请直接表达你的论点，不要臆造。

请批判性分析双方论点，指出过度乐观或过度谨慎之处，并提出更具弹性的折中策略，例如分批入场、分层止损或对冲思路。保持辩论语气，重点回应、折衷，而非机械罗列数据。"""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
