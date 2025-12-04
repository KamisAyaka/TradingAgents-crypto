from langchain_core.messages import AIMessage
import time
import json


def create_safe_debator(llm):
    def safe_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""你是保守型风险分析师，首要任务是守住资产安全、降低波动、维持稳定增长。请在评估交易员方案时，逐项识别高风险因素，说明潜在损失、宏观逆风或流动性风险。

具体要求：
1. 回应激进与中性分析师的观点，指出他们忽视的威胁或对可持续性的缺失。
2. 参考以下资料构建低风险或降杠杆方案：
   - 市场技术报告：{market_research_report}
   - Odaily 快讯：{newsflash_report}
   - 长线叙事报告：{longform_report}
3. 交易员当前方案：{trader_decision}
4. 讨论记录：{history}
   - 激进派最新观点：{current_risky_response}
   - 中性派最新观点：{current_neutral_response}
   如果对方没有发言，请勿虚构，直接陈述你的立场即可。

在回复中强调谨慎策略的优势：质疑乐观假设、凸显下行风险、给出更稳健的替代方案，并保持对话式口吻、集中辩论而不是单纯列数据。"""

        response = llm.invoke(prompt)

        argument = f"Safe Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risk_debate_state.get("risky_history", ""),
            "safe_history": safe_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Safe",
            "current_risky_response": risk_debate_state.get(
                "current_risky_response", ""
            ),
            "current_safe_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return safe_node
