import functools
import time
import json


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["asset_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        newsflash_report = state["newsflash_report"]
        longform_report = state["longform_report"]

        curr_situation = f"{market_research_report}\n\n{newsflash_report}\n\n{longform_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        context = {
            "role": "user",
            "content": f"以下是加密市场分析团队基于多维研究为 {company_name} 定制的投资方案，已综合技术面、Odaily 快讯与长线基本面叙事。请把这份方案作为制定下一步交易决策的依据。\n\n推荐投资方案：{investment_plan}\n\n请充分利用这些洞见，做出信息充分、策略明确的决定。",
        }

        messages = [
            {
                "role": "system",
                "content": f"""你是一名交易执行代理，需要结合市场数据与经验教训给出明确的买入、卖出或观望建议。请在充分分析后输出明确立场，并以“FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**”结尾确认推荐方向。务必参考过往类似情境的反思，避免重蹈覆辙。以下是你的历史经验与总结：{past_memory_str}""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
