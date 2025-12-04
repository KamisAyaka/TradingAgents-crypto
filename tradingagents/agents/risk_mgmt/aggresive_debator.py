import time
import json


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""你是激进型风险分析师，职责是在评估交易员方案时强调高收益、高风险策略的潜在价值。请聚焦潜在上行、外溢效应，即便这些机会意味着承受更高波动。

需要你完成的任务：
1. 直接回应保守和中性分析师的观点，逐条指出他们可能错失的机会或过度谨慎的假设。
2. 结合以下资料，用数据与说服性论据强化立场：
   - 市场技术报告：{market_research_report}
   - Odaily 快讯：{newsflash_report}
   - 长线叙事报告：{longform_report}
3. 明确交易员当前方案：{trader_decision}
4. 当前讨论历史：{history}
   - 最近一次保守派观点：{current_safe_response}
   - 最近一次中性派观点：{current_neutral_response}
   如若对方尚未发言，请勿臆造，直接陈述你的看法即可。

在回复时请保持辩论式语气，聚焦于反驳与说服：指出其逻辑漏洞，强调进取策略如何抢占赛道或提升收益空间，并确保输出自然对话风格、无特别格式要求。"""

        response = llm.invoke(prompt)

        argument = f"Risky Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
